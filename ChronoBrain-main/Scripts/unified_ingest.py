#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helper script to ingest documents and update FAISS/BM25 indexes from unified-agent."""

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_INPUT_DIR = Path(os.environ.get("UNIFIED_INGEST_INPUT_DIR", "/opt/airflow/data/documents"))
DEFAULT_STAGE_DIR = Path(os.environ.get("UNIFIED_INGEST_STAGE_DIR", "/opt/airflow/data/unified_stage"))
DEFAULT_UNIFIED_AGENT_DIR = Path(os.environ.get("UNIFIED_AGENT_DIR", "/opt/airflow/unified-agent"))
STAGE_FILENAME = "staged_chunks.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("unified_ingest")

SUPPORTED_EXTENSIONS = {
    ".pdf", ".ppt", ".pptx", ".txt", ".md", ".docx",
    ".mp3", ".wav", ".m4a", ".mp4", ".mov", ".avi"
}


def resolve_unified_agent_path() -> Path:
    """Resolve the unified-agent root directory and add it to sys.path."""
    unified_root = DEFAULT_UNIFIED_AGENT_DIR
    if not unified_root.exists():
        alternate = Path(__file__).resolve().parents[1] / "unified-agent"
        if alternate.exists():
            unified_root = alternate

    if not unified_root.exists():
        raise FileNotFoundError(
            f"Unified agent root not found. Tried: {DEFAULT_UNIFIED_AGENT_DIR} and {alternate}"
        )

    sys.path.insert(0, str(unified_root))
    logger.info(f"Using unified-agent root: {unified_root}")
    return unified_root


