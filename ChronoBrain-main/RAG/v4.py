import os
import sys
import re
import time
import hashlib
import logging
from collections import deque
from typing import Optional

from llama_index.core import (
    VectorStoreIndex,
    StorageContext,
    Settings,
    Document,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

# ── 1. CONFIGURATION ──────────────────────────────────────────────────────────

DATA_DIR    = "../data/transcripts"
DB_PATH     = "../data/chroma_v4"
LLM_MODEL   = "phi3"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

TOP_K              = 6
MIN_SCORE          = 0.45
MAX_CONTEXT_TOKENS = 1800
HISTORY_TURNS      = 3
LLM_TIMEOUT        = 360.0
LLM_RETRIES        = 1

MIN_ALPHA_RATIO = 0.6
MIN_QUERY_WORDS = 2

FALLBACK_MSG = "Je n'ai pas trouve d'informations pertinentes dans les donnees de formation pour repondre a cette question."
TIMEOUT_MSG  = "Le modele met trop de temps a repondre. Veuillez reessayer ou simplifier votre question."
FALLBACK_PHRASES = ["je n'ai pas trouve", "je ne sais pas", "je ne trouve pas", "je n'ai pas d'information", "information non disponible"]

logging.basicConfig(stream=sys.stdout, level=logging.WARNING, format="%(levelname)s | %(message)s")
log = logging.getLogger("chronobrain")

# ── 2. PERFORMANCE TRACKER ────────────────────────────────────────────────────

class PerformanceTracker:
    def __init__(self):
        self.queries = 0
        self.total_latency = 0
        self.fallbacks = 0

    def report(self, latency, is_fallback):
        self.queries += 1
        self.total_latency += latency
        if is_fallback: self.fallbacks += 1
        avg_latency = self.total_latency / self.queries
        hallucination_rate = (self.fallbacks / self.queries) * 100
        print(f"\n--- [Performance Metrics] ---")
        print(f"Avg Latency: {avg_latency:.2f}s | Fallback Rate: {hallucination_rate:.1f}%")
        print(f"-----------------------------")

tracker = PerformanceTracker()

# ── 3. FUNCTIONS (Validation, Chunking, Engine, Helpers) ──────────────────────

def is_valid_query(text: str) -> bool:
    words = text.split()
    if len(words) < MIN_QUERY_WORDS: return False
    alpha_chars = sum(c.isalpha() for c in text)
    total_chars = len(text.replace(" ", ""))
    if total_chars == 0 or (alpha_chars / total_chars < MIN_ALPHA_RATIO): return False
    if re.match(r'^(.)\1{3,}$', text.replace(" ", "")): return False
    return True

def parse_transcript(filepath: str) -> list[Document]:
    CHUNK_WORDS, MAX_GAP_SEC = 80, 3.0
    pattern = re.compile(r"\[(\d+):(\d+)\s*->\s*(\d+):(\d+)\]\s*(.*)")
    segments = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            m = pattern.match(line.strip())
            if m:
                sm, ss, em, es, text = m.groups()
                segments.append((int(sm)*60+int(ss), int(em)*60+int(es), text.strip()))
    
    chunks, buf_texts, buf_end, word_count = [], [], segments[0][1] if segments else 0, 0
    buf_start = segments[0][0] if segments else 0
    for start, end, text in segments:
        gap = (start - buf_end) if buf_texts else 0
        wc = len(text.split())
        if buf_texts and (gap > MAX_GAP_SEC or word_count + wc > CHUNK_WORDS):
            chunks.append(Document(text=" ".join(buf_texts), metadata={"source": os.path.basename(filepath), "start_time": f"{int(buf_start//60):02d}:{int(buf_start%60):02d}"}))
            buf_texts, word_count = [], 0
            buf_start = start
        if not buf_texts: buf_start = start
        buf_texts.append(text); buf_end = end; word_count += wc
    if buf_texts: chunks.append(Document(text=" ".join(buf_texts), metadata={"source": os.path.basename(filepath), "start_time": f"{int(buf_start//60):02d}:{int(buf_start%60):02d}"}))
    return chunks

def setup_engine():
    Settings.llm = Ollama(model=LLM_MODEL, request_timeout=LLM_TIMEOUT)
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL)
    Settings.chunk_size = 99999
    db = chromadb.PersistentClient(path=DB_PATH)
    collection = db.get_or_create_collection("chronobrain_docs")
    index = VectorStoreIndex.from_documents(
        [doc for f in os.listdir(DATA_DIR) if f.endswith(".txt") for doc in parse_transcript(os.path.join(DATA_DIR, f))],
        storage_context=StorageContext.from_defaults(vector_store=ChromaVectorStore(chroma_collection=collection))
    )
    return index

def build_prompt(context, history, question):
    hist_str = "\n".join([f"Q: {q}\nA: {a}" for q, a in history])
    return f"Vous etes ChronoBrain. Repondez en francais en utilisant le contexte. Si la reponse n'y est pas, dites: '{FALLBACK_MSG}'.\n\nContexte:\n{context}\n\nHistorique:\n{hist_str}\n\nQuestion: {question}\nReponse: "

def safe_llm_complete(llm, prompt):
    import httpx
    try: return str(llm.complete(prompt)).strip()
    except Exception as e: log.warning(f"LLM Error: {e}"); return None

# ── 4. MAIN LOOP ──────────────────────────────────────────────────────────────

def main():
    index = setup_engine()
    retriever = index.as_retriever(similarity_top_k=TOP_K)
    llm, cache, history = Settings.llm, {}, []

    print("\nChronoBrain prêt. Commandes: 'quit', 'reset', 'debug'.")

    while True:
        user_input = input("\n[ChronoBrain] Votre question: ").strip()
        if user_input.lower() == "quit": break
        if user_input.lower() == "reset": history, cache = [], {}; print("Reset."); continue
        if user_input.lower() == "debug": log.setLevel(logging.DEBUG); print("Debug ON."); continue
        if not is_valid_query(user_input): continue

        start_time = time.time()
        nodes = [n for n in retriever.retrieve(user_input) if (n.score or 0) >= MIN_SCORE]
        
        if not nodes:
            print(f"\nReponse: {FALLBACK_MSG}")
            tracker.report(time.time() - start_time, True)
            continue

        context = "\n\n".join([f"[{n.metadata.get('source')} {n.metadata.get('start_time')}] {n.get_content()}" for n in nodes[:3]])
        prompt = build_prompt(context, history[-HISTORY_TURNS:], user_input)
        
        answer = safe_llm_complete(llm, prompt)
        if answer is None: print(TIMEOUT_MSG); continue

        is_fallback = any(p in answer.lower() for p in FALLBACK_PHRASES)
        tracker.report(time.time() - start_time, is_fallback)
        print(f"\nReponse: {answer}")
        history.append((user_input, answer))

if __name__ == "__main__":
    main()