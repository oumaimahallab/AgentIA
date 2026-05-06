#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
semantic_chunker_llamaindex.py — ChronoBrain Semantic Chunking Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WHAT CHANGED FROM semantic_chunker.py:
  The chunking stage now uses LlamaIndex SemanticSplitterNodeParser
  instead of the manual numpy cosine similarity loop.

  SemanticSplitterNodeParser works like this internally:
    1. Splits text into sentences using sentence-splitters (spacy/nltk/regex)
    2. Embeds each sentence with YOUR local model (multilingual-e5-base)
    3. Computes similarity between consecutive sentences
    4. Places a chunk boundary where similarity drops below a percentile threshold
       (breakpoint_percentile_threshold=95 means: split at the 5% most
        dissimilar transitions — only the sharpest topic shifts)

  The key advantage over the manual loop:
    - Uses a PERCENTILE threshold, not an absolute one
      → adapts to each document's similarity distribution
      → no need to tune a magic number per file
    - Has a buffer_size parameter: instead of comparing sentence[i] vs sentence[i+1],
      it compares sentence[i] vs sentence[i+buffer_size]
      → less sensitive to single noisy/short sentences in transcripts

WHAT STAYS THE SAME (kept from semantic_chunker.py):
  - _reassemble_paragraphs()  ← timestamp-gap paragraph reassembly
  - clean_text()              ← all regex cleaning (fillers, stuttering, etc.)
  - load_txt_file()           ← .txt file loader
  - load_xlsx_file()          ← Excel file loader
  - save_output()             ← JSON + CSV output
  - log_performance()         ← Excel performance log

INSTALL:
  pip install llama-index
  pip install llama-index-embeddings-huggingface
  pip install sentence-transformers
  pip install numpy pandas openpyxl

USAGE:
  python semantic_chunker_llamaindex.py
  python semantic_chunker_llamaindex.py --data-dir ./transcripts
  python semantic_chunker_llamaindex.py --percentile 90   # more chunks
  python semantic_chunker_llamaindex.py --percentile 97   # fewer chunks
  python semantic_chunker_llamaindex.py --dry-run         # clean only, no chunking
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

class Config:
    # ── Paths ─────────────────────────────────────────────────────────────────
    DATA_DIR       = "../data/transcripts"
    OUTPUT_DIR     = "../data/chunks_v14"
    LOG_EXCEL_PATH = "../data/logs/performance_logs.xlsx"

    # ── Embedding model (LOCAL — no API needed) ───────────────────────────────
    # Runs entirely on your machine with sentence-transformers.
    # multilingual-e5-base handles French, English, and mixed transcripts.
    EMBEDDING_MODEL = "intfloat/multilingual-e5-base"

    # ── LlamaIndex SemanticSplitterNodeParser parameters ─────────────────────
    #
    # breakpoint_percentile_threshold:
    #   The splitter computes similarity between ALL consecutive sentence pairs,
    #   then places boundaries at the LOWEST X% similarity transitions.
    #   95 = split only at the 5% sharpest topic shifts (fewer, larger chunks)
    #   90 = split at the 10% sharpest shifts (more chunks, finer granularity)
    #   85 = even finer — good for dense technical content
    #   Recommended for Chronotime transcripts: 92-95
    BREAKPOINT_PERCENTILE = 95

    #
    # buffer_size:
    #   Instead of comparing sentence[i] vs sentence[i+1],
    #   compares sentence[i] vs sentence[i + buffer_size].
    #   buffer_size=1 = compare direct neighbours (default, most sensitive)
    #   buffer_size=2 = skip one sentence (more robust to single short sentences)
    #   For noisy speech transcripts, buffer_size=1 works well after cleaning.
    BUFFER_SIZE = 1

    # ── Timestamp gap (seconds) that signals a paragraph break ───────────────
    TIMESTAMP_GAP_SECONDS = 8

    # ── Output ────────────────────────────────────────────────────────────────
    MODEL_TAG = "llama_semantic_chunker_v1"


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("chunker")


