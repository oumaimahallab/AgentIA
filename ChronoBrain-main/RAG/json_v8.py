"""
ChronoBrain JSON v7 — retrieval-first + metrics + anti-hallucination
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

What this version does vs your txt-based v6/v7:
- Ingestion reads pre-chunked *.json files (like data/cleaned/*_cleaned.json)
  Each JSON file contains a list[dict] with fields:
    chunk_id, source, start_time, end_time, start_sec, end_sec, text, ...
- Keeps your improvements:
  - soft-floor fallback (MIN_SCORE + fallback_top_k)
  - dedup
  - cache
  - input validation
  - debug retrieval scores
  - faithfulness overlap metric
  - hallucination sentence stripper
  - performance metrics (per question + aggregate stats)

Run:
  python RAG/chronobrain_json_v7.py
Commands:
  quit | reset | stats | debug on/off | bench

Bench mode runs a small fixed test set and prints aggregate metrics.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
import chromadb
from llama_index.core import Document, Settings, StorageContext, VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore

# ── 1. CONFIG ────────────────────────────────────────────────────────────────

# Directory containing chunked JSON files
DATA_DIR = "../data/cleaned"

# Chroma persistence
DB_PATH = "../data/chroma_json_v8"
COLLECTION = "chronobrain_json_docs"

LLM_MODEL = "llama3"  # switch to "llama3" if available for stronger instruction following
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

TOP_K = 8
MIN_SCORE = 0.30
FALLBACK_TOP_K = 2
MAX_CONTEXT_TOKENS = 900
HISTORY_TURNS = 2

LLM_TIMEOUT = 360.0
LLM_RETRIES = 1

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

HALLUCINATION_MARKERS = [
    r"il pourrait",
    r"il se pourrait",
    r"cela pourrait",
    r"bien que cela",
    r"bien qu'il",
    r"cela dépend",
    r"je suppose",
    r"probablement",
    r"en général",
    r"à titre indicatif",
    r"à noter que",
    r"il est possible que",
    r"selon les cas",
    r"n'est pas mentionné",
    r"n'est pas précisé",
    r"n'a pas été précisé",
]

logging.basicConfig(stream=sys.stdout, level=logging.WARNING, format="%(levelname)s | %(message)s")
log = logging.getLogger("chronobrain-json")

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
    if re.match(r"^(.)\1{3,}$", text.replace(" ", "")):
        return False
    return True


# ── 3. JSON LOADER ────────────────────────────────────────────────────────────

def load_all_json_chunks(data_dir: str) -> list[Document]:
    """
    Reads *.json files containing list[chunk].
    Each chunk becomes one Document(text=chunk["text"], metadata=...).
    """
    docs: list[Document] = []
    base = Path(data_dir)
    for path in base.rglob("*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception as e:
            log.warning("Skip JSON (parse error): %s (%s)", path.name, e)
            continue

        if not isinstance(raw, list):
            log.warning("Skip JSON (not a list): %s", path.name)
            continue

        for item in raw:
            if not isinstance(item, dict):
                continue
            text = (item.get("text") or "").strip()
            if not text:
                continue
            meta = {
                "chunk_id": item.get("chunk_id"),
                "source": item.get("source") or path.name,
                "start_time": item.get("start_time"),
                "end_time": item.get("end_time"),
                "start_sec": item.get("start_sec"),
                "end_sec": item.get("end_sec"),
                "word_count": item.get("word_count"),
                "has_asr_warning": item.get("has_asr_warning"),
                "json_file": path.name,
            }
            docs.append(Document(text=text, metadata=meta))

    log.warning("Total JSON chunks loaded: %d", len(docs))
    return docs


# ── 4. ENGINE SETUP ───────────────────────────────────────────────────────────

def setup_engine():
    Settings.llm = Ollama(model=LLM_MODEL, request_timeout=LLM_TIMEOUT)
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL)
    Settings.chunk_size = 99999
    Settings.chunk_overlap = 0

    db = chromadb.PersistentClient(path=DB_PATH)
    collection = db.get_or_create_collection(COLLECTION)
    vec_store = ChromaVectorStore(chroma_collection=collection)

    if collection.count() > 0:
        log.warning("ChromaDB: %d vectors already indexed — skipping ingestion.", collection.count())
        return VectorStoreIndex.from_vector_store(vec_store)

    docs = load_all_json_chunks(DATA_DIR)
    storage_ctx = StorageContext.from_defaults(vector_store=vec_store)
    return VectorStoreIndex.from_documents(docs, storage_context=storage_ctx, show_progress=True)


# ── 5. RETRIEVAL HELPERS ──────────────────────────────────────────────────────

def retrieve_nodes(retriever, query: str, min_score: float, fallback_k: int):
    raw_nodes = retriever.retrieve(query)

    if DEBUG_RETRIEVAL:
        print("\n[DEBUG] Retrieval scores:")
        for i, n in enumerate(raw_nodes):
            print(
                f"  [{i}] score={float(n.score or 0):.3f} | "
                f"{n.metadata.get('source','?')} [{n.metadata.get('start_time','')}] | "
                f"{n.get_content()[:80].replace(chr(10),' ')}…"
            )

    filtered = [n for n in raw_nodes if (n.score or 0) >= min_score]
    if filtered:
        return filtered, False, raw_nodes

    if raw_nodes:
        best = sorted(raw_nodes, key=lambda n: n.score or 0, reverse=True)[:fallback_k]
        log.warning(
            "Score filter removed all nodes (best=%.3f < %.2f) — using top-%d fallback",
            best[0].score or 0,
            min_score,
            fallback_k,
        )
        return best, True, raw_nodes

    return [], False, raw_nodes


def deduplicate(nodes, threshold: float = 0.92):
    kept = []
    for node in nodes:
        words_a = set(node.get_content().lower().split())
        is_dup = any(
            len(words_a & set(k.get_content().lower().split()))
            / max(1, min(len(words_a), len(set(k.get_content().lower().split()))))
            > threshold
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


# ── 6. HALLUCINATION STRIPPER ────────────────────────────────────────────────

def strip_hallucinations(answer: str) -> str:
    if not answer:
        return answer

    sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
    cleaned: list[str] = []
    for sentence in sentences:
        s = sentence.lower()
        has_marker = any(re.search(marker, s) for marker in HALLUCINATION_MARKERS)
        if not has_marker:
            cleaned.append(sentence)

    result = " ".join(cleaned).strip()
    if result and result[-1] not in ".!?»":
        last_punct = max(result.rfind("."), result.rfind("!"), result.rfind("?"))
        if last_punct > len(result) // 2:
            result = result[: last_punct + 1].strip()
    return result if result else FALLBACK_MSG


# ── 7. PROMPT BUILDER ─────────────────────────────────────────────────────────

def build_prompt(context: str, history: list[tuple[str, str]], question: str, low_confidence: bool, sources: list[str]) -> str:
    history_str = ""
    if history:
        history_str = "\n".join(f"Question précédente: {q}\nRéponse: {a}" for q, a in history) + "\n\n"

    confidence_note = (
        "\nATTENTION: Le contexte ci-dessous est de faible pertinence. Soyez très prudent et n'inventez rien.\n"
        if low_confidence
        else ""
    )

    srcs = ""
    if sources:
        srcs = "Sources: " + ", ".join(sorted(set(sources))[:6]) + ("\n" if len(set(sources)) <= 6 else ", ...\n")

    return (
        "Vous êtes ChronoBrain, l'assistant officiel de l'entreprise.\n"
        "Utilisez UNIQUEMENT les informations du contexte ci-dessous. N'utilisez JAMAIS vos connaissances générales.\n"
        "Vous pouvez citer la source sous la forme [Source: nom_du_fichier] en fin de réponse.\n"
        f"{confidence_note}"
        f"{srcs}\n"
        "Contexte:\n"
        "──────────────────────────────\n"
        f"{context}\n"
        "──────────────────────────────\n\n"
        f"{history_str}"
        "Instructions:\n"
        "1. Répondez exclusivement en français.\n"
        "2. Réponse directe, complète et concise.\n"
        "3. Si le contexte ne contient pas la réponse, répondez EXACTEMENT:\n"
        "   \"Je n'ai pas trouvé cette information dans les données de formation.\"\n"
        "4. N'inventez aucun fait, chiffre, règle ou définition.\n\n"
        f"Question: {question}\n"
        "Réponse: "
    )


# ── 8. FAITHFULNESS METRIC ───────────────────────────────────────────────────

def fast_faithfulness_check(context: str, answer: str) -> dict:
    fallback_indicators = [
        "je n'ai pas trouvé",
        "je ne sais pas",
        "je n'ai pas cette information",
        "aucune information",
    ]
    a = answer.lower()
    c = context.lower()
    if any(p in a for p in fallback_indicators):
        return {"fidélité": "Oui", "hallucination": "Non", "score": 3, "overlap": 1.0}

    answer_words = set(re.findall(r"\b\w{4,}\b", a))
    context_words = set(re.findall(r"\b\w{4,}\b", c))
    if not answer_words:
        return {"fidélité": "Inconnu", "hallucination": "Inconnu", "score": 0, "overlap": 0.0}
    overlap = len(answer_words & context_words) / len(answer_words)
    if overlap >= 0.20:
        return {"fidélité": "Oui", "hallucination": "Non", "score": min(5, max(1, int(overlap * 7))), "overlap": overlap}
    return {"fidélité": "Non", "hallucination": "Oui", "score": max(1, int(overlap * 4)), "overlap": overlap}


# ── 9. SAFE LLM CALL ─────────────────────────────────────────────────────────

def safe_llm_complete(llm, prompt: str, retries: int = LLM_RETRIES) -> Optional[str]:
    for attempt in range(retries + 1):
        try:
            return str(llm.complete(prompt)).strip()
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            if attempt < retries:
                time.sleep(2)
            else:
                return None
        except Exception:
            return None


# ── 10. METRICS ──────────────────────────────────────────────────────────────

@dataclass
class QueryMetrics:
    latency_s: float
    used_fallback_nodes: bool
    cache_hit: bool
    stripped: bool
    faithful: bool
    overlap: float
    top_score: float


class PerformanceTracker:
    def __init__(self):
        self.queries = 0
        self.total_lat = 0.0
        self.cache_hits = 0
        self.unfaithful = 0
        self.used_soft_fallback = 0
        self.stripped = 0
        self.sum_overlap = 0.0
        self.sum_top_score = 0.0

    def record(self, m: QueryMetrics):
        self.queries += 1
        self.total_lat += m.latency_s
        self.sum_overlap += m.overlap
        self.sum_top_score += m.top_score
        if m.cache_hit:
            self.cache_hits += 1
        if not m.faithful:
            self.unfaithful += 1
        if m.used_fallback_nodes:
            self.used_soft_fallback += 1
        if m.stripped:
            self.stripped += 1

    def print_inline(self, m: QueryMetrics):
        self.record(m)
        avg = self.total_lat / self.queries
        unfaith_rate = (self.unfaithful / self.queries) * 100
        cache_rate = (self.cache_hits / self.queries) * 100
        fb_rate = (self.used_soft_fallback / self.queries) * 100
        strip_rate = (self.stripped / self.queries) * 100
        print(
            f"[Metrics] #{self.queries} | {m.latency_s:.1f}s (avg {avg:.1f}s) | "
            f"cache {cache_rate:.0f}% | soft-fb {fb_rate:.0f}% | "
            f"non-fidèle {unfaith_rate:.0f}% | strip {strip_rate:.0f}% | "
            f"topScore {m.top_score:.2f} | overlap {m.overlap:.2f}"
        )

    def print_stats(self):
        if self.queries == 0:
            print("Aucune requête enregistrée.\n")
            return
        avg_lat = self.total_lat / self.queries
        print(
            "\n=== Aggregate Metrics ===\n"
            f"Queries:          {self.queries}\n"
            f"Avg latency:      {avg_lat:.2f}s\n"
            f"Cache hit rate:   {(self.cache_hits/self.queries)*100:.1f}%\n"
            f"Soft-fallback:    {(self.used_soft_fallback/self.queries)*100:.1f}%\n"
            f"Unfaithful rate:  {(self.unfaithful/self.queries)*100:.1f}%\n"
            f"Stripped rate:    {(self.stripped/self.queries)*100:.1f}%\n"
            f"Avg overlap:      {self.sum_overlap/self.queries:.3f}\n"
            f"Avg top score:    {self.sum_top_score/self.queries:.3f}\n"
        )


# ── 11. CACHE ────────────────────────────────────────────────────────────────

class SimpleCache:
    def __init__(self, maxsize: int = 64):
        self._cache: dict[str, str] = {}
        self._keys = deque(maxlen=maxsize)

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


def run_one(retriever, llm, tracker: PerformanceTracker, cache: SimpleCache, history: list[tuple[str, str]], user_input: str):
    # Cache
    cached = cache.get(user_input)
    if cached:
        m = QueryMetrics(latency_s=0.0, used_fallback_nodes=False, cache_hit=True, stripped=False, faithful=True, overlap=1.0, top_score=0.0)
        tracker.print_inline(m)
        print(f"\n[cache] {cached}\n")
        return cached

    # Retrieval
    nodes, used_fallback_nodes, raw_nodes = retrieve_nodes(retriever, user_input, MIN_SCORE, FALLBACK_TOP_K)
    nodes = deduplicate(nodes)
    if not nodes:
        m = QueryMetrics(latency_s=0.0, used_fallback_nodes=False, cache_hit=False, stripped=False, faithful=True, overlap=1.0, top_score=0.0)
        tracker.print_inline(m)
        print(f"\nRéponse: {FALLBACK_MSG}\n")
        history.append((user_input, FALLBACK_MSG))
        return FALLBACK_MSG

    # Metrics about retrieval quality
    raw_top_score = float(max((n.score or 0) for n in raw_nodes) if raw_nodes else 0.0)

    context = trim_to_token_budget([n.get_content() for n in nodes], MAX_CONTEXT_TOKENS)
    sources = [n.metadata.get("source", "unknown") for n in nodes]
    prompt = build_prompt(context, history[-HISTORY_TURNS:], user_input, used_fallback_nodes, sources)

    # LLM
    t0 = time.time()
    raw = safe_llm_complete(llm, prompt)
    latency = time.time() - t0
    if raw is None:
        m = QueryMetrics(latency_s=latency, used_fallback_nodes=used_fallback_nodes, cache_hit=False, stripped=False, faithful=True, overlap=0.0, top_score=raw_top_score)
        tracker.print_inline(m)
        print(f"\nRéponse: {TIMEOUT_MSG}\n")
        return TIMEOUT_MSG

    before = raw.strip()
    after = strip_hallucinations(before)
    was_stripped = after != before

    evals = fast_faithfulness_check(context, after)
    faithful = evals.get("fidélité") == "Oui" and evals.get("hallucination") == "Non"
    overlap = float(evals.get("overlap") or 0.0)

    m = QueryMetrics(
        latency_s=latency,
        used_fallback_nodes=used_fallback_nodes,
        cache_hit=False,
        stripped=was_stripped,
        faithful=faithful,
        overlap=overlap,
        top_score=raw_top_score,
    )
    tracker.print_inline(m)

    print(f"\nRéponse: {after}")
    print(f"Qualité: fidélité={evals['fidélité']} | hallucination={evals['hallucination']} | score={evals['score']}/5\n")

    history.append((user_input, after))
    if "je n'ai pas trouvé" not in after.lower() and faithful:
        cache.set(user_input, after)
    return after


def bench(retriever, llm, tracker: PerformanceTracker, cache: SimpleCache, history: list[tuple[str, str]]):
    tests = [
        "Comment les heures supplémentaires sont-elles calculées ?",
        "C'est quoi la règle B_HS ?",
        "Comment fonctionne le journal de workflow ?",
        "Qu'est-ce que WKF TRACE ?",
        "iiiiiiii",
        "eeee",
    ]
    print("\n[bench] Running test set…\n")
    for q in tests:
        print(f"[Q] {q}")
        if not is_valid_query(q):
            print("Veuillez poser une question complète.\n")
            continue
        run_one(retriever, llm, tracker, cache, history, q)
    tracker.print_stats()


def main():
    global DEBUG_RETRIEVAL

    if not os.path.exists(DATA_DIR):
        print(f"Erreur: dossier '{DATA_DIR}' introuvable.")
        sys.exit(1)

    print("Initialisation de ChronoBrain JSON v7…")
    index = setup_engine()
    retriever = index.as_retriever(similarity_top_k=TOP_K)
    llm = Settings.llm
    tracker = PerformanceTracker()
    cache = SimpleCache()
    history: list[tuple[str, str]] = []

    print("\nChronoBrain prêt.")
    print("Commandes: 'quit' · 'reset' · 'stats' · 'debug on/off' · 'bench'\n")

    while True:
        try:
            user_input = input("[ChronoBrain] Votre question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            break

        if not user_input:
            continue
        cmd = user_input.lower()
        if cmd == "quit":
            break
        if cmd == "reset":
            history.clear()
            cache._cache.clear()
            print("Historique et cache effacés.\n")
            continue
        if cmd == "stats":
            tracker.print_stats()
            continue
        if cmd == "bench":
            bench(retriever, llm, tracker, cache, history)
            continue
        if cmd == "debug on":
            DEBUG_RETRIEVAL = True
            print("Mode debug activé — scores de retrieval affichés.\n")
            continue
        if cmd == "debug off":
            DEBUG_RETRIEVAL = False
            print("Mode debug désactivé.\n")
            continue

        if not is_valid_query(user_input):
            print("Veuillez poser une question complète.\n")
            continue

        print("Recherche en cours…")
        run_one(retriever, llm, tracker, cache, history, user_input)


if __name__ == "__main__":
    main()

