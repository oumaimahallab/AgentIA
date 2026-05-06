#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_data.py — ChronoBrain Agentic Data Cleaner (Hugging Face Edition)
Uses Mistral-7B-Instruct-v0.3 via Inference API
"""

from __future__ import annotations
import argparse, hashlib, json, logging, re, sys, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import requests
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- CONFIGURATION ---
DATA_DIR = "../data"
OUTPUT_FILE = "../data/v6_file_all_cleaned.txt"
QA_FILE = "../data/v6_qa_pairs.jsonl"
REPORT_FILE = "../data/v6_clean_report.txt"

# Hugging Face Settings

HF_TOKEN = os.getenv("HF_TOKEN")

MODEL_ID = "mistralai/Mistral-7B-Instruct-v0.2"

API_URL = f"https://api-inference.huggingface.co/models/{MODEL_ID}"

HEADERS = {
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json"
}

CHUNK_WORDS = 150 # Mistral can handle slightly larger context
CHUNK_OVERLAP = 20
BATCH_SIZE = 1  # For Mistral-7B via API, Batch Size 1 is most stable for JSON

# Regex for fast filtering (Stage 1)
_TECH = re.compile(r"\b(menu|onglet|bouton|cliqu|selectionn|parametrage|habilitation|profil|regle|calcul|workflow|validation|absence|chronotime|filtre|perimetre|compteur|horaire|planning|agenda|collab|admin|saisie|circuit)\b", re.IGNORECASE)
_NOISE = re.compile(r"\b(oui|non|exactement|accord|parfait|absolument|bonjour|euh|hein|ben|bah|voila|voilà|super|ok)\b", re.IGNORECASE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("cleaner")

@dataclass
class Chunk:
    chunk_id: str
    source: str
    text: str
    wc: int
    status: str = ""
    topic: str = ""
    category: str = ""
    actor: str = ""
    prerequisites: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    body: str = ""
    result: str = ""
    error_cases: list = field(default_factory=list)
    related_topics: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    qa_pairs: list = field(default_factory=list)
    notes: str = ""
    method: str = ""
    cleaned: str = ""

@dataclass
class Report:
    total: int = 0; kept: int = 0; noise: int = 0; dupes: int = 0
    skipped: int = 0; qa: int = 0; calls: int = 0
    t_rules: float = 0.0; t_llm: float = 0.0

# --- STAGE 1: LOCAL RULES ---

def chunk_file(path: Path) -> list[Chunk]:
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e: log.error("Cannot read %s: %s", path, e); return []
    text = text.replace("\r\n","\n").replace("\r","\n")
    text = re.sub(r"\[\d+:\d+\s*[-]>\s*\d+:\d+\]\s*", "", text)
    words = text.split()
    if not words: return []
    step = CHUNK_WORDS - CHUNK_OVERLAP
    chunks = []
    for start in range(0, len(words), step):
        w = words[start: start+CHUNK_WORDS]
        if len(w) < 8: break
        cid = hashlib.md5(f"{path.name}:{start}".encode()).hexdigest()[:10]
        chunks.append(Chunk(cid, path.name, " ".join(w), len(w)))
    return chunks

def rule_filter(c: Chunk) -> bool:
    if c.wc < 15: return True
    nr = len(_NOISE.findall(c.text)) / max(1, c.wc)
    if nr > 0.60: return True # High noise
    return False

def deduplicate(chunks: list[Chunk]) -> list[Chunk]:
    seen = []
    for c in chunks:
        if c.status == "NOISE": continue
        w = frozenset(re.findall(r"\b\w{4,}\b", c.text.lower()))
        for prev in seen:
            if len(w&prev)/len(w|prev) > 0.75:
                c.status="DUPLICATE"; break
        if c.status != "DUPLICATE": seen.append(w)
    return chunks

# --- STAGE 2: HUGGING FACE / MISTRAL ---

def _llm_hf(prompt: str, rpt: Report) -> Optional[str]:
    # Formats the prompt for Mistral Instruct
    formatted_prompt = f"<s>[INST] {prompt} [/INST]"
    
    payload = {
        "inputs": formatted_prompt,
        "parameters": {
            "max_new_tokens": 1500,
            "temperature": 0.1,
            "repetition_penalty": 1.1,
            "return_full_text": False
        }
    }

    for attempt in range(3):
        try:
            t0 = time.time()
            response = requests.post(API_URL, headers=HEADERS, json=payload, timeout=90)
            
            # Handle "Model Loading" (503)
            if response.status_code == 503:
                wait_time = response.json().get("estimated_time", 20)
                log.info(f"Model loading... waiting {wait_time}s")
                time.sleep(wait_time)
                continue
                
            response.raise_for_status()
            rpt.t_llm += time.time() - t0
            rpt.calls += 1
            
            res = response.json()
            if isinstance(res, list) and len(res) > 0:
                return res[0].get("generated_text", "").strip()
            return None
            
        except Exception as e:
            log.warning(f"Attempt {attempt+1} failed: {e}")
            time.sleep(5)
    return None

BATCH_PROMPT = """Tu es un expert Chronotime. Transforme ce fragment de transcription en documentation technique JSON.
Supprime les répétitions et les bruits (euh, voilà). Garde les termes techniques (démage, matricule).

