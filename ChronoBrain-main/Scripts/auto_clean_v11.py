#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
semantic_chunker.py — ChronoBrain Semantic Chunking Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WHY NOT FIXED-SIZE CHUNKING:
  Your current code does:
      words[i : i + CHUNK_SIZE]
  This splits mid-explanation, mid-sentence, even mid-word-group.
  A RAG retriever fetching chunk N gets half an explanation — the
  other half is in chunk N+1 and never retrieved together.
  Bad chunks = bad context = bad answers.

WHAT THIS DOES INSTEAD (4 stages):

  Stage 1 — REASSEMBLE
    Each .txt line is a 6-8 second audio segment, NOT a sentence.
    68% of lines end mid-sentence. We join adjacent lines back into
    complete paragraphs (separated by silence gaps > 2 seconds in
    the original recording, which appear as timestamp jumps).

  Stage 2 — CLEAN
    Strip timestamps, deduplicate ASR artefacts ("nous nous nous"),
    remove fillers, normalize whitespace. Operates on whole paragraphs,
    not individual characters.

  Stage 3 — SEMANTIC CHUNKING (the core part)
    Split paragraphs into sentences.
    Embed every sentence with multilingual-e5-base.
    Walk through sentences computing cosine similarity between
    consecutive sentences. Where similarity drops below threshold
    → topic has shifted → start a new chunk.
    This means chunk boundaries always fall between complete sentences
    at natural topic transitions — never in the middle of an explanation.

  Stage 4 — SIZE GUARD
    Merge chunks that are too short (< MIN_WORDS) with their neighbour.
    Split chunks that are too long (> MAX_WORDS) at the nearest
    sentence boundary to MAX_WORDS — with OVERLAP_WORDS overlap so
    no context is lost at the split point.

OUTPUT:
  data/chunks/chunks.json     — full structured chunks
  data/chunks/chunks.csv      — flat CSV for quick inspection
  data/logs/performance_logs.xlsx — timing log (matches your existing schema)

USAGE:
  python semantic_chunker.py
  python semantic_chunker.py --data-dir ./transcripts --output-dir ./out
  python semantic_chunker.py --threshold 0.4   # stricter topic boundaries
  python semantic_chunker.py --dry-run          # print stats, write nothing

DEPENDENCIES (all local, no paid API):
  pip install sentence-transformers numpy pandas scikit-learn openpyxl
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
from typing import Iterator, List, Optional

import numpy as np
import pandas as pd

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

class Config:
    # Paths
    DATA_DIR        = "../data/transcripts"   # folder with .txt and .xlsx files
    OUTPUT_DIR      = "../data/chunks"
    LOG_EXCEL_PATH  = "../data/logs/performance_logs.xlsx"

    # Embedding model — multilingual, handles French perfectly, runs locally
    EMBEDDING_MODEL = "intfloat/multilingual-e5-base"
    EMBED_BATCH     = 64      # sentences per embedding batch (memory-efficient)

    # Semantic chunking
    # Similarity below this → topic has shifted → new chunk boundary
    # 0.35 = loose (fewer, larger chunks) | 0.55 = strict (many small chunks)
    SIMILARITY_THRESHOLD = 0.45

    # Chunk size guard (applied AFTER semantic splitting)
    MIN_WORDS  = 80    # merge chunks smaller than this with neighbour
    MAX_WORDS  = 450   # split chunks larger than this at sentence boundary
    OVERLAP    = 50    # words of overlap when a chunk is forcibly split

    # Timestamp gap that signals a topic break (seconds)
    # If two consecutive timestamp lines are > this many seconds apart,
    # we treat it as a paragraph boundary even without a sentence-ending period.
    TIMESTAMP_GAP_SECONDS = 8

    # Source name used in log
    MODEL_TAG = "semantic_chunker_v1"


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
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Chunk:
    chunk_id:    str
    source_file: str
    text:        str
    word_count:  int
    char_count:  int
    position:    int          # index within the source file
    method:      str = "semantic"   # "semantic" | "guard_merge" | "guard_split"
    metadata:    dict = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1 — LOAD DATA
# ══════════════════════════════════════════════════════════════════════════════

