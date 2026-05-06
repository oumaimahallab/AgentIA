"""
ChronoBrain v3 — Bug-fixed & hardened
Fixes over v2:
  - MIN_SCORE raised to 0.45 (stops out-of-domain hallucination)
  - Early exit before LLM when no nodes pass the score filter
  - Timeout wrapped in try/except with retry + graceful message
  - Input validation: rejects empty/nonsense queries before retrieval
  - Absolute fallback if LLM times out (no crash)
"""

import os
import sys
import re
import hashlib
import logging
import time
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
DB_PATH     = "../data/chroma_v2"
LLM_MODEL   = "phi3"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

TOP_K              = 6
MIN_SCORE          = 0.45   # ← raised from 0.30; key fix for out-of-domain guard
MAX_CONTEXT_TOKENS = 1800
HISTORY_TURNS      = 3
LLM_TIMEOUT        = 360.0
LLM_RETRIES        = 1      # retry once on timeout before giving up

# Minimum real-word ratio to accept a query (blocks "aaaa", "???", etc.)
MIN_ALPHA_RATIO    = 0.6
MIN_QUERY_WORDS    = 2

FALLBACK_MSG = (
    "Je n'ai pas trouvé d'informations pertinentes dans les données "
    "de formation pour répondre à cette question."
)
TIMEOUT_MSG = (
    "Le modèle met trop de temps à répondre. "
    "Veuillez réessayer ou simplifier votre question."
)

logging.basicConfig(
    stream=sys.stdout,
    level=logging.WARNING,
    format="%(levelname)s | %(message)s",
)
log = logging.getLogger("chronobrain")


# ── 2. INPUT VALIDATION ───────────────────────────────────────────────────────

def is_valid_query(text: str) -> bool:
    """
    Reject queries that are too short, mostly non-alphabetic, or pure gibberish.
    Examples blocked: 'aaaa', '????', '123', '   '
    """
    words = text.split()
    if len(words) < MIN_QUERY_WORDS:
        return False
    alpha_chars = sum(c.isalpha() for c in text)
    total_chars = len(text.replace(" ", ""))
    if total_chars == 0:
        return False
    if alpha_chars / total_chars < MIN_ALPHA_RATIO:
        return False
    # Block runs of repeated characters: 'aaaa', 'abababab'
    if re.match(r'^(.)\1{3,}$', text.replace(" ", "")):
        return False
    return True


# ── 3. TIMESTAMP-AWARE CHUNKER ────────────────────────────────────────────────

def parse_transcript(filepath: str) -> list[Document]:
    CHUNK_WORDS = 80
    MAX_GAP_SEC = 3.0
    pattern = re.compile(r"\[(\d+):(\d+)\s*->\s*(\d+):(\d+)\]\s*(.*)")

    segments: list[tuple[float, float, str]] = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            m = pattern.match(line.strip())
            if not m:
                continue
            sm, ss, em, es, text = m.groups()
            start = int(sm) * 60 + int(ss)
            end   = int(em) * 60 + int(es)
            text  = text.strip()
            if text:
                segments.append((start, end, text))

    if not segments:
        return []

    def flush(texts, t_start, t_end):
        return Document(
            text=" ".join(texts),
            metadata={
                "source":     os.path.basename(filepath),
                "start_time": f"{int(t_start//60):02d}:{int(t_start%60):02d}",
                "end_time":   f"{int(t_end//60):02d}:{int(t_end%60):02d}",
            },
        )

    chunks, buf_texts = [], []
    buf_start = buf_end = word_count = 0

    for start, end, text in segments:
        gap = (start - buf_end) if buf_texts else 0
        wc  = len(text.split())
        if buf_texts and (gap > MAX_GAP_SEC or word_count + wc > CHUNK_WORDS):
            chunks.append(flush(buf_texts, buf_start, buf_end))
            buf_texts, word_count = [], 0
            buf_start = start
        if not buf_texts:
            buf_start = start
        buf_texts.append(text)
        buf_end    = end
        word_count += wc

    if buf_texts:
        chunks.append(flush(buf_texts, buf_start, buf_end))

    return chunks


