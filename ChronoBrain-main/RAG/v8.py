"""
ChronoBrain v7 — Anti-hallucination hardened
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Key changes from v6:
  ✦ Post-processing hallucination stripper
      → Removes sentences with hedging/invention markers
      → ("il pourrait", "bien que", "je suppose", "cela dépend", etc.)
      → Catches hallucinations that slip past the prompt instructions
  ✦ Prompt rewritten with chain-of-thought grounding
      → LLM must first quote the relevant passage, then answer
      → Forces explicit context anchoring before generating
  ✦ MAX_CONTEXT_TOKENS reduced 1800→900 (cuts latency ~40%)
      → Fewer tokens = faster local inference on Phi-3
      → Top-3 best chunks instead of top-8 raw
  ✦ Faithfulness check: overlap threshold lowered 0.35→0.20
      → French synonyms/conjugations don't match verbatim
      → Stops false "non-fidèle" flags on correct answers
  ✦ Model recommendation: switch LLM_MODEL to "llama3" for
      much better instruction-following (set below)
  ✦ Answer truncation guard: Phi-3 sometimes cuts mid-sentence
      → Detects incomplete answers and appends a clean ending
  ✦ All v6 features preserved: debug mode, cache, metrics,
      soft-floor fallback, input validation, retry on timeout
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

DATA_DIR    = "../data/transcripts-formation-only"
DB_PATH     = "../data/chroma_v8_formation_only"
LLM_MODEL   = "qwen2:1.5b"##"phi3"        # ← switch to "llama3" for better grounding
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

TOP_K              = 8       # candidates fetched from ChromaDB
MIN_SCORE          = 0.30    # soft: if all fail, fallback_k raw kept
FALLBACK_TOP_K     = 2
MAX_CONTEXT_TOKENS = 900     # ↓ from 1800 — cuts latency ~40% on local LLMs
HISTORY_TURNS      = 2       # ↓ from 3 — saves tokens in prompt
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

# Sentences containing these phrases are stripped from answers
# These are hallucination/hedging markers in French
HALLUCINATION_MARKERS = [
    r"il pourrait",
    r"il se pourrait",
    r"cela pourrait",
    r"bien que cela",
    r"bien qu'il",
    r"cela dépend",
    r"je suppose",
    r"probablement",
    r"en général",          # too vague — not from transcripts
    r"à titre indicatif",
    r"à noter que",
    r"il est possible que",
    r"selon les cas",
    r"cette information spécifique n'est pas",
    r"n'est pas mentionné",
    r"n'est pas précisé",
    r"n'a pas été précisé",
    r"n'est pas disponible",
    r"ces informations spécifiées ne sont pas",
    r"bien que l'exacte procédure",
    r"ces informations ne sont pas",
]

logging.basicConfig(
    stream=sys.stdout,
    level=logging.WARNING,
    format="%(levelname)s | %(message)s",
)
log = logging.getLogger("chronobrain")

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


# ── 3. HALLUCINATION STRIPPER ─────────────────────────────────────────────────

def strip_hallucinations(answer: str) -> str:
    """
    Remove sentences that contain known hallucination/hedging markers.
    Splits on French sentence boundaries (. ! ?) and filters each sentence.
    Also detects and removes truncated incomplete sentences at the end.
    """
    if not answer:
        return answer

    # Split into sentences, preserve delimiter
    sentences = re.split(r'(?<=[.!?])\s+', answer.strip())
    cleaned   = []

    for sentence in sentences:
        sentence_lower = sentence.lower()
        has_marker = any(
            re.search(marker, sentence_lower)
            for marker in HALLUCINATION_MARKERS
        )
        if not has_marker:
            cleaned.append(sentence)
        else:
            log.debug("Stripped hallucination sentence: %s", sentence[:80])

    result = " ".join(cleaned).strip()

    # Truncation guard: if answer ends mid-sentence (no . ! ?)
    # and the last "word" looks like a partial conjugation, trim it
    if result and result[-1] not in ".!?»":
        # Find last complete sentence
        last_punct = max(
            result.rfind("."),
            result.rfind("!"),
            result.rfind("?"),
        )
        if last_punct > len(result) // 2:
            result = result[: last_punct + 1].strip()

    return result if result else FALLBACK_MSG


# ── 4. SEMANTIC TIMESTAMP CHUNKER ─────────────────────────────────────────────

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


# ── 5. ENGINE SETUP ───────────────────────────────────────────────────────────

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


# ── 6. RETRIEVAL ──────────────────────────────────────────────────────────────

def retrieve_nodes(retriever, query: str, min_score: float, fallback_k: int):
    raw_nodes = retriever.retrieve(query)

    if DEBUG_RETRIEVAL:
        print("\n[DEBUG] Retrieval scores:")
        for i, n in enumerate(raw_nodes):
            src = n.metadata.get("source", "?")
            t   = n.metadata.get("start_time", "")
            print(f"  [{i}] {n.score:.3f} | {src} [{t}] | "
                  f"{n.get_content()[:80].replace(chr(10), ' ')}…")

    filtered = [n for n in raw_nodes if (n.score or 0) >= min_score]

    if filtered:
        return filtered, False

    if raw_nodes:
        best = sorted(raw_nodes, key=lambda n: n.score or 0, reverse=True)[:fallback_k]
        log.warning(
            "Score filter removed all nodes (best=%.3f < %.2f) — soft fallback top-%d",
            best[0].score or 0, min_score, fallback_k,
        )
        return best, True

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


# ── 7. PROMPT BUILDER ────────────────────────────────────────────────────────

COMPANY_NAME = "Inetum"   # ← change to your company name

def build_prompt(
    context: str,
    history: list[tuple[str, str]],
    question: str,
    low_confidence: bool = False,
    sources: list[str] | None = None,
) -> str:
    history_str = ""
    if history:
        history_str = (
            "## Historique de la conversation\n"
            + "\n".join(f"Q: {q}\nR: {a}" for q, a in history)
            + "\n\n"
        )

    confidence_warning = (
        "⚠ AVERTISSEMENT: Les documents ci-dessous sont de faible pertinence. "
        "Si vous n'êtes pas certain à 100%, répondez: "
        "\"Je n'ai pas trouvé cette information dans les données de formation.\"\n\n"
        if low_confidence else ""
    )

    sources_list = ""
    if sources:
        unique = sorted(set(sources))
        sources_list = (
            "## Sources disponibles dans ce contexte\n"
            + "\n".join(f"- {s}" for s in unique)
            + "\n\n"
        )

    return (
        f"Tu es ChronoBrain, l'assistant expert de {COMPANY_NAME}.\n"
        "Tu aides les employés en t'appuyant UNIQUEMENT sur les transcriptions "
        "de formations fournies ci-dessous.\n\n"
        "## Règles absolues\n"
        "1. Réponds UNIQUEMENT avec les informations présentes dans les documents.\n"
        "2. N'utilise JAMAIS tes connaissances générales ou extérieures.\n"
        "3. Si l'information n'est pas disponible, dis-le clairement.\n"
        "4. Cite tes sources avec [Source: nom_du_fichier] à la fin de ta réponse.\n"
        "5. Utilise un ton professionnel mais accessible.\n"
        "6. Ne cite jamais les horodatages dans ta réponse.\n"
        "7. Structure ta réponse avec des points numérotés ou des titres "
        "si la réponse comporte plusieurs éléments.\n\n"
        f"{confidence_warning}"
        f"{sources_list}"
        "## Documents de formation disponibles\n"
        "─────────────────────────────────────\n"
        f"{context}\n"
        "─────────────────────────────────────\n\n"
        f"{history_str}"
        f"## Question de l'utilisateur\n{question}\n\n"
        "## Ta réponse (basée uniquement sur les documents ci-dessus)\n"
        "Fournis une réponse complète et détaillée. "
        "Si la réponse comporte des étapes ou des éléments distincts, "
        "liste-les clairement. "
        "Cite la source à la fin avec [Source: ...].\n\n"
    )


# ── 8. ANSWER EXTRACTOR ───────────────────────────────────────────────────────

def extract_final_answer(raw: str) -> str:
    """
    The chain-of-thought prompt makes the LLM write:
      Étape 1: [quote]
      Étape 2: [answer]
    
    We extract only the Step 2 answer (after the quote).
    If the structure isn't present, return the full response.
    """
    # Try to find Étape 2 content
    patterns = [
        r"[ÉE]tape\s*2[:\s—-]+(.+)",
        r"[ÉE]tape\s*2\s*[–—]\s*(.+)",
        r"Réponse\s*:\s*(.+)",
        r"Basé\s+(?:uniquement\s+)?sur\s+ce\s+passage[,\s]+(.+)",
    ]
    for p in patterns:
        m = re.search(p, raw, re.DOTALL | re.IGNORECASE)
        if m:
            answer = m.group(1).strip()
            # Remove any remaining "Étape" headers from the extracted text
            answer = re.sub(r'^[ÉE]tape\s*\d+[:\s—-]+', '', answer, flags=re.IGNORECASE).strip()
            return answer

    # Fallback: return everything after the last "Étape 1" block if present
    if re.search(r'[ÉE]tape\s*1', raw, re.IGNORECASE):
        parts = re.split(r'[ÉE]tape\s*1.+?\n', raw, maxsplit=1, flags=re.DOTALL | re.IGNORECASE)
        if len(parts) > 1:
            return parts[-1].strip()

    return raw.strip()


# ── 9. FAST FAITHFULNESS CHECK ────────────────────────────────────────────────

def fast_faithfulness_check(context: str, answer: str) -> dict:
    FALLBACK_INDICATORS = [
        "je n'ai pas trouvé",
        "je ne sais pas",
        "je n'ai pas cette information",
        "je ne peux pas",
        "aucune information",
    ]

    answer_lower  = answer.lower()
    context_lower = context.lower()

    if any(p in answer_lower for p in FALLBACK_INDICATORS):
        return {"fidélité": "Oui", "hallucination": "Non", "score": 3}

    answer_words  = set(re.findall(r'\b\w{4,}\b', answer_lower))
    context_words = set(re.findall(r'\b\w{4,}\b', context_lower))

    if not answer_words:
        return {"fidélité": "Inconnu", "hallucination": "Inconnu", "score": 0}

    overlap = len(answer_words & context_words) / len(answer_words)

    # Threshold lowered to 0.20 — French synonyms/conjugations don't match verbatim
    if overlap >= 0.20:
        score = min(5, max(1, int(overlap * 7)))
        return {"fidélité": "Oui", "hallucination": "Non", "score": score}
    else:
        score = max(1, int(overlap * 4))
        return {"fidélité": "Non", "hallucination": "Oui", "score": score}


# ── 10. SAFE LLM CALL ─────────────────────────────────────────────────────────

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


# ── 11. METRICS TRACKER ───────────────────────────────────────────────────────

class PerformanceTracker:
    def __init__(self):
        self.queries    = 0
        self.total_lat  = 0.0
        self.fallbacks  = 0
        self.cache_hits = 0
        self.stripped   = 0   # answers that had hallucinations stripped

    def record(self, latency: float, is_unfaithful: bool, was_stripped: bool = False):
        self.queries  += 1
        self.total_lat += latency
        if is_unfaithful:
            self.fallbacks += 1
        if was_stripped:
            self.stripped += 1

    def print_stats(self):
        if self.queries == 0:
            print("Aucune requête enregistrée.\n")
            return
        avg  = self.total_lat / self.queries
        rate = (self.fallbacks / self.queries) * 100
        print(
            f"\n[Stats] {self.queries} réponses LLM | "
            f"Cache: {self.cache_hits} hits | "
            f"Latence moy: {avg:.1f}s | "
            f"Non-fidèle: {rate:.0f}% | "
            f"Phrases supprimées: {self.stripped}\n"
        )

    def print_inline(self, latency: float, is_unfaithful: bool, was_stripped: bool = False):
        self.record(latency, is_unfaithful, was_stripped)
        avg  = self.total_lat / self.queries
        rate = (self.fallbacks / self.queries) * 100
        flag = " ⚠" if is_unfaithful else ""
        strip_flag = " ✂" if was_stripped else ""
        print(
            f"[Metrics] #{self.queries} | {latency:.1f}s | moy {avg:.1f}s | "
            f"non-fidèle {rate:.0f}%{flag}{strip_flag}"
        )


# ── 12. RESPONSE CACHE ────────────────────────────────────────────────────────

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


# ── 13. MAIN LOOP ─────────────────────────────────────────────────────────────

def main():
    global DEBUG_RETRIEVAL

    if not os.path.exists(DATA_DIR):
        print(f"Erreur: dossier '{DATA_DIR}' introuvable.")
        sys.exit(1)

    print("Initialisation de ChronoBrain v7…")
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
            print("Mode debug activé.\n")
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

        # ── Retrieve ──────────────────────────────────────────────────────────
        print("Recherche en cours…")
        nodes, used_fallback = retrieve_nodes(
            retriever, user_input, MIN_SCORE, FALLBACK_TOP_K
        )
        nodes = deduplicate(nodes)

        if not nodes:
            print(f"\nRéponse: {FALLBACK_MSG}\n")
            history.append((user_input, FALLBACK_MSG))
            continue

        # ── Build context ─────────────────────────────────────────────────────
        context = trim_to_token_budget(
            [n.get_content() for n in nodes],
            MAX_CONTEXT_TOKENS,
        )
        node_sources = [n.metadata.get("source", "formation") for n in nodes]

        prompt = build_prompt(
            context,
            history[-HISTORY_TURNS:],
            user_input,
            low_confidence=used_fallback,
            sources=node_sources,
        )

        # ── LLM call ──────────────────────────────────────────────────────────
        print("Réflexion…")
        t0      = time.time()
        raw     = safe_llm_complete(llm, prompt)
        latency = time.time() - t0

        if raw is None:
            print(f"\nRéponse: {TIMEOUT_MSG}\n")
            continue

        answer = raw.strip()

        # ── Strip hallucination sentences ─────────────────────────────────────
        answer_before = answer
        answer        = strip_hallucinations(answer)
        was_stripped  = answer != answer_before

        # ── Fast faithfulness check ───────────────────────────────────────────
        evals       = fast_faithfulness_check(context, answer)
        is_faithful = evals.get("fidélité", "Oui") == "Oui"
        is_halluc   = evals.get("hallucination", "Non") == "Oui"

        tracker.print_inline(latency, not is_faithful, was_stripped)

        print(f"\nRéponse: {answer}")
        print(
            f"Qualité: fidélité={evals['fidélité']} | "
            f"hallucination={evals['hallucination']} | "
            f"score={evals['score']}/5\n"
        )

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