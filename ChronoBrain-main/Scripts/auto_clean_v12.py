#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chronobrain_rag.py  —  ChronoBrain RAG Chatbot
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WHAT THIS DOES:
  Loads your existing chunks.csv (or chunks.json), builds a FAISS vector
  index once, then lets you ask questions and get answers with the exact
  retrieved context displayed.

PIPELINE per question:
  1. Embed question with multilingual-e5-base
  2. FAISS search → top-K most similar chunks
  3. Send (question + chunks as context) to Groq LLM
  4. Return answer + show retrieved sources

USAGE:
  # First run — builds index (takes ~2 min for 1094 chunks)
  python chronobrain_rag.py

  # Subsequent runs — loads saved index instantly
  python chronobrain_rag.py

  # Single question (non-interactive)
  python chronobrain_rag.py --query "Comment valider une absence ?"

  # Use JSON instead of CSV
  python chronobrain_rag.py --chunks ../data/chunks/chunks.json

  # Show more retrieved chunks
  python chronobrain_rag.py --top-k 5

REQUIREMENTS:
  pip install sentence-transformers faiss-cpu numpy pandas groq python-dotenv openpyxl

.env file (in the same folder as this script):
  GROQ_API_KEY=your_key_here
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION  ← edit these to match your folder layout
# ══════════════════════════════════════════════════════════════════════════════

load_dotenv()

class Config:
    # Your chunks file (CSV or JSON produced by semantic_chunker.py)
    CHUNKS_CSV   = "../data/chunks/chunks.csv"
    CHUNKS_JSON  = "../data/chunks/chunks.json"

    # Where the FAISS index is saved after first run
    INDEX_PATH    = "../data/index/faiss.index"
    META_PATH     = "../data/index/metadata.json"

    # Performance log (same schema as your existing ChronoBrain code)
    LOG_EXCEL     = "../data/logs/performance_logs.xlsx"

    # Embedding model — runs 100% locally, no API, handles French perfectly
    EMBED_MODEL   = "intfloat/multilingual-e5-base"
    EMBED_BATCH   = 64          # chunks per embedding batch

    # Groq LLM
    GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL    = "llama-3.1-8b-instant"
    GROQ_URL      = "https://api.groq.com/openai/v1/chat/completions"
    LLM_TEMP      = 0.1         # low = factual, deterministic
    LLM_MAX_TOK   = 1024

    # Retrieval
    TOP_K         = 4           # chunks retrieved per question
    MAX_CTX_WORDS = 1800        # cap context sent to LLM (avoid token overflow)


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("chronobrain")


# ══════════════════════════════════════════════════════════════════════════════
# 1. LOAD CHUNKS
# ══════════════════════════════════════════════════════════════════════════════

def load_chunks(csv_path: str, json_path: str) -> list[dict]:
    """
    Load chunks from CSV or JSON.
    Prefers CSV if both exist and CSV is found first.
    Each chunk must have at least: chunk_id, source_file, text.
    """
    # Try CSV first
    for path in (csv_path, json_path):
        p = Path(path)
        if not p.exists():
            continue

        log.info("Loading chunks from: %s", p)

        if p.suffix == ".csv":
            df = pd.read_csv(p, dtype=str)
            # Fill NaN with empty string
            df = df.fillna("")
            chunks = df.to_dict(orient="records")

        elif p.suffix == ".json":
            with p.open(encoding="utf-8") as f:
                data = json.load(f)
            # Support both list-of-dicts and {chunks: [...]}
            chunks = data if isinstance(data, list) else data.get("chunks", [])

        else:
            continue

        # Validate: must have 'text' field
        valid = [c for c in chunks if c.get("text", "").strip()]
        log.info("  Loaded %d chunks (%d valid)", len(chunks), len(valid))
        return valid

    log.error("No chunks file found. Checked:\n  %s\n  %s", csv_path, json_path)
    log.error("Run semantic_chunker.py first to generate chunks.")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# 2. BUILD / LOAD FAISS INDEX
