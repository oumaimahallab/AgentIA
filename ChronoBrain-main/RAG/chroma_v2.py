"""
ChronoBrain v2 — Optimized RAG Chatbot
Improvements over v1:
  - Semantic timestamp-aware chunking (pre-processor)
  - Score filtering: drops low-relevance chunks
  - MMR-style deduplication to avoid repetitive context
  - Token budget trimming (never overflow the context window)
  - Conversation history (last N turns as context)
  - Response cache (skip LLM for repeated questions)
  - Graceful "not found" fallback
  - Structured logging for debugging retrieval quality
"""

import os
import sys
import re
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

DATA_DIR   = "../data/transcripts"
DB_PATH    = "../data/chroma_v2"
LLM_MODEL  = "phi3"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

# Retrieval knobs
TOP_K              = 6      # fetch more than needed, then filter
MIN_SCORE          = 0.30   # drop chunks below this cosine similarity
MAX_CONTEXT_TOKENS = 1800   # hard cap before sending to LLM (~4 chars/token)
HISTORY_TURNS      = 3      # how many previous Q/A pairs to include

logging.basicConfig(
    stream=sys.stdout,
    level=logging.WARNING,          # set DEBUG to see retrieval scores
    format="%(levelname)s | %(message)s",
)
log = logging.getLogger("chronobrain")


# ── 2. TIMESTAMP-AWARE CHUNKER ────────────────────────────────────────────────
#
# Transcript lines look like:  [83:13 -> 83:14] C'est souvent manager direct.
# Strategy: merge consecutive short lines into a single chunk until we hit
# a natural pause (>2 s gap) or a target word count.

def parse_transcript(filepath: str) -> list[Document]:
    """Read a transcript file and return semantically grouped Document chunks."""
    CHUNK_WORDS   = 80    # target words per chunk
    MAX_GAP_SEC   = 3.0   # break chunk on gap larger than this
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

    chunks: list[Document] = []
    buf_texts: list[str]   = []
    buf_start: float       = segments[0][0]
    buf_end: float         = segments[0][1]
    word_count             = 0

    def flush(texts, t_start, t_end):
        combined = " ".join(texts)
        meta = {
            "source":     os.path.basename(filepath),
            "start_time": f"{int(t_start//60):02d}:{int(t_start%60):02d}",
            "end_time":   f"{int(t_end//60):02d}:{int(t_end%60):02d}",
        }
        return Document(text=combined, metadata=meta)

    for i, (start, end, text) in enumerate(segments):
        gap = start - buf_end if buf_texts else 0
        wc  = len(text.split())

        if buf_texts and (gap > MAX_GAP_SEC or word_count + wc > CHUNK_WORDS):
            chunks.append(flush(buf_texts, buf_start, buf_end))
            buf_texts  = []
            buf_start  = start
            word_count = 0

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
                path = os.path.join(root, fname)
                parsed = parse_transcript(path)
                if parsed:
                    docs.extend(parsed)
                    log.debug("Loaded %d chunks from %s", len(parsed), fname)
                else:
                    # Fallback: load as plain text
                    with open(path, encoding="utf-8") as f:
                        docs.append(Document(text=f.read(),
                                             metadata={"source": fname}))
    log.warning("Total chunks loaded: %d", len(docs))
    return docs


# ── 3. INFRASTRUCTURE SETUP ───────────────────────────────────────────────────

def setup_engine():
    Settings.llm        = Ollama(model=LLM_MODEL, request_timeout=360.0)
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL)
    # Disable LlamaIndex's default node parser — we chunk manually
    Settings.chunk_size  = 99999
    Settings.chunk_overlap = 0

    db               = chromadb.PersistentClient(path=DB_PATH)
    collection       = db.get_or_create_collection("chronobrain_docs")
    vector_store     = ChromaVectorStore(chroma_collection=collection)
    storage_context  = StorageContext.from_defaults(vector_store=vector_store)

    docs = load_all_transcripts(DATA_DIR)
    if not docs:
        log.warning("No documents found — index will be empty.")

    index = VectorStoreIndex.from_documents(
        docs,
        storage_context=storage_context,
        show_progress=True,
    )
    return index


# ── 4. RETRIEVAL HELPERS ──────────────────────────────────────────────────────

def score_filter(nodes, min_score: float):
    """Drop nodes whose similarity score is below the threshold."""
    good = [n for n in nodes if (n.score or 0) >= min_score]
    dropped = len(nodes) - len(good)
    if dropped:
        log.debug("Score filter dropped %d/%d chunks (min=%.2f)", dropped, len(nodes), min_score)
    return good


