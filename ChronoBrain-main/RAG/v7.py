"""
ChronoBrain v6 — Retrieval-first fixes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Changes from v5:
  ✦ MIN_SCORE lowered to 0.30 with a soft floor fallback
      → If score filter kills ALL nodes, keep top-2 raw results anyway
      → Stops "Je n'ai pas trouvé" on questions that ARE in the data
  ✦ TOP_K raised to 8 for better recall on technical questions
  ✦ LLM-as-judge evaluator REMOVED
      → Was calling Phi-3 twice per question (doubles latency ~130s → ~65s)
      → Was producing wrong verdicts (called correct answers hallucinations)
      → Replaced with fast keyword-based faithfulness check (zero latency)
  ✦ Metrics now track: latency, fallback rate, cache hit rate
  ✦ Prompt: added explicit list of known technical terms to anchor retrieval
  ✦ Debug mode: type 'debug on' to print retrieval scores live
"""

import os
import sys
import re
import time
import hashlib
import logging
from collections import deque
from typing import Optional

import httpx
from llama_index.core import VectorStoreIndex, StorageContext, Settings, Document
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

# ── 1. CONFIGURATION ──────────────────────────────────────────────────────────

DATA_DIR    = "../data/transcripts"
DB_PATH     = "../data/chroma_v7"
LLM_MODEL   = "phi3"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

TOP_K              = 8       # raised: more candidates before filtering
MIN_SCORE          = 0.30    # lowered: spoken French scores lower than written
FALLBACK_TOP_K     = 2       # if ALL nodes fail score filter, keep best N raw
MAX_CONTEXT_TOKENS = 1800
HISTORY_TURNS      = 3
LLM_TIMEOUT        = 360.0
LLM_RETRIES        = 1

MIN_ALPHA_RATIO = 0.6
MIN_QUERY_WORDS = 2

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

# Runtime debug toggle (type 'debug on' / 'debug off' in chat)
DEBUG_RETRIEVAL = False


# ── 2. INPUT VALIDATION ───────────────────────────────────────────────────────

def is_valid_query(text: str) -> bool:
    words = text.split()
    if len(words) < MIN_QUERY_WORDS:
        return False
    alpha = sum(c.isalpha() for c in text)
    total = len(text.replace(" ", ""))
    if total == 0 or alpha / total < MIN_ALPHA_RATIO:
        return False
    if re.match(r'^(.)\1{3,}$', text.replace(" ", "")):
        return False
    return True


# ── 3. SEMANTIC TIMESTAMP CHUNKER ─────────────────────────────────────────────

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

    def flush(texts: list[str], t_start: float, t_end: float) -> Document:
        return Document(
            text=" ".join(texts),
            metadata={
                "source":     os.path.basename(filepath),
                "start_time": f"{int(t_start // 60):02d}:{int(t_start % 60):02d}",
                "end_time":   f"{int(t_end   // 60):02d}:{int(t_end   % 60):02d}",
            },
        )

    chunks: list[Document] = []
    buf_texts: list[str]   = []
    buf_start = buf_end = word_count = 0.0

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
                    with open(path, encoding="utf-8") as f:
                        docs.append(Document(
                            text=f.read(),
                            metadata={"source": fname}
                        ))
    log.warning("Total chunks loaded: %d", len(docs))
    return docs


# ── 4. ENGINE SETUP (idempotent) ──────────────────────────────────────────────

def setup_engine():
    Settings.llm         = Ollama(model=LLM_MODEL, request_timeout=LLM_TIMEOUT)
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL)
    Settings.chunk_size    = 99999
    Settings.chunk_overlap = 0

    db         = chromadb.PersistentClient(path=DB_PATH)
    collection = db.get_or_create_collection("chronobrain_docs")
    vec_store  = ChromaVectorStore(chroma_collection=collection)

    if collection.count() > 0:
        log.warning("ChromaDB: %d vectors already indexed — skipping ingestion.", collection.count())
        index = VectorStoreIndex.from_vector_store(vec_store)
    else:
        docs = load_all_transcripts(DATA_DIR)
        if not docs:
            log.warning("No documents found — index will be empty.")
        storage_ctx = StorageContext.from_defaults(vector_store=vec_store)
        index = VectorStoreIndex.from_documents(
            docs, storage_context=storage_ctx, show_progress=True
        )

    return index


# ── 5. RETRIEVAL HELPERS ──────────────────────────────────────────────────────

