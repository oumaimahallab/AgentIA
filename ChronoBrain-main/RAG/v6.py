"""
ChronoBrain v5 — Production-ready, all bugs fixed
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fixes over the broken v5:
  ✦ Restored gap+word semantic chunker (was reverted to naive batch-of-5)
  ✦ Restored is_valid_query() — blocks gibberish before LLM
  ✦ Prompt now hard-forbids outside knowledge ("N'utilisez que le contexte")
  ✦ safe_llm_complete() has retry + timeout guard (was removed)
  ✦ Evaluation prompt is now stricter and JSON-only
  ✦ Metrics tracker only fires on real LLM answers (not on early exits)
  ✦ Idempotent index: skips re-ingestion if ChromaDB already has data
"""

import os
import sys
import re
import time
import hashlib
import json
import logging
from collections import OrderedDict, deque
from pathlib import Path
from typing import Optional, Iterable, Any

import httpx
from llama_index.core import VectorStoreIndex, StorageContext, Settings, Document
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

# ── 1. CONFIGURATION ──────────────────────────────────────────────────────────

APP_DIR = Path(__file__).resolve().parent
REPO_DIR = APP_DIR.parent

def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v is not None and v.strip() else default

# Defaults are repo-relative (stable on Windows), but overridable via env vars.
DATA_DIR    = _env("CHRONOBRAIN_DATA_DIR", str(REPO_DIR / "data" / "transcripts"))
DB_PATH     = _env("CHRONOBRAIN_DB_PATH", str(REPO_DIR / "data" / "chroma_v66"))
LLM_MODEL   = _env("CHRONOBRAIN_LLM_MODEL", "phi3")
EMBED_MODEL = _env("CHRONOBRAIN_EMBED_MODEL", "BAAI/bge-small-en-v1.5")

TOP_K              = 6       # retrieve more, filter down
MIN_SCORE          = 0.45    # blocks out-of-domain answers
MAX_CONTEXT_TOKENS = 1800    # ~7200 chars max to LLM
HISTORY_TURNS      = 3
LLM_TIMEOUT        = 360.0
LLM_RETRIES        = 1

# Input validation
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


# ── 2. INPUT VALIDATION ───────────────────────────────────────────────────────

def is_valid_query(text: str) -> bool:
    """
    Blocks gibberish before it reaches the retriever or LLM.
    Rejects: 'aaaa', 'rrrrr', '????', single words, mostly numeric strings.
    """
    words = text.split()
    if len(words) < MIN_QUERY_WORDS:
        return False
    alpha = sum(c.isalpha() for c in text)
    total = len(text.replace(" ", ""))
    if total == 0 or alpha / total < MIN_ALPHA_RATIO:
        return False
    # Block repeated-character runs: 'aaaa', 'rrrrrr'
    if re.match(r'^(.)\1{3,}$', text.replace(" ", "")):
        return False
    return True


# ── 3. SEMANTIC TIMESTAMP CHUNKER ─────────────────────────────────────────────
#
# FIX: restored gap+word logic (was broken back to naive batch-of-5 in v5).
# Lines: [83:13 -> 83:14] C'est souvent manager direct.
# Merges consecutive short lines into ~80-word semantic units.
# Breaks on natural pause (>3s gap) OR when word budget is reached.

def parse_transcript(filepath: str) -> list[Document]:
    CHUNK_WORDS = 80
    MAX_GAP_SEC = 3.0
    pattern = re.compile(r"\[(\d+):(\d+)\s*->\s*(\d+):(\d+)\]\s*(.*)")

    segments: list[tuple[float, float, str]] = []
    with open(filepath, encoding="utf-8", errors="replace") as f:
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
                    with open(path, encoding="utf-8", errors="replace") as f:
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

    db         = chromadb.PersistentClient(path=str(DB_PATH))
    collection = db.get_or_create_collection("chronobrain_docs")
    vec_store  = ChromaVectorStore(chroma_collection=collection)

    # Skip re-ingestion if already indexed
    if collection.count() > 0:
        log.warning("ChromaDB already has %d vectors — skipping ingestion.", collection.count())
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

def score_filter(nodes, min_score: float):
    nodes = list(nodes)
    good = [n for n in nodes if float(getattr(n, "score", 0) or 0) >= min_score]
    dropped = len(nodes) - len(good)
    if dropped:
        log.debug("Score filter: dropped %d/%d (min=%.2f, kept: %s)",
                  dropped, len(nodes), min_score,
                  [f"{n.score:.3f}" for n in good])
    return good