Réponds UNIQUEMENT avec un tableau JSON [{{...}}].

Champs requis par objet :
- topic: Titre court
- category: "procedure" ou "concept"
- actor: "gestionnaire_rh", "administrateur", ou "collaborateur"
- body: Description synthétique des faits techniques
- steps: Liste d'étapes [{{ "n": 1, "action": "..." }}] (si procédure)
- qa_pairs: Liste [{{ "question": "...", "answer": "..." }}] (crée 1-2 paires Question/Réponse précises pour un RAG)

FRAGMENT :
{frags}"""

def _parse_json(raw: str):
    try:
        # Mistral sometimes wraps JSON in ```json blocks
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        
        start = raw.find("[")
        end = raw.rfind("]")
        if start != -1 and end != -1:
            return json.loads(raw[start:end+1])
    except:
        return None
    return None

def process_batch(chunks: list[Chunk], rpt: Report):
    frags = "\n\n".join(f"CHUNK:\n{c.text}" for c in chunks)
    raw = _llm_hf(BATCH_PROMPT.format(frags=frags), rpt)
    
    if not raw:
        for c in chunks: c.status="SKIP"
        return chunks

    parsed = _parse_json(raw)
    if not parsed:
        log.warning("JSON Parsing failed for batch")
        for c in chunks: c.status="SKIP"
        return chunks

    for i, c in enumerate(chunks):
        if i < len(parsed):
            res = parsed[i]
            c.status = "KEEP"
            c.topic = res.get("topic", "Sans titre")
            c.category = res.get("category", "info")
            c.body = res.get("body", "")
            c.actor = res.get("actor", "inconnu")
            c.steps = res.get("steps", [])
            c.qa_pairs = res.get("qa_pairs", [])
            
            # Build cleaned Markdown for RAG embedding
            md = f"## {c.topic}\n**Catégorie:** {c.category} | **Acteur:** {c.actor}\n\n{c.body}\n"
            if c.steps:
                md += "\n### Procédure :\n" + "\n".join([f"{s.get('n',i+1)}. {s.get('action')}" for i,s in enumerate(c.steps)])
            c.cleaned = md
    return chunks

# --- OUTPUT HANDLING ---

def _emit(c: Chunk, tf, qf, rf, rpt):
    if c.status == "KEEP" and c.cleaned:
        tf.write(f"\n\n---\n\n{c.cleaned}")
        rpt.kept += 1
        for qa in c.qa_pairs:
            qf.write(json.dumps({"instruction": qa['question'], "output": qa['answer'], "source": c.source}, ensure_ascii=False) + "\n")
            rpt.qa += 1
    rf.write(f"{c.chunk_id:<12} {c.status:<12} {c.topic[:40]}\n")

def run(files: list[Path]):
    rpt = Report()
    chunks = []
    for f in files: chunks.extend(chunk_file(f))
    rpt.total = len(chunks)
    
    # Pre-filter
    chunks = deduplicate(chunks)
    for c in chunks:
        if rule_filter(c): c.status = "NOISE"

    candidates = [c for c in chunks if not c.status]
    
    tf = Path(OUTPUT_FILE).open("w", encoding="utf-8")
    qf = Path(QA_FILE).open("w", encoding="utf-8")
    rf = Path(REPORT_FILE).open("w", encoding="utf-8")
    
    log.info(f"Processing {len(candidates)} candidates with Mistral HF API...")
    
    for i in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[i : i + BATCH_SIZE]
        processed = process_batch(batch, rpt)
        for c in processed:
            _emit(c, tf, qf, rf, rpt)
        log.info(f"Progress: {i+len(batch)}/{len(candidates)} chunks")

    tf.close(); qf.close(); rf.close()
    return rpt

if __name__ == "__main__":
    if not HF_TOKEN:
        print("ERROR: HF_TOKEN not found in .env file.")
        sys.exit(1)
    
    target_files = sorted(Path(DATA_DIR).glob("*.txt"))
    if not target_files:
        print(f"No files found in {DATA_DIR}")
        sys.exit(1)
        
    start_time = time.time()
    report = run(target_files)
    
    print(f"\nDone in {(time.time()-start_time)/60:.1f} minutes.")
    print(f"Kept: {report.kept} | QA Pairs: {report.qa} | API Calls: {report.calls}")