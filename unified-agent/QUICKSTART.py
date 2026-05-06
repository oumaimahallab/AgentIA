#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QUICKSTART - Get started in 5 minutes
"""

print("""
╔════════════════════════════════════════════════════════════════════════╗
║                    UNIFIED AGENT - QUICKSTART                          ║
╚════════════════════════════════════════════════════════════════════════╝

📋 What is this?
  • ONE intelligent agent combining two projects:
    ✓ ChronoBrain: HR, transcriptions, voice
    ✓ DataCl: Documents, RAG, universal retrieval
  • Handles PDF, PPT, audio, video, text
  • No duplication, no conflicts
  • Clean, scalable architecture


⚡ 5-MINUTE SETUP
─────────────────────────────────────────────────────────────────────────

STEP 1: Create Virtual Environment
  $ python -m venv venv
  $ venv\\Scripts\\activate          (Windows)
  $ source venv/bin/activate         (Mac/Linux)

STEP 2: Install Dependencies
  $ pip install -r requirements.txt

STEP 3: Setup Groq API Key
  1. Go to: https://console.groq.com
  2. Create account or login
  3. Generate API key
  4. Set environment variable:
     set GROQ_API_KEY=your_key        (Windows)
     export GROQ_API_KEY=your_key     (Mac/Linux)

STEP 4: Run Setup Verification
  $ python scripts/setup.py

STEP 5: Try It!
  $ python main.py answer "Qu'est-ce qu'une habilitation?"


🎮 USAGE EXAMPLES
─────────────────────────────────────────────────────────────────────────

Interactive Mode (Recommended for testing):
  $ python main.py demo

Answer a single question:
  $ python main.py answer "Your question here?"

Batch process questions:
  $ python main.py batch questions.txt --output results.txt

Check system status:
  $ python main.py status

Run tests:
  $ python main.py test
  $ python main.py test --suite retrieval
  $ python main.py test --suite llm


📁 PROJECT STRUCTURE
─────────────────────────────────────────────────────────────────────────

unified-agent/
  ├── config/           ← Configuration management
  ├── core/             ← Deduplication, intent detection
  ├── ingestion/        ← Multi-format document parsing
  ├── retrieval/        ← FAISS + BM25 hybrid search
  ├── llm/              ← Groq + Ollama orchestration
  ├── tools/            ← HR calculations, extensible tools
  ├── orchestration/    ← Agent + Dispatcher
  ├── tests/            ← Unit & integration tests
  ├── scripts/          ← Setup, demo, utilities
  ├── data/             ← Documents, indices
  ├── main.py           ← CLI entry point
  └── requirements.txt  ← Dependencies


🔧 CONFIGURATION
─────────────────────────────────────────────────────────────────────────

Edit config/settings.py to customize:
  • LLM parameters (temperature, max_tokens)
  • Retrieval settings (TOP_K, alpha weight)
  • Paths (data, indices, models)
  • Embedding model
  • Groq/Ollama endpoints


🚀 ADVANCED USAGE
─────────────────────────────────────────────────────────────────────────

1. Use Ollama (Local LLM) as primary:
   - Download Ollama from https://ollama.ai
   - Run: ollama run llama2
   - Agent will automatically use it if Groq fails

2. Customize retrieval:
   - hybrid_retriever.py controls semantic + keyword weight
   - Adjust TOP_K in config for more/fewer results
   - Use reranker for better ranking

3. Add more tools:
   - Create new tool in tools/
   - Register in HRTools or create new tool class
   - Agent will auto-detect and use

4. Extend for more document types:
   - Add handler in ingestion/unified_ingester.py
   - Implement parse_format() method
   - Register in ingest() dispatcher


❓ TROUBLESHOOTING
─────────────────────────────────────────────────────────────────────────

ImportError for modules:
  → Run: pip install -r requirements.txt
  → Verify venv is activated

GROQ_API_KEY not found:
  → Set environment variable (see STEP 3)
  → Or create .env file with GROQ_API_KEY=your_key

FAISS/BM25 indices not found:
  → Normal on first run, they'll be created
  → Check data/ directory has write permissions

Ollama not responding:
  → Download from https://ollama.ai
  → Run: ollama serve
  → In another terminal: ollama run llama2

Slow responses:
  → Reduce TOP_K in config
  → Use lighter embeddings model
  → Check CPU/GPU availability


📚 NEXT STEPS
─────────────────────────────────────────────────────────────────────────

1. Run the demo:  python main.py demo
2. Try some questions
3. Check the answers - they should cite sources
4. Experiment with different questions
5. Customize for your needs


📖 DOCUMENTATION
─────────────────────────────────────────────────────────────────────────

• ARCHITECTURE_UNIFIÉE.md  - Detailed system design
• GUIDE_IMPLEMENTATION.md  - Implementation phases
• README.md                - Full documentation
• scripts/demo.py          - Demo with examples


🆘 NEED HELP?
─────────────────────────────────────────────────────────────────────────

• Check logs in orchestration/
• Review example code in scripts/demo.py
• Run tests: python main.py test
• Check config in config/settings.py


✅ READY TO GO!
─────────────────────────────────────────────────────────────────────────

Run: python main.py demo

This will:
  1. Initialize the agent
  2. Show system status
  3. Run example questions
  4. Start interactive mode

Happy querying! 🎉

""")


if __name__ == "__main__":
    # This script just prints info
    pass