def deduplicate(nodes, threshold: float = 0.92):
    def word_set(text: str) -> set[str]:
        return set(re.findall(r"\w+", text.lower()))

    kept: list[Any] = []
    kept_sets: list[set[str]] = []
    for node in nodes:
        words_a = word_set(node.get_content())
        is_dup = False
        for words_b in kept_sets:
            overlap = len(words_a & words_b) / max(1, min(len(words_a), len(words_b)))
            if overlap > threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(node)
            kept_sets.append(words_a)
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
# FIX: added "N'utilisez jamais de connaissances extérieures" to stop the LLM
# from answering geography/general-knowledge questions from its training data.

def build_prompt(context: str, history: list[tuple[str, str]], question: str) -> str:
    history_str = ""
    if history:
        history_str = "\n".join(
            f"Question précédente: {q}\nRéponse: {a}" for q, a in history
        ) + "\n\n"

    return (
        "Vous êtes ChronoBrain, l'assistant officiel de l'entreprise. "
        "Utilisez UNIQUEMENT les informations du contexte ci-dessous. "
        "N'utilisez JAMAIS vos connaissances générales ou extérieures au contexte.\n\n"
        f"Contexte extrait des formations:\n"
        f"──────────────────────────────\n"
        f"{context}\n"
        f"──────────────────────────────\n\n"
        f"{history_str}"
        "Instructions:\n"
        "1. Répondez exclusivement en français.\n"
        "2. Réponse directe, complète et concise.\n"
        "3. Ne citez pas les horodatages.\n"
        "4. Si le contexte ne contient pas la réponse, répondez EXACTEMENT: "
        "\"Je n'ai pas trouvé cette information dans les données de formation.\"\n"
        "5. N'inventez aucun fait, chiffre, règle ou définition.\n\n"
        f"Question: {question}\n"
        "Réponse: "
    )


# ── 7. SAFE LLM CALL WITH RETRY ──────────────────────────────────────────────
# FIX: restored retry + exception handling (was a bare try/except in v5).

def safe_llm_complete(llm, prompt: str, retries: int = LLM_RETRIES) -> Optional[str]:
    for attempt in range(retries + 1):
        try:
            return str(llm.complete(prompt)).strip()
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException):
            if attempt < retries:
                log.warning("Timeout (attempt %d/%d), retry in 2s…", attempt + 1, retries + 1)
                time.sleep(2)
            else:
                log.warning("LLM failed after %d attempts.", retries + 1)
                return None
        except Exception as e:
            log.warning("LLM error: %s", e)
            return None


# ── 8. LLM-AS-JUDGE EVALUATION ───────────────────────────────────────────────
# FIX: prompt is now stricter and JSON-only; parse is more defensive.

JUDGE_PROMPT = """\
Tu es un évaluateur strict. Analyse la réponse du chatbot.

Contexte utilisé:
{context}

Réponse du chatbot:
{answer}

Évalue selon ces critères:
- fidélité: La réponse est-elle basée UNIQUEMENT sur le contexte? (Oui/Non)
- hallucination: La réponse contient-elle des informations absentes du contexte? (Oui/Non)
- score: Note globale de 1 (mauvais) à 5 (excellent)

Réponds UNIQUEMENT en JSON valide, sans aucun texte autour:
{{"fidélité": "Oui/Non", "hallucination": "Oui/Non", "score": N}}"""


def evaluate_response(llm, context: str, answer: str) -> dict:
    prompt = JUDGE_PROMPT.format(context=context[:1500], answer=answer)
    try:
        raw = str(llm.complete(prompt)).strip()
        # Be defensive: the judge may wrap JSON in prose or markdown fences.
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise ValueError("No JSON object found")
        return json.loads(m.group(0))
    except Exception as e:
        log.debug("Judge parse error: %s", e)
        return {"fidélité": "Inconnu", "hallucination": "Inconnu", "score": 0}


# ── 9. METRICS TRACKER ───────────────────────────────────────────────────────
# FIX: only tracks real LLM answers, not early-exit fallbacks.