def load_all_transcripts(data_dir: str) -> list[Document]:
    docs: list[Document] = []
    for root, _, files in os.walk(data_dir):
        for fname in files:
            if fname.endswith((".txt", ".md")):
                path   = os.path.join(root, fname)
                parsed = parse_transcript(path)
                if parsed:
                    docs.extend(parsed)
                else:
                    with open(path, encoding="utf-8") as f:
                        docs.append(Document(text=f.read(),
                                             metadata={"source": fname}))
    log.warning("Total chunks loaded: %d", len(docs))
    return docs


# ── 4. ENGINE SETUP ───────────────────────────────────────────────────────────

def setup_engine():
    Settings.llm         = Ollama(model=LLM_MODEL, request_timeout=LLM_TIMEOUT)
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL)
    Settings.chunk_size  = 99999
    Settings.chunk_overlap = 0

    db          = chromadb.PersistentClient(path=DB_PATH)
    collection  = db.get_or_create_collection("chronobrain_docs")
    vec_store   = ChromaVectorStore(chroma_collection=collection)
    storage_ctx = StorageContext.from_defaults(vector_store=vec_store)

    docs  = load_all_transcripts(DATA_DIR)
    index = VectorStoreIndex.from_documents(
        docs, storage_context=storage_ctx, show_progress=True
    )
    return index


# ── 5. RETRIEVAL HELPERS ──────────────────────────────────────────────────────

def score_filter(nodes, min_score: float):
    good    = [n for n in nodes if (n.score or 0) >= min_score]
    dropped = len(nodes) - len(good)
    if dropped:
        log.debug("Score filter: dropped %d/%d (min=%.2f, kept scores: %s)",
                  dropped, len(nodes), min_score,
                  [f"{n.score:.2f}" for n in good])
    return good


def deduplicate(nodes, threshold: float = 0.92):
    kept = []
    for node in nodes:
        words_a = set(node.get_content().lower().split())
        dup = any(
            len(words_a & set(k.get_content().lower().split())) /
            max(1, min(len(words_a), len(set(k.get_content().lower().split())))) > threshold
            for k in kept
        )
        if not dup:
            kept.append(node)
    return kept


def trim_to_token_budget(chunks: list[str], budget: int) -> str:
    char_budget = budget * 4
    result, total = [], 0
    for chunk in chunks:
        if total + len(chunk) > char_budget:
            break
        result.append(chunk)
        total += len(chunk)
    return "\n\n".join(result)


# ── 6. PROMPT BUILDER ─────────────────────────────────────────────────────────

def build_prompt(context: str, history: list[tuple[str, str]], question: str) -> str:
    history_str = ""
    if history:
        history_str = "\n".join(
            f"Question précédente: {q}\nRéponse: {a}" for q, a in history
        ) + "\n\n"

    return (
        "Vous êtes ChronoBrain, l'assistant officiel de l'entreprise. "
        "Utilisez UNIQUEMENT les informations du contexte ci-dessous. "
        "Si la réponse ne s'y trouve pas, dites-le explicitement.\n\n"
        f"Contexte:\n──────────────\n{context}\n──────────────\n\n"
        f"{history_str}"
        "Instructions:\n"
        "1. Répondez exclusivement en français.\n"
        "2. Réponse directe et concise.\n"
        "3. Ne citez pas les horodatages.\n"
        "4. Si le contexte est insuffisant, répondez: "
        "\"Je n'ai pas trouvé cette information dans les données de formation.\"\n\n"
        f"Question: {question}\n"
        "Réponse: "
    )


# ── 7. LLM CALL WITH RETRY + TIMEOUT GUARD ───────────────────────────────────

