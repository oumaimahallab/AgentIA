"""
ChronoBrain — Clean JSON Ingestion Module
══════════════════════════════════════════
Drop-in replacement for load_all_transcripts() in chronobrain_v7.py.

Instead of parsing raw .txt files on every startup, this reads the
pre-cleaned JSON produced by transcript_cleaner.py.

Benefits:
  - Startup is ~3x faster (no re-parsing, no noise filtering)
  - Chunks are richer: chunk_id, asr_warning flag, exact sec timestamps
  - New transcripts: run transcript_cleaner.py → re-ingest once
"""

import os
import json
import logging
from pathlib import Path
from llama_index.core import Document

log = logging.getLogger("chronobrain")


def load_cleaned_chunks(cleaned_dir: str) -> list[Document]:
    """
    Load all *_cleaned.json files from cleaned_dir.
    Each JSON file is an array of chunk objects produced by transcript_cleaner.py.
    Returns a list of LlamaIndex Document objects ready for VectorStoreIndex.
    """
    cleaned_path = Path(cleaned_dir)
    if not cleaned_path.exists():
        raise FileNotFoundError(
            f"Cleaned data directory not found: {cleaned_dir}\n"
            f"Run: python transcript_cleaner.py --input <transcripts> --output {cleaned_dir}"
        )

    docs: list[Document] = []
    json_files = sorted(cleaned_path.glob("*_cleaned.json"))

    if not json_files:
        raise FileNotFoundError(
            f"No *_cleaned.json files found in {cleaned_dir}.\n"
            f"Run transcript_cleaner.py first."
        )

    for jf in json_files:
        chunks = json.loads(jf.read_text(encoding="utf-8"))
        for c in chunks:
            doc = Document(
                text=c["text"],
                metadata={
                    "chunk_id":       c["chunk_id"],
                    "source":         c["source"],
                    "start_time":     c["start_time"],
                    "end_time":       c["end_time"],
                    "start_sec":      c["start_sec"],
                    "end_sec":        c["end_sec"],
                    "word_count":     c["word_count"],
                    "asr_warning":    c.get("has_asr_warning", False),
                },
            )
            docs.append(doc)

        log.debug("Loaded %d chunks from %s", len(chunks), jf.name)

    log.warning("Total clean chunks loaded: %d from %d files", len(docs), len(json_files))
    return docs