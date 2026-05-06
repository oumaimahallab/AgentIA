# ChronoBrain — Production RAG Chatbot

Local, private, hallucination-resistant chatbot for Inetum training data.
Built with Hybrid Retrieval (FAISS + BM25), Llama3, and strict grounding.

---

## Architecture

```
User query
    │
    ▼
is_valid_query()          ← validator.py
    │
    ▼
ResponseCache.get()       ← cache.py  (skip LLM if repeated question)
    │
    ▼
HybridRetriever.retrieve()  ← hybrid_retriever.py
    ├── FAISS semantic search  (BGE embeddings, cosine similarity)
    ├── BM25 keyword search    (rank_bm25)
    ├── Hybrid fusion          (0.7 × semantic + 0.3 × BM25)
    ├── Metadata boost         (prefer clean chunks + longer chunks)
    ├── Score filter           (MIN_SCORE = 0.45)
    ├── Soft-floor fallback    (keep top-2 if all filtered)
    └── MMR deduplication
    │
    ▼
build_prompt()            ← llm.py
    │
    ▼
safe_complete()           ← llm.py  (Llama3 via Ollama, retry on timeout)
    │
    ▼
strip_hallucinations()    ← postprocess.py
faithfulness_check()      ← postprocess.py
    │
    ▼
ResponseCache.set()
ConversationHistory.add()
    │
    ▼
Answer displayed
```

---

## Installation

### 1. Install Ollama and pull Llama3

```bash
# Install Ollama: https://ollama.com
ollama pull llama3
```

### 2. Clone / set up the project

```bash
cd /path/to/project
pip install -r requirements.txt
```

### 3. Prepare your data

Place your pre-cleaned JSON files (from `transcript_cleaner.py`) in:
```
data/clean_json/
    Formation_xxx_cleaned.json
    Formation_yyy_cleaned.json
    ...
```

Each JSON file must be an array of chunk objects:
```json
[
  {
    "chunk_id":        "formation_xxx_02m33_03m21",
    "source":          "formation_xxx.txt",
    "start_time":      "02:33",
    "end_time":        "03:21",
    "start_sec":       153,
    "end_sec":         201,
    "text":            "...",
    "word_count":      74,
    "has_asr_warning": false
  }
]
```

---

## Step 1 — Ingest data (build FAISS + BM25 indices)

```bash
python ingest.py
```

Options:
```bash
python ingest.py --data path/to/custom/json   # custom data folder
python ingest.py --force                       # force full re-ingestion
```

What it creates:
```
db/
├── faiss_index/
│   ├── index.faiss    ← FAISS vector index
│   └── chunks.pkl     ← chunk metadata + text
├── bm25_index.pkl     ← BM25 keyword index
└── metadata.db        ← SQLite: tracks which files are ingested
```

---

## Step 2 — Run the chatbot

### CLI
```bash
python main.py
```

With options:
```bash
python main.py --debug      # show retrieval scores after each answer
python main.py --no-eval    # skip keyword-overlap faithfulness check
```

### Streamlit UI
```bash
streamlit run  py
```

---

## Chat commands

| Command      | Effect                              |
|---|---|
| `quit`       | Exit                                |
| `reset`      | Clear history + cache               |
| `stats`      | Show session metrics                |
| `debug on`   | Enable retrieval score display      |
| `debug off`  | Disable retrieval score display     |

---

## Configuration (config.py)

| Parameter          | Default | Description                                |
|---|---|---|
| `LLM_MODEL`        | `llama3` | Ollama model name                        |
| `EMBED_MODEL`      | `BAAI/bge-small-en-v1.5` | Sentence embedding model  |
| `TOP_K`            | `6`     | Candidates fetched per retriever           |
| `MIN_SCORE`        | `0.45`  | Fused score threshold                      |
| `SEMANTIC_WEIGHT`  | `0.7`   | Weight for FAISS in hybrid fusion          |
| `BM25_WEIGHT`      | `0.3`   | Weight for BM25 in hybrid fusion           |
| `MAX_CONTEXT_TOKENS` | `900` | Token budget sent to LLM                  |
| `HISTORY_TURNS`    | `3`     | Conversation turns kept in context         |
| `LOG_LEVEL`        | `WARNING` | Set `DEBUG` for verbose retrieval logs  |

---

## Project structure

```
/project
├── main.py               CLI chatbot
├──  py                Streamlit UI (bonus)
├── config.py             All configuration
├── validator.py          Input validation
├── hybrid_retriever.py   FAISS + BM25 hybrid retrieval
├── llm.py                Prompt builder + Ollama interface
├── postprocess.py        Hallucination stripper + faithfulness check
├── cache.py              LRU response cache
├── ingest.py             Index builder
├── requirements.txt
│
├── data/
│   └── clean_json/       Pre-cleaned JSON chunks
│
└── db/
    ├── faiss_index/
    │   ├── index.faiss
    │   └── chunks.pkl
    ├── bm25_index.pkl
    └── metadata.db
```

---

## Troubleshooting

**`FileNotFoundError: FAISS index not found`**
→ Run `python ingest.py` first.

**Ollama timeout**
→ Llama3 needs ~8 GB RAM. Check `ollama ps` to confirm model is loaded.
→ Increase `LLM_TIMEOUT` in config.py if needed.

**Poor answer quality**
→ Run `python main.py --debug` and check retrieval scores.
→ If scores are low (< 0.3), lower `MIN_SCORE` in config.py.
→ If scores are high but answers wrong, the relevant chunk may be in a different JSON file — check `data/clean_json/`.

**Hallucinations still occurring**
→ Ensure you are using `llama3`, not `phi3`. Llama3 follows grounding instructions significantly better.
→ Check `LOG_LEVEL = "DEBUG"` in config.py to see which chunks are retrieved.