def safe_llm_complete(llm, prompt: str, retries: int = LLM_RETRIES) -> Optional[str]:
    """
    Call llm.complete() with retry on timeout.
    Returns None if all attempts fail — caller shows TIMEOUT_MSG.
    """
    import httpx
    for attempt in range(retries + 1):
        try:
            response = llm.complete(prompt)
            return str(response).strip()
        except (httpx.ReadTimeout, httpx.ConnectTimeout, Exception) as e:
            if attempt < retries:
                log.warning("LLM timeout (attempt %d/%d), retrying…", attempt + 1, retries + 1)
                time.sleep(2)
            else:
                log.warning("LLM failed after %d attempts: %s", retries + 1, e)
                return None


# ── 8. RESPONSE CACHE ─────────────────────────────────────────────────────────

class SimpleCache:
    def __init__(self, maxsize: int = 64):
        self._cache: dict[str, str] = {}
        self._keys  = deque(maxlen=maxsize)

    def _key(self, text: str) -> str:
        return hashlib.md5(text.lower().strip().encode()).hexdigest()

    def get(self, q: str) -> Optional[str]:
        return self._cache.get(self._key(q))

    def set(self, q: str, a: str):
        k = self._key(q)
        if k not in self._cache:
            if len(self._keys) == self._keys.maxlen:
                self._cache.pop(self._keys[0], None)
            self._keys.append(k)
        self._cache[k] = a


# ── 9. MAIN LOOP ──────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(DATA_DIR):
        print(f"Erreur: dossier '{DATA_DIR}' introuvable.")
        sys.exit(1)

    print("Initialisation de ChronoBrain v3…")
    index     = setup_engine()
    retriever = index.as_retriever(similarity_top_k=TOP_K)
    llm       = Settings.llm
    cache     = SimpleCache()
    history: list[tuple[str, str]] = []

    print("\nChronoBrain prêt. Tapez 'quit' pour quitter, 'reset' pour effacer l'historique.\n")

    while True:
        try:
            user_input = input("[ChronoBrain] Votre question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        if user_input.lower() == "reset":
            history.clear()
            cache._cache.clear()
            print("Historique effacé.\n")
            continue

        # ── FIX 1: Reject gibberish before touching the LLM ──────────────────
        if not is_valid_query(user_input):
            print("Veuillez poser une question complète.\n")
            continue

        # ── Cache hit ─────────────────────────────────────────────────────────
        cached = cache.get(user_input)
        if cached:
            print(f"\n[cache] {cached}\n")
            continue

        # ── Retrieve ──────────────────────────────────────────────────────────
        print("Recherche en cours…")
        nodes = retriever.retrieve(user_input)
        nodes = score_filter(nodes, MIN_SCORE)
        nodes = deduplicate(nodes)

        for i, n in enumerate(nodes):
            log.debug("  [%d] %.3f | %s | %s…",
                      i, n.score or 0,
                      n.metadata.get("source", "?"),
                      n.get_content()[:60].replace("\n", " "))

        # ── FIX 2: Early exit — no LLM call when nothing relevant found ───────
        if not nodes:
            print(f"\nRéponse: {FALLBACK_MSG}\n")
            history.append((user_input, FALLBACK_MSG))
            continue

        # ── Build context + prompt ────────────────────────────────────────────
        context = trim_to_token_budget(
            [n.get_content() for n in nodes], MAX_CONTEXT_TOKENS
        )
        prompt = build_prompt(context, history[-HISTORY_TURNS:], user_input)

        # ── FIX 3: Safe LLM call — catches timeout, never crashes ─────────────
        print("Réflexion…")
        answer = safe_llm_complete(llm, prompt)

        if answer is None:
            print(f"\nRéponse: {TIMEOUT_MSG}\n")
            continue

        # ── Fallback detection ────────────────────────────────────────────────
        FALLBACK_PHRASES = ["je n'ai pas trouvé", "je ne sais pas", "je ne trouve pas"]
        is_fallback = any(p in answer.lower() for p in FALLBACK_PHRASES)

        print(f"\nRéponse: {answer}\n")

        history.append((user_input, answer))
        if not is_fallback:
            cache.set(user_input, answer)


if __name__ == "__main__":
    main()