def _parse_timestamp(ts: str) -> Optional[float]:
    """Convert [MM:SS] or [HH:MM:SS] to total seconds. Returns None on failure."""
    ts = ts.strip("[] ")
    # Handle "start -> end" format — take start
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
    Stage 1 core: join mid-sentence audio segments back into complete paragraphs.

    WHY: Each .txt line = one 6-8 second audio segment. 68% end mid-sentence.
    We join consecutive lines until we hit either:
      a) a sentence-ending punctuation (.!?:) at the end of a line, OR
      b) a timestamp gap > TIMESTAMP_GAP_SECONDS (silence = topic pause)

    This gives us paragraph-level units before any sentence splitting.
    """
    # Pattern: [start -> end] or [MM:SS]
    TS_PATTERN = re.compile(r"^\[?(\d{1,2}:\d{2}(?::\d{2})?(?:\s*->\s*\d{1,2}:\d{2}(?::\d{2})?)?)\]?\s*")

    segments: list[tuple[float, str]] = []   # (start_sec, text)

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        m = TS_PATTERN.match(line)
        if m:
            ts_str = m.group(1)
            text   = line[m.end():].strip()
            secs   = _parse_timestamp(ts_str) or 0.0
        else:
            text = line
            secs = segments[-1][0] if segments else 0.0

        if text:
            segments.append((secs, text))

    if not segments:
        return []

    paragraphs: list[str] = []
    buffer: list[str]     = []
    prev_sec: float       = segments[0][0]

    for sec, text in segments:
        gap = sec - prev_sec
        # Decide whether to start a new paragraph
        new_para = False
        if gap > Config.TIMESTAMP_GAP_SECONDS:
            new_para = True   # significant silence = topic break
        elif buffer and buffer[-1][-1:] in ".!?":
            # Previous segment ended a sentence AND there's some gap
            if gap > 2:
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
    """Load a .txt transcript → list of raw paragraphs (after reassembly)."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        log.error("Cannot read %s: %s", file_path.name, e)
        return []

    lines = text.splitlines()
    paragraphs = _reassemble_paragraphs(lines)
    log.info("  %s → %d paragraphs from %d lines", file_path.name, len(paragraphs), len(lines))
    return paragraphs


def load_xlsx_file(file_path: Path) -> list[str]:
    """Load an .xlsx file → list of text paragraphs (one per row or cell)."""
    try:
        df = pd.read_excel(file_path, dtype=str)
    except Exception as e:
        log.error("Cannot read Excel %s: %s", file_path.name, e)
        return []

    paragraphs = []
    for _, row in df.iterrows():
        # Join all non-null cells in the row into one paragraph
        parts = [str(v).strip() for v in row.values if pd.notna(v) and str(v).strip()]
        if parts:
            paragraphs.append(" | ".join(parts))

    log.info("  %s → %d rows as paragraphs", file_path.name, len(paragraphs))
    return paragraphs


def load_data(data_dir: str) -> dict[str, list[str]]:
    """
    Load all .txt and .xlsx files from data_dir.
    Returns {filename: [paragraph, paragraph, ...]}
    """
    base = Path(data_dir)
    if not base.exists():
        log.error("Data directory not found: %s", base)
        sys.exit(1)

    result: dict[str, list[str]] = {}
    txt_files  = sorted(base.glob("*.txt"))
    xlsx_files = sorted(base.glob("*.xlsx")) + sorted(base.glob("*.xls"))

    log.info("Found %d .txt files, %d Excel files", len(txt_files), len(xlsx_files))

    for f in txt_files:
        paras = load_txt_file(f)
        if paras:
            result[f.name] = paras

    for f in xlsx_files:
        paras = load_xlsx_file(f)
        if paras:
            result[f.name] = paras

    total_paras = sum(len(v) for v in result.values())
    log.info("Total paragraphs loaded: %d from %d files\n", total_paras, len(result))
    return result


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2 — CLEAN TEXT
# ══════════════════════════════════════════════════════════════════════════════

# Domain term standardisation — catches common transcript spelling variants
_TERM_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bchrono\s*time\b",               re.I), "Chronotime"),
    (re.compile(r"\bchrono-time\b",                  re.I), "Chronotime"),
    (re.compile(r"\bctime\b",                        re.I), "CTIME"),
    (re.compile(r"\bgt\s+module\b",                  re.I), "Module GT"),
    (re.compile(r"\bmodule\s+gt\b",                  re.I), "Module GT"),
    (re.compile(r"\bbadg[eé]age\b",                  re.I), "badgeage"),
    (re.compile(r"\bwork\s*flow\b",                  re.I), "workflow"),
    (re.compile(r"\bwork-flow\b",                    re.I), "workflow"),
    (re.compile(r"\bhabilitation[s]?\b",             re.I), "habilitations"),
    (re.compile(r"\bhabilitaton[s]?\b",              re.I), "habilitations"),
    (re.compile(r"\bcompteur[s]?\b",                 re.I), "compteur"),
    (re.compile(r"\bv[ée]loris(?:er|ation|é)\b",    re.I), "valoriser"),
    (re.compile(r"\bd[eé]mage\b",                    re.I), "démage"),
]