class PerformanceTracker:
    def __init__(self):
        self.queries   = 0
        self.total_lat = 0.0
        self.fallbacks = 0

    def record(self, latency: float, is_fallback: bool):
        self.queries   += 1
        self.total_lat += latency
        if is_fallback:
            self.fallbacks += 1
        avg = self.total_lat / self.queries
        rate = (self.fallbacks / self.queries) * 100
        print(f"\n[Metrics] {self.queries} réponses | "
              f"Latence moy: {avg:.1f}s | "
              f"Taux non-fidèle: {rate:.0f}%")

    def summary(self) -> str:
        if self.queries == 0:
            return "Aucune requête enregistrée."
        avg = self.total_lat / self.queries
        rate = (self.fallbacks / self.queries) * 100
        return (
            f"Total: {self.queries} | "
            f"Latence moy: {avg:.1f}s | "
            f"Non-fidèle: {self.fallbacks} ({rate:.0f}%)"
        )


# ── 10. RESPONSE CACHE ────────────────────────────────────────────────────────

class SimpleCache:
    def __init__(self, maxsize: int = 64):
        self._cache: "OrderedDict[str, str]" = OrderedDict()
        self._maxsize = maxsize

    def _key(self, text: str) -> str:
        return hashlib.md5(text.lower().strip().encode()).hexdigest()

    def get(self, q: str) -> Optional[str]:
        k = self._key(q)
        v = self._cache.get(k)
        if v is None:
            return None
        # LRU: mark as most recent
        self._cache.move_to_end(k)
        return v

    def set(self, q: str, a: str):
        k = self._key(q)
        self._cache[k] = a
        self._cache.move_to_end(k)
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)


# ── 11. MAIN LOOP ─────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(DATA_DIR):
        print(f"Erreur: dossier '{DATA_DIR}' introuvable.")
        sys.exit(1)

    print("Initialisation de ChronoBrain v5…")
    index     = setup_engine()
    retriever = index.as_retriever(similarity_top_k=TOP_K)
    llm       = Settings.llm
    tracker   = PerformanceTracker()
    cache     = SimpleCache()
    history: list[tuple[str, str]] = []

    print("\nChronoBrain prêt.")
    print("Commandes: 'quit' · 'reset' (efface historique) · 'stats' (métriques)\n")

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
            print(tracker.summary() + "\n")
            continue

        # ── Block gibberish immediately ───────────────────────────────────────
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
            log.debug("  [%d] %.3f | %s [%s] | %s…",
                      i, n.score or 0,
                      n.metadata.get("source", "?"),
                      n.metadata.get("start_time", ""),
                      n.get_content()[:60].replace("\n", " "))

        # ── Early exit: nothing relevant found ────────────────────────────────
        if not nodes:
            print(f"\nRéponse: {FALLBACK_MSG}\n")
            history.append((user_input, FALLBACK_MSG))
            continue

        # ── Build context + prompt ────────────────────────────────────────────
        context = trim_to_token_budget(
            [n.get_content() for n in nodes],
            MAX_CONTEXT_TOKENS,
        )
        prompt = build_prompt(context, history[-HISTORY_TURNS:], user_input)

        # ── LLM call (safe, with retry) ───────────────────────────────────────
        print("Réflexion…")
        start = time.time()
        answer = safe_llm_complete(llm, prompt)
        latency = time.time() - start

        if answer is None:
            print(f"\nRéponse: {TIMEOUT_MSG}\n")
            continue

        # ── Evaluate with LLM-as-judge ────────────────────────────────────────
        evals = evaluate_response(llm, context, answer)
        is_hallucination = evals.get("hallucination", "Non").lower() == "oui"
        is_unfaithful    = evals.get("fidélité", "Oui").lower() == "non"
        is_fallback      = is_hallucination or is_unfaithful

        tracker.record(latency, is_fallback)

        print(f"\nRéponse: {answer}")
        print(f"Qualité: fidélité={evals.get('fidélité','?')} | "
              f"hallucination={evals.get('hallucination','?')} | "
              f"score={evals.get('score','?')}/5\n")

        # ── Update history + cache ────────────────────────────────────────────
        FALLBACK_PHRASES = [
            "je n'ai pas trouvé",
            "je ne sais pas",
            "je n'ai pas cette information",
        ]
        is_explicit_fallback = any(p in answer.lower() for p in FALLBACK_PHRASES)

        history.append((user_input, answer))
        if not is_explicit_fallback and not is_hallucination:
            cache.set(user_input, answer)


if __name__ == "__main__":
    main()