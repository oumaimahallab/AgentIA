"""
config.py — Central configuration for ChronoBrain
All tuneable parameters in one place.
"""

import os

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DATA_DIR        = os.path.join(BASE_DIR, "cleaned")
FAISS_DIR       = os.path.join(BASE_DIR, "db", "faiss_index")
BM25_PATH       = os.path.join(BASE_DIR, "db", "bm25_index.pkl")
SQLITE_PATH     = os.path.join(BASE_DIR, "db", "metadata.db")

# ── Models ────────────────────────────────────────────────────────────────────
LLM_MODEL       = "llama3"
EMBED_MODEL     = "BAAI/bge-small-en-v1.5"
OLLAMA_BASE_URL = "http://localhost:11434"

# ── Retrieval ─────────────────────────────────────────────────────────────────
TOP_K              = 6       # candidates fetched per retriever before fusion
MIN_SCORE          = 0.45    # fused score threshold
FALLBACK_TOP_K     = 2       # kept when all nodes fail threshold
SEMANTIC_WEIGHT    = 0.7     # weight for FAISS score in hybrid fusion
BM25_WEIGHT        = 0.3     # weight for BM25 score in hybrid fusion
MMR_THRESHOLD      = 0.92    # word-overlap threshold for deduplication

# ── LLM ───────────────────────────────────────────────────────────────────────
LLM_TIMEOUT        = 360.0
LLM_RETRIES        = 1
MAX_CONTEXT_TOKENS = 900     # ~3600 chars sent to LLM
HISTORY_TURNS      = 3
COMPANY_NAME       = "Inetum"

# ── Input validation ──────────────────────────────────────────────────────────
MIN_QUERY_WORDS    = 2
MIN_ALPHA_RATIO    = 0.6

# ── Cache ─────────────────────────────────────────────────────────────────────
CACHE_SIZE         = 64

# ── Faithfulness check ────────────────────────────────────────────────────────
MIN_OVERLAP_RATIO  = 0.20    # keyword overlap below this → reject answer

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL          = "WARNING"   # set "DEBUG" to see retrieval scores live