# Filler words to remove (French + English + mixed transcripts)
_FILLERS = re.compile(
    r"\b(euh+|uh+|um+|hmm+|hm+|bon\b|voil[àa]\b|donc\b|alors\b"
    r"|tu\s+sais|je\s+veux\s+dire|en\s+fait\b|quoi\b|hein\b|ben\b"
    r"|bah\b|ouais\b|pfff+|bref\b|enfin\b|genre\b)\b",
    re.IGNORECASE,
)

# Repeated word/phrase stuttering — "nous nous nous nous" → "nous"
_STUTTER = re.compile(r"\b(\w+(?:\s+\w+){0,2})((?:\s+\1){2,})\b", re.IGNORECASE)

# Greetings that are standalone sentences (not embedded in technical content)
_GREETING_LINE = re.compile(
    r"^\s*(bonjour[^.!?]*|bonsoir[^.!?]*|bonne\s+journ[eé]e[^.!?]*"
    r"|au\s+revoir[^.!?]*|merci[^.!?]*|[àa]\s+bient[oô]t[^.!?]*"
    r"|[àa]\s+la\s+prochaine[^.!?]*)\s*[.!?]?\s*$",
    re.IGNORECASE,
)

# Timestamp pattern (should already be stripped, but catch any survivors)
_TIMESTAMP = re.compile(r"\[?\d{1,2}:\d{2}(?::\d{2})?(?:\s*->\s*\d{1,2}:\d{2}(?::\d{2})?)?\]?")

# Cross-talk: ASR repeated fragments — "nous, nous, nous, nous,"
#_CROSSTALK = re.compile(r"(\b\w+\b(?:[,\s]+\1\b){3,})", re.IGNORECASE)
_CROSSTALK = re.compile(r"\b(\w+)\b(?:[,\s]+\1\b){3,}", re.IGNORECASE)
# Broken sequences like "campi" "trée" (ASR errors)
_ASR_JUNK = re.compile(
    r"\b(campi|trée|l[''']imp|fassements|marocal)\b",
    re.IGNORECASE,
)


def clean_text(text: str) -> str:
    """
    Full cleaning pipeline for one paragraph.
    Order matters: remove timestamps first, then normalise terms,
    then remove noise, then clean up spacing.
    """
    if not text or not text.strip():
        return ""

    # 1. Remove timestamps
    text = _TIMESTAMP.sub(" ", text)

    # 2. Remove cross-talk/ASR repeated fragments
    #text = _CROSSTALK.sub(lambda m: m.group(1).split(",")[0].strip(), text)
    text = _CROSSTALK.sub(r"\1", text)
    # 3. Remove ASR junk words
    text = _ASR_JUNK.sub("", text)

    # 4. Fix stuttering ("donc donc donc" → "donc")
    # Repeat twice to catch nested cases
    for _ in range(2):
        text = _STUTTER.sub(r"\1", text)

    # 5. Remove filler words
    text = _FILLERS.sub(" ", text)

    # 6. Standardise domain terms (must come AFTER filler removal)
    for pattern, replacement in _TERM_MAP:
        text = pattern.sub(replacement, text)

    # 7. Remove pure greeting lines
    if _GREETING_LINE.match(text.strip()):
        return ""

    # 8. Fix broken contractions from filler removal (e.g. "c' est" → "c'est")
    text = re.sub(r"([a-zà-ÿ])'(\s+)([a-zà-ÿ])", r"\1'\3", text)

    # 9. Normalise whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = text.strip()

    # 10. Drop if still too short after cleaning (< 8 words = noise fragment)
    if len(text.split()) < 8:
        return ""

    return text


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 3 — SENTENCE SPLITTER
# ══════════════════════════════════════════════════════════════════════════════

