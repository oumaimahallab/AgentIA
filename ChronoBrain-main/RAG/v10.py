"""
ChronoBrain v10 — Debugged & Production-hardened
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REQUIREMENTS
  pip install llama-index llama-index-embeddings-huggingface
              llama-index-vector-stores-chroma llama-index-llms-ollama
              chromadb httpx sentence-transformers langdetect rank-bm25

OLLAMA
  ollama serve          ← keep running in background
  ollama pull llama3

DATA
  Place *_cleaned.txt files in DATA_DIR.

RUN
  python chronobrain_v10.py
  python chronobrain_v10.py --debug     # show retrieval scores
  python chronobrain_v10.py --rebuild   # force re-index

COMMANDS
  quit | reset | stats | debug on/off | bench
"""

from __future__ import annotations

import hashlib, logging, os, pickle, re, sys, time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Dependency check ──────────────────────────────────────────────────────────
try:
    import httpx
    import chromadb
    import numpy as np
    from langdetect import detect as _langdetect
    from rank_bm25 import BM25Okapi
    from llama_index.core import Document, Settings, StorageContext, VectorStoreIndex
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from llama_index.llms.ollama import Ollama
    from llama_index.vector_stores.chroma import ChromaVectorStore
except ImportError as e:
    print(f"\n[ERROR] Missing dependency: {e}")
    print("pip install llama-index llama-index-embeddings-huggingface "
          "llama-index-vector-stores-chroma llama-index-llms-ollama "
          "chromadb httpx sentence-transformers langdetect rank-bm25\n")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# 1. CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

DATA_DIR  = "../data/cleaned_txt"
DB_PATH   = "../data/chroma_v10"
BM25_PATH = "../data/chroma_v10/bm25_v10.pkl"

# FIX #1: Use llama3 (much better instruction-following than phi3)
LLM_MODEL   = "llama3"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

# Retrieval
TOP_K              = 8
#MIN_SCORE          = 0.28    # FIX #2: lowered — BGE on spoken French scores 0.25-0.40
MIN_SCORE = 0.50  # Raise this significantly

FALLBACK_TOP_K     = 2
DEDUP_THRESH       = 0.90
BM25_WEIGHT        = 0.30    # hybrid fusion weight for keyword search
SEMANTIC_WEIGHT    = 0.70

# Context & history
MAX_CONTEXT_TOKENS = 1200    # FIX #3: raised from 900 — Llama3 handles 4k easily
HISTORY_TURNS      = 2

# FIX #4: LLM hyperparameters — these are the core hallucination controls
LLM_TEMPERATURE    = 0.05    # near-zero: forces the model to stick to context
LLM_TOP_P          = 0.85    # nucleus sampling — ignore low-prob tokens
LLM_MAX_TOKENS     = 1024    # enough for a detailed structured answer
LLM_TIMEOUT        = 240.0   # FIX #5: raised — Llama3 locally needs 180-300s
LLM_RETRIES        = 1

# FIX #6: Data quality filters — applied at load time
MIN_CHUNK_WORDS    = 15      # drop chunks shorter than this
REQUIRED_LANGUAGE  = "fr"    # drop non-French chunks (catches English ASR errors)

# Input validation
MIN_QUERY_WORDS = 2
MIN_ALPHA_RATIO = 0.6

# FIX #7: Faithfulness check — raised threshold (0.20 was too permissive)
MIN_OVERLAP_RATIO = 0.28

# Messages
FALLBACK_MSG = (
    "Je n'ai pas trouvé d'informations pertinentes dans les données "
    "de formation pour répondre à cette question."
)
TIMEOUT_MSG = (
    "Le modèle met trop de temps à répondre. "
    "Veuillez réessayer ou simplifier votre question."
)
OLLAMA_DOWN_MSG = (
    "\n[ERREUR] Impossible de joindre Ollama.\n"
    "Lancez: ollama serve    (dans un terminal séparé)\n"
    "Puis:   ollama pull llama3\n"
)

