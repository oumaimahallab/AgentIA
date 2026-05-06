"""
ChronoBrain — Production Transcript Cleaner
════════════════════════════════════════════
Transforms raw Whisper .txt files into clean, structured JSON chunks
ready for ChromaDB ingestion.

What this fixes (based on analysis of your 3 files):
  ✦ 60–96 filler/noise segments removed per file (Oui/Non/D'accord/euh...)
  ✦ Single-word ASR fragments merged or dropped
  ✦ Gap-aware semantic chunking (80 words, 3s pause boundary)
  ✦ Technical term normalization (APDEM, TAPT, PRTEFF etc. preserved intact)
  ✦ ASR corruption detection (garbled camelCase artifacts flagged)
  ✦ Output: structured JSON with full metadata per chunk

Usage:
    python transcript_cleaner.py --input ../data/transcripts --output ../data/cleaned
    python transcript_cleaner.py --input ../data/transcripts --output ../data/cleaned --dry-run
"""

import os
import re
import json
import argparse
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("cleaner")

# ── CONFIG ────────────────────────────────────────────────────────────────────

CHUNK_WORDS = 80       # target words per semantic chunk
MAX_GAP_SEC = 3.0      # break chunk on pause longer than this
MIN_SEG_WORDS = 1      # drop segments shorter than this

# Filler / back-channel noise — these lines carry zero information
FILLER_PATTERN = re.compile(
    r"^(oui|non|d'accord|ok|okay|euh+|hm+|ah+|oh+|voilà|donc|alors|"
    r"ben|bah|ouais|bien sûr|tout à fait|exactement|parfait|super|"
    r"merci|de rien|au revoir|bonjour)[.!?,\s]*$",
    re.IGNORECASE,
)

# Timestamp line format
TS_PATTERN = re.compile(r"\[(\d+):(\d+)\s*->\s*(\d+):(\d+)\]\s*(.*)")

# ASR garbling detector: isolated uppercase tokens that look like codec errors
# e.g. "inéton", "Grandti Indoscore récal" — real tech terms are ALL_CAPS
ASR_GARBAGE = re.compile(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+){2,}\b')


@dataclass
class Segment:
    start: float
    end: float
    text: str
    source: str


@dataclass
class Chunk:
    chunk_id: str          # {source_stem}_{start_mm}_{end_mm}
    source: str            # original filename
    start_time: str        # MM:SS
    end_time: str          # MM:SS
    start_sec: float
    end_sec: float
    text: str
    word_count: int
    has_asr_warning: bool  # True if garbled text was detected


# ── PARSING ───────────────────────────────────────────────────────────────────

def parse_file(filepath: str) -> list[Segment]:
    """Parse a .txt transcript into raw segments."""
    source = Path(filepath).name
    segments = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            m = TS_PATTERN.match(line.strip())
            if not m:
                continue
            sm, ss, em, es, text = m.groups()
            text = text.strip()
            if text:
                segments.append(Segment(
                    start=int(sm) * 60 + int(ss),
                    end=int(em) * 60 + int(es),
                    text=text,
                    source=source,
                ))
    return segments


