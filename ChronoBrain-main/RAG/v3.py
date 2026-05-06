"""
ChronoBrain v4 — Best of v2 + v3 merged
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FROM v2 (kept for answer quality):
  ✓ Rich prompt with numbered instructions (gives complete, detailed answers)
  ✓ Debug logging with source file + timestamp per retrieved chunk
  ✓ Extended fallback phrase list

FROM v3 (kept for robustness):
  ✓ is_valid_query() — blocks 'aaaa', '????', single chars before any LLM call
  ✓ MIN_SCORE = 0.45 — stops out-of-domain hallucination
  ✓ Early exit when no nodes pass score filter (no LLM call at all)
  ✓ safe_llm_complete() — retries once, never crashes on timeout
  ✓ LLM_TIMEOUT / LLM_RETRIES constants

NEW in v4:
  ✓ Prompt instruction 5: preserve technical terms exactly (B_HS, RESP2, etc.)
  ✓ Prompt instruction 6: if concept has steps/rules, list them clearly
  ✓ Labeled context: each chunk shows its source file for LLM clarity
  ✓ 'debug' command at runtime to enable score logging without restarting
"""

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
DB_PATH     = "../data/chroma_v3"
LLM_MODEL   = "phi3"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

TOP_K              = 6       # fetch more, then filter down
MIN_SCORE          = 0.45    # v3 fix: stops out-of-domain hallucination
MAX_CONTEXT_TOKENS = 1800    # hard cap (~4 chars/token)
HISTORY_TURNS      = 3       # Q/A pairs kept in context
LLM_TIMEOUT        = 360.0   # seconds before Ollama times out
LLM_RETRIES        = 1       # retry once on timeout before giving up

# Input validation thresholds
MIN_ALPHA_RATIO = 0.6   # at least 60% of non-space chars must be letters
MIN_QUERY_WORDS = 2     # must have at least 2 words

FALLBACK_MSG = (
    "Je n'ai pas trouve d'informations pertinentes dans les donnees "
    "de formation pour repondre a cette question."
)
TIMEOUT_MSG = (
    "Le modele met trop de temps a repondre. "
    "Veuillez reessayer ou simplifier votre question."
)

FALLBACK_PHRASES = [
    "je n'ai pas trouve",
    "je ne sais pas",
    "je ne trouve pas",
    "je n'ai pas d'information",
    "information non disponible",
]

logging.basicConfig(
    stream=sys.stdout,
    level=logging.WARNING,   # switch to DEBUG (or type 'debug' at runtime)
    format="%(levelname)s | %(message)s",
)
log = logging.getLogger("chronobrain")


# ── 2. INPUT VALIDATION (from v3) ─────────────────────────────────────────────