# Hallucination / hedging markers
HALLUCINATION_MARKERS = [
    r"il pourrait", r"il se pourrait", r"cela pourrait",
    r"bien que cela", r"bien qu[''']il", r"cela d[eé]pend",
    r"je suppose", r"probablement", r"[àa] titre indicatif",
    r"il est possible que", r"selon les cas",
    r"n[''']est pas mentionn[eé]", r"n[''']est pas pr[eé]cis[eé]",
    r"n[''']a pas [eé]t[eé] pr[eé]cis[eé]", r"n[''']est pas disponible",
    r"ces informations.*ne sont pas", r"bien que l[''']exacte proc[eé]dure",
    r"je ne suis pas s[uû]r", r"je ne suis pas certain",
    r"il faudrait v[eé]rifier",
]
_HALLUC_RE = re.compile("|".join(HALLUCINATION_MARKERS), re.IGNORECASE)

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
# 3. DATA LOADING WITH QUALITY FILTERS
# ══════════════════════════════════════════════════════════════════════════════

# FIX #8: Noise patterns that should never reach the LLM
_NOISE_PATTERNS = re.compile(
    r"^("
    r"allô\s*[?!]?|"                          # phone noise
    r"sous-titres r[eé]alis[eé]s.*|"          # subtitle watermarks
    r"excusez-moi.*|"                         # interruption fillers
    r"oui[,.]?\s*$|non[,.]?\s*$|"            # back-channel (already filtered)
    r"d['']accord[,.]?\s*$|"
    r"merci[,.]?\s*$|au revoir[,.]?\s*$|"
    r"ici[,]?\s*$|"                           # single isolated word
    r"bon app[eé]tit.*"                       # end-of-session noise
    r")$",
    re.IGNORECASE,
)

def _is_noise_chunk(text: str, word_count: int) -> bool:
    """Return True if this chunk should be excluded from the index."""
    if word_count < MIN_CHUNK_WORDS:
        return True
    if _NOISE_PATTERNS.match(text.strip()):
        return True
    return False

def _detect_language(text: str) -> str:
    """Detect language of a text chunk. Returns ISO 639-1 code."""
    try:
        # Only check the first 200 chars for speed
        return _langdetect(text[:200])
    except Exception:
        return "fr"  # assume French on failure

# ══════════════════════════════════════════════════════════════════════════════
# 3. DATA LOADING (Updated for .txt)
# ══════════════════════════════════════════════════════════════════════════════

def load_all_txt_chunks(data_dir: str) -> tuple[list[Document], list[dict]]:
    """Loads plain text files and returns (Documents, raw_dicts for BM25)."""
    docs = []
    raw_dicts = []
    
    for path in Path(data_dir).glob("*.txt"):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                # Matches clean text lines (no timestamp metadata)
                text = line.strip()
                if not text:
                    continue
                
                meta = {
                    "source": path.name,
                    "chunk_id": hashlib.md5(text.encode()).hexdigest()[:10]
                }
                docs.append(Document(text=text, metadata=meta))
                raw_dicts.append({"text": text, "chunk_id": meta["chunk_id"]})
                
    return docs, raw_dicts
# ══════════════════════════════════════════════════════════════════════════════
# 4. BM25 INDEX  (keyword search — critical for technical terms)
# ══════════════════════════════════════════════════════════════════════════════