def deduplicate(nodes, similarity_threshold: float = 0.92):
    """
    Simple MMR-style text deduplication.
    If two chunks share >threshold of their words, keep only the higher-scored one.
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
            if overlap > similarity_threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(node)
    return kept


def trim_to_token_budget(chunks: list[str], budget: int) -> str:
    """
    Concatenate chunks until we'd exceed `budget` characters (~4 chars/token).
    Returns the trimmed context string.
    """
    char_budget = budget * 4
    result, total = [], 0
    for chunk in chunks:
        if total + len(chunk) > char_budget:
            break
        result.append(chunk)
        total += len(chunk)
    return "\n\n".join(result)


# ── 5. PROMPT BUILDER ─────────────────────────────────────────────────────────

def build_prompt(context: str, history: list[tuple[str, str]], question: str) -> str:
    history_str = ""
    if history:
        lines = []
        for q, a in history:
            lines.append(f"Question précédente: {q}")
            lines.append(f"Réponse: {a}")
        history_str = "\n".join(lines) + "\n\n"

    no_ctx = not context.strip()
    if no_ctx:
        return (
            f"Vous êtes ChronoBrain, l'assistant officiel de l'entreprise. "
            f"Répondez uniquement en français.\n\n"
            f"{history_str}"
            f"Question: {question}\n"
            f"Si vous ne trouvez pas la réponse dans vos données, dites-le clairement.\n"
            f"Réponse: "
        )

    return (
        f"Vous êtes ChronoBrain, l'assistant officiel de l'entreprise. "
        f"Utilisez uniquement les informations du contexte ci-dessous.\n\n"
        f"Contexte extrait des formations:\n"
        f"─────────────────────────────\n"
        f"{context}\n"
        f"─────────────────────────────\n\n"
        f"{history_str}"
        f"Instructions:\n"
        f"1. Répondez exclusivement en français.\n"
        f"2. Réponse directe, complète, concise.\n"
        f"3. Ne citez pas les horodatages.\n"
        f"4. Si le contexte ne contient pas la réponse, dites-le.\n\n"
        f"Question: {question}\n"
        f"Réponse: "
    )


# ── 6. RESPONSE CACHE ─────────────────────────────────────────────────────────

class SimpleCache:
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
                old = self._keys[0]
                self._cache.pop(old, None)
            self._keys.append(k)
        self._cache[k] = answer


# ── 7. MAIN LOOP ──────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(DATA_DIR):
        print(f"Erreur: dossier '{DATA_DIR}' introuvable.")
        sys.exit(1)

    print("Initialisation de ChronoBrain v2…")
    index    = setup_engine()
    retriever = index.as_retriever(similarity_top_k=TOP_K)
    llm      = Settings.llm
    cache    = SimpleCache()
    history: list[tuple[str, str]] = []   # [(question, answer), …]

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

        # ── Cache hit ──
        cached = cache.get(user_input)
        if cached:
            print(f"\n[cache] {cached}\n")
            continue

        # ── Retrieve ──
        print("Recherche en cours…")
        nodes = retriever.retrieve(user_input)

        # Filter by score
        nodes = score_filter(nodes, MIN_SCORE)

        # Deduplicate
        nodes = deduplicate(nodes)

        # Log what we retrieved
        for i, n in enumerate(nodes):
            src  = n.metadata.get("source", "?")
            t    = n.metadata.get("start_time", "")
            score = n.score or 0
            log.debug("  [%d] %.3f | %s %s | %s…", i, score, src, t,
                      n.get_content()[:60].replace("\n", " "))

        # Build context string within token budget
        context = trim_to_token_budget(
            [n.get_content() for n in nodes],
            MAX_CONTEXT_TOKENS,
        )

        # ── Build prompt ──
        recent_history = history[-HISTORY_TURNS:]
        prompt = build_prompt(context, recent_history, user_input)

        # ── LLM call ──
        print("Réflexion…")
        response = llm.complete(prompt)
        answer   = str(response).strip()

        # ── Fallback detection ──
        FALLBACK_PHRASES = ["je ne sais pas", "je ne trouve pas", "je n'ai pas"]
        is_fallback = any(p in answer.lower() for p in FALLBACK_PHRASES)

        if not nodes and not is_fallback:
            answer = (
                "Je n'ai pas trouvé d'informations pertinentes dans les données "
                "de formation pour répondre à cette question."
            )

        print(f"\nRéponse: {answer}\n")

        # ── Update history + cache ──
        history.append((user_input, answer))
        if not is_fallback:
            cache.set(user_input, answer)


if __name__ == "__main__":
    main()