# ══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Chunk:
    chunk_id:    str
    source_file: str
    text:        str
    word_count:  int
    char_count:  int
    position:    int
    method:      str = "llama_semantic"
    metadata:    dict = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1 — LOAD + REASSEMBLE
# (kept exactly from semantic_chunker.py)
# ══════════════════════════════════════════════════════════════════════════════

def _parse_timestamp(ts: str) -> Optional[float]:
    ts = ts.strip("[] ")
    if "->" in ts:
        ts = ts.split("->")[0].strip()
    parts = ts.split(":")
    try:
        parts = [float(p) for p in parts]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    except ValueError:
        pass
    return None


def _reassemble_paragraphs(lines: list[str]) -> list[str]:
    """
    Join mid-sentence audio segments back into complete paragraphs.

    Each .txt line = one 6-8 second audio segment (NOT a sentence).
    68% of lines end mid-sentence in Chronotime transcripts.
    We join consecutive lines until either:
      a) a sentence-ending punctuation (.!?) AND timestamp gap > 2s, or
      b) timestamp gap > TIMESTAMP_GAP_SECONDS (silence = topic pause)

    This produces paragraph-level units — the right input for SemanticSplitter.
    """
    TS_PATTERN = re.compile(
        r"^\[?(\d{1,2}:\d{2}(?::\d{2})?(?:\s*->\s*\d{1,2}:\d{2}(?::\d{2})?)?)\]?\s*"
    )

    segments: list[tuple[float, str]] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        m = TS_PATTERN.match(line)
        if m:
            text = line[m.end():].strip()
            secs = _parse_timestamp(m.group(1)) or 0.0
        else:
            text = line
            secs = segments[-1][0] if segments else 0.0
        if text:
            segments.append((secs, text))

    if not segments:
        return []

    paragraphs: list[str] = []
    buffer: list[str] = []
    prev_sec = segments[0][0]

    for sec, text in segments:
        gap = sec - prev_sec
        new_para = False
        if gap > Config.TIMESTAMP_GAP_SECONDS:
            new_para = True
        elif buffer and buffer[-1][-1:] in ".!?" and gap > 2:
            new_para = True

        if new_para and buffer:
            paragraphs.append(" ".join(buffer))
            buffer = [text]
        else:
            buffer.append(text)
        prev_sec = sec

    if buffer:
        paragraphs.append(" ".join(buffer))

    return paragraphs


def load_txt_file(file_path: Path) -> list[str]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        log.error("Cannot read %s: %s", file_path.name, e)
        return []
    lines = text.splitlines()
    paragraphs = _reassemble_paragraphs(lines)
    log.info("  %s → %d paragraphs from %d lines",
             file_path.name, len(paragraphs), len(lines))
    return paragraphs


def load_xlsx_file(file_path: Path) -> list[str]:
    try:
        df = pd.read_excel(file_path, dtype=str)
    except Exception as e:
        log.error("Cannot read Excel %s: %s", file_path.name, e)
        return []
    paragraphs = []
    for _, row in df.iterrows():
        parts = [str(v).strip() for v in row.values
                 if pd.notna(v) and str(v).strip()]
        if parts:
            paragraphs.append(" | ".join(parts))
    log.info("  %s → %d rows", file_path.name, len(paragraphs))
    return paragraphs


def load_data(data_dir: str) -> dict[str, list[str]]:
    base = Path(data_dir)
    if not base.exists():
        log.error("Data directory not found: %s", base)
        sys.exit(1)

    result: dict[str, list[str]] = {}
    txt_files  = sorted(base.glob("*.txt"))
    xlsx_files = sorted(base.glob("*.xlsx")) + sorted(base.glob("*.xls"))
    log.info("Found %d .txt + %d Excel files", len(txt_files), len(xlsx_files))

    for f in txt_files:
        paras = load_txt_file(f)
        if paras:
            result[f.name] = paras
    for f in xlsx_files:
        paras = load_xlsx_file(f)
        if paras:
            result[f.name] = paras

    total = sum(len(v) for v in result.values())
    log.info("Total paragraphs: %d from %d files\n", total, len(result))
    return result


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2 — CLEAN TEXT
# (kept exactly from semantic_chunker.py)
# ══════════════════════════════════════════════════════════════════════════════