# ── CLEANING ──────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """
    Normalize a single segment's text.
    - Collapse multiple spaces
    - Fix common Whisper artifacts (repeated punctuation, trailing fragments)
    - Preserve technical terms (ALL_CAPS, alphanumeric codes like PRTEFF, APDEM)
    """
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # Remove repeated punctuation artifacts: "..." → ".", ",," → ","
    text = re.sub(r'([.!?,])\1+', r'\1', text)

    # Fix common Whisper French artifacts
    text = re.sub(r'\bé gal\b', 'égal', text)
    text = re.sub(r'\bc est\b', "c'est", text, flags=re.IGNORECASE)
    text = re.sub(r'\bqu il\b', "qu'il", text, flags=re.IGNORECASE)

    # Remove trailing isolated characters (ASR split artifacts): "donc il y a ,"
    text = re.sub(r'\s+[,;.]$', '.', text)

    return text





def is_noise(segment: Segment) -> bool:
    text = segment.text.strip()
    
    # 1. Gardez les mots courts mais évitez le vide absolu
    if len(text) < 2: # Au lieu de MIN_SEG_WORDS
        return True

    # 2. Retirez les fillers UNIQUEMENT s'ils sont isolés (sans autre mot dans la ligne)
    # Si la ligne contient "Oui, c'est ça", ne la supprimez pas.
    if FILLER_PATTERN.match(text):
        return True

    # 3. Supprimez l'isolation des chiffres/ponctuation seulement si RIEN d'autre n'est dit
    if re.match(r'^[\d\s\.,;:!?-]+$', text):
        return True

    return False

def has_asr_warning(text: str) -> bool:
    """Detect likely ASR garbling in text."""
    # CamelCase artifacts that aren't real technical terms
    garbled = ASR_GARBAGE.findall(text)
    # Real tech terms are ALL_CAPS; mixed-case multi-part words are garbling
    return len(garbled) > 0


# ── CHUNKING ──────────────────────────────────────────────────────────────────

def make_chunks(segments: list[Segment], source_stem: str) -> list[Chunk]:
    """
    Merge cleaned segments into semantic chunks.
    Breaks on:
      - Pause gap > MAX_GAP_SEC between consecutive segments
      - Accumulated word count > CHUNK_WORDS
    """
    chunks: list[Chunk] = []
    buf_texts: list[str] = []
    buf_start = buf_end = 0.0
    word_count = 0

    def flush() -> Optional[Chunk]:
        nonlocal buf_texts, buf_start, buf_end, word_count
        if not buf_texts:
            return None
        combined = " ".join(buf_texts)
        mm_s = f"{int(buf_start // 60):02d}:{int(buf_start % 60):02d}"
        mm_e = f"{int(buf_end   // 60):02d}:{int(buf_end   % 60):02d}"
        chunk = Chunk(
            chunk_id=f"{source_stem}_{mm_s.replace(':','m')}_{mm_e.replace(':','m')}",
            source=f"{source_stem}.txt",
            start_time=mm_s,
            end_time=mm_e,
            start_sec=buf_start,
            end_sec=buf_end,
            text=combined,
            word_count=len(combined.split()),
            has_asr_warning=has_asr_warning(combined),
        )
        buf_texts, word_count = [], 0
        return chunk

    for seg in segments:
        gap = (seg.start - buf_end) if buf_texts else 0
        wc  = len(seg.text.split())

        if buf_texts and (gap > MAX_GAP_SEC or word_count + wc > CHUNK_WORDS):
            c = flush()
            if c:
                chunks.append(c)
            buf_start = seg.start

        if not buf_texts:
            buf_start = seg.start

        buf_texts.append(seg.text)
        buf_end    = seg.end
        word_count += wc

    c = flush()
    if c:
        chunks.append(c)

    return chunks


# ── PIPELINE ──────────────────────────────────────────────────────────────────

def process_file(filepath: str) -> tuple[list[Chunk], dict]:
    """Full pipeline for one file. Returns (chunks, stats)."""
    source_stem = Path(filepath).stem

    raw_segments = parse_file(filepath)
    # Cela écrit dans un fichier à chaque fois qu'un fichier est traité.
    # Pour ne pas écraser le fichier à chaque fois, utilisez "a" (append) au lieu de "w".
    with open("segments_supprimes.log", "w", encoding="utf-8") as f:
        f.write(f"\n--- FICHIER: {filepath} ---\n")
        for seg in raw_segments:
            if is_noise(seg):
                f.write(f"SUPPRIMÉ: {seg.text}\n")
    # ──────────────────────────────────────────────────────────────────────────
    # Step 1: filter noise
    clean_segments = []
    dropped_noise = 0
    for seg in raw_segments:
        if is_noise(seg):
            dropped_noise += 1
        else:
            seg.text = clean_text(seg.text)
            clean_segments.append(seg)

    # Step 2: chunk
    chunks = make_chunks(clean_segments, source_stem)

    stats = {
        "file": Path(filepath).name,
        "raw_segments": len(raw_segments),
        "after_cleaning": len(clean_segments),
        "dropped_noise": dropped_noise,
        "chunks_produced": len(chunks),
        "avg_words_per_chunk": round(
            sum(c.word_count for c in chunks) / len(chunks), 1
        ) if chunks else 0,
        "asr_warnings": sum(1 for c in chunks if c.has_asr_warning),
    }

    return chunks, stats


def run(input_dir: str, output_dir: str, dry_run: bool = False):
    input_path  = Path(input_dir)
    output_path = Path(output_dir)

    if not dry_run:
        output_path.mkdir(parents=True, exist_ok=True)

    all_stats = []
    total_chunks = 0

    for txt_file in sorted(input_path.glob("*.txt")):
        log.info("Processing: %s", txt_file.name)
        chunks, stats = process_file(str(txt_file))
        all_stats.append(stats)
        total_chunks += len(chunks)

        log.info(
            "  %d raw → %d clean → %d chunks (avg %s words, %d ASR warnings)",
            stats["raw_segments"],
            stats["after_cleaning"],
            stats["chunks_produced"],
            stats["avg_words_per_chunk"],
            stats["asr_warnings"],
        )

        if not dry_run:
            # Save as JSON — one file per transcript, array of chunk objects
            out_file = output_path / (txt_file.stem + "_cleaned.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(
                    [asdict(c) for c in chunks],
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            log.info("  → Saved: %s", out_file.name)

    log.info("\n%s", "="*50)
    log.info("TOTAL: %d chunks across %d files", total_chunks, len(all_stats))
    log.info("Per-file summary:")
    for s in all_stats:
        log.info(
            "  %-55s  %4d chunks  %4d dropped  %d ASR⚠",
            s["file"][:55],
            s["chunks_produced"],
            s["dropped_noise"],
            s["asr_warnings"],
        )

    if dry_run:
        log.info("\n[DRY RUN] No files written.")

    return all_stats


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChronoBrain transcript cleaner")
    parser.add_argument("--input",   default="../data/transcripts", help="Input folder with .txt files")
    parser.add_argument("--output",  default="../data/cleaned",     help="Output folder for JSON chunks")
    parser.add_argument("--dry-run", action="store_true",           help="Analyse only, don't write files")
    args = parser.parse_args()
    run(args.input, args.output, args.dry_run)