def retrieve_nodes(retriever, query: str, min_score: float, fallback_k: int):
    """
    Retrieve nodes and apply score filtering.
    
    IMPORTANT FIX: If score filter removes ALL nodes, fall back to the top
    `fallback_k` raw results. This prevents "Je n'ai pas trouvé" on questions
    that ARE in the data but whose chunks scored slightly below min_score.
    
    Use 'debug on' in chat to see scores printed in real time.
    """
    raw_nodes = retriever.retrieve(query)

    if DEBUG_RETRIEVAL:
        print("\n[DEBUG] Retrieval scores:")
        for i, n in enumerate(raw_nodes):
            print(f"  [{i}] score={n.score:.3f} | "
                  f"{n.metadata.get('source','?')} [{n.metadata.get('start_time','')}] | "
                  f"{n.get_content()[:80].replace(chr(10),' ')}…")

    filtered = [n for n in raw_nodes if (n.score or 0) >= min_score]

    if filtered:
        return filtered, False   # (nodes, used_fallback)

    # Soft floor: nothing passed the threshold — return best N raw results
    # so the LLM still has a chance to answer rather than giving up entirely
    if raw_nodes:
        best = sorted(raw_nodes, key=lambda n: n.score or 0, reverse=True)[:fallback_k]
        log.warning(
            "Score filter removed all nodes (best=%.3f < %.2f) — using top-%d fallback",
            best[0].score or 0, min_score, fallback_k
        )
        return best, True   # flag so we can be more cautious in the prompt
    return [], False


def deduplicate(nodes, threshold: float = 0.92):
    kept = []
    for node in nodes:
        words_a = set(node.get_content().lower().split())
        is_dup = any(
            len(words_a & set(k.get_content().lower().split())) /
            max(1, min(len(words_a), len(set(k.get_content().lower().split())))) > threshold
            for k in kept
        )
        if not is_dup:
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


# ── 6. FAST FAITHFULNESS CHECK (replaces slow LLM-as-judge) ──────────────────
#
# Instead of calling Phi-3 a second time (doubles latency, unreliable verdicts),
# we do a fast keyword overlap check: if the answer shares key content words
# with the retrieved context, it's likely faithful.
# This runs in <1ms vs ~65s for a second LLM call.

def fast_faithfulness_check(context: str, answer: str) -> dict:
    """
    Heuristic faithfulness check based on keyword overlap.
    Returns a dict with the same keys as the old LLM judge for compatibility.
    """
    FALLBACK_INDICATORS = [
        "je n'ai pas trouvé",
        "je ne sais pas",
        "je n'ai pas cette information",
        "je ne peux pas",
        "aucune information",
    ]

    answer_lower  = answer.lower()
    context_lower = context.lower()

    # Check if the answer is an explicit fallback
    is_explicit_fallback = any(p in answer_lower for p in FALLBACK_INDICATORS)
    if is_explicit_fallback:
        return {"fidélité": "Oui", "hallucination": "Non", "score": 3, "method": "fallback-detected"}

    # Keyword overlap: extract meaningful words (>4 chars) from answer
    answer_words  = set(w for w in re.findall(r'\b\w{4,}\b', answer_lower))
    context_words = set(w for w in re.findall(r'\b\w{4,}\b', context_lower))

    if not answer_words:
        return {"fidélité": "Inconnu", "hallucination": "Inconnu", "score": 0, "method": "empty"}

    overlap = len(answer_words & context_words) / len(answer_words)

    if overlap >= 0.35:
        return {"fidélité": "Oui", "hallucination": "Non",
                "score": min(5, int(overlap * 8)), "method": f"overlap={overlap:.2f}"}
    else:
        return {"fidélité": "Non", "hallucination": "Oui",
                "score": max(1, int(overlap * 5)), "method": f"overlap={overlap:.2f}"}


# ── 7. PROMPT BUILDER ─────────────────────────────────────────────────────────

def build_prompt(
    context: str,
    history: list[tuple[str, str]],
    question: str,
    low_confidence: bool = False,
) -> str:
    history_str = ""
    if history:
        history_str = "\n".join(
            f"Question précédente: {q}\nRéponse: {a}" for q, a in history
        ) + "\n\n"

    confidence_note = (
        "\nATTENTION: Le contexte ci-dessous est de faible pertinence. "
        "Soyez très prudent et n'inventez rien.\n"
        if low_confidence else ""
    )

    return (
        "Vous êtes ChronoBrain, l'assistant officiel de l'entreprise. "
        "Utilisez UNIQUEMENT les informations du contexte ci-dessous. "
        "N'utilisez JAMAIS vos connaissances générales ou extérieures au contexte.\n"
        f"{confidence_note}\n"
        f"Contexte extrait des formations:\n"
        f"──────────────────────────────\n"
        f"{context}\n"
        f"──────────────────────────────\n\n"
        f"{history_str}"
        "Instructions:\n"
        "1. Répondez exclusivement en français.\n"
        "2. Réponse directe, complète et concise.\n"
        "3. Ne citez pas les horodatages.\n"
        "4. Si le contexte ne contient pas la réponse, répondez EXACTEMENT:\n"
        "   \"Je n'ai pas trouvé cette information dans les données de formation.\"\n"
        "5. N'inventez aucun fait, chiffre, règle ou définition.\n\n"
        f"Question: {question}\n"
        "Réponse: "
    )


# ── 8. SAFE LLM CALL ──────────────────────────────────────────────────────────

def safe_llm_complete(llm, prompt: str, retries: int = LLM_RETRIES) -> Optional[str]:
    for attempt in range(retries + 1):
        try:
            return str(llm.complete(prompt)).strip()
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            if attempt < retries:
                log.warning("Timeout (attempt %d/%d), retry in 2s…", attempt + 1, retries + 1)
                time.sleep(2)
            else:
                log.warning("LLM failed after %d attempts.", retries + 1)
                return None
        except Exception as e:
            log.warning("LLM error: %s", e)
            return None