_TERM_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bchrono\s*time\b",            re.I), "Chronotime"),
    (re.compile(r"\bchrono-time\b",               re.I), "Chronotime"),
    (re.compile(r"\bctime\b",                     re.I), "CTIME"),
    (re.compile(r"\bgt\s+module\b",               re.I), "Module GT"),
    (re.compile(r"\bmodule\s+gt\b",               re.I), "Module GT"),
    (re.compile(r"\bbadg[eé]age\b",               re.I), "badgeage"),
    (re.compile(r"\bwork\s*flow\b",               re.I), "workflow"),
    (re.compile(r"\bwork-flow\b",                 re.I), "workflow"),
    (re.compile(r"\bhabilitation[s]?\b",          re.I), "habilitations"),
    (re.compile(r"\bhabilitaton[s]?\b",           re.I), "habilitations"),
    (re.compile(r"\bcompteur[s]?\b",              re.I), "compteur"),
    (re.compile(r"\bv[ée]loris(?:er|ation|é)\b", re.I), "valoriser"),
    (re.compile(r"\bd[eé]mage\b",                 re.I), "démage"),
]

_FILLERS = re.compile(
    r"\b(euh+|uh+|um+|hmm+|hm+|bon\b|voil[àa]\b|donc\b|alors\b"
    r"|tu\s+sais|je\s+veux\s+dire|en\s+fait\b|quoi\b|hein\b|ben\b"
    r"|bah\b|ouais\b|pfff+|bref\b|enfin\b|genre\b)\b",
    re.IGNORECASE,
)

_STUTTER    = re.compile(r"\b(\w+(?:\s+\w+){0,2})((?:\s+\1){2,})\b", re.IGNORECASE)
_GREETING   = re.compile(
    r"^\s*(bonjour[^.!?]*|bonsoir[^.!?]*|bonne\s+journ[eé]e[^.!?]*"
    r"|au\s+revoir[^.!?]*|merci[^.!?]*|[àa]\s+bient[oô]t[^.!?]*)\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_TIMESTAMP  = re.compile(
    r"\[?\d{1,2}:\d{2}(?::\d{2})?(?:\s*->\s*\d{1,2}:\d{2}(?::\d{2})?)?\]?"
)
#_CROSSTALK  = re.compile(r"(\b\w+\b(?:[,\s]+\b\1\b){3,})", re.IGNORECASE)
# Group 1 captures the word. 
# Then we look for that same word (\1) repeated 3 or more times.
_CROSSTALK = re.compile(r"\b(\w+)\b(?:[,\s]+\1\b){3,}", re.IGNORECASE)

_ASR_JUNK   = re.compile(r"\b(campi|trée|l[''']imp|fassements|marocal)\b", re.IGNORECASE)


