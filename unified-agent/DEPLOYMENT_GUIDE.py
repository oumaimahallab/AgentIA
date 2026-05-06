#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEPLOYMENT GUIDE - From Development to Production
"""

print("""
╔════════════════════════════════════════════════════════════════════════╗
║               UNIFIED AGENT - DEPLOYMENT GUIDE                         ║
╚════════════════════════════════════════════════════════════════════════╝


═════════════════════════════════════════════════════════════════════════
 SECTION 1: DEPLOYMENT OPTIONS
═════════════════════════════════════════════════════════════════════════

The unified agent can be deployed in multiple ways:

1. LOCAL DEVELOPMENT
   • Single machine, for testing and development
   • No special setup needed
   • Good for: prototyping, demos, proof-of-concept

2. LOCAL PRODUCTION
   • Single machine with persistent indices
   • Background service
   • Good for: single-user, team small scale

3. DOCKER CONTAINERIZATION
   • Reproducible environment
   • Easy scaling, deployment
   • Good for: Kubernetes, cloud platforms

4. REST API SERVICE
   • Network accessible
   • Multiple clients can connect
   • Good for: web apps, integrations

5. CLOUD DEPLOYMENT
   • AWS, Azure, GCP
   • Managed resources
   • Good for: large-scale, high availability


═════════════════════════════════════════════════════════════════════════
 SECTION 2: LOCAL DEVELOPMENT TO PRODUCTION
═════════════════════════════════════════════════════════════════════════

STEP 1: Prepare Production Config
─────────────────────────────────────────────────────────────────────────

Create config/production.py:

  from config.settings import UnifiedAgentConfig
  
  prod_config = UnifiedAgentConfig(
      # More conservative for stability
      retrieval=dict(
          SEMANTIC_TOP_K=20,
          KEYWORD_TOP_K=15,
          ALPHA=0.6,  # 60% semantic, 40% keyword
          MAX_CONTEXT_TOKENS=3000
      ),
      # Groq primary, Ollama fallback
      llm=dict(
          GROQ_ENABLED=True,
          GROQ_MODEL="llama-3.1-8b-instant",
          OLLAMA_ENABLED=True,
          OLLAMA_ENDPOINT="http://ollama:11434",
      ),
      # Persistence paths
      paths=dict(
          FAISS_INDEX_DIR="/data/indices/faiss",
          BM25_INDEX_DIR="/data/indices/bm25",
          LOGS_DIR="/var/log/unified-agent",
      )
  )


STEP 2: Setup Persistent Storage
─────────────────────────────────────────────────────────────────────────

Create data directories:
  $ mkdir -p data/indices/faiss
  $ mkdir -p data/indices/bm25
  $ mkdir -p data/documents
  $ mkdir -p logs

Set permissions:
  $ chmod 755 data/
  $ chmod 755 data/indices/


STEP 3: Index All Documents
─────────────────────────────────────────────────────────────────────────

Before production, index your documents:

  from ingestion.unified_ingester import UnifiedIngester
  from retrieval.faiss_manager import FAISSManager
  from retrieval.bm25_manager import BM25Manager
  
  ingester = UnifiedIngester()
  faiss = FAISSManager()
  bm25 = BM25Manager()
  
  # Load all documents
  documents = ingester.ingest_directory("data/documents")
  
  # Index them
  faiss.build_from_documents(documents)
  bm25.build_from_documents(documents)
  
  # Save indices
  faiss.save("data/indices/faiss")
  bm25.save("data/indices/bm25")


STEP 4: Environment Setup
─────────────────────────────────────────────────────────────────────────

Create .env file:

  # Production API keys
  GROQ_API_KEY=your_production_key
  
  # Ollama endpoint
  OLLAMA_ENDPOINT=http://ollama-service:11434
  
  # Paths
  WORKSPACE_ROOT=/app
  FAISS_INDEX_DIR=/data/indices/faiss
  BM25_INDEX_DIR=/data/indices/bm25
  
  # Logging
  LOG_LEVEL=INFO
  LOG_FILE=/var/log/unified-agent/agent.log


STEP 5: Run as Background Service
─────────────────────────────────────────────────────────────────────────