def is_valid_query(text: str) -> bool:
    """
    Block queries that are pure gibberish before hitting ChromaDB or the LLM.
    Rejects: 'aaaa', '????', '123', single-word under threshold, etc.
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
    # Block repeated-character runs: 'aaaa', 'ababab'
    if re.match(r'^(.)\1{3,}$', text.replace(" ", "")):
        return False
    return True


# ── 3. TIMESTAMP-AWARE CHUNKER (from v2) ──────────────────────────────────────

def parse_transcript(filepath: str) -> list[Document]:
    """
    Merge consecutive short transcript lines into semantically coherent chunks.
    Breaks on long silences (>MAX_GAP_SEC) or when chunk exceeds CHUNK_WORDS.
    Expected line format: [MM:SS -> MM:SS] Text here.
    """
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

    def flush(texts: list[str], t_start: float, t_end: float) -> Document:
        return Document(
            text=" ".join(texts),
            metadata={
                "source":     os.path.basename(filepath),
                "start_time": f"{int(t_start//60):02d}:{int(t_start%60):02d}",
                "end_time":   f"{int(t_end//60):02d}:{int(t_end%60):02d}",
            },
        )

    chunks: list[Document] = []
    buf_texts: list[str]   = []
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
                    log.debug("Loaded %d chunks from %s", len(parsed), fname)
                else:
                    # Fallback: load file as a single plain-text document
                    with open(path, encoding="utf-8") as f:
                        docs.append(Document(text=f.read(),
                                             metadata={"source": fname}))
    log.warning("Total chunks loaded: %d", len(docs))
    return docs


# ── 4. ENGINE SETUP ───────────────────────────────────────────────────────────

def setup_engine():
    Settings.llm         = Ollama(model=LLM_MODEL, request_timeout=LLM_TIMEOUT)
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL)
    Settings.chunk_size  = 99999   # disable LlamaIndex's own splitter
    Settings.chunk_overlap = 0

    db          = chromadb.PersistentClient(path=DB_PATH)
    collection  = db.get_or_create_collection("chronobrain_docs")
    vec_store   = ChromaVectorStore(chroma_collection=collection)
    storage_ctx = StorageContext.from_defaults(vector_store=vec_store)

    docs = load_all_transcripts(DATA_DIR)
    if not docs:
        log.warning("No documents found — index will be empty.")

    index = VectorStoreIndex.from_documents(
        docs, storage_context=storage_ctx, show_progress=True
    )
    return index


# ── 5. RETRIEVAL HELPERS ──────────────────────────────────────────────────────

def score_filter(nodes, min_score: float):
    """Drop any node whose cosine similarity score is below min_score."""
    good    = [n for n in nodes if (n.score or 0) >= min_score]
    dropped = len(nodes) - len(good)
    if dropped:
        log.debug(
            "Score filter: kept %d/%d chunks (min=%.2f) | scores kept: %s",
            len(good), len(nodes), min_score,
            [f"{n.score:.3f}" for n in good],
        )
    return good


def deduplicate(nodes, threshold: float = 0.92):
    """
    Remove near-duplicate chunks (word overlap > threshold).
    Keeps the first (highest-scored) chunk when duplicates are found.
    """
    kept = []
    for node in nodes:
        words_a = set(node.get_content().lower().split())
        is_dup  = False
        for kept_node in kept:
            words_b = set(kept_node.get_content().lower().split())
            if not words_a or not words_b:
                continue
            overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
            if overlap > threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(node)
    return kept


def trim_to_token_budget(chunks: list[str], budget: int) -> str:
    """Join chunks up to the character budget (~4 chars per token)."""
    char_budget = budget * 4
    result, total = [], 0
    for chunk in chunks:
        if total + len(chunk) > char_budget:
            break
        result.append(chunk)
        total += len(chunk)
    return "\n\n".join(result)


# ── 6. PROMPT BUILDER (v2 richness + v4 technical instructions) ───────────────

def build_prompt(context: str, history: list[tuple[str, str]], question: str) -> str:
    history_str = ""
    if history:
        lines = []
        for q, a in history:
            lines.append(f"Question precedente: {q}")
            lines.append(f"Reponse precedente: {a}")
        history_str = "\n".join(lines) + "\n\n"

    return (
        "Vous etes ChronoBrain, l'assistant officiel de l'entreprise. "
        "Votre role est de repondre aux questions sur les formations et procedures internes "
        "en vous basant UNIQUEMENT sur le contexte fourni ci-dessous.\n\n"
        "Contexte extrait des formations:\n"
        "─────────────────────────────\n"
        f"{context}\n"
        "─────────────────────────────\n\n"
        f"{history_str}"
        "Instructions:\n"
        "1. Repondez EXCLUSIVEMENT en francais.\n"
        "2. Fournissez une reponse directe, complete et bien structuree.\n"
        "3. Ne citez pas les horodatages dans votre reponse.\n"
        "4. Si le contexte ne contient pas la reponse, dites exactement: "
        "\"Je n'ai pas trouve cette information dans les donnees de formation.\"\n"
        "5. Conservez les termes techniques exacts tels qu'ils apparaissent dans le contexte "
        "(ex: B_HS, RESP2, GFI) — ne les traduisez pas et ne les modifiez pas.\n"
        "6. Si la question porte sur une regle, un calcul ou des etapes, "
        "detaillez-les clairement point par point.\n\n"
        f"Question: {question}\n"
        "Reponse: "
    )


# ── 7. SAFE LLM CALL WITH RETRY (from v3) ────────────────────────────────────

def safe_llm_complete(llm, prompt: str, retries: int = LLM_RETRIES) -> Optional[str]:
    """
    Wraps llm.complete() with timeout handling and one automatic retry.
    Returns None if all attempts fail — caller prints TIMEOUT_MSG instead of crashing.
    """
    import httpx
    for attempt in range(retries + 1):
        try:
            return str(llm.complete(prompt)).strip()
        except (httpx.ReadTimeout, httpx.ConnectTimeout, Exception) as exc:
            if attempt < retries:
                log.warning(
                    "LLM timeout on attempt %d/%d — retrying in 2s… (%s)",
                    attempt + 1, retries + 1, exc,
                )
                time.sleep(2)
            else:
                log.warning("LLM failed after %d attempt(s): %s", retries + 1, exc)
                return None


# ── 8. RESPONSE CACHE ─────────────────────────────────────────────────────────

class SimpleCache:
    """LRU-style in-memory cache keyed by MD5 of the normalized question."""

    def __init__(self, maxsize: int = 64):
        self._cache: dict[str, str] = {}
        self._keys  = deque(maxlen=maxsize)

    def _key(self, text: str) -> str:
        return hashlib.md5(text.lower().strip().encode()).hexdigest()

    def get(self, question: str) -> Optional[str]:
        return self._cache.get(self._key(question))

    def set(self, question: str, answer: str):
        k = self._key(question)
        if k not in self._cache:
            if len(self._keys) == self._keys.maxlen:
                self._cache.pop(self._keys[0], None)
            self._keys.append(k)
        self._cache[k] = answer



# --- ADD THIS CLASS BEFORE MAIN LOOP ---
class PerformanceTracker:
    def __init__(self):
        self.queries = 0
        self.total_latency = 0
        self.fallbacks = 0  # Likely hallucination or "I don't know"

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
# ── 9. MAIN LOOP ──────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(DATA_DIR):
        print(f"Erreur: dossier '{DATA_DIR}' introuvable.")
        sys.exit(1)

    print("Initialisation de ChronoBrain v4...")
    index     = setup_engine()
    retriever = index.as_retriever(similarity_top_k=TOP_K)
    llm       = Settings.llm
    cache     = SimpleCache()
    history: list[tuple[str, str]] = []

    print("\nChronoBrain pret.")
    print("Commandes: 'quit' pour quitter | 'reset' pour effacer l'historique | 'debug' pour activer les logs\n")

    while True:
        try:
            user_input = input("[ChronoBrain] Votre question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            break

        # ── Special commands ──────────────────────────────────────────────────
        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        if user_input.lower() == "reset":
            history.clear()
            cache._cache.clear()
            print("Historique et cache effaces.\n")
            continue
        if user_input.lower() == "debug":
            log.setLevel(logging.DEBUG)
            logging.getLogger().setLevel(logging.DEBUG)
            print("Mode debug active — les scores de recuperation seront affiches.\n")
            continue

        # ── v3: Reject gibberish before any DB/LLM call ───────────────────────
        if not is_valid_query(user_input):
            print("Veuillez poser une question complete en francais.\n")
            continue

        # ── Cache hit ─────────────────────────────────────────────────────────
        cached = cache.get(user_input)
        if cached:
            print(f"\n[cache] {cached}\n")
            continue

        # ── Retrieve ──────────────────────────────────────────────────────────
        print("Recherche en cours...")
        nodes = retriever.retrieve(user_input)

        # v3: filter by score — MIN_SCORE=0.45 blocks out-of-domain answers
        nodes = score_filter(nodes, MIN_SCORE)

        # v2: remove near-duplicate chunks
        nodes = deduplicate(nodes)

        # v2: log chunk details when debug is enabled
        for i, n in enumerate(nodes):
            log.debug(
                "  [%d] score=%.3f | %s (%s->%s) | %s...",
                i,
                n.score or 0,
                n.metadata.get("source", "?"),
                n.metadata.get("start_time", ""),
                n.metadata.get("end_time", ""),
                n.get_content()[:70].replace("\n", " "),
            )

        # ── v3: Early exit — never call the LLM when retrieval is empty ───────
        if not nodes:
            print(f"\nReponse: {FALLBACK_MSG}\n")
            history.append((user_input, FALLBACK_MSG))
            continue

        # ── Build labeled context (v4: source labels help technical answers) ──
        labeled_chunks = [
            "[{src} {ts}]\n{text}".format(
                src=n.metadata.get("source", "?"),
                ts=n.metadata.get("start_time", ""),
                text=n.get_content(),
            )
            for n in nodes
        ]
        context = trim_to_token_budget(labeled_chunks, MAX_CONTEXT_TOKENS)

        # ── Build prompt (v2 richness + v4 technical instructions) ───────────
        prompt = build_prompt(context, history[-HISTORY_TURNS:], user_input)

        # ── v3: Safe LLM call — retries once, never crashes ───────────────────
        
# --- INSIDE THE MAIN LOOP (Replace LLM Call section) ---

        start_time = time.time()
        
        # ── LLM Call ──
        print("Reflexion...")
        answer = safe_llm_complete(llm, prompt)
        
        latency = time.time() - start_time
        
        if answer is None:
            print(f"\nReponse: {TIMEOUT_MSG}\n")
            continue

        # ── Fallback/Hallucination Detection ──
        is_fallback = any(p in answer.lower() for p in FALLBACK_PHRASES)
        
        # Display Metrics
        tracker.report(latency, is_fallback)
        print(f"\nReponse: {answer}\n")


        # ── Fallback detection (v2 extended phrase list) ──────────────────────
        is_fallback = any(p in answer.lower() for p in FALLBACK_PHRASES)

        print(f"\nReponse: {answer}\n")

        # ── Update history + cache ────────────────────────────────────────────
        history.append((user_input, answer))
        if not is_fallback:
            cache.set(user_input, answer)
    
# --- IN


if __name__ == "__main__":
    main()