def get_document_paths(source_dir: Path) -> List[Path]:
    """Return supported document/audio/video paths from a directory."""
    if not source_dir.exists() or not source_dir.is_dir():
        logger.warning(f"Source directory does not exist: {source_dir}")
        return []

    files = [
        path
        for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    files.sort()
    return files


def fingerprint_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_index_metadata(file_path: Path, chunk_index: int, chunk_text: str, source_type: str) -> Dict[str, str]:
    return {
        "chunk_id": f"{file_path.name}_{chunk_index}",
        "fingerprint": fingerprint_text(chunk_text),
        "text": chunk_text,
        "source": file_path.name,
        "type": source_type,
        "location": str(file_path.parent),
    }


def stage_file_path(stage_dir: Path) -> Path:
    stage_dir.mkdir(parents=True, exist_ok=True)
    return stage_dir / STAGE_FILENAME


def write_stage_chunks(stage_dir: Path, chunks: List[Dict[str, str]]) -> None:
    stage_path = stage_file_path(stage_dir)
    with open(stage_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    logger.info(f"✓ Wrote {len(chunks)} staged chunks to {stage_path}")


def load_stage_chunks(stage_dir: Path) -> List[Dict[str, str]]:
    stage_path = stage_file_path(stage_dir)
    if not stage_path.exists():
        logger.error(f"Stage file not found: {stage_path}")
        return []
    with open(stage_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    logger.info(f"✓ Loaded {len(chunks)} staged chunks from {stage_path}")
    return chunks


def load_existing_fingerprints(faiss_manager) -> set:
    return {
        meta.get("fingerprint")
        for meta in getattr(faiss_manager, "metadata", [])
        if meta.get("fingerprint")
    }


def stage_documents(
    input_dir: Path = DEFAULT_INPUT_DIR,
    stage_dir: Path = DEFAULT_STAGE_DIR,
) -> Dict[str, int]:
    """Extract document chunks and write them to a stage file."""
    resolve_unified_agent_path()
    from ingestion.unified_ingester import UnifiedIngester

    ingester = UnifiedIngester(language="fr", clean_text=True, extract_entities=True)
    source_files = get_document_paths(input_dir)

    if not source_files:
        logger.info(f"No supported files found in {input_dir}")
        return {"staged_chunks": 0, "processed_files": 0}

    logger.info(f"Found {len(source_files)} supported files to stage")

    staged_chunks: List[Dict[str, str]] = []
    processed_files = 0

    for file_path in source_files:
        logger.info(f"Staging file: {file_path}")
        try:
            result = ingester.ingest(file_path)
            if not result:
                logger.warning(f"Skipping file because ingestion failed: {file_path}")
                continue

            chunks, metadata = result
            for idx, chunk_text in enumerate(chunks):
                chunk_meta = build_index_metadata(file_path, idx, chunk_text, metadata.source_type.value)
                staged_chunks.append(chunk_meta)

            processed_files += 1
        except Exception as exc:
            logger.exception(f"Failed to stage {file_path}: {exc}")

    write_stage_chunks(stage_dir, staged_chunks)
    return {"staged_chunks": len(staged_chunks), "processed_files": processed_files}


def index_documents_from_stage(
    stage_dir: Path = DEFAULT_STAGE_DIR,
    skip_existing: bool = True,
    rebuild: bool = False,
) -> Dict[str, int]:
    """Load staged chunks from disk and index them into FAISS and BM25."""
    resolve_unified_agent_path()
    from config.settings import get_config
    from retrieval.embeddings import EmbeddingsManager
    from retrieval.faiss_manager import FAISSManager
    from retrieval.bm25_manager import BM25Manager

    config = get_config()
    logger.info("Initializing index managers for stage indexing...")

    embeddings = EmbeddingsManager(
        model_name=config.embeddings.MODEL_NAME,
        device=config.embeddings.DEVICE,
    )
    faiss_mgr = FAISSManager(config.paths.FAISS_INDEX_DIR, embedding_dim=embeddings.get_embedding_dim())
    bm25_mgr = BM25Manager(config.paths.BM25_INDEX_DIR)

    if rebuild:
        logger.info("Rebuilding indexes from scratch...")
        faiss_mgr.rebuild_from_scratch()
        bm25_mgr.rebuild_from_scratch()

    existing_fingerprints = load_existing_fingerprints(faiss_mgr) if skip_existing else set()
    staged_chunks = load_stage_chunks(stage_dir)

    if not staged_chunks:
        logger.info("No staged chunks to index")
        return {"indexed_chunks": 0, "skipped_chunks": 0}

    new_texts: List[str] = []
    new_metadatas: List[Dict[str, str]] = []
    skipped_chunks = 0

    for chunk in staged_chunks:
        fingerprint = chunk.get("fingerprint")
        if skip_existing and fingerprint in existing_fingerprints:
            skipped_chunks += 1
            continue
        new_texts.append(chunk.get("text", ""))
        new_metadatas.append(chunk)
        existing_fingerprints.add(fingerprint)

    if new_texts:
        logger.info(f"Embedding {len(new_texts)} new chunks")
        batch_size = config.embeddings.BATCH_SIZE or 32
        embeddings_array = embeddings.embed_batch(new_texts, batch_size=batch_size)
        faiss_mgr.add_embeddings(embeddings_array, new_metadatas)
        bm25_mgr.add_documents(new_texts, new_metadatas)
        faiss_mgr.save()
        bm25_mgr.save()
        logger.info("Index update complete")

    return {
        "indexed_chunks": len(new_texts),
        "skipped_chunks": skipped_chunks,
    }


def ingest_all_documents(
    input_dir: Path = DEFAULT_INPUT_DIR,
    skip_existing: bool = True,
    rebuild: bool = False,
) -> Dict[str, Optional[int]]:
    """Ingest documents from input_dir and update unified-agent indexes."""
    resolve_unified_agent_path()

    from ingestion.unified_ingester import UnifiedIngester
    from config.settings import get_config
    from retrieval.embeddings import EmbeddingsManager
    from retrieval.faiss_manager import FAISSManager
    from retrieval.bm25_manager import BM25Manager

    config = get_config()
    logger.info("Initializing UnifiedIngester and index managers...")

    ingester = UnifiedIngester(language="fr", clean_text=True, extract_entities=True)
    embeddings = EmbeddingsManager(
        model_name=config.embeddings.MODEL_NAME,
        device=config.embeddings.DEVICE,
    )
    faiss_mgr = FAISSManager(config.paths.FAISS_INDEX_DIR, embedding_dim=embeddings.get_embedding_dim())
    bm25_mgr = BM25Manager(config.paths.BM25_INDEX_DIR)

    if rebuild:
        logger.info("Rebuilding indexes from scratch...")
        faiss_mgr.rebuild_from_scratch()
        bm25_mgr.rebuild_from_scratch()

    existing_fingerprints = load_existing_fingerprints(faiss_mgr) if skip_existing else set()
    source_files = get_document_paths(input_dir)

    if not source_files:
        logger.info(f"No supported files found in {input_dir}")
        return {"new_chunks": 0, "processed_files": 0}

    logger.info(f"Found {len(source_files)} supported files to ingest")

    new_texts: List[str] = []
    new_metadatas: List[Dict[str, str]] = []
    processed_files = 0
    skipped_files = 0

    for file_path in source_files:
        logger.info(f"Ingesting file: {file_path}")
        try:
            result = ingester.ingest(file_path)
            if not result:
                logger.warning(f"Skipping file because ingestion failed: {file_path}")
                continue

            chunks, metadata = result
            if not chunks:
                logger.warning(f"No chunks returned for: {file_path}")
                continue

            new_chunks = 0
            for idx, chunk_text in enumerate(chunks):
                fingerprint = fingerprint_text(chunk_text)
                if skip_existing and fingerprint in existing_fingerprints:
                    continue
                chunk_meta = build_index_metadata(file_path, idx, chunk_text, metadata.source_type.value)
                new_texts.append(chunk_text)
                new_metadatas.append(chunk_meta)
                existing_fingerprints.add(fingerprint)
                new_chunks += 1

            if new_chunks == 0:
                skipped_files += 1
                logger.info(f"All chunks already indexed for {file_path}")
            else:
                logger.info(f"Added {new_chunks} new chunks for {file_path}")

            processed_files += 1

        except Exception as exc:
            logger.exception(f"Failed to ingest {file_path}: {exc}")

    if new_texts:
        logger.info(f"Embedding {len(new_texts)} new chunks")
        batch_size = config.embeddings.BATCH_SIZE or 32
        embeddings_array = embeddings.embed_batch(new_texts, batch_size=batch_size)
        faiss_mgr.add_embeddings(embeddings_array, new_metadatas)
        bm25_mgr.add_documents(new_texts, new_metadatas)
        faiss_mgr.save()
        bm25_mgr.save()
        logger.info("Index update complete")
    else:
        logger.info("No new chunks to add to indexes")

    return {
        "new_chunks": len(new_texts),
        "processed_files": processed_files,
        "skipped_files": skipped_files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified Agent ingestion helper for Airflow")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--stage",
        action="store_true",
        help="Stage extracted document chunks to disk without indexing",
    )
    group.add_argument(
        "--index",
        action="store_true",
        help="Index staged chunks from disk into FAISS and BM25",
    )
    group.add_argument(
        "--ingest",
        action="store_true",
        help="Run the full ingest + index workflow in a single step",
    )

    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Source directory containing documents to ingest",
    )
    parser.add_argument(
        "--stage-dir",
        type=Path,
        default=DEFAULT_STAGE_DIR,
        help="Directory to store or read staged document chunks",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Do not skip already indexed chunks by fingerprint",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild indexes from scratch before ingesting",
    )

    args = parser.parse_args()

    if args.stage:
        result = stage_documents(input_dir=args.input_dir, stage_dir=args.stage_dir)
    elif args.index:
        result = index_documents_from_stage(
            stage_dir=args.stage_dir,
            skip_existing=not args.no_skip_existing,
            rebuild=args.rebuild,
        )
    else:
        result = ingest_all_documents(
            input_dir=args.input_dir,
            skip_existing=not args.no_skip_existing,
            rebuild=args.rebuild,
        )

    logger.info(f"Result: {result}")
    return 0 if any(value for value in result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