# ══════════════════════════════════════════════════════════════════════════════

def _get_embedder():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        log.error("pip install sentence-transformers")
        sys.exit(1)
    log.info("Loading embedding model: %s", Config.EMBED_MODEL)
    return SentenceTransformer(Config.EMBED_MODEL)


def _embed(model, texts: list[str], prefix: str = "passage: ") -> np.ndarray:
    """
    Embed a list of texts in batches.
    multilingual-e5-base requires 'passage: ' prefix for documents,
    'query: ' prefix for search queries.
    Returns L2-normalised float32 array (N, D).
    """
    all_embs = []
    for i in range(0, len(texts), Config.EMBED_BATCH):
        batch = [prefix + t for t in texts[i: i + Config.EMBED_BATCH]]
        embs  = model.encode(batch, normalize_embeddings=True,
                             show_progress_bar=False)
        all_embs.append(embs.astype(np.float32))
        if (i // Config.EMBED_BATCH) % 5 == 0 and i > 0:
            log.info("  Embedded %d/%d chunks...", i, len(texts))
    return np.vstack(all_embs)


def build_index(chunks: list[dict], model) -> tuple:
    """
    Embed all chunks and build a FAISS flat index.
    Returns (faiss_index, metadata_list).
    Also saves both to disk so next run is instant.
    """
    try:
        import faiss
    except ImportError:
        log.error("pip install faiss-cpu")
        sys.exit(1)

    texts = [c["text"] for c in chunks]
    log.info("Embedding %d chunks (this runs once, then is saved)...", len(texts))

    t0   = time.time()
    embs = _embed(model, texts, prefix="passage: ")
    log.info("Embedding done in %.1fs", time.time() - t0)

    dim   = embs.shape[1]
    index = faiss.IndexFlatIP(dim)   # Inner-product = cosine on normalised vectors
    index.add(embs)
    log.info("FAISS index built: %d vectors, dim=%d", index.ntotal, dim)

    # Save index and metadata
    idx_path  = Path(Config.INDEX_PATH)
    meta_path = Path(Config.META_PATH)
    idx_path.parent.mkdir(parents=True, exist_ok=True)

    faiss.write_index(index, str(idx_path))

    # Save lightweight metadata (text + source only — no need to re-embed later)
    meta = [{"chunk_id":    c.get("chunk_id", str(i)),
              "source_file": c.get("source_file", ""),
              "word_count":  c.get("word_count", ""),
              "method":      c.get("method", ""),
              "text":        c["text"]}
            for i, c in enumerate(chunks)]

    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

    log.info("Index saved → %s", idx_path)
    log.info("Metadata saved → %s", meta_path)
    return index, meta


def load_index(model) -> tuple:
    """
    Load saved FAISS index + metadata from disk.
    Falls back to build_index if not found.
    """
    try:
        import faiss
    except ImportError:
        log.error("pip install faiss-cpu")
        sys.exit(1)

    idx_path  = Path(Config.INDEX_PATH)
    meta_path = Path(Config.META_PATH)

    if idx_path.exists() and meta_path.exists():
        log.info("Loading saved FAISS index from: %s", idx_path)
        index = faiss.read_index(str(idx_path))
        with meta_path.open(encoding="utf-8") as f:
            meta = json.load(f)
        log.info("Index loaded: %d vectors", index.ntotal)
        return index, meta

    # Not found — build from scratch
    log.info("No saved index found — building from chunks...")
    chunks = load_chunks(Config.CHUNKS_CSV, Config.CHUNKS_JSON)
    return build_index(chunks, model)


# ══════════════════════════════════════════════════════════════════════════════
# 3. RETRIEVAL
# ══════════════════════════════════════════════════════════════════════════════

def retrieve(question: str, index, meta: list[dict],
             model, top_k: int = Config.TOP_K) -> list[dict]:
    """
    Embed the question and retrieve top_k most similar chunks.
    Returns list of chunk dicts with an added 'score' field.

    WHY top_k=4 by default:
      Each chunk is ~430 words. 4 chunks ≈ 1720 words of context.
      Groq's llama-3.1-8b can handle 8k tokens — this leaves
      plenty of room for the question and the answer.
    """
    q_emb = _embed(model, [question], prefix="query: ")

    # FAISS returns (scores, indices) — scores are inner products (cosine)
    scores, indices = index.search(q_emb, top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(meta):
            continue
        chunk = dict(meta[idx])
        chunk["score"] = float(score)
        results.append(chunk)

    return results


# ══════════════════════════════════════════════════════════════════════════════
# 4. CONTEXT BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_context(retrieved: list[dict]) -> str:
    """
    Build the context string sent to the LLM.
    Caps at MAX_CTX_WORDS to avoid token overflow.
    Includes source attribution so the LLM can reference it in the answer.
    """
    parts = []
    total_words = 0

    for i, chunk in enumerate(retrieved, 1):
        source = Path(chunk.get("source_file", "?")).stem
        # Trim source name to something readable
        source = source[:60].rstrip()
        text   = chunk["text"].strip()
        words  = text.split()

        # If this chunk would overflow the budget, truncate it
        remaining = Config.MAX_CTX_WORDS - total_words
        if remaining <= 50:
            break
        if len(words) > remaining:
            text  = " ".join(words[:remaining]) + "…"
            words = words[:remaining]

        parts.append(f"[Source {i} — {source}]\n{text}")
        total_words += len(words)

    return "\n\n---\n\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# 5. LLM CALL (Groq)
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """\
Tu es ChronoBrain, l'assistant expert de la plateforme Chronotime (CTIME) chez Inetum.

RÈGLE ABSOLUE : Réponds UNIQUEMENT à partir des extraits fournis dans le contexte.
N'utilise jamais tes connaissances générales sur Chronotime ou sur d'autres logiciels.

FORMAT DE RÉPONSE :
- Réponds en français, ton professionnel et didactique.
- Pour les procédures : utilise des étapes numérotées (Étape 1, Étape 2...).
- Pour les concepts : une définition claire puis les détails.
- Cite la source quand tu utilises une information spécifique : [Source N].
- Si l'information n'est pas dans le contexte : réponds exactement
  "Je n'ai pas trouvé cette information dans les données de formation."

INTERDICTIONS :
- Ne dis pas "selon mes connaissances" ou "généralement".
- Ne devine pas. Si c'est absent du contexte, dis-le.
"""

def ask_llm(question: str, context: str) -> str:
    """Send question + retrieved context to Groq and return the answer."""
    import requests

    if not Config.GROQ_API_KEY or Config.GROQ_API_KEY == "your_key_here":
        return (
            "[ERREUR] GROQ_API_KEY non configurée.\n"
            "Ajoutez GROQ_API_KEY=votre_clé dans votre fichier .env"
        )

    user_msg = (
        f"CONTEXTE (extraits de formation Chronotime) :\n\n"
        f"{context}\n\n"
        f"─────────────────────────────────────────\n\n"
        f"QUESTION : {question}"
    )

    payload = {
        "model":       Config.GROQ_MODEL,
        "temperature": Config.LLM_TEMP,
        "max_tokens":  Config.LLM_MAX_TOK,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
    }

    headers = {
        "Authorization": f"Bearer {Config.GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }

    try:
        resp = requests.post(Config.GROQ_URL, headers=headers,
                             json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except requests.exceptions.Timeout:
        return "[ERREUR] Groq a mis trop de temps à répondre. Réessayez."
    except requests.exceptions.HTTPError as e:
        return f"[ERREUR HTTP] {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return f"[ERREUR] {e}"


# ══════════════════════════════════════════════════════════════════════════════
# 6. PERFORMANCE LOGGER
# ══════════════════════════════════════════════════════════════════════════════

def log_performance(question: str, answer: str, response_time: float,
                    retrieved: list[dict]) -> None:
    """
    Append one row to the Excel performance log.
    Same schema as your existing ChronoBrain code, plus retrieved sources.
    """
    log_path = Path(Config.LOG_EXCEL)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    sources = " | ".join(
        Path(r.get("source_file", "?")).stem[:40] for r in retrieved
    )

    new_row = pd.DataFrame({
        "Timestamp":            [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        "Model":                [Config.GROQ_MODEL],
        "Question":             [question],
        "Answer":               [answer],   # truncate for Excel readability
        "Response Time (s)":    [round(response_time, 3)],
        "Chunks Retrieved":     [len(retrieved)],
        "Top Score":            [round(retrieved[0]["score"], 3) if retrieved else 0],
        "Sources":              [sources],
    })

    if log_path.exists():
        try:
            df_old   = pd.read_excel(log_path)
            df_final = pd.concat([df_old, new_row], ignore_index=True)
        except Exception:
            df_final = new_row
    else:
        df_final = new_row

    try:
        df_final.to_excel(log_path, index=False)
    except Exception as e:
        log.warning("Could not save Excel log: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
# 7. DISPLAY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _print_separator(char="═", width=65):
    print(char * width)

def _print_retrieved(retrieved: list[dict]) -> None:
    """Show the retrieved chunks so the user can verify the context."""
    print()
    print("┌" + "─" * 63 + "┐")
    print("│  CONTEXTE RÉCUPÉRÉ (chunks utilisés pour répondre)           │")
    print("└" + "─" * 63 + "┘")

    for i, chunk in enumerate(retrieved, 1):
        source   = Path(chunk.get("source_file", "?")).stem
        score    = chunk.get("score", 0)
        wc       = chunk.get("word_count", "?")
        method   = chunk.get("method", "")
        preview  = chunk["text"].replace("\n", " ")[:200]

        print(f"\n  [{i}] Score: {score:.3f}  |  {wc} mots  |  {method}")
        print(f"       Source: {source[:60]}")
        print(f"       Texte:  {preview}…")

    print()


def _print_answer(question: str, answer: str, elapsed: float) -> None:
    _print_separator()
    print(f"  Q: {question}")
    _print_separator("─")
    print()
    print(answer)
    print()
    _print_separator("─")
    print(f"  ⏱  Temps de réponse : {elapsed:.2f}s")
    _print_separator()


# ══════════════════════════════════════════════════════════════════════════════
# 8. FULL QUERY FUNCTION  (one question → one answer with sources)
# ══════════════════════════════════════════════════════════════════════════════

def query(question: str, index, meta: list[dict], model,
          top_k: int = Config.TOP_K,
          show_context: bool = True) -> str:
    """
    Full RAG pipeline for one question:
      retrieve → build context → ask LLM → display → log

    Returns the answer string.
    """
    if not question.strip():
        return ""

    t0 = time.time()

    # Step 1: Retrieve relevant chunks
    retrieved = retrieve(question, index, meta, model, top_k=top_k)

    if not retrieved:
        answer = "Je n'ai pas trouvé cette information dans les données de formation."
        _print_answer(question, answer, time.time() - t0)
        return answer

    # Step 2: Build context string
    context = build_context(retrieved)

    # Step 3: Ask LLM
    answer = ask_llm(question, context)

    elapsed = time.time() - t0

    # Step 4: Display
    if show_context:
        _print_retrieved(retrieved)
    _print_answer(question, answer, elapsed)

    # Step 5: Log
    log_performance(question, answer, elapsed, retrieved)

    return answer


# ══════════════════════════════════════════════════════════════════════════════
# 9. INTERACTIVE CHAT LOOP
# ══════════════════════════════════════════════════════════════════════════════

def interactive_loop(index, meta: list[dict], model) -> None:
    """
    Interactive question loop.
    Commands:
      quit / exit   — stop
      context on    — show retrieved chunks (default)
      context off   — hide retrieved chunks
      top 3/5/8     — change number of retrieved chunks
    """
    top_k        = Config.TOP_K
    show_context = True

    _print_separator()
    print("  ChronoBrain — Assistant Chronotime (CTIME)")
    print(f"  Modèle : {Config.GROQ_MODEL}")
    print(f"  Index  : {len(meta)} chunks de {len(set(c['source_file'] for c in meta))} fichiers")
    _print_separator()
    print()
    print("  Commandes : quit | context on/off | top 3/5/8")
    print()

    while True:
        try:
            question = input("  Votre question : ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Au revoir.")
            break

        if not question:
            continue

        cmd = question.lower()

        if cmd in ("quit", "exit", "q"):
            print("  Au revoir.")
            break

        if cmd == "context on":
            show_context = True
            print("  Affichage des sources activé.\n")
            continue

        if cmd == "context off":
            show_context = False
            print("  Affichage des sources désactivé.\n")
            continue

        if cmd.startswith("top "):
            try:
                top_k = int(cmd.split()[1])
                print(f"  Top-K réglé à {top_k}.\n")
            except (IndexError, ValueError):
                print("  Usage : top 3\n")
            continue

        print()
        query(question, index, meta, model, top_k=top_k,
              show_context=show_context)
        print()


# ══════════════════════════════════════════════════════════════════════════════
# 10. MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="ChronoBrain RAG Chatbot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES
  # Interactive chat (default)
  python chronobrain_rag.py

  # Single question
  python chronobrain_rag.py --query "Comment créer un profil utilisateur ?"

  # Force rebuild of the FAISS index (e.g. after adding new chunks)
  python chronobrain_rag.py --rebuild

  # Show 5 retrieved chunks per question
  python chronobrain_rag.py --top-k 5

  # Use a specific chunks file
  python chronobrain_rag.py --chunks ./my_chunks.csv

  # Hide the retrieved chunks (just show the answer)
  python chronobrain_rag.py --no-context
        """,
    )
    parser.add_argument("--query",      "-q",  help="Single question (non-interactive)")
    parser.add_argument("--chunks",     "-c",  help="Path to chunks CSV or JSON file")
    parser.add_argument("--top-k",      "-k",  type=int, default=Config.TOP_K,
                        help=f"Chunks to retrieve per question (default: {Config.TOP_K})")
    parser.add_argument("--rebuild",    action="store_true",
                        help="Force rebuild FAISS index even if one exists")
    parser.add_argument("--no-context", action="store_true",
                        help="Hide retrieved chunks — only show the answer")
    args = parser.parse_args()

    if args.chunks:
        Config.CHUNKS_CSV  = args.chunks
        Config.CHUNKS_JSON = args.chunks
    Config.TOP_K = args.top_k

    # Check Groq key early
    if not Config.GROQ_API_KEY:
        log.warning("GROQ_API_KEY not set — LLM calls will fail.")
        log.warning("Create a .env file with: GROQ_API_KEY=your_key_here")

    # Load embedding model
    model = _get_embedder()

    # Build or load FAISS index
    if args.rebuild and Path(Config.INDEX_PATH).exists():
        log.info("--rebuild: deleting existing index")
        Path(Config.INDEX_PATH).unlink(missing_ok=True)
        Path(Config.META_PATH).unlink(missing_ok=True)

    index, meta = load_index(model)

    # Run
    if args.query:
        print()
        query(args.query, index, meta, model,
              top_k=args.top_k,
              show_context=not args.no_context)
    else:
        interactive_loop(index, meta, model)


if __name__ == "__main__":
    main()


    #q = "À quoi sert le matricule alpha et dans quels cas est-il utilisé ?"
    #q = "Quelle est la différence entre un programme hebdomadaire et un cycle ?"
    #q = "Que se passe-t-il lorsqu’un collaborateur badge en dehors de sa plage horaire ?"
    #q = "Comment les heures supplémentaires sont‑elles calculées ?"
    #q = "Comment créer client principal ?"
    #q = "c'est quoi la difference entre astreinte et heures supplémentaire?"
    #q = "eeeeeeeeeeeeeeeee"
    #q = "comment fonctionnent asreinte realisees et astreinte prevue ?"
    #q = "comment creer un profile utilisateur?"    