#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_data.py — Agentic Data Cleaner for ChronoBrain
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WHAT THIS DOES
  This is a 3-stage autonomous agent that reads your raw .txt transcript files
  and produces two clean outputs:
    1.  file_all_cleaned.txt   — structured Markdown ready for RAG indexing
    2.  qa_pairs.jsonl         — (question, answer) training pairs for fine-tuning
                                  (Step 1 of the fine-tuning roadmap)

THE GIGO PROBLEM IT SOLVES
  Raw transcripts contain:
  - Noise:       "oui", "d'accord", "donc euh", "voilà exactement"
  - Fragments:   sentences cut mid-way at speaker turns
  - Off-topic:   greetings, "on se rappelle vendredi", logistics
  - Repetition:  same concept explained 3 times in a row
  - No structure: raw prose with no titles, steps, or sections
  These all poison the embedding index — the LLM retrieves irrelevant chunks
  and hallucinates. Fix the data, fix the answers.

THE 3 STAGES
  Stage 1 — AUDIT:     classify every chunk → KEEP / NOISE / INCOMPLETE / DUPLICATE
  Stage 2 — REWRITE:   fix INCOMPLETE chunks using a 3-chunk sliding window context
  Stage 3 — STRUCTURE: reformat KEEP/REWRITTEN chunks as Markdown + generate QA pairs

RUN
  python clean_data.py                        # cleans all .txt in DATA_DIR
  python clean_data.py --input my_file.txt    # clean one specific file
  python clean_data.py --dry-run              # audit only, no output written
  python clean_data.py --ollama-url http://...# use ngrok tunnel (Colab)

OUTPUT
  ../data/file_all_cleaned.txt   — drop this into DATA_DIR for ChronoBrain
  ../data/qa_pairs.jsonl         — use this for fine-tuning (one JSON per line)
  ../data/clean_report.txt       — what was kept, dropped, rewritten, why

REQUIREMENTS
  pip install ollama httpx
  ollama serve + ollama pull llama3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────

DATA_DIR    = "../data"
OUTPUT_FILE = "../data/file_all_cleaned.txt"
QA_FILE     = "../data/qa_pairs.jsonl"
REPORT_FILE = "../data/clean_report.txt"

LLM_MODEL       = "llama3"
LLM_TEMPERATURE = 0.0     # deterministic — cleaning is not creative
LLM_TOP_P       = 0.7
LLM_MAX_TOKENS  = 1200
LLM_RETRIES     = 2
OLLAMA_URL      = "http://localhost:11434"   # override with --ollama-url

# How many words per raw chunk before sending to the LLM
CHUNK_WORDS     = 120
CHUNK_OVERLAP   = 20      # sliding window overlap
CONTEXT_WINDOW  = 3       # chunks of context fed to REWRITE stage