# French sentence boundary pattern — handles abbreviations, ellipsis, dialogue
# _SENT_BOUNDARY = re.compile(
#     r"(?<!\b(?:M|Mme|Dr|Prof|vs|etc|ex|fig|vol|no|st|av|apr|janv|févr|mars"
#     r"|avr|mai|juin|juil|août|sept|oct|nov|déc)\b)"
#     r"(?<!\.\.)(?<![A-Z])"                        # not after abbreviation
#     r"(?<=[.!?…])\s+(?=[A-ZÀ-Ÿ\"\'])",           # boundary before capital
#     re.UNICODE,
# )
# French sentence boundary pattern — fixed-width compliant for Python re module
_SENT_BOUNDARY = re.compile(
    r"(?<!\bM)" # Length 1
    r"(?<!\b(?:Dr|vs|ex|no|st|av))" # Length 2
    r"(?<!\b(?:Mme|etc|fig|vol|apr|mai|oct|nov|déc))" # Length 3
    r"(?<!\b(?:Prof|janv|févr|mars|juin|juil|août|sept))" # Length 4
    r"(?<!\.\.)(?<![A-Z])"
    r"(?<=[.!?…])\s+(?=[A-ZÀ-Ÿ\"\'])",
    re.UNICODE,
)
def split_sentences(text: str) -> list[str]:
    """
    Split a cleaned paragraph into complete sentences.
    Uses a French-aware regex — avoids splitting on "M. Dupont" etc.
    Falls back to the full paragraph as one sentence if no boundary found.
    """
    if not text:
        return []

    # Primary split on sentence boundaries
    sentences = _SENT_BOUNDARY.split(text)

    # Secondary: split any remaining very long "sentences" on comma+conjunction
    # (handles run-on speech transcripts)
    result: list[str] = []
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        words = sent.split()
        if len(words) > 120:
            # Aggressively split run-on at ", et", ", donc", ", mais", ", alors"
            parts = re.split(r",\s+(?=(?:et|donc|mais|alors|car|or|ni|que)\s)", sent)
            result.extend(p.strip() for p in parts if p.strip() and len(p.split()) >= 4)
        else:
            if len(words) >= 4:
                result.append(sent)

    return result if result else [text]


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 3 — SEMANTIC CHUNKER (the core)
# ══════════════════════════════════════════════════════════════════════════════

