#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_data.py — ChronoBrain Agentic Data Cleaner (fast edition)
Old version: 928 chunks x 3 LLM calls x 70s = 54 hours
New version: ~58 batches x 1 call x 70s  = ~1 hour

How:
  1. 75% of chunks rejected by fast regex rules — zero LLM calls
  2. Duplicates removed by Jaccard similarity — zero LLM calls
  3. Remaining chunks batched 4 per LLM call (audit+structure+QA merged)
  4. Output written to disk after every batch (tail -f to watch live)
"""

from __future__ import annotations
import argparse,hashlib,json,logging,re,sys,time
from dataclasses import dataclass,field
from pathlib import Path
from typing import Optional

DATA_DIR    = "../data"
OUTPUT_FILE = "../data/file_all_cleaned_4.txt"
QA_FILE     = "../data/qa_pairs_4.jsonl"
REPORT_FILE = "../data/clean_report_4.txt"
LLM_MODEL       = "llama3"
LLM_TEMPERATURE = 0.0
LLM_TOP_P       = 0.7
LLM_MAX_TOKENS  = 2000
LLM_RETRIES     = 2
OLLAMA_URL      = "http://localhost:11434"
CHUNK_WORDS     = 120
CHUNK_OVERLAP   = 20
BATCH_SIZE      = 4

_TECH = re.compile(
    r"\b(menu|onglet|bouton|cliqu|selectionn|parametrage|configur"
    r"|habilitation|profil|regle|calcul|workflow|validation|absence"
    r"|controle|procedure|etape|fonctionnalite|chronotime|ctime"
    r"|filtre|perimetre|compteur|horaire|planning|agenda"
    r"|b_hs|resp2|prteff|apdem|collab|admin|saisie|circuit"
    r"|dupliquer|enregistrer|valider|annuler|creer|supprimer|modifier)\b",
    re.IGNORECASE,
)

_NOISE = re.compile(
    r"\b(oui|non|exactement|accord|parfait|absolument"
    r"|bonjour|bonsoir|salut|merci|euh|hein|ben|bah"
    r"|voila|voilà|super|ok|okay|certes)\b",
    re.IGNORECASE,
)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("cleaner")


@dataclass
class Chunk:
    chunk_id:       str
    source:         str
    text:           str
    wc:             int
    status:         str  = ""
    topic:          str  = ""
    category:       str  = ""
    actor:          str  = ""
    prerequisites:  list = field(default_factory=list)
    steps:          list = field(default_factory=list)
    body:           str  = ""
    result:         str  = ""
    error_cases:    list = field(default_factory=list)
    related_topics: list = field(default_factory=list)
    flags:          list = field(default_factory=list)
    qa_pairs:       list = field(default_factory=list)
    notes:          str  = ""
    method:         str  = ""

@dataclass
class Report:
    total:int=0; kept:int=0; noise:int=0; dupes:int=0
    skipped:int=0; qa:int=0; calls:int=0
    t_rules:float=0.0; t_llm:float=0.0


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
    log.info("  %s -> %d chunks", path.name, len(chunks))
    return chunks


def rule_filter(c: Chunk) -> bool:
    # Returns True if chunk should be dropped without LLM
    if c.wc < 12: return True
    nr = len(_NOISE.findall(c.text)) / max(1, c.wc)
    ht = bool(_TECH.search(c.text))
    if nr > 0.70: return True
    if nr > 0.50 and not ht: return True
    return False


def deduplicate(chunks: list[Chunk]) -> list[Chunk]:
    def _w(t): return frozenset(w.lower() for w in re.findall(r"\b\w{4,}\b", t))
    seen = []
    for c in chunks:
        if c.status == "NOISE": continue
        w = _w(c.text)
        if not w: continue
        for prev in seen:
            if prev and len(w&prev)/len(w|prev) > 0.72:
                c.status="DUPLICATE"; c.method="dedup"
                c.notes="Near-duplicate of earlier chunk"; break
        if c.status != "DUPLICATE": seen.append(w)
    return chunks


def _llm(prompt: str, rpt: Report) -> Optional[str]:
    try:
        import ollama as _o
        client = _o.Client(host=OLLAMA_URL)
    except ImportError: log.error("pip install ollama"); sys.exit(1)
    for attempt in range(LLM_RETRIES+1):
        try:
            t0 = time.time()
            r  = client.generate(LLM_MODEL, prompt, options={
                "temperature":LLM_TEMPERATURE,"top_p":LLM_TOP_P,
                "num_predict":LLM_MAX_TOKENS,"repeat_penalty":1.15,
                "stop":["---END---"],
            })
            rpt.t_llm += time.time()-t0; rpt.calls += 1
            return r["response"].strip()
        except Exception as e:
            if attempt < LLM_RETRIES: log.warning("Retry %d/%d in 3s",attempt+1,LLM_RETRIES+1); time.sleep(3)
            else: log.error("LLM failed: %s",e); return None
    return None


def _parse(raw: str) -> Optional[list]:
    if not raw: return None
    raw = re.sub(r"^```(?:json)?\s*","",raw.strip(),flags=re.MULTILINE)
    raw = re.sub(r"\s*```$",         "",raw.strip(),flags=re.MULTILINE)
    try:
        v = json.loads(raw.strip())
        return v if isinstance(v,list) else None
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]",raw,re.DOTALL)
        if m:
            try:
                v = json.loads(m.group())
                return v if isinstance(v,list) else None
            except Exception: pass
    return None


BATCH_PROMPT = """\
Tu es un expert technique Chronotime (CTIME) chez Inetum.
Ton rôle : STRUCTURER {n} fragments de transcription, pas seulement les nettoyer.