Create systemd service (Linux):

  [Unit]
  Description=Unified Agent Service
  After=network.target
  
  [Service]
  Type=simple
  User=unified-agent
  WorkingDirectory=/opt/unified-agent
  ExecStart=/opt/unified-agent/venv/bin/python main.py
  Restart=on-failure
  RestartSec=10
  Environment="GROQ_API_KEY=your_key"
  
  [Install]
  WantedBy=multi-user.target

Then:
  $ sudo systemctl enable unified-agent
  $ sudo systemctl start unified-agent


═════════════════════════════════════════════════════════════════════════
 SECTION 3: DOCKER DEPLOYMENT
═════════════════════════════════════════════════════════════════════════

Create Dockerfile:

  FROM python:3.10-slim
  
  WORKDIR /app
  
  # Install system dependencies
  RUN apt-get update && apt-get install -y \\
      build-essential \\
      && rm -rf /var/lib/apt/lists/*
  
  # Copy project
  COPY . /app
  
  # Install Python dependencies
  RUN pip install --no-cache-dir -r requirements.txt
  
  # Pre-build indices (optional)
  RUN python scripts/setup.py
  
  # Create persistent volumes
  VOLUME ["/data", "/logs"]
  
  # Expose port for API
  EXPOSE 8000
  
  # Run agent
  CMD ["python", "main.py"]


Create docker-compose.yml:

  version: '3.8'
  
  services:
    ollama:
      image: ollama/ollama:latest
      ports:
        - "11434:11434"
      volumes:
        - ollama_data:/root/.ollama
      command: serve
  
    unified-agent:
      build: .
      ports:
        - "8000:8000"
      environment:
        - GROQ_API_KEY=${GROQ_API_KEY}
        - OLLAMA_ENDPOINT=http://ollama:11434
      volumes:
        - ./data:/data
        - ./logs:/var/log/unified-agent
      depends_on:
        - ollama
      restart: unless-stopped
  
  volumes:
    ollama_data:


Deploy with Docker Compose:
  $ GROQ_API_KEY=your_key docker-compose up -d


═════════════════════════════════════════════════════════════════════════
 SECTION 4: REST API DEPLOYMENT
═════════════════════════════════════════════════════════════════════════

Create api/api_server.py:

  from fastapi import FastAPI, HTTPException
  from pydantic import BaseModel
  from orchestration.dispatcher import Dispatcher
  import logging
  
  app = FastAPI(title="Unified Agent API")
  dispatcher = Dispatcher()
  
  class QuestionRequest(BaseModel):
      question: str
      verbose: bool = False
  
  @app.post("/answer")
  async def answer(request: QuestionRequest):
      try:
          result = dispatcher.dispatch(request.question)
          return result
      except Exception as e:
          raise HTTPException(status_code=500, detail=str(e))
  
  @app.get("/status")
  async def status():
      return dispatcher.agent.get_system_status()
  
  @app.get("/health")
  async def health():
      return {"status": "ok"}


Run API server:
  $ pip install fastapi uvicorn
  $ uvicorn api.api_server:app --host 0.0.0.0 --port 8000

Access API:
  POST http://your-server:8000/answer
  {
    "question": "Qu'est-ce qu'une habilitation?",
    "verbose": true
  }


═════════════════════════════════════════════════════════════════════════
 SECTION 5: PERFORMANCE TUNING
═════════════════════════════════════════════════════════════════════════

OPTIMIZE RESPONSE TIME:

1. Reduce retrieval TOP_K:
   • From 20 to 12 reduces retrieval time by ~40%
   • Trade-off: slightly lower quality

2. Use GPU for embeddings:
   • Set EMBEDDING_DEVICE="cuda" in config
   • 10x faster embedding on NVIDIA GPUs

3. Cache embeddings:
   • Already implemented in EmbeddingsManager
   • Add persistent cache for frequent queries

4. Use BM25 for frequent queries:
   • Keyword search is faster than semantic
   • Hybrid search weight: 0.4 semantic + 0.6 keyword

5. Pre-warm indices on startup:
   • Load indices at service start
   • Cache first batch of documents

6. Batch processing:
   • Process multiple questions together
   • Better GPU utilization


OPTIMIZE RESOURCE USAGE:

1. Memory:
   • FAISS index uses ~100MB per 100k documents
   • Pre-allocate based on expected size

2. CPU:
   • Embedding inference uses CPU by default
   • Consider multi-process for high load

3. Disk:
   • Indices persist to disk
   • SSD recommended for production


═════════════════════════════════════════════════════════════════════════
 SECTION 6: MONITORING & LOGGING
═════════════════════════════════════════════════════════════════════════

Setup Logging:

  import logging
  
  logging.basicConfig(
      level=logging.INFO,
      format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
      handlers=[
          logging.FileHandler("logs/agent.log"),
          logging.StreamHandler()
      ]
  )


Monitor Key Metrics:

  • Response time: target <3 seconds
  • Cache hit rate: track embeddings cache
  • Error rate: should be <1%
  • GPU/CPU utilization: identify bottlenecks


═════════════════════════════════════════════════════════════════════════
 SECTION 7: SECURITY
═════════════════════════════════════════════════════════════════════════

1. API Security:
   • Use HTTPS in production
   • Implement authentication (JWT, OAuth)
   • Rate limiting per client

2. Secrets Management:
   • Use environment variables or secret vaults
   • Never commit API keys
   • Rotate keys regularly

3. Input Validation:
   • Validate and sanitize queries
   • Check input length limits
   • Prevent injection attacks

4. Access Control:
   • Restrict who can access documents
   • Audit all queries
   • Log sensitive operations

5. Data Privacy:
   • Encrypt data at rest
   • Use HTTPS for data in transit
   • Comply with privacy regulations


═════════════════════════════════════════════════════════════════════════
 SECTION 8: TROUBLESHOOTING
═════════════════════════════════════════════════════════════════════════

ISSUE: High latency (>5 seconds)
SOLUTION:
  • Check Groq API status
  • Reduce TOP_K in config
  • Enable GPU for embeddings
  • Check network latency to Groq

ISSUE: Out of memory
SOLUTION:
  • Reduce TOP_K
  • Use smaller embedding model
  • Increase virtual memory
  • Run on machine with more RAM

ISSUE: Groq API quota exceeded
SOLUTION:
  • Ollama will auto-fallback
  • Increase rate limiting
  • Consider upgrading Groq plan

ISSUE: Poor answer quality
SOLUTION:
  • Check document indexing
  • Increase TOP_K
  • Adjust hybrid search weight
  • Enable reranker

ISSUE: Indices not loading
SOLUTION:
  • Verify file permissions
  • Check disk space
  • Rebuild indices
  • Check log files


═════════════════════════════════════════════════════════════════════════
 SECTION 9: SCALING
═════════════════════════════════════════════════════════════════════════

HORIZONTAL SCALING:

1. Docker Swarm / Kubernetes:
   • Deploy multiple containers
   • Load balancer for distribution
   • Shared volume for indices

2. Database Backend:
   • Store documents in PostgreSQL
   • Indices in Redis
   • Queries distributed across replicas

3. Message Queue:
   • Process questions asynchronously
   • Queue with RabbitMQ/Kafka
   • Multiple workers process tasks


VERTICAL SCALING:

1. Larger machines:
   • More CPU cores for inference
   • More RAM for indices
   • GPU for embeddings

2. Dedicated services:
   • Separate Ollama service
   • Separate embedding service
   • Separate retrieval service


═════════════════════════════════════════════════════════════════════════
 SECTION 10: MONITORING CHECKLIST
═════════════════════════════════════════════════════════════════════════

Daily:
  ☐ Check error logs for critical issues
  ☐ Verify Groq API is responding
  ☐ Test with sample query

Weekly:
  ☐ Review response time metrics
  ☐ Check disk usage
  ☐ Verify backups

Monthly:
  ☐ Performance review
  ☐ Security updates
  ☐ Cost analysis


═════════════════════════════════════════════════════════════════════════
 QUICK START PRODUCTION CHECKLIST
═════════════════════════════════════════════════════════════════════════

Before going live:

  ☐ Set up environment variables
  ☐ Create production config
  ☐ Index all documents
  ☐ Test with sample queries
  ☐ Setup logging
  ☐ Configure monitoring
  ☐ Plan backup strategy
  ☐ Document support process
  ☐ Train on-call team
  ☐ Plan incident response


Ready for production! 🚀

""")


if __name__ == "__main__":
    pass