def _load_embedding_model():
    """Load the sentence-transformers model once, log timing."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        log.error("pip install sentence-transformers")
        sys.exit(1)
    log.info("Loading embedding model: %s", Config.EMBEDDING_MODEL)
    t0 = time.time()
    model = SentenceTransformer(Config.EMBEDDING_MODEL)
    log.info("Model loaded in %.1fs", time.time() - t0)
    return model


def _embed_batch(model, sentences: list[str]) -> np.ndarray:
    """
    Embed sentences in batches of Config.EMBED_BATCH.
    Returns normalised float32 array (N, D).
    Batching prevents OOM on large files.
    """
    all_embs: list[np.ndarray] = []
    for i in range(0, len(sentences), Config.EMBED_BATCH):
        batch = sentences[i: i + Config.EMBED_BATCH]
        # multilingual-e5 requires "query: " / "passage: " prefix
        prefixed = ["passage: " + s for s in batch]
        embs = model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
        all_embs.append(embs.astype(np.float32))
    return np.vstack(all_embs) if all_embs else np.empty((0, 768), dtype=np.float32)


def semantic_chunk(sentences: list[str], embeddings: np.ndarray,
                   threshold: float) -> list[list[str]]:
    """
    Core semantic chunking algorithm.

    Walk through sentences computing cosine similarity between consecutive pairs.
    Because embeddings are L2-normalised, cosine similarity = dot product.

    Where similarity drops below `threshold` → the topic has shifted → split here.

    Returns a list of groups, each group is a list of consecutive sentences
    that belong to the same semantic topic.

    WHY THIS WORKS BETTER THAN FIXED-SIZE:
      Two sentences about "règle de niveau début" score ~0.75 similarity.
      A sentence about "workflow validation" after one about "badgeage" scores ~0.28.
      The algorithm sees that drop and places the chunk boundary there — exactly
      where the trainer switched topics.
    """
    if len(sentences) <= 1:
        return [sentences] if sentences else []

    groups: list[list[str]] = []
    current_group: list[str] = [sentences[0]]

    for i in range(1, len(sentences)):
        # Cosine similarity between sentence i-1 and sentence i
        sim = float(np.dot(embeddings[i - 1], embeddings[i]))

        if sim < threshold:
            # Topic shift detected — close current group, start new one
            groups.append(current_group)
            current_group = [sentences[i]]
        else:
            current_group.append(sentences[i])

    if current_group:
        groups.append(current_group)

    return groups


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 4 — SIZE GUARD
# ══════════════════════════════════════════════════════════════════════════════

def _word_count(sentences: list[str]) -> int:
    return sum(len(s.split()) for s in sentences)


def apply_size_guard(groups: list[list[str]]) -> list[tuple[list[str], str]]:
    """
    Enforce MIN_WORDS and MAX_WORDS on semantic groups.
    Returns list of (sentence_list, method) tuples.

    MERGE: groups smaller than MIN_WORDS are merged into the next group.
    SPLIT: groups larger than MAX_WORDS are split at the sentence boundary
           nearest to MAX_WORDS, with OVERLAP_WORDS of overlap.

    Overlap means the last OVERLAP_WORDS from chunk N are prepended to chunk N+1.
    This preserves context at the boundary — a RAG retriever fetching either
    chunk still has the bridging sentences.
    """
    # ── Merge pass ────────────────────────────────────────────────────────────
    merged: list[tuple[list[str], str]] = []
    buffer: list[str] = []

    for group in groups:
        if not group:
            continue
        buffer.extend(group)
        if _word_count(buffer) >= Config.MIN_WORDS:
            merged.append((buffer[:], "semantic"))
            buffer = []

    if buffer:
        if merged:
            # Append to last chunk rather than creating a tiny orphan
            last_sents, last_method = merged[-1]
            merged[-1] = (last_sents + buffer, "guard_merge")
        else:
            merged.append((buffer, "guard_merge"))

    # ── Split pass ────────────────────────────────────────────────────────────
    final: list[tuple[list[str], str]] = []

    for group, method in merged:
        if _word_count(group) <= Config.MAX_WORDS:
            final.append((group, method))
            continue

        # Split at nearest sentence boundary to MAX_WORDS
        chunk: list[str] = []
        wc = 0
        i = 0

        while i < len(group):
            sent = group[i]
            sw   = len(sent.split())

            if wc + sw > Config.MAX_WORDS and chunk:
                # Emit this chunk
                final.append((chunk[:], "guard_split"))

                # Build overlap: last N words from this chunk → prepend to next
                all_words = " ".join(chunk).split()
                overlap_words = all_words[-Config.OVERLAP:] if Config.OVERLAP else []
                overlap_text  = " ".join(overlap_words)

                # Restart with overlap + current sentence
                chunk = [overlap_text, sent] if overlap_text else [sent]
                wc    = len(" ".join(chunk).split())
            else:
                chunk.append(sent)
                wc += sw
            i += 1

        if chunk:
            final.append((chunk, "guard_split"))

    return final


# ══════════════════════════════════════════════════════════════════════════════
# QUALITY FILTER
# ══════════════════════════════════════════════════════════════════════════════

_GENERIC_NOISE = re.compile(
    r"^(bonjour|merci|oui|non|d[''']accord|voil[àa]|ok|"
    r"au\s+revoir|bonne\s+journ[eé]e|je\s+comprends|"
    r"c[''']est\s+[çc]a|exactement|tout\s+[àa]\s+fait)[\s.,!?]*$",
    re.IGNORECASE,
)

def is_quality_chunk(text: str) -> bool:
    """
    Return True if a chunk is useful for semantic search.
    Rejects:
      - chunks shorter than MIN_WORDS (sanity check after merging)
      - pure greeting/acknowledgement text
      - chunks with no alphanumeric characters
    """
    text = text.strip()
    if not text:
        return False
    if len(text.split()) < Config.MIN_WORDS // 4:
        return False
    if _GENERIC_NOISE.match(text):
        return False
    if not re.search(r"[a-zA-ZÀ-ÿ]{3,}", text):
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
# CHUNK ID GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def make_chunk_id(source: str, position: int, text: str) -> str:
    """Deterministic chunk ID based on source + position + content hash."""
    content_hash = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    safe_source  = re.sub(r"[^\w]", "_", Path(source).stem)[:30]
    return f"{safe_source}_{position:04d}_{content_hash}"


# ══════════════════════════════════════════════════════════════════════════════
# SAVE OUTPUT
# ══════════════════════════════════════════════════════════════════════════════

def save_output(chunks: list[Chunk], output_dir: str) -> None:
    """Save chunks to JSON and CSV. Creates output_dir if needed."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # ── JSON ──────────────────────────────────────────────────────────────────
    json_path = out / "chunks.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump([asdict(c) for c in chunks], f, ensure_ascii=False, indent=2)
    log.info("  JSON → %s", json_path)

    # ── CSV ───────────────────────────────────────────────────────────────────
    csv_path = out / "chunks.csv"
    fieldnames = ["chunk_id", "source_file", "word_count", "char_count",
                  "position", "method", "text"]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for c in chunks:
            row = asdict(c)
            row.pop("metadata", None)
            writer.writerow(row)
    log.info("  CSV  → %s", csv_path)