def _tokenize_fr(text: str) -> list[str]:
    """French-aware tokeniser for BM25."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return [t for t in text.split() if len(t) > 1]

def build_bm25(raw_chunks: list[dict]) -> BM25Okapi:
    tokenized = [_tokenize_fr(c["text"]) for c in raw_chunks]
    return BM25Okapi(tokenized)

def save_bm25(bm25: BM25Okapi, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(bm25, f)

def load_bm25(path: str) -> Optional[BM25Okapi]:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return pickle.load(f)



# ══════════════════════════════════════════════════════════════════════════════
# 5. ENGINE SETUP (Updated for .txt)
# ══════════════════════════════════════════════════════════════════════════════

def setup_engine(force_rebuild: bool = False):
    print(f"\nChargement du modèle d'embedding ({EMBED_MODEL})...")
    Settings.embed_model  = HuggingFaceEmbedding(model_name=EMBED_MODEL)
    Settings.chunk_size   = 99_999
    Settings.chunk_overlap = 0

    db         = chromadb.PersistentClient(path=DB_PATH)
    collection = db.get_or_create_collection("chronobrain_v10")
    vec_store  = ChromaVectorStore(chroma_collection=collection)

    bm25_index  = None
    raw_chunks: list[dict] = []

    if collection.count() > 0 and not force_rebuild:
        print(f"ChromaDB: {collection.count()} vecteurs chargés.")
        index      = VectorStoreIndex.from_vector_store(vec_store)
        bm25_index = load_bm25(BM25_PATH)
    else:
        if force_rebuild and collection.count() > 0:
            db.delete_collection("chronobrain_v10")
            collection = db.get_or_create_collection("chronobrain_v10")
            vec_store  = ChromaVectorStore(chroma_collection=collection)

        print(f"\nIndexation depuis '{DATA_DIR}'...")
        docs, raw_chunks = load_all_txt_chunks(DATA_DIR) # <--- Using updated loader

        if not docs:
            print(f"[ERREUR] Aucun document valide trouvé dans '{DATA_DIR}'")
            sys.exit(1)

        storage_ctx = StorageContext.from_defaults(vector_store=vec_store)
        index = VectorStoreIndex.from_documents(docs, storage_context=storage_ctx, show_progress=True)

        print("Construction de l'index BM25...")
        bm25_index = build_bm25(raw_chunks) # <--- Now receives the list[dict]
        save_bm25(bm25_index, BM25_PATH)

    return index, bm25_index, raw_chunks


# ══════════════════════════════════════════════════════════════════════════════
# 6. HYBRID RETRIEVAL  (FAISS/ChromaDB semantic + BM25 keyword)
# ══════════════════════════════════════════════════════════════════════════════

def _bm25_search(bm25: BM25Okapi, raw_chunks: list[dict],
                 query: str, top_k: int) -> list[tuple[int, float]]:
    """
    Return top_k (index, normalised_score) pairs from BM25.
    Critical for technical terms: B_HS, RESP2, PRTEFF, APDEM etc.
    """
    if bm25 is None or not raw_chunks:
        return []
    tokens     = _tokenize_fr(query)
    raw_scores = np.array(bm25.get_scores(tokens))
    max_s      = raw_scores.max()
    if max_s <= 0:
        return []
    norm_scores = raw_scores / max_s
    top_idx     = np.argsort(norm_scores)[::-1][:top_k]
    return [(int(i), float(norm_scores[i])) for i in top_idx]

def retrieve_hybrid(retriever, bm25: Optional[BM25Okapi],
                    raw_chunks: list[dict], query: str,
                    min_score: float, fallback_k: int,
                    debug: bool = False):
    """
    1. ChromaDB semantic search
    2. BM25 keyword search (if index available)
    3. Fuse scores: final = 0.70*semantic + 0.30*bm25
    4. Filter by min_score, deduplicate, soft-fallback
    Returns (nodes_or_dicts, used_fallback)
    """
    # ── Semantic retrieval ────────────────────────────────────────────────────
    raw_nodes = retriever.retrieve(query)

    # Build score map: chunk_id → (node, semantic_score)
    sem_map: dict[str, tuple] = {}
    for n in raw_nodes:
        cid = n.metadata.get("chunk_id") or n.get_content()[:40]
        sem_map[cid] = (n, float(n.score or 0))

    # ── BM25 keyword retrieval ────────────────────────────────────────────────
    bm25_scores: dict[str, float] = {}
    if bm25 is not None and raw_chunks:
        bm25_results = _bm25_search(bm25, raw_chunks, query, TOP_K * 2)
        for idx, score in bm25_results:
            if idx < len(raw_chunks):
                cid = raw_chunks[idx].get("chunk_id", "")
                bm25_scores[cid] = score

    # ── Fuse scores ───────────────────────────────────────────────────────────
    all_cids = set(sem_map) | set(bm25_scores)
    fused: dict[str, tuple] = {}  # cid → (node_or_none, fused_score)

    for cid in all_cids:
        sem_s   = sem_map.get(cid, (None, 0.0))[1]
        bm25_s  = bm25_scores.get(cid, 0.0)
        final_s = SEMANTIC_WEIGHT * sem_s + BM25_WEIGHT * bm25_s

        node = sem_map.get(cid, (None,))[0]
        fused[cid] = (node, final_s)

    # ── Sort by fused score ───────────────────────────────────────────────────
    ranked = sorted(fused.values(), key=lambda x: -x[1])

    if debug:
        print("\n[DEBUG] Hybrid scores (top 10):")
        for node, score in ranked[:10]:
            if node:
                src = node.metadata.get("source", "?")
                t   = node.metadata.get("start_time", "")
                print(f"  {score:.3f} | {src} [{t}] | "
                      f"{node.get_content()[:70].replace(chr(10), ' ')}…")

    # ── Score filter ──────────────────────────────────────────────────────────
    filtered = [(n, s) for n, s in ranked if s >= min_score and n is not None]

    used_fallback = False
    if not filtered:
        # Keep top-N with any score
        filtered = [(n, s) for n, s in ranked[:fallback_k] if n is not None]
        used_fallback = bool(filtered)
        if used_fallback:
            log.warning("Soft fallback: best fused score=%.3f < %.2f",
                        ranked[0][1] if ranked else 0, min_score)

    # ── MMR deduplication ─────────────────────────────────────────────────────
    kept:  list[tuple] = []
    for node, score in filtered:
        words_a = set(node.get_content().lower().split())
        is_dup  = any(
            len(words_a & set(k.get_content().lower().split())) /
            max(1, min(len(words_a), len(set(k.get_content().lower().split())))) > DEDUP_THRESH
            for k, _ in kept
        )
        if not is_dup:
            kept.append((node, score))

    return kept, used_fallback


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
# 7. HALLUCINATION STRIPPER
# ══════════════════════════════════════════════════════════════════════════════

def strip_hallucinations(answer: str) -> str:
    if not answer:
        return answer
    sentences = re.split(r"(?<=[.!?»])\s+", answer.strip())
    cleaned   = [s for s in sentences if not _HALLUC_RE.search(s.lower())]
    result    = " ".join(cleaned).strip()
    if result and result[-1] not in ".!?»":
        last = max(result.rfind("."), result.rfind("!"), result.rfind("?"))
        if last > len(result) // 2:
            result = result[: last + 1].strip()
    return result if result else FALLBACK_MSG


# ══════════════════════════════════════════════════════════════════════════════
# 8. PROMPT BUILDER  (rewritten — key fix for answer quality)
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# 8. PROMPT BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_prompt(
    nodes_with_scores: list[tuple],
    history:    list[tuple[str, str]],
    question:   str,
    low_conf:   bool,
) -> str:
    """
    Prompt simplified: No extractions metadata, just the raw knowledge.
    """
    # Simply join the text content of the retrieved nodes
    context_str = "\n\n".join([node.get_content() for node, _ in nodes_with_scores])

    # Trim to token budget
    char_budget = MAX_CONTEXT_TOKENS * 4
    if len(context_str) > char_budget:
        context_str = context_str[:char_budget] + "…"

    history_str = ""
    if history:
        lines = []
        for q, a in history[-HISTORY_TURNS:]:
            lines.append(f"[Tour précédent]\nQ: {q}\nR: {a}")
        history_str = "\n\n".join(lines) + "\n\n"

    low_conf_note = (
        "\n⚠ AVERTISSEMENT: Si tu n'es pas certain à 100%, réponds exactement: "
        "\"Je n'ai pas trouvé cette information dans les données de formation.\"\n"
    ) if low_conf else ""

    system = (
        f"Tu es ChronoBrain, l'expert technique de la solution Chronotime (CTIME) chez Inetum.\n"
        f"CONTEXTE: Les informations fournies sont des transcriptions de sessions de formation "
        f"internes enregistrées. Ces réunions expliquent le fonctionnement réel de la plateforme "
        f"pour les employés d'Inetum.\n"
        f"RÈGLE ABSOLUE: Tu réponds UNIQUEMENT en utilisant les détails techniques et "
        f"les procédures explicitées dans ces transcriptions de formation.\n\n"
        f"TON STYLE:\n"
        f"- Ton professionnel, didactique et orienté solution.\n"
        f"- Utilise un format Markdown structuré (Titres #, sous-titres ##, gras **).\n"
        f"- Pour les procédures, utilise des étapes numérotées claires (Étape 1, Étape 2...).\n"
        f"- Utilise des émojis pertinents (✅, ℹ️, 👉) pour aérer la lecture.\n"
        f"- Si une question porte sur une manipulation, donne le cheminement exact évoqué dans la formation.\n\n"
        f"INTERDICTIONS:\n"
        f"- Ne mentionne jamais que ce sont des 'transcriptions de réunions'.\n"
        f"- Ne cite pas les noms des fichiers sources.\n"
        f"- N'utilise pas tes connaissances générales sur Chronotime si ce n'est pas dans les extraits.\n"
        f"- Bannis les formulations vagues : 'cela dépend', 'probablement', 'il est possible que'.\n\n"
        f"FALLBACK: Si l'information est absente, réponds EXACTEMENT: "
        f"\"Je n'ai pas trouvé cette information dans les données de formation.\""
    )

    user = (
        f"{low_conf_note}"
        f"BASE DE CONNAISSANCES:\n"
        f"{'─'*50}\n"
        f"{context_str}\n"
        f"{'─'*50}\n\n"
        f"{history_str}"
        f"QUESTION: {question}\n\n"
        f"Fournis une réponse structurée, formatée en Markdown, et basée UNIQUEMENT sur la base de connaissances ci-dessus."
    )

    return f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n{system}<|eot_id|>" \
           f"<|start_header_id|>user<|end_header_id|>\n{user}<|eot_id|>" \
           f"<|start_header_id|>assistant<|end_header_id|>\n"

# ══════════════════════════════════════════════════════════════════════════════
# 9. FAITHFULNESS CHECK
# ══════════════════════════════════════════════════════════════════════════════

def fast_faithfulness_check(context: str, question: str, answer: str) -> dict:
    """
    FIX #12: Improved faithfulness check
    - Ignores French stop words in overlap calculation
    - Combines context overlap + question relevance
    - Raised threshold from 0.20 to 0.28
    """
    FRENCH_STOPWORDS = {
        "le", "la", "les", "un", "une", "des", "du", "de", "à", "au", "aux",
        "et", "ou", "mais", "donc", "car", "pour", "dans", "sur", "avec",
        "vous", "nous", "ils", "elle", "que", "qui", "dont", "quand",
        "comme", "plus", "très", "bien", "tout", "faire", "être", "avoir",
        "cette", "cela", "voilà", "alors", "aussi", "même",
    }

    EXPLICIT_FALLBACK = [
        "je n'ai pas trouvé", "je ne sais pas",
        "je n'ai pas cette information", "aucune information",
    ]

    a_low = answer.lower()
    if any(p in a_low for p in EXPLICIT_FALLBACK):
        return {"fidélité": "Oui", "hallucination": "Non", "score": 3, "overlap": 1.0}

    def _meaningful_words(text: str) -> set[str]:
        return {w for w in re.findall(r"\b\w{4,}\b", text.lower())
                if w not in FRENCH_STOPWORDS}

    answer_words  = _meaningful_words(answer)
    context_words = _meaningful_words(context)
    question_words = _meaningful_words(question)

    if not answer_words:
        return {"fidélité": "Inconnu", "hallucination": "Inconnu", "score": 0, "overlap": 0.0}

    ctx_overlap = len(answer_words & context_words) / len(answer_words)
    q_overlap   = len(answer_words & question_words) / max(1, len(question_words))
    combined    = 0.75 * ctx_overlap + 0.25 * q_overlap

    if combined >= MIN_OVERLAP_RATIO:
        return {"fidélité": "Oui", "hallucination": "Non",
                "score": min(5, max(1, int(combined * 8))), "overlap": combined}
    return {"fidélité": "Non", "hallucination": "Oui",
            "score": max(1, int(combined * 4)), "overlap": combined}


# ══════════════════════════════════════════════════════════════════════════════
# 10. SAFE LLM CALL  (direct Ollama with explicit hyperparameters)
# ══════════════════════════════════════════════════════════════════════════════

def safe_llm_complete(prompt: str, retries: int = LLM_RETRIES) -> Optional[str]:
    """
    FIX #13: Direct Ollama call with explicit temperature/top_p/max_tokens.
    LlamaIndex's Settings.llm.complete() doesn't cleanly expose all params.
    Using the ollama library directly gives full control.
    """
    import ollama as _ollama
    for attempt in range(retries + 1):
        try:
            response = _ollama.generate(
                model   = LLM_MODEL,
                prompt  = prompt,
                options = {
                    "temperature":   LLM_TEMPERATURE,   # 0.05 — stays on context
                    "top_p":         LLM_TOP_P,          # 0.85 — nucleus sampling
                    "num_predict":   LLM_MAX_TOKENS,     # max output tokens
                    "repeat_penalty": 1.1,               # discourages repetition loops
                    "stop": ["<|eot_id|>", "[INST]"],    # Llama3 stop tokens
                },
            )
            return response["response"].strip()

        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            if attempt < retries:
                log.warning("Timeout (essai %d/%d), retry dans 3s…",
                            attempt + 1, retries + 1)
                time.sleep(3)
            else:
                log.warning("LLM échec après %d essais.", retries + 1)
                return None

        except httpx.ConnectError:
            print(OLLAMA_DOWN_MSG)
            return None

        except Exception as e:
            log.warning("LLM erreur: %s", e)
            if "10061" in str(e) or "refused" in str(e).lower():
                print(OLLAMA_DOWN_MSG)
            return None
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 11. METRICS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PerformanceTracker:
    queries:     int   = field(default=0)
    total_lat:   float = field(default=0.0)
    cache_hits:  int   = field(default=0)
    unfaithful:  int   = field(default=0)
    soft_fb:     int   = field(default=0)
    stripped:    int   = field(default=0)
    sum_overlap: float = field(default=0.0)

    def record(self, latency: float, faithful: bool, cache_hit: bool,
               used_fb: bool, stripped: bool, overlap: float) -> None:
        self.queries    += 1
        self.total_lat  += latency
        self.sum_overlap += overlap
        if cache_hit:       self.cache_hits  += 1
        if not faithful:    self.unfaithful  += 1
        if used_fb:         self.soft_fb     += 1
        if stripped:        self.stripped    += 1

    def print_inline(self, latency: float, faithful: bool, cache_hit: bool,
                     used_fb: bool, stripped: bool, overlap: float) -> None:
        self.record(latency, faithful, cache_hit, used_fb, stripped, overlap)
        avg   = self.total_lat / max(1, self.queries)
        flags = ""
        if used_fb:    flags += " [fallback]"
        if stripped:   flags += " [stripped]"
        if not faithful: flags += " [⚠ unfaithful]"
        if cache_hit:  flags += " [cache]"
        print(f"[Metrics] #{self.queries} | {latency:.1f}s (moy {avg:.1f}s) | "
              f"overlap={overlap:.2f}{flags}")

    def print_stats(self) -> None:
        if self.queries == 0:
            print("Aucune requête.\n"); return
        avg = self.total_lat / self.queries
        print(
            f"\n[Stats] {self.queries} requêtes | latence moy {avg:.1f}s | "
            f"cache {self.cache_hits} | non-fidèle {self.unfaithful} | "
            f"fallback {self.soft_fb} | stripped {self.stripped} | "
            f"overlap moy {self.sum_overlap/self.queries:.3f}\n"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 12. CACHE
# ══════════════════════════════════════════════════════════════════════════════

class SimpleCache:
    def __init__(self, maxsize: int = 64):
        self._cache: dict[str, str] = {}
        self._keys  = deque(maxlen=maxsize)

    def _key(self, t: str) -> str:
        return hashlib.md5(t.lower().strip().encode()).hexdigest()

    def get(self, q: str) -> Optional[str]:
        return self._cache.get(self._key(q))

    def set(self, q: str, a: str) -> None:
        k = self._key(q)
        if k not in self._cache:
            if len(self._keys) == self._keys.maxlen:
                self._cache.pop(self._keys[0], None)
            self._keys.append(k)
        self._cache[k] = a

    def clear(self) -> None:
        self._cache.clear(); self._keys.clear()


# ══════════════════════════════════════════════════════════════════════════════
# 13. BENCH
# ══════════════════════════════════════════════════════════════════════════════

BENCH_QUESTIONS = [
    # Technical questions that require exact keyword matching (test BM25)
    "Qu'est-ce que la règle B_HS et à quoi sert-elle ?",
    "Quels sont les éléments obligatoires à livrer avec un motif d'absence ?",
    "Comment les heures supplémentaires sont-elles calculées ?",
    "Quelles sont les étapes du moteur pour calculer les HSS en fin de semaine ?",
    # Habilitations questions (test semantic retrieval)
    "Comment configurer les habilitations d'un utilisateur dans Chronotime ?",
    "Qu'est-ce qu'un profil utilisateur et comment est-il construit ?",
    "À quoi sert la configuration de navigation dans Chronotime ?",
    # Robustness tests
    "iiiiiiii",    # should be blocked by validator
    "C'est quoi la capitale du Maroc ?",  # out-of-domain, should return FALLBACK_MSG
]

def run_bench(retriever, bm25, raw_chunks, tracker, cache, history):
    print("\n[bench] Questions de test...\n")
    for q in BENCH_QUESTIONS:
        print(f"[Q] {q}")
        if not is_valid_query(q):
            print("→ Requête invalide (bloquée).\n"); continue
        run_one(retriever, bm25, raw_chunks, tracker, cache, history, q)
    tracker.print_stats()


# ══════════════════════════════════════════════════════════════════════════════
# 14. CORE QUERY HANDLER
# ══════════════════════════════════════════════════════════════════════════════

def run_one(retriever, bm25, raw_chunks, tracker, cache, history, user_input) -> str:
    # Cache hit
    cached = cache.get(user_input)
    if cached:
        tracker.print_inline(0.0, True, True, False, False, 1.0)
        print(f"\n[cache] {cached}\n")
        return cached

    # Hybrid retrieval
    nodes_scores, used_fb = retrieve_hybrid(
        retriever, bm25, raw_chunks, user_input,
        MIN_SCORE, FALLBACK_TOP_K, debug=DEBUG_RETRIEVAL
    )

    if not nodes_scores:
        tracker.print_inline(0.0, True, False, False, False, 1.0)
        print(f"\nRéponse: {FALLBACK_MSG}\n")
        history.append((user_input, FALLBACK_MSG))
        return FALLBACK_MSG

    # Build context + prompt
    context    = "\n\n".join(n.get_content() for n, _ in nodes_scores)
    context    = trim_to_token_budget([n.get_content() for n, _ in nodes_scores],
                                      MAX_CONTEXT_TOKENS)
    prompt     = build_prompt(nodes_scores, history[-HISTORY_TURNS:],
                              user_input, used_fb)

    # LLM call
    print("Réflexion…")
    t0      = time.time()
    raw     = safe_llm_complete(prompt)
    latency = time.time() - t0

    if raw is None:
        print(f"\nRéponse: {TIMEOUT_MSG}\n")
        return TIMEOUT_MSG

    # Post-processing
    before       = raw
    after        = strip_hallucinations(raw)
    was_stripped = after != before

    # Faithfulness
    faith    = fast_faithfulness_check(context, user_input, after)
    faithful = faith["fidélité"] == "Oui"
    overlap  = float(faith.get("overlap", 0))

    tracker.print_inline(latency, faithful, False, used_fb, was_stripped, overlap)

    print(f"\nRéponse:\n{after}")
    print(f"\n[Qualité] fidélité={faith['fidélité']} | "
          f"hallucination={faith['hallucination']} | "
          f"score={faith['score']}/5\n")

    # Update state
    FALLBACK_PHRASES = ["je n'ai pas trouvé", "je ne sais pas"]
    is_fallback_ans  = any(p in after.lower() for p in FALLBACK_PHRASES)
    history.append((user_input, after))
    if not is_fallback_ans and faithful:
        cache.set(user_input, after)

    return after


# ══════════════════════════════════════════════════════════════════════════════
# 15. MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    global DEBUG_RETRIEVAL

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug",   action="store_true", help="Show retrieval scores")
    parser.add_argument("--rebuild", action="store_true", help="Force full re-index")
    args = parser.parse_args()
    DEBUG_RETRIEVAL = args.debug

    if not os.path.exists(DATA_DIR):
        print(f"\n[ERREUR] Dossier de données introuvable: '{DATA_DIR}'")
        print(f"  mkdir -p {DATA_DIR}  puis placez vos *_cleaned.txt ici.")
        sys.exit(1)

    print("\n" + "═" * 55)
    print("  ChronoBrain v10 — Assistant formation Chronotime")
    print("═" * 55)

    index, bm25, raw_chunks = setup_engine(force_rebuild=args.rebuild)
    retriever = index.as_retriever(similarity_top_k=TOP_K)

    if bm25 is not None:
        print(f"✓ Hybrid retrieval (semantic + BM25 sur {len(raw_chunks)} chunks)")
    else:
        print("⚠ BM25 non disponible — semantic uniquement (relancer avec --rebuild)")

    tracker = PerformanceTracker()
    cache   = SimpleCache()
    history: list[tuple[str, str]] = []

    print("\nChronoBrain prêt.")
    print("Commandes: quit | reset | stats | debug on/off | bench\n")

    while True:
        try:
            user_input = input("[ChronoBrain] Votre question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir."); break

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd == "quit":
            break
        if cmd == "reset":
            history.clear(); cache.clear()
            print("Historique et cache effacés.\n"); continue
        if cmd == "stats":
            tracker.print_stats(); continue
        if cmd == "bench":
            run_bench(retriever, bm25, raw_chunks, tracker, cache, history); continue
        if cmd == "debug on":
            DEBUG_RETRIEVAL = True;  print("Debug activé.\n");   continue
        if cmd == "debug off":
            DEBUG_RETRIEVAL = False; print("Debug désactivé.\n"); continue

        if not is_valid_query(user_input):
            print("Veuillez poser une question complète (minimum 2 mots).\n"); continue

        print("Recherche en cours…")
        run_one(retriever, bm25, raw_chunks, tracker, cache, history, user_input)


if __name__ == "__main__":
    main()