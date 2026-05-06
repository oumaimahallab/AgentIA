import os
import sys
import re
import time
import hashlib
import json
import logging
import httpx
from collections import deque
from typing import Optional

from llama_index.core import VectorStoreIndex, StorageContext, Settings, Document
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

# ── 1. CONFIGURATION ──────────────────────────────────────────────────────────
DATA_DIR    = "../data/transcripts"
DB_PATH     = "../data/chroma_v5"
LLM_MODEL   = "phi3" 
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

TOP_K              = 6
MIN_SCORE          = 0.45
MAX_CONTEXT_TOKENS = 1800
HISTORY_TURNS      = 3
LLM_TIMEOUT        = 360.0
LLM_RETRIES        = 1

logging.basicConfig(stream=sys.stdout, level=logging.WARNING, format="%(levelname)s | %(message)s")
log = logging.getLogger("chronobrain")

# ── 2. METRICS TRACKER ────────────────────────────────────────────────────────
class PerformanceTracker:
    def __init__(self):
        self.queries = 0
        self.total_latency = 0
        self.fallbacks = 0
    def report(self, latency, is_fallback):
        self.queries += 1
        self.total_latency += latency
        if is_fallback: self.fallbacks += 1
        print(f"\n--- [Metrics] Avg Latency: {self.total_latency/self.queries:.2f}s | Hallucination/Fallback Rate: {(self.fallbacks/self.queries)*100:.1f}% ---")

tracker = PerformanceTracker()

# ── 3. EVALUATION (LLM-AS-A-JUDGE) ────────────────────────────────────────────
def evaluate_response(llm, context, answer):
    prompt = f"""
    Tu es un assistant strict. 
CONTRAT:
1. Réponds UNIQUEMENT en utilisant le contexte ci-dessous.
2. Si la réponse n'est pas dans le contexte, dis: "Je n'ai pas cette information."
3. Ne termine pas ta réponse par des répétitions.
4. N'invente rien.
    Contexte: {context[:1000]}
    Réponse: {answer}
    
    1. Fidélité: La réponse est-elle basée UNIQUEMENT sur le contexte ? (Oui/Non)
    2. Hallucination: La réponse contient-elle des faits inventés ? (Oui/Non)
    3. Score: Note de 1 à 5.
    
    Réponds UNIQUEMENT en JSON: {{"fidélité": "Oui/Non", "hallucination": "Oui/Non", "score": 0}}"""
    try:
        res = llm.complete(prompt)
        content = str(res).strip()
        if "```json" in content: content = content.split("```json")[1].split("```")[0]
        return json.loads(content)
    except: return {"fidélité": "Inconnu", "hallucination": "Inconnu", "score": 0}

# ── 4. CORE LOGIC (Chunking/Engine/Helpers) ──────────────────────────────────
def parse_transcript(filepath: str) -> list[Document]:
    pattern = re.compile(r"\[(\d+):(\d+)\s*->\s*(\d+):(\d+)\]\s*(.*)")
    segments = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            m = pattern.match(line.strip())
            if m:
                sm, ss, em, es, text = m.groups()
                segments.append((text.strip()))
    
    chunks = []
    for i in range(0, len(segments), 5):
        chunks.append(Document(text=" ".join(segments[i:i+5]), metadata={"source": os.path.basename(filepath)}))
    return chunks

def setup_engine():
    Settings.llm = Ollama(model=LLM_MODEL, request_timeout=LLM_TIMEOUT)
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL)
    Settings.chunk_size = 99999
    
    db = chromadb.PersistentClient(path=DB_PATH)
    col = db.get_or_create_collection("chronobrain_docs")
    if col.count() == 0:
        docs = [doc for f in os.listdir(DATA_DIR) if f.endswith(".txt") for doc in parse_transcript(os.path.join(DATA_DIR, f))]
        index = VectorStoreIndex.from_documents(docs, storage_context=StorageContext.from_defaults(vector_store=ChromaVectorStore(chroma_collection=col)))
    else:
        index = VectorStoreIndex.from_vector_store(ChromaVectorStore(chroma_collection=col))
    return index

def safe_llm_complete(llm, prompt):
    try: return str(llm.complete(prompt)).strip()
    except Exception as e: log.warning(f"LLM Error: {e}"); return None

# ── 5. MAIN LOOP ──────────────────────────────────────────────────────────────
def main():
    if not os.path.exists(DATA_DIR): print("Erreur: Dossier introuvable."); sys.exit(1)
    
    print("Initialisation ChronoBrain v4...")
    index = setup_engine()
    retriever = index.as_retriever(similarity_top_k=3)
    llm = Settings.llm
    history = []

    while True:
        user_input = input("\n[ChronoBrain] Votre question (quit pour quitter): ").strip()
        if user_input.lower() == "quit": break
        if not user_input: continue

        start_time = time.time()
        nodes = [n for n in retriever.retrieve(user_input) if (n.score or 0) >= MIN_SCORE]
        
        if not nodes:
            print("\nRéponse: Je n'ai pas trouvé d'informations dans les données de formation.")
            tracker.report(time.time() - start_time, True)
            continue

        context = "\n\n".join([n.get_content() for n in nodes])
        prompt = f"Répondez en français de manière directe. \nContexte: {context}\n\nQuestion: {user_input}\nRéponse:"
        
        answer = safe_llm_complete(llm, prompt)
        if answer is None: print("Timeout."); continue

        # Eval
        evals = evaluate_response(llm, context, answer)
        latency = time.time() - start_time
        is_fallback = "non" in evals.get("fidélité", "").lower()
        
        tracker.report(latency, is_fallback)
        print(f"\nRéponse: {answer}")
        print(f"Qualité: {evals}")
        history.append((user_input, answer))

if __name__ == "__main__":
    main()