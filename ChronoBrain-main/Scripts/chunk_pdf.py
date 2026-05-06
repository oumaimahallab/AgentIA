# stage2_chunk_embed.py — Chunk + Embed raw_extracts.json → FAISS index
# Run this AFTER stage1_extract.py

import os
import re
import json
import time
import requests
import numpy as np
import faiss
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# CONFIG
# ==========================================
class Config:
    INPUT_JSON          = "../data/stage1/raw_extracts.json"
    OUTPUT_CHUNKS_JSON  = "../data/stage2/chunks.json"
    INDEX_PATH          = "../data/stage2/vector.index"
    METADATA_PATH       = "../data/stage2/metadata.json"
    LOG_PATH            = "../data/logs/stage2_log.xlsx"

    EMBEDDING_MODEL     = "intfloat/multilingual-e5-base"
    MAX_CHUNK_WORDS     = 400

    # Optional: LLM enrichment via Groq (topic + keywords)
    USE_LLM_ENRICHMENT  = True
    GROQ_API_KEY        = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL          = "llama-3.1-8b-instant"
    GROQ_URL            = "https://api.groq.com/openai/v1/chat/completions"


# ==========================================
# CHUNKER
# ==========================================
def split_into_chunks(text: str, max_words: int = Config.MAX_CHUNK_WORDS) -> List[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), max_words):
        chunk = " ".join(words[i:i + max_words]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


# ==========================================
# LLM ENRICHMENT (topic + keywords)
# ==========================================
def llm_enrich(text: str) -> Dict:
    """Call Groq to extract topic and keywords. Returns defaults on failure."""
    if not Config.USE_LLM_ENRICHMENT or not Config.GROQ_API_KEY:
        return {"topic": "General", "keywords": []}

    prompt = f"""Extract the topic and 3-5 keywords from this French text.
Return ONLY valid JSON, no markdown, no explanation.
Format: {{"topic": "...", "keywords": ["...", "..."]}}

Text: {text[:800]}"""

    try:
        res = requests.post(
            Config.GROQ_URL,
            headers={
                "Authorization": f"Bearer {Config.GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": Config.GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1
            },
            timeout=20
        )
        content = res.json()["choices"][0]["message"]["content"].strip()
        # strip markdown fences if present
        content = re.sub(r"```json|```", "", content).strip()
        return json.loads(content)
    except Exception as e:
        print(f"  [LLM WARN] enrichment failed: {e}")
        return {"topic": "General", "keywords": []}


# ==========================================
# LOGGER
# ==========================================
def log_result(source_file: str, duration: float, num_chunks: int, error: str = ""):
    row = {
        "Timestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        "Source File": [source_file],
        "Processing Time (s)": [round(duration, 3)],
        "Chunks Created": [num_chunks],
        "Error": [error]
    }
    df_new = pd.DataFrame(row)
    os.makedirs(os.path.dirname(Config.LOG_PATH), exist_ok=True)

    if os.path.exists(Config.LOG_PATH):
        df_old = pd.read_excel(Config.LOG_PATH)
        pd.concat([df_old, df_new], ignore_index=True).to_excel(Config.LOG_PATH, index=False)
    else:
        df_new.to_excel(Config.LOG_PATH, index=False)


# ==========================================
# MAIN
# ==========================================
if __name__ == "__main__":

    # --- Load raw extracts ---
    if not os.path.exists(Config.INPUT_JSON):
        print(f"❌ Input not found: {Config.INPUT_JSON}")
        print("   Run stage1_extract.py first.")
        exit(1)

    with open(Config.INPUT_JSON, "r", encoding="utf-8") as f:
        raw_extracts: List[Dict] = json.load(f)

    print(f"📥 Loaded {len(raw_extracts)} raw pages/slides from {Config.INPUT_JSON}")

    # --- Load embedder ---
    print(f"\n🔄 Loading embedding model: {Config.EMBEDDING_MODEL}")
    embedder = SentenceTransformer(Config.EMBEDDING_MODEL)

    os.makedirs(os.path.dirname(Config.OUTPUT_CHUNKS_JSON), exist_ok=True)

    all_chunks: List[Dict] = []
    faiss_index = None

    # --- Group by source file for LLM enrichment efficiency ---
    files_seen = {}
    for extract in raw_extracts:
        src = extract["source_file"]
        if src not in files_seen:
            files_seen[src] = []
        files_seen[src].append(extract)

    # --- Process each file's pages/slides ---
    for source_file, pages in files_seen.items():
        print(f"\n📄 Chunking: {source_file} ({len(pages)} pages/slides)")
        start = time.time()
        file_chunks = []
        error_msg = ""

        try:
            # LLM enrichment: sample first 3 pages for topic/keywords
            sample_text = " ".join([p["raw_text"] for p in pages[:3]])
            enrichment = llm_enrich(sample_text)
            topic    = enrichment.get("topic", "General")
            keywords = enrichment.get("keywords", [])

            for page in pages:
                sub_chunks = split_into_chunks(page["raw_text"])
                for i, chunk_text in enumerate(sub_chunks):
                    file_chunks.append({
                        "text": chunk_text,
                        "source_file": source_file,
                        "type": page["type"],
                        "page_or_slide": page["page_or_slide"],
                        "chunk_index": i,
                        "extraction_method": page["extraction_method"],
                        "metadata": {
                            "topic": topic,
                            "keywords": keywords
                        }
                    })

            print(f"  ✅ {len(file_chunks)} chunks | topic: {topic}")

        except Exception as e:
            error_msg = str(e)
            print(f"  ❌ Error: {e}")

        duration = time.time() - start
        log_result(source_file, duration, len(file_chunks), error_msg)
        all_chunks.extend(file_chunks)

    # --- Embed all chunks ---
    print(f"\n🧠 Embedding {len(all_chunks)} chunks...")
    # multilingual-e5 needs "passage: " prefix
    texts_to_embed = [f"passage: {c['text']}" for c in all_chunks]

    embeddings = embedder.encode(
        texts_to_embed,
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=64
    )
    embeddings = np.array(embeddings).astype("float32")

    # --- Build FAISS index ---
    dimension = embeddings.shape[1]
    faiss_index = faiss.IndexFlatIP(dimension)   # cosine similarity (vectors are normalized)
    faiss_index.add(embeddings)
    print(f"✅ FAISS index built: {faiss_index.ntotal} vectors")

    # --- Save everything ---
    faiss.write_index(faiss_index, Config.INDEX_PATH)
    print(f"💾 Index saved to: {Config.INDEX_PATH}")

    with open(Config.METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)
    print(f"💾 Metadata saved to: {Config.METADATA_PATH}")

    with open(Config.OUTPUT_CHUNKS_JSON, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)
    print(f"💾 Chunks saved to: {Config.OUTPUT_CHUNKS_JSON}")

    print(f"\n✅ Pipeline complete.")
    print(f"   Total chunks indexed: {len(all_chunks)}")
    print(f"\n▶️  Your chatbot can now load:")
    print(f"   Index    → {Config.INDEX_PATH}")
    print(f"   Metadata → {Config.METADATA_PATH}")