PRINCIPE FONDAMENTAL :
  Ne supprime pas un fragment incomplet ou mal formulé.
  Préserve TOUTE information technique, même partielle, en la marquant avec flags.
  Un fragment incomplet avec flags=["incomplete"] vaut mieux qu'un fragment supprimé.

ACTEURS RECONNUS (champ actor) :
  responsable_equipe  → manager qui valide, consulte son équipe
  gestionnaire_rh     → RH, ADV, paie — configure et supervise
  administrateur      → paramètre le système, gère les habilitations
  collaborateur       → saisit ses propres données
  systeme             → traitement automatique, moteur de calcul, batch

CATÉGORIES (champ category) :
  procedure  → actions séquentielles dans l'interface (steps requis)
  concept    → définition d'un terme ou d'une fonctionnalité (body requis)
  rule       → règle de calcul, algorithme, condition logique (body requis)
  config     → paramétrage système (steps ou body selon le cas)
  logistics  → organisation interne, aucune valeur technique (qa_pairs vide)

RÉPONDS UNIQUEMENT avec un tableau JSON de {n} objets, dans l'ordre exact.
Schéma de chaque objet :

[{{
  "id": 1,
  "topic": "Titre court et précis de l'unité de connaissance",
  "category": "procedure|concept|rule|config|logistics",
  "actor": "responsable_equipe|gestionnaire_rh|administrateur|collaborateur|systeme|inconnu",
  "prerequisites": ["Ce qui doit déjà exister avant de commencer"],
  "steps": [
    {{"n": 1, "action": "Description précise", "ui_element": "menu|bouton|champ|liste|onglet|lien|autre"}}
  ],
  "body": "Pour concept/rule/config : texte Markdown structuré. Vide pour procedure.",
  "result": "Ce qui change dans le système après. Vide si non mentionné.",
  "error_cases": [
    {{"symptom": "Ce que l'utilisateur voit", "cause": "Pourquoi", "fix": "Comment corriger"}}
  ],
  "related_topics": ["autres concepts liés mentionnés"],
  "flags": [],
  "qa_pairs": [
    {{"question": "Question naturelle en français", "answer": "Réponse complète et autonome", "difficulty": "basic|advanced"}}
  ]
}}]

RÈGLES STRICTES :
1. steps[] uniquement pour category=procedure. concept/rule/config → utilise body.
2. flags accepte : "incomplete" (fragment coupé), "inferred" (déduit du contexte),
   "uncertain" (terme ambigu), "no_ui" (règle sans interface graphique).