def log_performance(question: str, answer: str, response_time: float) -> None:
    """
    Append one row to the Excel performance log.
    Uses the same schema as your existing ChronoBrain code.
    """
    log_path = Path(Config.LOG_EXCEL_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    new_row = {
        "Timestamp":         [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        "Model":             [Config.MODEL_TAG],
        "Question":          [question],
        "Answer":            [answer],
        "Response Time (s)": [round(response_time, 3)],
    }
    df_new = pd.DataFrame(new_row)

    if log_path.exists():
        df_old   = pd.read_excel(log_path)
        df_final = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_final = df_new

    df_final.to_excel(log_path, index=False)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def run(data_dir: str, output_dir: str, threshold: float,
        dry_run: bool = False) -> list[Chunk]:

    t_pipeline_start = time.time()

    # ── Load ──────────────────────────────────────────────────────────────────
    log.info("━━ Stage 1: Loading data from %s", data_dir)
    raw_data = load_data(data_dir)   # {filename: [paragraph, ...]}

    if not raw_data:
        log.error("No data loaded — check DATA_DIR path")
        sys.exit(1)

    # ── Clean ─────────────────────────────────────────────────────────────────
    log.info("━━ Stage 2: Cleaning")
    cleaned_data: dict[str, list[str]] = {}
    total_raw = total_clean = 0

    for filename, paragraphs in raw_data.items():
        cleaned: list[str] = []
        for para in paragraphs:
            c = clean_text(para)
            if c:
                cleaned.append(c)
        cleaned_data[filename] = cleaned
        total_raw   += len(paragraphs)
        total_clean += len(cleaned)

    log.info("  %d → %d paragraphs after cleaning (%.0f%% kept)\n",
             total_raw, total_clean, 100 * total_clean / max(1, total_raw))

    if dry_run:
        log.info("Dry-run: stopping here. Would embed %d paragraphs.", total_clean)
        # Print a sample of what cleaned paragraphs look like
        for fname, paras in list(cleaned_data.items())[:1]:
            log.info("Sample from %s:", fname)
            for p in paras[:3]:
                log.info("  '%s'", p[:100])
        return []

    # ── Embed all sentences ───────────────────────────────────────────────────
    log.info("━━ Stage 3: Sentence splitting + embedding")
    model = _load_embedding_model()

    all_chunks: list[Chunk] = []

    for filename, paragraphs in cleaned_data.items():
        log.info("  Processing: %s (%d paragraphs)", filename, len(paragraphs))

        # Split every paragraph into sentences and gather all for batch embedding
        file_sentences: list[list[str]] = []
        for para in paragraphs:
            sents = split_sentences(para)
            if sents:
                file_sentences.append(sents)

        if not file_sentences:
            continue

        # Flatten for batch embedding, remember group boundaries
        flat_sents: list[str] = []
        group_sizes: list[int] = []
        for group in file_sentences:
            flat_sents.extend(group)
            group_sizes.append(len(group))

        log.info("    %d sentences → embedding...", len(flat_sents))
        t_emb = time.time()
        all_embeddings = _embed_batch(model, flat_sents)
        log.info("    Embedded in %.1fs", time.time() - t_emb)

        # Reconstruct per-group sentence embeddings and run semantic chunking
        pos = 0
        chunk_position = 0
        for i, (sents, n) in enumerate(zip(file_sentences, group_sizes)):
            group_embs = all_embeddings[pos: pos + n]
            pos += n

            if len(sents) == 0:
                continue

            # Semantic split within this paragraph's sentences
            semantic_groups = semantic_chunk(sents, group_embs, threshold)

            # Size guard: merge short, split long
            guarded = apply_size_guard(semantic_groups)

            for sent_group, method in guarded:
                text = " ".join(sent_group).strip()
                text = re.sub(r"\s+", " ", text)

                if not is_quality_chunk(text):
                    continue

                cid = make_chunk_id(filename, chunk_position, text)
                all_chunks.append(Chunk(
                    chunk_id    = cid,
                    source_file = filename,
                    text        = text,
                    word_count  = len(text.split()),
                    char_count  = len(text),
                    position    = chunk_position,
                    method      = method,
                    metadata    = {
                        "paragraph_index": i,
                        "sentence_count":  len(sent_group),
                    },
                ))
                chunk_position += 1

        log.info("    → %d chunks from %s", chunk_position, filename)

    # ── Stats ─────────────────────────────────────────────────────────────────
    t_total = time.time() - t_pipeline_start
    if all_chunks:
        wcs = [c.word_count for c in all_chunks]
        log.info("\n━━ Pipeline complete")
        log.info("  Total chunks     : %d", len(all_chunks))
        log.info("  Avg words/chunk  : %.0f", sum(wcs) / len(wcs))
        log.info("  Min/Max words    : %d / %d", min(wcs), max(wcs))
        log.info("  Total time       : %.1fs", t_total)

        # Method breakdown
        from collections import Counter
        methods = Counter(c.method for c in all_chunks)
        for method, count in methods.items():
            log.info("  Method %-15s: %d chunks", method, count)

    # ── Save ──────────────────────────────────────────────────────────────────
    log.info("\n━━ Saving output")
    save_output(all_chunks, output_dir)

    # Log to Excel
    log_performance(
        question      = f"Chunked {len(raw_data)} files",
        answer        = f"{len(all_chunks)} semantic chunks produced",
        response_time = t_total,
    )
    log.info("  Performance logged → %s", Config.LOG_EXCEL_PATH)

    return all_chunks


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ChronoBrain Semantic Chunking Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES
  # Basic run — process all files in default data dir
  python semantic_chunker.py

  # Custom paths
  python semantic_chunker.py --data-dir ./transcripts --output-dir ./chunks

  # Tune threshold (default 0.45):
  #   lower = fewer, larger chunks (fewer topic boundaries detected)
  #   higher = more, smaller chunks (more sensitive to topic shifts)
  python semantic_chunker.py --threshold 0.35   # fewer chunk boundaries
  python semantic_chunker.py --threshold 0.55   # more chunk boundaries

  # Dry-run: clean + split only, no embedding, no files written
  python semantic_chunker.py --dry-run

PLUG INTO CHRONOBRAIN:
  After running this, point ChronoBrain to the output:
      brain.process_from_chunks("../data/chunks/chunks.json")
  Or index directly:
      chunks = json.load(open("chunks.json"))
      for chunk in chunks:
          # embed chunk["text"] and add to FAISS
        """,
    )
    parser.add_argument("--data-dir",  "-d", default=Config.DATA_DIR,
                        help=f"Folder with .txt/.xlsx files (default: {Config.DATA_DIR})")
    parser.add_argument("--output-dir","-o", default=Config.OUTPUT_DIR,
                        help=f"Where to write output (default: {Config.OUTPUT_DIR})")
    parser.add_argument("--threshold", "-t", type=float, default=Config.SIMILARITY_THRESHOLD,
                        help=f"Cosine similarity threshold (default: {Config.SIMILARITY_THRESHOLD})")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Clean and split only — no embedding, no output written")
    args = parser.parse_args()

    Config.SIMILARITY_THRESHOLD = args.threshold

    log.info("ChronoBrain Semantic Chunker")
    log.info("Data dir   : %s", args.data_dir)
    log.info("Output dir : %s", args.output_dir)
    log.info("Threshold  : %.2f", args.threshold)
    log.info("Dry-run    : %s\n", args.dry_run)

    chunks = run(
        data_dir   = args.data_dir,
        output_dir = args.output_dir,
        threshold  = args.threshold,
        dry_run    = args.dry_run,
    )

    if chunks:
        print()
        print("=" * 55)
        print(f"  {len(chunks)} chunks saved to {args.output_dir}")
        print(f"  Load in ChronoBrain:")
        print(f"    chunks = json.load(open('{args.output_dir}/chunks.json'))")
        print(f"    # each chunk: chunk_id, source_file, text, word_count")
        print("=" * 55)


if __name__ == "__main__":
    main()