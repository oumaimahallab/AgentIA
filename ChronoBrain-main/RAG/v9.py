"""
ChronoBrain v8 — Complete ready-to-run script
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REQUIREMENTS
  pip install llama-index llama-index-embeddings-huggingface
              llama-index-vector-stores-chroma llama-index-llms-ollama
              chromadb httpx sentence-transformers

OLLAMA SETUP (run BEFORE this script)
  1. Install Ollama from https://ollama.com
  2. In a terminal: ollama serve          ← keep this running
  3. In another terminal: ollama pull llama3

DATA
  Place your *_cleaned.json files in the folder set by DATA_DIR below.
  Each JSON must be a list of dicts with at minimum a "text" field.
  The cleaned.json files you already have work perfectly.

RUN
  python chronobrain_v8.py

COMMANDS (at the prompt)
  quit        → exit
  reset       → clear history and cache
  stats       → print aggregate metrics
  debug on/off → show/hide retrieval scores
  bench       → run built-in test questions
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Check dependencies early ──────────────────────────────────────────────────
try:
    import httpx
    import chromadb
    from llama_index.core import Document, Settings, StorageContext, VectorStoreIndex
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from llama_index.llms.ollama import Ollama
    from llama_index.vector_stores.chroma import ChromaVectorStore
except ImportError as e:
    print(f"\n[ERROR] Missing dependency: {e}")
    print("\nInstall everything with:")
    print("  pip install llama-index llama-index-embeddings-huggingface "
          "llama-index-vector-stores-chroma llama-index-llms-ollama "
          "chromadb httpx sentence-transformers\n")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# 1. CONFIGURATION  ← edit these paths to match your setup
# ══════════════════════════════════════════════════════════════════════════════

# Folder that contains your *_cleaned.json files
DATA_DIR = "../data/cleaned"

# Where ChromaDB stores its vectors (created automatically)
DB_PATH  = "./data/chroma_v9"

# Ollama model — llama3 gives the best grounding
# fallback: "phi3" / "qwen2:1.5b" if llama3 is not pulled yet
LLM_MODEL   = "llama3"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

# Retrieval
TOP_K          = 8
MIN_SCORE      = 0.30
FALLBACK_TOP_K = 2
DEDUP_THRESH   = 0.92

# Context & history
MAX_CONTEXT_TOKENS = 900
HISTORY_TURNS      = 2

# LLM
LLM_TIMEOUT = 120.0
LLM_RETRIES = 1

# Input validation
MIN_ALPHA_RATIO = 0.6
MIN_QUERY_WORDS = 2

# ── Messages ──────────────────────────────────────────────────────────────────
FALLBACK_MSG = (
    "Je n'ai pas trouve d'informations pertinentes dans les donnees "
    "de formation pour repondre a cette question."
)
TIMEOUT_MSG = (
    "Le modele met trop de temps a repondre. "
    "Veuillez reessayer ou simplifier votre question."
)
OLLAMA_DOWN_MSG = (
    "\n[ERREUR] Impossible de joindre Ollama (connexion refusee).\n"
    "Assurez-vous qu'Ollama tourne en arriere-plan :\n"
    "  1. Ouvrez un terminal separe\n"
    "  2. Lancez : ollama serve\n"
    "  3. Relancez ce script\n"
)

# ── Hallucination / hedging markers (French) ──────────────────────────────────
HALLUCINATION_MARKERS = [
    r"il pourrait",
    r"il se pourrait",
    r"cela pourrait",
    r"bien que cela",
    r"bien qu'il",
    r"cela depend",
    r"je suppose",
    r"probablement",
    r"en general",
    r"a titre indicatif",
    r"a noter que",
    r"il est possible que",
    r"selon les cas",
    r"n'est pas mentionne",
    r"n'est pas precise",
    r"n'a pas ete precise",
    r"n'est pas disponible",
    r"ces informations ne sont pas",
    r"bien que l'exacte procedure",
]

logging.basicConfig(stream=sys.stdout, level=logging.WARNING,
                    format="%(levelname)s | %(message)s")
log = logging.getLogger("chronobrain")

DEBUG_RETRIEVAL = False


# ══════════════════════════════════════════════════════════════════════════════
# 2. INPUT VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# 3. DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_all_json_chunks(data_dir: str) -> list[Document]:
    docs: list[Document] = []
    base = Path(data_dir)
    json_files = list(base.rglob("*.json"))

    if not json_files:
        log.warning("No JSON files found in %s", data_dir)
        return docs

    for path in json_files:
        try:
            raw = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception as e:
            log.warning("Skip (parse error): %s -- %s", path.name, e)
            continue

        if not isinstance(raw, list):
            log.warning("Skip (not a list): %s", path.name)
            continue

        file_chunks = 0
        for item in raw:
            if not isinstance(item, dict):
                continue
            text = (item.get("text") or "").strip()
            if not text:
                continue
            meta = {
                "chunk_id":        str(item.get("chunk_id", "")),
                "source":          str(item.get("source") or path.name),
                "start_time":      str(item.get("start_time", "")),
                "end_time":        str(item.get("end_time", "")),
                "start_sec":       item.get("start_sec"),
                "end_sec":         item.get("end_sec"),
                "word_count":      item.get("word_count"),
                "has_asr_warning": bool(item.get("has_asr_warning", False)),
                "json_file":       path.name,
            }
            docs.append(Document(text=text, metadata=meta))
            file_chunks += 1

        print(f"  + {path.name} -- {file_chunks} chunks")

    print(f"\nTotal chunks loaded: {len(docs)}")
    return docs


# ══════════════════════════════════════════════════════════════════════════════
# 4. ENGINE SETUP
# ══════════════════════════════════════════════════════════════════════════════

def setup_engine():
    print(f"\nChargement du modele d'embedding ({EMBED_MODEL})...")
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL)

    print(f"Connexion a Ollama (modele: {LLM_MODEL})...")
    Settings.llm = Ollama(model=LLM_MODEL, request_timeout=LLM_TIMEOUT)

    Settings.chunk_size    = 99_999
    Settings.chunk_overlap = 0

    db         = chromadb.PersistentClient(path=DB_PATH)
    collection = db.get_or_create_collection("chronobrain_docs")
    vec_store  = ChromaVectorStore(chroma_collection=collection)

    if collection.count() > 0:
        print(f"ChromaDB: {collection.count()} vecteurs deja indexes -- chargement rapide.")
        return VectorStoreIndex.from_vector_store(vec_store)

    print(f"\nPremiere execution -- indexation depuis '{DATA_DIR}' ...")
    docs = load_all_json_chunks(DATA_DIR)
    if not docs:
        print(f"\n[ATTENTION] Aucun document trouve dans '{DATA_DIR}'.")
        sys.exit(1)

    print("\nCreation des embeddings et indexation dans ChromaDB...")
    storage_ctx = StorageContext.from_defaults(vector_store=vec_store)
    index = VectorStoreIndex.from_documents(
        docs, storage_context=storage_ctx, show_progress=True
    )
    print(f"Indexation terminee -- {collection.count()} vecteurs stockes.\n")
    return index


# ══════════════════════════════════════════════════════════════════════════════
# 5. RETRIEVAL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def retrieve_nodes(retriever, query: str, min_score: float, fallback_k: int):
    raw_nodes = retriever.retrieve(query)

    if DEBUG_RETRIEVAL:
        print("\n[DEBUG] Scores de retrieval:")
        for i, n in enumerate(raw_nodes):
            print(
                f"  [{i}] score={float(n.score or 0):.3f} | "
                f"{n.metadata.get('source','?')} [{n.metadata.get('start_time','')}] | "
                f"{n.get_content()[:80].replace(chr(10),' ')}..."
            )

    filtered = [n for n in raw_nodes if (n.score or 0) >= min_score]
    if filtered:
        return filtered, False, raw_nodes

    if raw_nodes:
        best = sorted(raw_nodes, key=lambda n: n.score or 0, reverse=True)[:fallback_k]
        log.warning(
            "Score filter: best=%.3f < %.2f -- soft fallback top-%d",
            best[0].score or 0, min_score, fallback_k,
        )
        return best, True, raw_nodes

    return [], False, raw_nodes


def deduplicate(nodes, threshold: float = DEDUP_THRESH):
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


# ══════════════════════════════════════════════════════════════════════════════
# 6. HALLUCINATION STRIPPER
# ══════════════════════════════════════════════════════════════════════════════

def strip_hallucinations(answer: str) -> str:
    if not answer:
        return answer

    sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
    cleaned   = []
    for sentence in sentences:
        s = sentence.lower()
        if not any(re.search(marker, s) for marker in HALLUCINATION_MARKERS):
            cleaned.append(sentence)

    result = " ".join(cleaned).strip()

    if result and result[-1] not in ".!?":
        last_punct = max(result.rfind("."), result.rfind("!"), result.rfind("?"))
        if last_punct > len(result) // 2:
            result = result[: last_punct + 1].strip()

    return result if result else FALLBACK_MSG


# ══════════════════════════════════════════════════════════════════════════════
# 7. PROMPT BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_prompt(
    context: str,
    history: list[tuple[str, str]],
    question: str,
    low_confidence: bool,
    sources: list[str],
) -> str:
    history_str = ""
    if history:
        history_str = (
            "\n".join(f"Question precedente: {q}\nReponse: {a}" for q, a in history)
            + "\n\n"
        )

    confidence_note = (
        "\nATTENTION: Le contexte ci-dessous est de faible pertinence. "
        "Si vous n'etes pas certain, repondez: "
        "\"Je n'ai pas trouve cette information dans les donnees de formation.\"\n"
        if low_confidence else ""
    )

    srcs = ""
    if sources:
        unique = sorted(set(sources))
        srcs = "Sources: " + ", ".join(unique[:6]) + "\n"

    return (
        "Vous etes ChronoBrain, l'assistant officiel de l'entreprise.\n"
        "Utilisez UNIQUEMENT les informations du contexte ci-dessous.\n"
        "N'utilisez JAMAIS vos connaissances generales.\n\n"
        f"{confidence_note}"
        f"{srcs}\n"
        "Contexte:\n"
        "------------------------------\n"
        f"{context}\n"
        "------------------------------\n\n"
        f"{history_str}"
        "Instructions:\n"
        "1. Repondez exclusivement en francais.\n"
        "2. Reponse directe, complete et structuree (utilisez des points numerotes si necessaire).\n"
        "3. Si le contexte ne contient pas la reponse, repondez EXACTEMENT:\n"
        "   \"Je n'ai pas trouve cette information dans les donnees de formation.\"\n"
        "4. N'inventez aucun fait, chiffre, regle ou definition.\n"
        "5. Citez la source avec [Source: nom_du_fichier] en fin de reponse.\n\n"
        f"Question: {question}\n"
        "Reponse: "
    )


# ══════════════════════════════════════════════════════════════════════════════
# 8. FAITHFULNESS CHECK
# ══════════════════════════════════════════════════════════════════════════════

def fast_faithfulness_check(context: str, answer: str) -> dict:
    fallback_indicators = [
        "je n'ai pas trouve",
        "je ne sais pas",
        "je n'ai pas cette information",
        "aucune information",
    ]
    a = answer.lower()
    c = context.lower()

    if any(p in a for p in fallback_indicators):
        return {"fidelite": "Oui", "hallucination": "Non", "score": 3, "overlap": 1.0}

    answer_words  = set(re.findall(r"\b\w{4,}\b", a))
    context_words = set(re.findall(r"\b\w{4,}\b", c))

    if not answer_words:
        return {"fidelite": "Inconnu", "hallucination": "Inconnu", "score": 0, "overlap": 0.0}

    overlap = len(answer_words & context_words) / len(answer_words)

    if overlap >= 0.20:
        return {
            "fidelite": "Oui",
            "hallucination": "Non",
            "score": min(5, max(1, int(overlap * 7))),
            "overlap": overlap,
        }
    return {
        "fidelite": "Non",
        "hallucination": "Oui",
        "score": max(1, int(overlap * 4)),
        "overlap": overlap,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 9. SAFE LLM CALL
# ══════════════════════════════════════════════════════════════════════════════

def safe_llm_complete(llm, prompt: str, retries: int = LLM_RETRIES) -> Optional[str]:
    for attempt in range(retries + 1):
        try:
            return str(llm.complete(prompt)).strip()
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            if attempt < retries:
                time.sleep(2)
            else:
                return None
        except httpx.ConnectError:
            print(OLLAMA_DOWN_MSG)
            return None
        except Exception as e:
            log.warning("LLM error: %s", e)
            if "10061" in str(e) or "refused" in str(e).lower():
                print(OLLAMA_DOWN_MSG)
            return None

# ══════════════════════════════════════════════════════════════════════════════
# 10. METRICS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class QueryMetrics:
    latency_s:           float
    used_fallback_nodes: bool
    cache_hit:           bool
    stripped:            bool
    faithful:            bool
    overlap:             float
    top_score:           float


@dataclass
class PerformanceTracker:
    queries:            int   = field(default=0)
    total_lat:          float = field(default=0.0)
    cache_hits:         int   = field(default=0)
    unfaithful:         int   = field(default=0)
    used_soft_fallback: int   = field(default=0)
    stripped:           int   = field(default=0)
    sum_overlap:        float = field(default=0.0)
    sum_top_score:      float = field(default=0.0)

    def record(self, m: QueryMetrics):
        self.queries        += 1
        self.total_lat      += m.latency_s
        self.sum_overlap    += m.overlap
        self.sum_top_score  += m.top_score
        if m.cache_hit:            self.cache_hits         += 1
        if not m.faithful:         self.unfaithful         += 1
        if m.used_fallback_nodes:  self.used_soft_fallback += 1
        if m.stripped:             self.stripped           += 1

    def print_inline(self, m: QueryMetrics):
        self.record(m)
        avg          = self.total_lat / self.queries
        unfaith_rate = (self.unfaithful         / self.queries) * 100
        cache_rate   = (self.cache_hits          / self.queries) * 100
        fb_rate      = (self.used_soft_fallback  / self.queries) * 100
        strip_rate   = (self.stripped            / self.queries) * 100
        print(
            f"[Metrics] #{self.queries} | {m.latency_s:.1f}s (moy {avg:.1f}s) | "
            f"cache {cache_rate:.0f}% | soft-fb {fb_rate:.0f}% | "
            f"non-fidele {unfaith_rate:.0f}% | strip {strip_rate:.0f}% | "
            f"topScore {m.top_score:.2f} | overlap {m.overlap:.2f}"
        )

    def print_stats(self):
        if self.queries == 0:
            print("Aucune requete enregistree.\n")
            return
        avg = self.total_lat / self.queries
        print(
            "\n=== Metriques agregees ===\n"
            f"Requetes totales  : {self.queries}\n"
            f"Latence moyenne   : {avg:.2f}s\n"
            f"Cache hit rate    : {(self.cache_hits/self.queries)*100:.1f}%\n"
            f"Soft-fallback     : {(self.used_soft_fallback/self.queries)*100:.1f}%\n"
            f"Non-fidele        : {(self.unfaithful/self.queries)*100:.1f}%\n"
            f"Strips            : {(self.stripped/self.queries)*100:.1f}%\n"
            f"Overlap moyen     : {self.sum_overlap/self.queries:.3f}\n"
            f"Top-score moyen   : {self.sum_top_score/self.queries:.3f}\n"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 11. CACHE
# ══════════════════════════════════════════════════════════════════════════════

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

    def clear(self):
        self._cache.clear()
        self._keys.clear()


# ══════════════════════════════════════════════════════════════════════════════
# 12. CORE QUERY HANDLER
# ══════════════════════════════════════════════════════════════════════════════

def run_one(
    retriever,
    llm,
    tracker: PerformanceTracker,
    cache: SimpleCache,
    history: list[tuple[str, str]],
    user_input: str,
) -> str:
    cached = cache.get(user_input)
    if cached:
        m = QueryMetrics(0.0, False, True, False, True, 1.0, 0.0)
        tracker.print_inline(m)
        print(f"\n[cache] {cached}\n")
        return cached

    nodes, used_fallback, raw_nodes = retrieve_nodes(
        retriever, user_input, MIN_SCORE, FALLBACK_TOP_K
    )
    nodes = deduplicate(nodes)

    if not nodes:
        m = QueryMetrics(0.0, False, False, False, True, 1.0, 0.0)
        tracker.print_inline(m)
        print(f"\nReponse: {FALLBACK_MSG}\n")
        history.append((user_input, FALLBACK_MSG))
        return FALLBACK_MSG

    raw_top_score = float(
        max((n.score or 0) for n in raw_nodes) if raw_nodes else 0.0
    )

    context = trim_to_token_budget(
        [n.get_content() for n in nodes], MAX_CONTEXT_TOKENS
    )
    sources = [n.metadata.get("source", "unknown") for n in nodes]
    prompt  = build_prompt(
        context, history[-HISTORY_TURNS:], user_input, used_fallback, sources
    )

    t0      = time.time()
    raw     = safe_llm_complete(llm, prompt)
    latency = time.time() - t0

    if raw is None:
        m = QueryMetrics(latency, used_fallback, False, False, True, 0.0, raw_top_score)
        tracker.print_inline(m)
        print(f"\nReponse: {TIMEOUT_MSG}\n")
        return TIMEOUT_MSG

    before       = raw.strip()
    after        = strip_hallucinations(before)
    was_stripped = after != before

    evals    = fast_faithfulness_check(context, after)
    faithful = evals["fidelite"] == "Oui" and evals["hallucination"] == "Non"
    overlap  = float(evals.get("overlap") or 0.0)

    m = QueryMetrics(latency, used_fallback, False, was_stripped, faithful, overlap, raw_top_score)
    tracker.print_inline(m)

    print(f"\nReponse: {after}")
    print(
        f"Qualite: fidelite={evals['fidelite']} | "
        f"hallucination={evals['hallucination']} | "
        f"score={evals['score']}/5\n"
    )

    history.append((user_input, after))
    if "je n'ai pas trouve" not in after.lower() and faithful:
        cache.set(user_input, after)

    return after


# ══════════════════════════════════════════════════════════════════════════════
# 13. BENCH MODE
# ══════════════════════════════════════════════════════════════════════════════

BENCH_QUESTIONS = [
    "Comment les heures supplementaires sont-elles calculees ?",
    "C'est quoi la regle B_HS ?",
    "Comment fonctionne le journal de workflow ?",
    "Qu'est-ce que WKF TRACE ?",
    "Comment creer un client principal ?",
    "iiiiiiii",
    "eeee",
]

def bench(retriever, llm, tracker, cache, history):
    print("\n[bench] Lancement des questions de test...\n")
    for q in BENCH_QUESTIONS:
        print(f"[Q] {q}")
        if not is_valid_query(q):
            print("-> Requete invalide (bloquee par la validation).\n")
            continue
        run_one(retriever, llm, tracker, cache, history, q)
    tracker.print_stats()


# ══════════════════════════════════════════════════════════════════════════════
# 14. MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    global DEBUG_RETRIEVAL

    if not os.path.exists(DATA_DIR):
        print(f"\n[ERREUR] Dossier de donnees introuvable: '{DATA_DIR}'")
        print("Creez le dossier et placez-y vos fichiers *_cleaned.json:")
        print(f"  mkdir -p {DATA_DIR}")
        sys.exit(1)

    json_files = list(Path(DATA_DIR).rglob("*.json"))
    if not json_files:
        print(f"\n[ERREUR] Aucun fichier .json trouve dans '{DATA_DIR}'")
        print("Copiez vos fichiers *_cleaned.json dans ce dossier.")
        sys.exit(1)

    print("\n" + "=" * 55)
    print("  ChronoBrain v8 -- Assistant formation Chronotime")
    print("=" * 55)

    index     = setup_engine()
    retriever = index.as_retriever(similarity_top_k=TOP_K)
    llm       = Settings.llm
    tracker   = PerformanceTracker()
    cache     = SimpleCache()
    history:  list[tuple[str, str]] = []

    print("\nChronoBrain est pret.")
    print("Commandes: quit | reset | stats | debug on/off | bench\n")

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
            print("Au revoir.")
            break
        if cmd == "reset":
            history.clear()
            cache.clear()
            print("Historique et cache effaces.\n")
            continue
        if cmd == "stats":
            tracker.print_stats()
            continue
        if cmd == "bench":
            bench(retriever, llm, tracker, cache, history)
            continue
        if cmd == "debug on":
            DEBUG_RETRIEVAL = True
            print("Mode debug active.\n")
            continue
        if cmd == "debug off":
            DEBUG_RETRIEVAL = False
            print("Mode debug desactive.\n")
            continue

        if not is_valid_query(user_input):
            print("Veuillez poser une question complete (minimum 2 mots).\n")
            continue

        print("Recherche en cours...")
        run_one(retriever, llm, tracker, cache, history, user_input)


if __name__ == "__main__":
    main()