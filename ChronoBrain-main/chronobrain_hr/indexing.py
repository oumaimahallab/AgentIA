from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

from .config import HRConfig


_TS_PATTERN = re.compile(r"\[(\d+):(\d+)\s*->\s*(\d+):(\d+)\]\s*(.*)")


def _parse_transcript_file(path: Path) -> list[Document]:
    """
    Parses transcript lines formatted like:
      [00:11 -> 00:19] some text...
    Falls back to a whole-file document if no timestamped lines are found.
    """
    segments: list[tuple[float, float, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    for line in text.splitlines():
        m = _TS_PATTERN.match(line.strip())
        if not m:
            continue
        sm, ss, em, es, seg_text = m.groups()
        seg_text = seg_text.strip()
        if not seg_text:
            continue
        start = int(sm) * 60 + int(ss)
        end = int(em) * 60 + int(es)
        segments.append((start, end, seg_text))

    if not segments:
        return [Document(text=text, metadata={"source": path.name})]

    # Chunk adjacent segments into ~80-word chunks; keep semantic timestamps
    CHUNK_WORDS = 80
    MAX_GAP_SEC = 3.0

    def flush(buf: list[str], t_start: float, t_end: float) -> Document:
        return Document(
            text=" ".join(buf),
            metadata={
                "source": path.name,
                "start_time": f"{int(t_start // 60):02d}:{int(t_start % 60):02d}",
                "end_time": f"{int(t_end // 60):02d}:{int(t_end % 60):02d}",
            },
        )

    chunks: list[Document] = []
    buf: list[str] = []
    buf_start = 0.0
    buf_end = 0.0
    wc_total = 0

    for start, end, seg_text in segments:
        gap = (start - buf_end) if buf else 0
        wc = len(seg_text.split())
        if buf and (gap > MAX_GAP_SEC or wc_total + wc > CHUNK_WORDS):
            chunks.append(flush(buf, buf_start, buf_end))
            buf = []
            wc_total = 0
            buf_start = start
        if not buf:
            buf_start = start
        buf.append(seg_text)
        buf_end = end
        wc_total += wc

    if buf:
        chunks.append(flush(buf, buf_start, buf_end))

    return chunks


def iter_documents(transcripts_dir: Path) -> Iterable[Document]:
    for root, _, files in os.walk(transcripts_dir):
        for fname in files:
            if not fname.lower().endswith((".txt", ".md")):
                continue
            path = Path(root) / fname
            for doc in _parse_transcript_file(path):
                yield doc


def get_or_build_index(cfg: HRConfig) -> VectorStoreIndex:
    cfg.chroma_db_dir.mkdir(parents=True, exist_ok=True)

    db = chromadb.PersistentClient(path=str(cfg.chroma_db_dir))
    collection = db.get_or_create_collection(cfg.collection_name)
    vector_store = ChromaVectorStore(chroma_collection=collection)

    # If already indexed, just load
    if collection.count() > 0:
        return VectorStoreIndex.from_vector_store(vector_store)

    docs = list(iter_documents(cfg.transcripts_dir))
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    return VectorStoreIndex.from_documents(docs, storage_context=storage_context, show_progress=True)