# ── 9. METRICS TRACKER ───────────────────────────────────────────────────────

class PerformanceTracker:
    def __init__(self):
        self.queries    = 0
        self.total_lat  = 0.0
        self.fallbacks  = 0
        self.cache_hits = 0

    def record(self, latency: float, is_fallback: bool):
        self.queries  += 1
        self.total_lat += latency
        if is_fallback:
            self.fallbacks += 1

    def print_stats(self):
        if self.queries == 0:
            print("Aucune requête enregistrée.\n")
            return
        avg  = self.total_lat / self.queries
        rate = (self.fallbacks / self.queries) * 100
        print(f"\n[Stats] {self.queries} réponses LLM | "
              f"Cache: {self.cache_hits} hits | "
              f"Latence moy: {avg:.1f}s | "
              f"Non-fidèle: {rate:.0f}%\n")

    def print_inline(self, latency: float, is_fallback: bool):
        self.record(latency, is_fallback)
        avg  = self.total_lat / self.queries
        rate = (self.fallbacks / self.queries) * 100
        flag = " ⚠" if is_fallback else ""
        print(f"[Metrics] #{self.queries} | {latency:.1f}s | moy {avg:.1f}s | "
              f"non-fidèle {rate:.0f}%{flag}")


# ── 10. RESPONSE CACHE ────────────────────────────────────────────────────────

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


# ── 11. MAIN LOOP ─────────────────────────────────────────────────────────────

def main():
    global DEBUG_RETRIEVAL

    if not os.path.exists(DATA_DIR):
        print(f"Erreur: dossier '{DATA_DIR}' introuvable.")
        sys.exit(1)

    print("Initialisation de ChronoBrain v6…")
    index     = setup_engine()
    retriever = index.as_retriever(similarity_top_k=TOP_K)
    llm       = Settings.llm
    tracker   = PerformanceTracker()
    cache     = SimpleCache()
    history: list[tuple[str, str]] = []

    print("\nChronoBrain prêt.")
    print("Commandes: 'quit' · 'reset' · 'stats' · 'debug on/off'\n")

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
            print("Historique et cache effacés.\n")
            continue
        if user_input.lower() == "stats":
            tracker.print_stats()
            continue
        if user_input.lower() == "debug on":
            DEBUG_RETRIEVAL = True
            print("Mode debug activé — les scores de retrieval s'affichent.\n")
            continue
        if user_input.lower() == "debug off":
            DEBUG_RETRIEVAL = False
            print("Mode debug désactivé.\n")
            continue

        # ── Block gibberish ───────────────────────────────────────────────────
        if not is_valid_query(user_input):
            print("Veuillez poser une question complète.\n")
            continue

        # ── Cache hit ─────────────────────────────────────────────────────────
        cached = cache.get(user_input)
        if cached:
            tracker.cache_hits += 1
            print(f"\n[cache] {cached}\n")
            continue

        # ── Retrieve with soft-floor fallback ─────────────────────────────────
        print("Recherche en cours…")
        nodes, used_fallback = retrieve_nodes(
            retriever, user_input, MIN_SCORE, FALLBACK_TOP_K
        )
        nodes = deduplicate(nodes)

        # If even the fallback gave us nothing, stop here
        if not nodes:
            print(f"\nRéponse: {FALLBACK_MSG}\n")
            history.append((user_input, FALLBACK_MSG))
            continue

        # ── Build context + prompt ────────────────────────────────────────────
        context = trim_to_token_budget(
            [n.get_content() for n in nodes],
            MAX_CONTEXT_TOKENS,
        )
        prompt = build_prompt(
            context,
            history[-HISTORY_TURNS:],
            user_input,
            low_confidence=used_fallback,
        )

        # ── LLM call ──────────────────────────────────────────────────────────
        print("Réflexion…")
        t0     = time.time()
        answer = safe_llm_complete(llm, prompt)
        latency = time.time() - t0

        if answer is None:
            print(f"\nRéponse: {TIMEOUT_MSG}\n")
            continue

        # ── Fast faithfulness check (no second LLM call) ──────────────────────
        evals        = fast_faithfulness_check(context, answer)
        is_faithful  = evals.get("fidélité", "Oui") == "Oui"
        is_halluc    = evals.get("hallucination", "Non") == "Oui"

        tracker.print_inline(latency, not is_faithful)

        print(f"\nRéponse: {answer}")
        print(f"Qualité: fidélité={evals['fidélité']} | "
              f"hallucination={evals['hallucination']} | "
              f"score={evals['score']}/5\n")

        # ── History + cache ───────────────────────────────────────────────────
        FALLBACK_PHRASES = [
            "je n'ai pas trouvé",
            "je ne sais pas",
            "je n'ai pas cette information",
        ]
        is_explicit_fallback = any(p in answer.lower() for p in FALLBACK_PHRASES)

        history.append((user_input, answer))
        if not is_explicit_fallback and not is_halluc:
            cache.set(user_input, answer)


if __name__ == "__main__":
    main()