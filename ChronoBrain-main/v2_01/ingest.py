"""
ingest.py — Ingestion pipeline for ChronoBrain
Builds FAISS + BM25 indices from pre-cleaned JSON chunk files.

Features:
  - Idempotent: skips already-ingested files via SQLite tracking
  - Stores chunk metadata separately (chunks.pkl alongside FAISS index)
  - Progress display

Usage:
    python ingest.py                        # ingest all new files
    python ingest.py --force                # re-ingest everything
    python ingest.py --data path/to/json   # custom data dir
"""

import os
import json
import pickle
import sqlite3
import logging
import argparse
from pathlib import Path

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

from config import (
    DATA_DIR, FAISS_DIR, BM25_PATH, SQLITE_PATH, EMBED_MODEL
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("chronobrain.ingest")


# ── Tokeniser (shared with hybrid_retriever) ──────────────────────────────────

def _tokenize(text: str) -> list[str]:
    import re
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return [t for t in text.split() if len(t) > 1]


# ── SQLite metadata store ─────────────────────────────────────────────────────

def init_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ingested_files (
            filename      TEXT PRIMARY KEY,
            ingested_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            chunk_count   INTEGER,
            source_path   TEXT
        )
    """)
    conn.commit()
    return conn


def is_already_ingested(conn: sqlite3.Connection, filename: str) -> bool:
    row = conn.execute(
        "SELECT filename FROM ingested_files WHERE filename = ?", (filename,)
    ).fetchone()
    return row is not None


def mark_ingested(
    conn: sqlite3.Connection,
    filename: str,
    chunk_count: int,
    source_path: str,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO ingested_files (filename, chunk_count, source_path) "
        "VALUES (?, ?, ?)",
        (filename, chunk_count, source_path),
    )
    conn.commit()


# ── Main ingestion pipeline ───────────────────────────────────────────────────

def run(data_dir: str, force: bool = False) -> None:
    data_path = Path(data_dir)
    if not data_path.exists():
        log.error("Data directory not found: %s", data_dir)
        return

    json_files = sorted(data_path.glob("*.json"))
    if not json_files:
        log.error("No .json files found in %s", data_dir)
        return

    os.makedirs(FAISS_DIR, exist_ok=True)
    conn = init_db(SQLITE_PATH)

    # ── Load or initialise existing index ────────────────────────────────────
    index_path  = os.path.join(FAISS_DIR, "index.faiss")
    chunks_path = os.path.join(FAISS_DIR, "chunks.pkl")

    all_chunks:     list[dict] = []
    all_embeddings: list[np.ndarray] = []

    if os.path.exists(index_path) and not force:
        log.info("Loading existing FAISS index + chunks…")
        existing_index = faiss.read_index(index_path)
        with open(chunks_path, "rb") as f:
            all_chunks = pickle.load(f)
        log.info("  %d vectors already indexed.", existing_index.ntotal)
    else:
        existing_index = None
        if force:
            log.info("--force: rebuilding index from scratch.")

    # ── Load embedder ─────────────────────────────────────────────────────────
    log.info("Loading embedding model: %s", EMBED_MODEL)
    embedder = SentenceTransformer(EMBED_MODEL)

    # ── Process each JSON file ────────────────────────────────────────────────
    new_chunks: list[dict] = []
    for jf in json_files:
        if not force and is_already_ingested(conn, jf.name):
            log.info("  Skipping (already ingested): %s", jf.name)
            continue

        log.info("  Ingesting: %s", jf.name)
        chunks = json.loads(jf.read_text(encoding="utf-8"))

        # Filter out ASR-warned chunks if you want stricter quality:
        # chunks = [c for c in chunks if not c.get("has_asr_warning", False)]

        new_chunks.extend(chunks)
        mark_ingested(conn, jf.name, len(chunks), str(jf))
        log.info("    → %d chunks loaded.", len(chunks))

    if not new_chunks and existing_index is not None:
        log.info("Nothing new to ingest. Index is up to date.")
        conn.close()
        return

    # ── Embed new chunks ──────────────────────────────────────────────────────
    if new_chunks:
        log.info("Embedding %d new chunks…", len(new_chunks))
        texts = [c["text"] for c in new_chunks]
        batch_size = 64
        new_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i: i + batch_size]
            vecs  = embedder.encode(batch, normalize_embeddings=True, show_progress_bar=False)
            new_embeddings.extend(vecs)
            log.info("  Embedded %d / %d", min(i + batch_size, len(texts)), len(texts))
        new_embeddings_np = np.array(new_embeddings, dtype="float32")

    # ── Build / extend FAISS index ────────────────────────────────────────────
    dim = new_embeddings_np.shape[1] if new_chunks else 0

    if existing_index is None or force:
        log.info("Building new FAISS IndexFlatIP (dim=%d)…", dim)
        index = faiss.IndexFlatIP(dim)
        combined_chunks = new_chunks
        combined_embeddings = new_embeddings_np
    else:
        log.info("Extending existing FAISS index…")
        index = existing_index
        combined_chunks     = all_chunks + new_chunks
        combined_embeddings = new_embeddings_np  # only add new ones

    index.add(combined_embeddings)
    log.info("FAISS index now has %d vectors.", index.ntotal)

    # ── Combine all chunks for saving ─────────────────────────────────────────
    if existing_index is None or force:
        final_chunks = combined_chunks
    else:
        final_chunks = all_chunks + new_chunks

    # ── Build BM25 index (always rebuilt from all chunks) ────────────────────
    log.info("Building BM25 index over %d chunks…", len(final_chunks))
    tokenized = [_tokenize(c["text"]) for c in final_chunks]
    bm25      = BM25Okapi(tokenized)

    # ── Save everything ───────────────────────────────────────────────────────
    faiss.write_index(index, index_path)
    with open(chunks_path, "wb") as f:
        pickle.dump(final_chunks, f)
    with open(BM25_PATH, "wb") as f:
        pickle.dump(bm25, f)

    log.info("Saved FAISS index    → %s", index_path)
    log.info("Saved chunk metadata → %s", chunks_path)
    log.info("Saved BM25 index     → %s", BM25_PATH)
    log.info("Done. Total chunks in index: %d", len(final_chunks))

    conn.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChronoBrain ingestion pipeline")
    parser.add_argument("--data",  default=DATA_DIR, help="Path to clean JSON folder")
    parser.add_argument("--force", action="store_true", help="Force full re-ingestion")
    args = parser.parse_args()
    run(args.data, force=args.force)