3. Conserve EXACTEMENT les noms : menus, boutons, codes (B_HS, RESP2, PRTEFF, APDEM).
4. Génère 2 qa_pairs minimum : 1 basic (comment faire) + 1 advanced (pourquoi/condition).
5. category=logistics → qa_pairs=[], body="" sauf si information utile présente.
6. Ne résume pas — structure. Toute information du fragment doit être récupérable.

FRAGMENTS :
{frags}
---END---
"""


def _build_cleaned_text(c) -> str:
    """Build embeddable text from structured fields."""
    parts = []
    header = f"## {c.topic}" if c.topic else f"## {c.category.capitalize()}"
    labels = {
        "responsable_equipe": "Responsable d'equipe",
        "gestionnaire_rh": "Gestionnaire RH",
        "administrateur": "Administrateur",
        "collaborateur": "Collaborateur",
        "systeme": "Systeme",
    }
    if c.actor and c.actor not in ("inconnu", ""):
        header += f"  *(role : {labels.get(c.actor, c.actor)})*"
    parts.append(header)
    if c.prerequisites:
        parts.append("**Prerequis :**")
        for p in c.prerequisites:
            parts.append(f"- {p}")
    if c.steps:
        for s in c.steps:
            n   = s.get("n", "?")
            act = s.get("action", "")
            ui  = s.get("ui_element", "")
            line = f"Etape {n} --- {act}"
            if ui and ui not in ("autre", ""):
                line += f" [{ui}]"
            parts.append(line)
    elif c.body:
        parts.append(c.body)
    if c.result:
        parts.append(f"**Resultat :** {c.result}")
    if c.error_cases:
        parts.append("**Problemes connus :**")
        for ec in c.error_cases:
            sym = ec.get("symptom", "")
            fix = ec.get("fix", "")
            if sym:
                parts.append(f"- {sym}" + (f" -> {fix}" if fix else ""))
    if c.related_topics:
        parts.append(f"**Voir aussi :** {', '.join(c.related_topics)}")
    clean_flags = [f for f in (c.flags or []) if f != "noise"]
    if clean_flags:
        parts.append(f"[{', '.join(clean_flags)}]")
    return "\n\n".join(p for p in parts if p)


def process_batch(chunks: list[Chunk], rpt: Report) -> list[Chunk]:
    frags = "\n\n".join(f"[Fragment {i+1}]\n{c.text}" for i,c in enumerate(chunks))
    raw   = _llm(BATCH_PROMPT.format(n=len(chunks), frags=frags), rpt)
    if raw is None:
        for c in chunks: c.status="SKIP"; c.notes="LLM failed"; c.method="llm"
        return chunks
    parsed = _parse(raw)
    if not parsed:
        log.warning("  JSON parse failed — keeping raw. Preview: %s", raw[:120])
        for c in chunks: c.status="KEEP"; c.cleaned=c.text; c.method="llm"; c.notes="JSON parse failed"
        return chunks
    for i,c in enumerate(chunks):
        if i >= len(parsed): c.status="KEEP"; c.cleaned=c.text; c.method="llm"; continue
        res = parsed[i]
        if not isinstance(res,dict): c.status="KEEP"; c.cleaned=c.text; c.method="llm"; continue
        keep = res.get("keep",True)
        cat  = str(res.get("category","unknown")).lower()
        flags = res.get("flags", [])
        is_noise = (cat == "noise" or
                    (cat == "logistics" and not res.get("qa_pairs") and not res.get("body")))
        if is_noise and "incomplete" not in flags and "inferred" not in flags:
            c.status="NOISE"; c.category="noise"; c.method="llm"; c.notes="LLM: noise"
        else:
            c.status         = "KEEP"
            c.category       = cat
            c.method         = "llm"
            c.topic          = str(res.get("topic", "")).strip()
            c.actor          = str(res.get("actor", "inconnu")).strip()
            c.prerequisites  = res.get("prerequisites", []) or []
            c.steps          = res.get("steps", []) or []
            c.body           = str(res.get("body", "")).strip()
            c.result         = str(res.get("result", "")).strip()
            c.error_cases    = res.get("error_cases", []) or []
            c.related_topics = res.get("related_topics", []) or []
            c.flags          = flags
            c.cleaned        = _build_cleaned_text(c)
            c.qa_pairs       = [
                qa for qa in res.get("qa_pairs", [])
                if isinstance(qa, dict)
                and qa.get("question","").strip()
                and qa.get("answer","").strip()
            ]
    return chunks


_first = [True]

def _open_outputs():
    for p in (OUTPUT_FILE,QA_FILE,REPORT_FILE): Path(p).parent.mkdir(parents=True,exist_ok=True)
    tf = Path(OUTPUT_FILE).open("w",encoding="utf-8",buffering=1)
    qf = Path(QA_FILE).open("w",    encoding="utf-8",buffering=1)
    rf = Path(REPORT_FILE).open("w", encoding="utf-8",buffering=1)
    rf.write("ChronoBrain Cleaning Report\n" + "="*42 + "\n")
    rf.write("Live — updated after every batch\n\n")
    rf.write(f"{'ID':<12} {'STATUS':<12} {'METHOD':<8} {'CATEGORY':<12} NOTES\n" + "-"*80 + "\n")
    rf.flush()
    log.info("  Output files open — watch them with: tail -f %s", OUTPUT_FILE)
    return tf, qf, rf

def _emit(c: Chunk, tf, qf, rf, rpt: Report):
    if c.status=="KEEP" and c.cleaned:
        if not _first[0]: tf.write("\n\n---\n\n")
        _first[0]=False; tf.write(c.cleaned); tf.flush()
    for qa in c.qa_pairs:
        rec = {
            "instruction": qa.get("question","").strip(),
            "input":       "",
            "output":      qa.get("answer","").strip(),
            "difficulty":  qa.get("difficulty","basic"),
            "source":      c.source,
            "topic":       c.topic,
            "category":    c.category,
            "actor":       c.actor,
            "chunk_id":    c.chunk_id,
            "flags":       c.flags,
        }
        if rec["instruction"] and rec["output"]:
            qf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            qf.flush(); rpt.qa += 1
    rf.write(f"{c.chunk_id:<12} {c.status:<12} {c.method:<8} {c.category:<12} {c.notes[:55]}\n")
    rf.flush()
    if   c.status=="KEEP":      rpt.kept    += 1
    elif c.status=="NOISE":     rpt.noise   += 1
    elif c.status=="DUPLICATE": rpt.dupes   += 1
    elif c.status=="SKIP":      rpt.skipped += 1

def _close(tf,qf,rf,rpt:Report):
    rf.write(f"\n{'='*42}\nTotal:{rpt.total} Kept:{rpt.kept} Noise:{rpt.noise} "
             f"Dupes:{rpt.dupes} QA:{rpt.qa} LLM_calls:{rpt.calls} "
             f"LLM_time:{rpt.t_llm:.0f}s\n")
    rf.flush(); tf.close(); qf.close(); rf.close()


def run(files: list[Path], dry_run:bool=False) -> Report:
    rpt=Report(); _first[0]=True
    chunks: list[Chunk]=[]
    for f in files: log.info("Reading: %s",f.name); chunks.extend(chunk_file(f))
    rpt.total=len(chunks)
    log.info("Total: %d chunks\n",rpt.total)

    log.info("Stage 1A: Rule filter (no LLM)")
    t0=time.time()
    for c in chunks:
        if rule_filter(c): c.status="NOISE"; c.method="rule"; c.notes="Rule: noise/filler"
    rpt.t_rules+=time.time()-t0
    n_noise=sum(1 for c in chunks if c.status=="NOISE")
    log.info("  %d/%d dropped (%.0f%%) — no LLM used\n",n_noise,rpt.total,100*n_noise/max(1,rpt.total))

    log.info("Stage 1B: Deduplication (no LLM)")
    t0=time.time(); chunks=deduplicate(chunks); rpt.t_rules+=time.time()-t0
    n_dup=sum(1 for c in chunks if c.status=="DUPLICATE")
    log.info("  %d duplicates found\n",n_dup)

    candidates=[c for c in chunks if c.status not in ("NOISE","DUPLICATE")]
    log.info("  %d chunks (%.0f%%) go to LLM — %d%% handled by rules\n",
             len(candidates),100*len(candidates)/max(1,rpt.total),
             100-int(100*len(candidates)/max(1,rpt.total)))

    if dry_run:
        from collections import Counter
        log.info("Dry-run: no LLM, no files.")
        for s,n in sorted(Counter(c.status or "PENDING" for c in chunks).items()):
            log.info("  %-12s %d",s,n)
        return rpt

    tf,qf,rf = _open_outputs()
    for c in chunks:
        if c.status in ("NOISE","DUPLICATE"): _emit(c,tf,qf,rf,rpt)

    n_batches=(len(candidates)+BATCH_SIZE-1)//BATCH_SIZE
    log.info("Stage 2: LLM batches (%d batches of %d)",n_batches,BATCH_SIZE)
    done=0
    for bi in range(0,len(candidates),BATCH_SIZE):
        batch=candidates[bi:bi+BATCH_SIZE]; bn=bi//BATCH_SIZE+1
        log.info("  Batch %d/%d — %d chunks",bn,n_batches,len(batch))
        for c in process_batch(batch,rpt):
            _emit(c,tf,qf,rf,rpt); done+=1
        if bn%5==0:
            rate=done/max(1,rpt.t_llm)*60
            eta=(len(candidates)-done)/max(0.01,rate)
            log.info("  >> %d/%d done | %d QA pairs | ~%.0f min left",done,len(candidates),rpt.qa,eta)

    _close(tf,qf,rf,rpt)
    return rpt


def main():
    global OLLAMA_URL,LLM_MODEL,OUTPUT_FILE,QA_FILE,REPORT_FILE,BATCH_SIZE
    p=argparse.ArgumentParser(description="ChronoBrain fast data cleaner (~30x faster)")
    p.add_argument("--input","-i"); p.add_argument("--data-dir","-d",default=DATA_DIR)
    p.add_argument("--output","-o",default=OUTPUT_FILE); p.add_argument("--qa-output",default=QA_FILE)
    p.add_argument("--report",default=REPORT_FILE); p.add_argument("--ollama-url",default=OLLAMA_URL)
    p.add_argument("--model",default=LLM_MODEL); p.add_argument("--batch","-b",type=int,default=BATCH_SIZE)
    p.add_argument("--dry-run",action="store_true",
        help="Rule-classify only — no LLM calls, instant")
    args=p.parse_args()
    OLLAMA_URL=args.ollama_url; LLM_MODEL=args.model
    OUTPUT_FILE=args.output; QA_FILE=args.qa_output; REPORT_FILE=args.report; BATCH_SIZE=args.batch
    files=([Path(args.input)] if args.input else sorted(Path(args.data_dir).glob("formation_chrono_1.txt")))
    if not files or not files[0].exists(): log.error("No files found"); sys.exit(1)

    log.info("ChronoBrain Fast Data Cleaner")
    log.info("File  : %s",[f.name for f in files])
    log.info("Model : %s @ %s",LLM_MODEL,OLLAMA_URL)
    log.info("Batch : %d chunks/call\n",BATCH_SIZE)

    if not args.dry_run:
        try:
            import ollama as _o; _o.Client(host=OLLAMA_URL).list(); log.info("✓ Ollama reachable\n")
        except Exception as e: log.error("Cannot reach Ollama: %s",e); sys.exit(1)

    t0=time.time(); rpt=run(files,dry_run=args.dry_run); tot=time.time()-t0
    print()
    print("="*55)
    print(f"  Chunks       : {rpt.total}")
    print(f"  Kept         : {rpt.kept}")
    print(f"  Noise        : {rpt.noise}")
    print(f"  Duplicates   : {rpt.dupes}")
    print(f"  QA pairs     : {rpt.qa}")
    print(f"  LLM calls    : {rpt.calls}  (old version would have made {rpt.total*3})")
    print(f"  Total time   : {tot/60:.1f} min")
    if not args.dry_run:
        print(f"\n  Cleaned text : {OUTPUT_FILE}")
        print(f"  QA pairs     : {QA_FILE}")
        print(f"  Next step    : python chronobrain_v10.py --rebuild")
    print("="*55)

if __name__=="__main__":
    main()