# Noise patterns: chunks matching these are dropped before any LLM call (fast)
_FAST_NOISE = re.compile(
    r"^(oui[,\s.!]*|non[,\s.!]*|d[''']accord[,\s.!]*|voil[àa][,\s.!]*"
    r"|exactement[,\s.!]*|tr[eè]s bien[,\s.!]*|bien s[uû]r[,\s.!]*"
    r"|bien entendu[,\s.!]*|c[''']est [çc]a[,\s.!]*"
    r"|ok[,\s.!]*|okay[,\s.!]*|parfait[,\s.!]*"
    r"|bonne journ[eé]e.*|[àa] bient[oô]t.*|au revoir.*"
    r"|merci[,\s.!]*|je vous remercie.*"
    r"|bonjour.*|bonsoir.*|salut.*"
    r"|donc[,\s.!]{0,2}$|euh[,\s.!]{0,2}$"
    r"|\[inaudible\].*|\[rires\].*"
    r")$",
    re.IGNORECASE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cleaner")


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class Chunk:
    chunk_id:   str
    source:     str
    text:       str
    word_count: int
    # filled by the pipeline
    status:     str = ""        # KEEP | NOISE | INCOMPLETE | DUPLICATE | SKIP
    cleaned:    str = ""
    category:   str = ""        # procedure | concept | rule | logistics | unknown
    qa_pairs:   list[dict] = field(default_factory=list)
    notes:      str = ""

@dataclass
class CleanReport:
    total:       int = 0
    kept:        int = 0
    noise:       int = 0
    incomplete:  int = 0
    rewritten:   int = 0
    duplicate:   int = 0
    skipped:     int = 0
    qa_total:    int = 0
    errors:      list[str] = field(default_factory=list)


# ── LLM call ─────────────────────────────────────────────────────────────────

def llm_call(prompt: str, max_tokens: int = LLM_MAX_TOKENS) -> Optional[str]:
    """Single LLM call via Ollama — temperature=0.0 for deterministic output."""
    try:
        import ollama as _ollama
        client = _ollama.Client(host=OLLAMA_URL)
    except ImportError:
        log.error("ollama not installed — run: pip install ollama")
        sys.exit(1)

    for attempt in range(LLM_RETRIES + 1):
        try:
            resp = client.generate(
                model=LLM_MODEL,
                prompt=prompt,
                options={
                    "temperature":    LLM_TEMPERATURE,
                    "top_p":          LLM_TOP_P,
                    "num_predict":    max_tokens,
                    "repeat_penalty": 1.15,
                    "stop":           ["<|eot_id|>", "---END---"],
                },
            )
            raw = resp["response"].strip()
            return raw
        except Exception as e:
            if attempt < LLM_RETRIES:
                log.warning("LLM timeout (attempt %d/%d) — retrying in 3s…",
                            attempt + 1, LLM_RETRIES + 1)
                time.sleep(3)
            else:
                log.error("LLM failed after %d attempts: %s", LLM_RETRIES + 1, e)
                return None
    return None


def parse_json_from_llm(raw: str) -> Optional[dict]:
    """Extract JSON from LLM output — handles markdown code fences."""
    if not raw:
        return None
    # Strip ```json ... ``` fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw.strip(), flags=re.MULTILINE)
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract the first {...} block
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return None


# ── Stage 1: AUDIT ──────────────────────────────────────────────────────────

AUDIT_PROMPT = """\
Tu es un expert en documentation technique française pour le logiciel Chronotime (CTIME) chez Inetum.

Analyse ce fragment de transcription et classe-le avec précision.

FRAGMENT:
\"\"\"
{text}
\"\"\"

RÉPONDS UNIQUEMENT EN JSON (rien d'autre, pas de commentaire, pas de markdown) :
{{
  "status": "<KEEP|NOISE|INCOMPLETE|DUPLICATE>",
  "category": "<procedure|concept|rule|logistics|unknown>",
  "notes": "<explication courte en 1 phrase>"
}}

RÈGLES DE CLASSIFICATION :
- KEEP       → contient une information technique utile, une procédure, une règle ou une définition claire
- NOISE      → bavardage, salutations, rires, hésitations ("euh", "donc"), phrases sans contenu
- INCOMPLETE → commence une procédure ou une explication mais ne la termine pas (phrase coupée, "donc le menu il va...")
- DUPLICATE  → répète mot pour mot ou presque une information déjà connue

CATÉGORIES :
- procedure  → étapes à suivre dans l'interface ("aller dans le menu X, cliquer sur Y")
- concept    → définition d'un terme ou d'une fonctionnalité ("le profil utilisateur est...")
- rule       → règle de calcul ou de configuration ("la règle B_HS calcule...")
- logistics  → organisation, planning, qui fait quoi (pas de valeur technique)
- unknown    → impossible à catégoriser
"""


def audit_chunk(chunk: Chunk) -> Chunk:
    """Stage 1: classify a single chunk."""
    # Fast path: regex noise filter (no LLM needed)
    if _FAST_NOISE.match(chunk.text.strip()) or chunk.word_count < 8:
        chunk.status   = "NOISE"
        chunk.category = "unknown"
        chunk.notes    = "Filtered by fast noise regex (no LLM needed)"
        return chunk

    prompt = AUDIT_PROMPT.format(text=chunk.text)
    raw    = llm_call(prompt, max_tokens=200)

    if raw is None:
        chunk.status = "SKIP"
        chunk.notes  = "LLM call failed"
        return chunk

    parsed = parse_json_from_llm(raw)
    if parsed:
        chunk.status   = parsed.get("status",   "KEEP").upper()
        chunk.category = parsed.get("category", "unknown").lower()
        chunk.notes    = parsed.get("notes",    "")
    else:
        # If JSON parse failed, keep the chunk — don't silently drop data
        chunk.status = "KEEP"
        chunk.notes  = f"JSON parse failed — kept by default. Raw: {raw[:80]}"

    return chunk


# ── Stage 2: REWRITE ─────────────────────────────────────────────────────────

REWRITE_PROMPT = """\
Tu es un expert technique Chronotime. Tu dois compléter et corriger un fragment incomplet.

CONTEXTE (fragments précédents et suivants) :
\"\"\"
{context}
\"\"\"

FRAGMENT INCOMPLET À CORRIGER :
\"\"\"
{text}
\"\"\"

INSTRUCTIONS :
1. Complète la pensée interrompue en utilisant le contexte.
2. Supprime les hésitations ("euh", "donc euh", "voilà"), les répétitions et le bruit.
3. Reformule en français technique clair et concis.
4. Préserve TOUS les noms de menus, boutons, champs et termes techniques (B_HS, RESP2, etc.).
5. Si le fragment n'a aucune valeur technique même avec le contexte, réponds exactement : NOISE

RÉPONDS avec le texte corrigé uniquement (pas de JSON, pas de commentaire).
"""


def rewrite_chunk(chunk: Chunk, context_text: str) -> Chunk:
    """Stage 2: rewrite an INCOMPLETE chunk using surrounding context."""
    prompt = REWRITE_PROMPT.format(
        context=context_text,
        text=chunk.text,
    )
    raw = llm_call(prompt, max_tokens=400)

    if raw is None:
        chunk.status = "SKIP"
        chunk.notes += " | Rewrite failed"
        return chunk

    if raw.strip().upper() == "NOISE":
        chunk.status = "NOISE"
        chunk.notes += " | Downgraded to NOISE after rewrite attempt"
        return chunk

    chunk.cleaned = raw.strip()
    chunk.status  = "REWRITTEN"
    return chunk


# ── Stage 3: STRUCTURE ───────────────────────────────────────────────────────

STRUCTURE_PROMPT = """\
Tu es un expert en documentation technique Chronotime (CTIME) chez Inetum.

Transforme ce fragment en documentation structurée et génère des paires question-réponse.

FRAGMENT :
\"\"\"
{text}
\"\"\"

CATÉGORIE : {category}

RÉPONDS UNIQUEMENT EN JSON (rien d'autre) :
{{
  "cleaned": "<texte restructuré en Markdown — titres ##, étapes numérotées si procédure, gras pour termes clés>",
  "qa_pairs": [
    {{"question": "<question naturelle en français>", "answer": "<réponse complète en français>"}},
    {{"question": "<autre question variante>", "answer": "<réponse complète>"}}
  ]
}}

RÈGLES pour le champ "cleaned" :
- Si CATÉGORIE = procedure : utilise obligatoirement "Étape 1 —", "Étape 2 —", etc.
- Si CATÉGORIE = concept   : commence par "## [NomDuConcept]" puis une définition en 2-3 phrases
- Si CATÉGORIE = rule      : commence par "## Règle : [NomDeLaRègle]" puis le détail technique
- Conserve tous les noms de menus, boutons, champs et codes techniques (B_HS, RESP2, etc.)
- Rédige EN FRANÇAIS uniquement

RÈGLES pour le champ "qa_pairs" :
- Génère 2 à 4 paires selon la richesse du fragment
- Les questions doivent être naturelles : "Comment...", "Qu'est-ce que...", "À quoi sert...", "Pourquoi..."
- Les réponses doivent être complètes et autonomes (compréhensibles sans le fragment d'origine)
- Les QA pairs serviront à fine-tuner un LLM — sois précis et exhaustif
"""


def structure_chunk(chunk: Chunk) -> Chunk:
    """Stage 3: reformat a KEEP/REWRITTEN chunk and generate QA pairs."""
    source_text = chunk.cleaned if chunk.cleaned else chunk.text
    prompt = STRUCTURE_PROMPT.format(
        text=source_text,
        category=chunk.category or "unknown",
    )
    raw = llm_call(prompt, max_tokens=LLM_MAX_TOKENS)

    if raw is None:
        # Fallback: keep original text, no QA pairs
        chunk.cleaned  = source_text
        chunk.qa_pairs = []
        chunk.notes   += " | Structure call failed — kept raw text"
        return chunk

    parsed = parse_json_from_llm(raw)
    if parsed:
        chunk.cleaned  = parsed.get("cleaned",  source_text).strip()
        chunk.qa_pairs = parsed.get("qa_pairs", [])
        # Validate QA pairs
        chunk.qa_pairs = [
            qa for qa in chunk.qa_pairs
            if isinstance(qa, dict)
            and qa.get("question", "").strip()
            and qa.get("answer", "").strip()
        ]
    else:
        chunk.cleaned  = source_text
        chunk.qa_pairs = []
        chunk.notes   += f" | Structure JSON parse failed. Raw: {raw[:80]}"

    return chunk


# ── Chunker ──────────────────────────────────────────────────────────────────

def chunk_text(file_path: Path) -> list[Chunk]:
    """
    Sliding-window word chunker — same logic as in chronobrain_fixed.py.
    Produces Chunk objects with deterministic chunk_ids.
    """
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        log.error("Cannot read %s: %s", file_path, e)
        return []

    # Normalise line endings, strip timestamp markers [MM:SS -> MM:SS]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\[\d+:\d+\s*[-–>]+\s*\d+:\d+\]\s*", "", text)

    words = text.split()
    if not words:
        return []

    step    = CHUNK_WORDS - CHUNK_OVERLAP
    chunks  = []

    for start in range(0, len(words), step):
        chunk_words = words[start: start + CHUNK_WORDS]
        if len(chunk_words) < 5:   # skip trailing micro-chunks
            break
        chunk_text_str = " ".join(chunk_words)
        cid = hashlib.md5(f"{file_path.name}:{start}".encode()).hexdigest()[:10]
        chunks.append(Chunk(
            chunk_id   = cid,
            source     = file_path.name,
            text       = chunk_text_str,
            word_count = len(chunk_words),
        ))

    log.info("  Chunked %s → %d chunks", file_path.name, len(chunks))
    return chunks


# ── Duplicate detection ───────────────────────────────────────────────────────

def detect_duplicates(chunks: list[Chunk]) -> list[Chunk]:
    """
    Mark duplicates using Jaccard similarity on word sets.
    Runs without LLM — fast O(n²) but n is small for transcript files.
    """
    def words(text: str) -> set[str]:
        return {w.lower() for w in re.findall(r"\b\w{4,}\b", text)}

    seen: list[set] = []
    for chunk in chunks:
        if chunk.status in ("NOISE", "SKIP"):
            continue
        w = words(chunk.text)
        for prev in seen:
            if not w or not prev:
                continue
            jaccard = len(w & prev) / len(w | prev)
            if jaccard > 0.75:
                chunk.status = "DUPLICATE"
                chunk.notes  = f"Jaccard similarity {jaccard:.2f} with earlier chunk"
                break
        if chunk.status != "DUPLICATE":
            seen.append(w)

    return chunks


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(
    files:   list[Path],
    dry_run: bool = False,
) -> CleanReport:
    """Run all 3 stages on a list of files. Return the report."""
    report = CleanReport()
    all_chunks: list[Chunk] = []

    # ── Chunk all files ───────────────────────────────────────────────────────
    for f in files:
        log.info("Reading: %s", f.name)
        all_chunks.extend(chunk_text(f))

    report.total = len(all_chunks)
    log.info("Total chunks to process: %d", report.total)

    # ── Stage 1: AUDIT ────────────────────────────────────────────────────────
    log.info("")
    log.info("━━ STAGE 1: AUDIT ━━")
    for i, chunk in enumerate(all_chunks):
        log.info("  [%d/%d] Auditing chunk %s...", i + 1, report.total, chunk.chunk_id)
        all_chunks[i] = audit_chunk(chunk)
        status = all_chunks[i].status
        log.info("    → %s  [%s]  %s",
                 status, all_chunks[i].category, all_chunks[i].notes[:60])

    # ── Duplicate detection (fast, no LLM) ───────────────────────────────────
    all_chunks = detect_duplicates(all_chunks)

    # ── Stage 2: REWRITE (INCOMPLETE chunks only) ─────────────────────────────
    log.info("")
    log.info("━━ STAGE 2: REWRITE ━━")
    for i, chunk in enumerate(all_chunks):
        if chunk.status != "INCOMPLETE":
            continue
        # Build context: up to CONTEXT_WINDOW chunks before and after
        ctx_start = max(0, i - CONTEXT_WINDOW)
        ctx_end   = min(len(all_chunks), i + CONTEXT_WINDOW + 1)
        context_parts = [
            c.text for j, c in enumerate(all_chunks[ctx_start:ctx_end])
            if j != (i - ctx_start) and c.status not in ("NOISE", "DUPLICATE")
        ]
        context_text = "\n\n---\n\n".join(context_parts[:CONTEXT_WINDOW * 2])

        log.info("  Rewriting chunk %s...", chunk.chunk_id)
        all_chunks[i] = rewrite_chunk(chunk, context_text)
        log.info("    → %s", all_chunks[i].status)

    if dry_run:
        log.info("Dry-run mode — stopping before Stage 3 (no files written)")
        _print_audit_summary(all_chunks, report)
        return report

    # ── Open output files NOW — stream each chunk immediately after Stage 3 ──
    txt_fh, qa_fh, rpt_fh = _open_output_files()
    first_section = [True]   # mutable flag so _stream_chunk can track separators

    # ── Stage 3: STRUCTURE (KEEP + REWRITTEN) ─────────────────────────────────
    log.info("")
    log.info("━━ STAGE 3: STRUCTURE + QA GENERATION ━━")
    for i, chunk in enumerate(all_chunks):
        if chunk.status not in ("KEEP", "REWRITTEN"):
            # still write noise/duplicate/skip lines to the report in real time
            _stream_chunk(chunk, txt_fh, qa_fh, rpt_fh, report, first_section)
            continue
        log.info("  [%s] Structuring chunk %s...", chunk.category, chunk.chunk_id)
        all_chunks[i] = structure_chunk(chunk)
        n_qa = len(all_chunks[i].qa_pairs)
        log.info("    → %d QA pairs generated  ✎ written to disk", n_qa)
        # Write to disk immediately — file is readable right now
        _stream_chunk(all_chunks[i], txt_fh, qa_fh, rpt_fh, report, first_section)

    # ── Count final stats ─────────────────────────────────────────────────────
    for c in all_chunks:
        if c.status == "KEEP":         report.kept       += 1
        elif c.status == "REWRITTEN":  report.rewritten  += 1
        elif c.status == "NOISE":      report.noise      += 1
        elif c.status == "INCOMPLETE": report.incomplete += 1
        elif c.status == "DUPLICATE":  report.duplicate  += 1
        elif c.status == "SKIP":       report.skipped    += 1

    # ── Finalise report (stats summary appended at the end) ───────────────────
    _finalise_report(report, rpt_fh)
    txt_fh.close()
    qa_fh.close()
    rpt_fh.close()
    log.info("✓ All output files closed.")
    return report


def _print_audit_summary(chunks: list[Chunk], report: CleanReport) -> None:
    statuses = {}
    for c in chunks:
        statuses[c.status] = statuses.get(c.status, 0) + 1
    log.info("")
    log.info("=== AUDIT SUMMARY ===")
    for status, count in sorted(statuses.items()):
        log.info("  %-12s %d", status, count)


def _open_output_files() -> tuple:
    """
    Open all 3 output files for streaming writes.
    Returns (txt_handle, qa_handle, report_handle).
    Called ONCE at pipeline start — each chunk is written immediately after
    processing so you can see results in real time without waiting for the end.
    """
    out_path = Path(OUTPUT_FILE)
    qa_path  = Path(QA_FILE)
    rpt_path = Path(REPORT_FILE)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    rpt_path.parent.mkdir(parents=True, exist_ok=True)

    txt_fh = out_path.open("w", encoding="utf-8", buffering=1)   # line-buffered
    qa_fh  = qa_path.open("w",  encoding="utf-8", buffering=1)
    rpt_fh = rpt_path.open("w", encoding="utf-8", buffering=1)

    # Write report header immediately so the file exists and is non-empty
    rpt_fh.write("ChronoBrain Data Cleaning Report\n")
    rpt_fh.write("=" * 40 + "\n")
    rpt_fh.write("(streaming — updated after every chunk)\n\n")
    rpt_fh.write("PER-CHUNK DETAIL\n")
    rpt_fh.write("-" * 40 + "\n")
    rpt_fh.flush()

    log.info("✓ Output files opened for real-time streaming:")
    log.info("    %s", out_path)
    log.info("    %s", qa_path)
    log.info("    %s", rpt_path)

    return txt_fh, qa_fh, rpt_fh


def _stream_chunk(
    chunk:   Chunk,
    txt_fh,
    qa_fh,
    rpt_fh,
    report:  CleanReport,
    first_section: list,   # mutable flag: [True] until first section written
) -> None:
    """
    Write one processed chunk to disk immediately after it is ready.
    Called right after structure_chunk() so the file is updated in real time.
    """
    # ── Cleaned text ──────────────────────────────────────────────────────────
    if chunk.status in ("KEEP", "REWRITTEN") and chunk.cleaned:
        if first_section[0]:
            first_section[0] = False
        else:
            txt_fh.write("\n\n---\n\n")
        txt_fh.write(chunk.cleaned)
        txt_fh.flush()                          # ← flush to disk immediately

    # ── QA pairs ──────────────────────────────────────────────────────────────
    for qa in chunk.qa_pairs:
        record = {
            "instruction": qa.get("question", "").strip(),
            "input":       "",
            "output":      qa.get("answer", "").strip(),
            "source":      chunk.source,
            "category":    chunk.category,
            "chunk_id":    chunk.chunk_id,
        }
        qa_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        qa_fh.flush()                           # ← flush to disk immediately
        report.qa_total += 1

    # ── Report line ───────────────────────────────────────────────────────────
    line = (
        f"[{chunk.chunk_id}] {chunk.status:12s} [{chunk.category:10s}] "
        f"{chunk.source}  |  {chunk.notes[:80]}\n"
    )
    rpt_fh.write(line)
    rpt_fh.flush()                              # ← flush to disk immediately


def _finalise_report(report: CleanReport, rpt_fh) -> None:
    """Append the summary stats block to the report file."""
    rpt_fh.write("\n" + "=" * 40 + "\n")
    rpt_fh.write("FINAL SUMMARY\n")
    rpt_fh.write(f"Total chunks processed : {report.total}\n")
    rpt_fh.write(f"  KEPT                 : {report.kept}\n")
    rpt_fh.write(f"  REWRITTEN            : {report.rewritten}\n")
    rpt_fh.write(f"  NOISE (dropped)      : {report.noise}\n")
    rpt_fh.write(f"  DUPLICATE (dropped)  : {report.duplicate}\n")
    rpt_fh.write(f"  INCOMPLETE (failed)  : {report.incomplete}\n")
    rpt_fh.write(f"  SKIPPED (LLM error)  : {report.skipped}\n")
    rpt_fh.write(f"QA pairs generated     : {report.qa_total}\n")
    rpt_fh.flush()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    # Must declare globals before any reference to them (including default= in argparse)
    global OLLAMA_URL, LLM_MODEL, OUTPUT_FILE, QA_FILE

    parser = argparse.ArgumentParser(
        description="Agentic data cleaner for ChronoBrain — fixes GIGO at the source.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES
  python clean_data.py
      Clean all .txt files in DATA_DIR (../data by default)

  python clean_data.py --input /path/to/my_transcript.txt
      Clean a single file

  python clean_data.py --dry-run
      Audit only — classify chunks, print report, write nothing

  python clean_data.py --ollama-url https://YOUR.ngrok-free.app
      Use a remote Ollama server (Colab/ngrok)

  python clean_data.py --data-dir /content/data --output /content/data/clean.txt
      Custom paths for Colab
        """,
    )
    parser.add_argument(
        "--input", "-i",
        help="Path to a single .txt file to clean (default: all .txt in DATA_DIR)",
    )
    parser.add_argument(
        "--data-dir", "-d",
        default=DATA_DIR,
        help=f"Directory containing raw .txt files (default: {DATA_DIR})",
    )
    parser.add_argument(
        "--output", "-o",
        default=OUTPUT_FILE,
        help=f"Where to write the cleaned text (default: {OUTPUT_FILE})",
    )
    parser.add_argument(
        "--qa-output",
        default=QA_FILE,
        help=f"Where to write QA pairs JSONL (default: {QA_FILE})",
    )
    parser.add_argument(
        "--ollama-url",
        default=OLLAMA_URL,
        help=f"Ollama server URL (default: {OLLAMA_URL})",
    )
    parser.add_argument(
        "--model",
        default=LLM_MODEL,
        help=f"Ollama model name (default: {LLM_MODEL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Audit only — classify every chunk but write no output files",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show full chunk text during audit",
    )
    args = parser.parse_args()

    # Apply CLI overrides to module-level config
    OLLAMA_URL   = args.ollama_url
    LLM_MODEL    = args.model
    OUTPUT_FILE  = args.output
    QA_FILE      = args.qa_output

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Collect input files
    if args.input:
        files = [Path(args.input)]
        if not files[0].exists():
            log.error("File not found: %s", files[0])
            sys.exit(1)
    else:
        base  = Path(args.data_dir)
        files = sorted(base.glob("*.txt"))
        if not files:
            log.error("No .txt files found in %s", base)
            sys.exit(1)

    log.info("ChronoBrain Agentic Data Cleaner")
    log.info("Files to process: %s", [f.name for f in files])
    log.info("Ollama server:    %s", OLLAMA_URL)
    log.info("Model:            %s", LLM_MODEL)
    log.info("Dry-run:          %s", args.dry_run)
    log.info("")

    # Verify Ollama is reachable
    try:
        import ollama as _ollama
        client = _ollama.Client(host=OLLAMA_URL)
        client.list()
        log.info("✓ Ollama reachable at %s", OLLAMA_URL)
    except Exception as e:
        log.error("Cannot reach Ollama at %s: %s", OLLAMA_URL, e)
        log.error("Make sure Ollama is running: ollama serve")
        sys.exit(1)

    t0     = time.time()
    report = run_pipeline(files, dry_run=args.dry_run)
    elapsed = time.time() - t0

    # Print final summary
    print()
    print("=" * 55)
    print("  CLEANING COMPLETE")
    print("=" * 55)
    print(f"  Chunks processed  : {report.total}")
    print(f"  Kept + rewritten  : {report.kept + report.rewritten}")
    print(f"  Dropped (noise)   : {report.noise}")
    print(f"  Dropped (duplic.) : {report.duplicate}")
    print(f"  QA pairs produced : {report.qa_total}")
    print(f"  Time              : {elapsed:.0f}s")
    print()
    if not args.dry_run:
        print(f"  Cleaned text  → {OUTPUT_FILE}")
        print(f"  QA pairs      → {QA_FILE}")
        print(f"  Report        → {REPORT_FILE}")
        print()
        print("NEXT STEPS:")
        print("  1. Copy the cleaned text to your DATA_DIR and run:")
        print("     python chronobrain_v10.py --rebuild")
        print("  2. Use qa_pairs.jsonl for fine-tuning (Step 1 of roadmap)")
    print("=" * 55)


if __name__ == "__main__":
    main()