def clean_text(text: str) -> str:
    if not text or not text.strip():
        return ""
    text = _TIMESTAMP.sub(" ", text)
    text = _CROSSTALK.sub(lambda m: m.group(1).split(",")[0].strip(), text)
    text = _ASR_JUNK.sub("", text)
    for _ in range(2):
        text = _STUTTER.sub(r"\1", text)
    text = _FILLERS.sub(" ", text)
    for pattern, replacement in _TERM_MAP:
        text = pattern.sub(replacement, text)
    if _GREETING.match(text.strip()):
        return ""
    text = re.sub(r"([a-zà-ÿ])'(\s+)([a-zà-ÿ])", r"\1'\3", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = text.strip()
    if len(text.split()) < 8:
        return ""
    return text


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 3 — LLAMAINDEX SEMANTIC SPLITTER
# ══════════════════════════════════════════════════════════════════════════════

def _load_llama_components():
    """
    Load the LlamaIndex embedding wrapper and SemanticSplitterNodeParser.

    HuggingFaceEmbedding wraps sentence-transformers so LlamaIndex can use
    your local multilingual-e5-base model — no OpenAI API key needed.

    SemanticSplitterNodeParser does:
      1. sentence tokenisation (built-in or via nltk)
      2. embed every sentence with your local model
      3. compute consecutive-sentence similarity
      4. place boundaries at the lowest-similarity transitions
         (defined by breakpoint_percentile_threshold)
    """
    try:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        from llama_index.core.node_parser import SemanticSplitterNodeParser
    except ImportError:
        log.error(
            "LlamaIndex not installed. Run:\n"
            "  pip install llama-index llama-index-embeddings-huggingface"
        )
        sys.exit(1)

    log.info("Loading embedding model: %s", Config.EMBEDDING_MODEL)
    t0 = time.time()

    # HuggingFaceEmbedding wraps your local sentence-transformers model
    embed_model = HuggingFaceEmbedding(
        model_name=Config.EMBEDDING_MODEL,
        # multilingual-e5 requires "passage: " prefix for documents
        query_instruction="query: ",
        text_instruction="passage: ",
    )

    log.info("Model loaded in %.1fs", time.time() - t0)

    # SemanticSplitterNodeParser — the LlamaIndex semantic chunker
    splitter = SemanticSplitterNodeParser(
        embed_model=embed_model,

        # How many sentence neighbours to compare when measuring similarity.
        # buffer_size=1: compare sentence[i] vs sentence[i+1] (default)
        # buffer_size=2: compare sentence[i] vs sentence[i+2]
        # For noisy transcripts, 1 works well after cleaning.
        buffer_size=Config.BUFFER_SIZE,

        # Where to place chunk boundaries.
        # The splitter computes all consecutive-sentence similarity scores,
        # then splits at the LOWEST percentile scores.
        # 95 = only the 5% sharpest topic shifts become boundaries
        # 90 = the 10% sharpest shifts (more, smaller chunks)
        breakpoint_percentile_threshold=Config.BREAKPOINT_PERCENTILE,
    )

    return splitter


def chunk_with_llama(splitter, text: str, source_name: str) -> list[str]:
    """
    Run LlamaIndex SemanticSplitterNodeParser on one cleaned text.

    The splitter works with LlamaIndex Document objects —
    we wrap the text, run the splitter, then extract the node texts.

    Returns a list of chunk strings (each is a semantically coherent group
    of sentences, as determined by the embedding similarity).
    """
    try:
        from llama_index.core import Document
    except ImportError:
        log.error("pip install llama-index")
        sys.exit(1)

    if not text or not text.strip():
        return []

    # Wrap text in a LlamaIndex Document
    doc = Document(text=text, metadata={"source": source_name})

    # Run the semantic splitter
    # get_nodes_from_documents returns a list of TextNode objects
    nodes = splitter.get_nodes_from_documents([doc])

    # Extract clean text from each node
    chunks = []
    for node in nodes:
        chunk_text = node.get_content().strip()
        chunk_text = re.sub(r"\s+", " ", chunk_text)
        if chunk_text and len(chunk_text.split()) >= 8:
            chunks.append(chunk_text)

    return chunks


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 4 — OUTPUT
# ══════════════════════════════════════════════════════════════════════════════

def make_chunk_id(source: str, position: int, text: str) -> str:
    h = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    s = re.sub(r"[^\w]", "_", Path(source).stem)[:30]
    return f"{s}_{position:04d}_{h}"


def save_output(chunks: list[Chunk], output_dir: str) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = out / "chunks.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump([asdict(c) for c in chunks], f, ensure_ascii=False, indent=2)
    log.info("  JSON → %s  (%d chunks)", json_path, len(chunks))

    # CSV
    csv_path = out / "chunks_v14.csv"
    fields   = ["chunk_id", "source_file", "word_count", "char_count",
                "position", "method", "text"]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for c in chunks:
            row = asdict(c)
            row.pop("metadata", None)
            w.writerow(row)
    log.info("  CSV  → %s", csv_path)


def log_performance(question: str, answer: str, response_time: float) -> None:
    log_path = Path(Config.LOG_EXCEL_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    new_row = pd.DataFrame({
        "Timestamp":         [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        "Model":             [Config.MODEL_TAG],
        "Question":          [question],
        "Answer":            [answer],
        "Response Time (s)": [round(response_time, 3)],
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
        log.warning("Could not write Excel log: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def run(data_dir: str, output_dir: str,
        percentile: int, dry_run: bool = False) -> list[Chunk]:

    Config.BREAKPOINT_PERCENTILE = percentile
    t_start = time.time()

    # ── Load ──────────────────────────────────────────────────────────────────
    log.info("━━ Stage 1: Load + reassemble paragraphs")
    raw_data = load_data(data_dir)

    # ── Clean ─────────────────────────────────────────────────────────────────
    log.info("━━ Stage 2: Clean text")
    cleaned_data: dict[str, str] = {}   # filename → one big cleaned string
    total_raw = total_kept = 0

    for filename, paragraphs in raw_data.items():
        cleaned_paragraphs = []
        for para in paragraphs:
            c = clean_text(para)
            if c:
                cleaned_paragraphs.append(c)
        total_raw  += len(paragraphs)
        total_kept += len(cleaned_paragraphs)

        if cleaned_paragraphs:
            # Join all cleaned paragraphs into one document per file.
            # SemanticSplitterNodeParser works best on a continuous text —
            # it finds boundaries across paragraph joins too.
            cleaned_data[filename] = "\n\n".join(cleaned_paragraphs)

    log.info("  %d → %d paragraphs after cleaning (%.0f%% kept)\n",
             total_raw, total_kept, 100 * total_kept / max(1, total_raw))

    if dry_run:
        log.info("Dry-run: stopping before LlamaIndex. Cleaned %d files.", len(cleaned_data))
        for fname, text in list(cleaned_data.items())[:2]:
            log.info("  Sample (%s): '%s ...'", fname, text[:120])
        return []

    # ── Load LlamaIndex splitter ──────────────────────────────────────────────
    log.info("━━ Stage 3: Loading LlamaIndex SemanticSplitterNodeParser")
    log.info("  Embedding model  : %s (local, no API)", Config.EMBEDDING_MODEL)
    log.info("  Buffer size      : %d", Config.BUFFER_SIZE)
    log.info("  Breakpoint pct   : %d  (split at %d%% sharpest transitions)\n",
             Config.BREAKPOINT_PERCENTILE,
             100 - Config.BREAKPOINT_PERCENTILE)

    splitter = _load_llama_components()

    # ── Chunk ─────────────────────────────────────────────────────────────────
    log.info("━━ Stage 4: Semantic chunking")
    all_chunks: list[Chunk] = []

    for filename, full_text in cleaned_data.items():
        log.info("  Chunking: %s  (%d words)", filename, len(full_text.split()))

        t0 = time.time()
        chunk_texts = chunk_with_llama(splitter, full_text, filename)
        elapsed = time.time() - t0

        log.info("    → %d chunks in %.1fs", len(chunk_texts), elapsed)

        for pos, text in enumerate(chunk_texts):
            cid = make_chunk_id(filename, pos, text)
            all_chunks.append(Chunk(
                chunk_id    = cid,
                source_file = filename,
                text        = text,
                word_count  = len(text.split()),
                char_count  = len(text),
                position    = pos,
                method      = "llama_semantic",
                metadata    = {
                    "breakpoint_percentile": Config.BREAKPOINT_PERCENTILE,
                    "buffer_size":           Config.BUFFER_SIZE,
                    "embedding_model":       Config.EMBEDDING_MODEL,
                },
            ))

    # ── Stats ─────────────────────────────────────────────────────────────────
    t_total = time.time() - t_start
    if all_chunks:
        wcs = [c.word_count for c in all_chunks]
        log.info("\n━━ Done")
        log.info("  Total chunks     : %d", len(all_chunks))
        log.info("  Avg words/chunk  : %.0f", sum(wcs) / len(wcs))
        log.info("  Min / Max words  : %d / %d", min(wcs), max(wcs))
        log.info("  Total time       : %.1fs", t_total)

        # Word-count distribution
        bins = [(0,50),(50,150),(150,300),(300,500),(500,99999)]
        labels = ["<50","50-150","150-300","300-500",">500"]
        for (lo,hi), label in zip(bins, labels):
            n = sum(1 for w in wcs if lo <= w < hi)
            bar = "█" * (n * 30 // max(1,len(wcs)))
            log.info("  %7s words : %4d  %s", label, n, bar)

    # ── Save ──────────────────────────────────────────────────────────────────
    log.info("\n━━ Saving output to %s", output_dir)
    save_output(all_chunks, output_dir)

    log_performance(
        question      = f"Chunked {len(cleaned_data)} files with LlamaIndex",
        answer        = f"{len(all_chunks)} semantic chunks (breakpoint={Config.BREAKPOINT_PERCENTILE})",
        response_time = t_total,
    )

    return all_chunks


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ChronoBrain — LlamaIndex SemanticSplitterNodeParser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES
  python semantic_chunker_llamaindex.py
  python semantic_chunker_llamaindex.py --data-dir ./transcripts
  python semantic_chunker_llamaindex.py --percentile 90   # more chunks
  python semantic_chunker_llamaindex.py --percentile 97   # fewer chunks
  python semantic_chunker_llamaindex.py --dry-run         # clean only, no LLM

TUNING breakpoint_percentile:
  95 (default) → split only at the 5% sharpest topic shifts  → ~300-500 word chunks
  92           → split at the 8% sharpest shifts              → ~200-400 word chunks
  88           → split at the 12% sharpest shifts             → ~100-300 word chunks
  Start with 95, look at output chunk sizes, adjust down if chunks are too big.

OUTPUT FILES:
  ../data/chunks/chunks.json   — full structured chunks (use with chronobrain_rag.py)
  ../data/chunks/chunks.csv    — flat CSV for inspection
        """,
    )
    parser.add_argument("--data-dir",   "-d", default=Config.DATA_DIR)
    parser.add_argument("--output-dir", "-o", default=Config.OUTPUT_DIR)
    parser.add_argument("--percentile", "-p", type=int,
                        default=Config.BREAKPOINT_PERCENTILE,
                        help="Breakpoint percentile (default 95, lower = more chunks)")
    parser.add_argument("--buffer",     "-b", type=int, default=Config.BUFFER_SIZE,
                        help="Sentence comparison buffer (default 1)")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Clean only — no LlamaIndex, no output written")
    args = parser.parse_args()

    Config.BUFFER_SIZE = args.buffer

    log.info("ChronoBrain — LlamaIndex Semantic Chunker")
    log.info("Data dir    : %s", args.data_dir)
    log.info("Output dir  : %s", args.output_dir)
    log.info("Percentile  : %d", args.percentile)
    log.info("Buffer size : %d", args.buffer)
    log.info("Dry-run     : %s\n", args.dry_run)

    chunks = run(
        data_dir   = args.data_dir,
        output_dir = args.output_dir,
        percentile = args.percentile,
        dry_run    = args.dry_run,
    )

    if chunks:
        print()
        print("=" * 60)
        print(f"  {len(chunks)} chunks → {args.output_dir}")
        print()
        print("  Next step — run the RAG chatbot:")
        print("    python chronobrain_rag.py --chunks ../data/chunks/chunks.json --rebuild")
        print("=" * 60)


if __name__ == "__main__":
    main()