import sys
import os
import json
import logging
import numpy as np
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.append(str(PROJECT_ROOT))

from config.settings import get_config
from retrieval.embeddings import EmbeddingsManager
from retrieval.faiss_manager import FAISSManager
from retrieval.bm25_manager import BM25Manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rebuild")

def rebuild():
    config = get_config()
    
    # 1. Paths
    DOCUMENTS_JSON = PROJECT_ROOT.parent / "DataCl" / "data" / "processed" / "documents.json"
    TRANSCRIPTS_JSON = PROJECT_ROOT.parent / "ChronoBrain-main" / "data" / "metadata_v13" / "metadata_v13.json"
    
    logger.info(f"Loading documents from: {DOCUMENTS_JSON}")
    logger.info(f"Loading transcripts from: {TRANSCRIPTS_JSON}")
    
    import hashlib
    
    # 2. Load and merge
    chunks = []
    
    def get_fingerprint(text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def chunk_text(text, max_chars=1500, overlap=200):
        """Découpe un texte en morceaux de max_chars avec un chevauchement."""
        if len(text) <= max_chars:
            return [text]
        
        chunks_list = []
        start = 0
        while start < len(text):
            end = start + max_chars
            # On essaie de couper sur un espace pour ne pas couper de mots
            if end < len(text):
                last_space = text.rfind(' ', start, end)
                if last_space != -1 and last_space > start + (max_chars // 2):
                    end = last_space
            
            chunk = text[start:end].strip()
            if len(chunk) > 20: # Évite les morceaux trop petits
                chunks_list.append(chunk)
                
            start = end - overlap
            if start >= len(text) - overlap:
                break
                
        return chunks_list

    if DOCUMENTS_JSON.exists():
        with open(DOCUMENTS_JSON, encoding="utf-8") as f:
            data = json.load(f)
            for i, doc in enumerate(data):
                text = doc.get("text", "").strip()
                if not text or len(text.split()) < 10:
                    continue
                    
                chunks.append({
                    "chunk_id": f"doc_{i}",
                    "fingerprint": get_fingerprint(text),
                    "content": text,
                    "source": doc.get("source", "Document"),
                    "type": "document",
                    "location": doc.get("location", "")
                })
    
    if TRANSCRIPTS_JSON.exists():
        with open(TRANSCRIPTS_JSON, encoding="utf-8") as f:
            data = json.load(f)
            for i, doc in enumerate(data):
                text = doc.get("text", "").strip()
                # On filtre les "Ok", "Oui", etc. qui polluent l'index
                if not text or len(text.split()) < 10:
                    continue
                    
                topic = doc.get("topic", "")
                source_name = doc.get("source", "")
                
                # Si le topic est "Error" ou vide, on essaie de l'extraire du nom de fichier
                if not topic or topic == "Error":
                    import re
                    match = re.search(r"^(.*?)(?:-\d{8}|_GT)", source_name)
                    if match:
                        topic = match.group(1).replace("_", " ").strip()
                    else:
                        topic = source_name.split("-")[0].strip()
                
                # On préfixe le texte avec le sujet pour aider la recherche sémantique
                prefix = f"Sujet: {topic}\n" if topic and topic != "Error" else ""
                
                # Découpage en morceaux pour les transcriptions (souvent très longues)
                text_chunks = chunk_text(text, max_chars=1200, overlap=300)
                
                for j, sub_text in enumerate(text_chunks):
                    full_text = prefix + sub_text
                    suffix = f"_{j}" if len(text_chunks) > 1 else ""
                    
                    chunks.append({
                        "chunk_id": f"transcript_{i}{suffix}",
                        "fingerprint": get_fingerprint(full_text),
                        "content": full_text,
                        "source": source_name,
                        "type": "transcription",
                        "location": topic
                    })
    
    if not chunks:
        logger.error("No chunks found!")
        return
    
    logger.info(f"Total chunks to index: {len(chunks)}")
    
    # 3. Initialize components
    embeddings = EmbeddingsManager(config.embeddings.MODEL_NAME)
    faiss_mgr = FAISSManager(config.paths.FAISS_INDEX_DIR, embedding_dim=embeddings.get_embedding_dim())
    bm25_mgr = BM25Manager(config.paths.BM25_INDEX_DIR)
    
    # 4. Clear and Rebuild
    faiss_mgr.rebuild_from_scratch()
    bm25_mgr.rebuild_from_scratch()
    
    # 5. Indexing
    texts = [c["content"] for c in chunks]
    
    # BM25 - Simple index all
    logger.info("Indexing BM25...")
    bm25_mgr.add_documents(texts, chunks)
    bm25_mgr.save()
    
    # FAISS - Process in batches
    batch_size = 128
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i : i + batch_size]
        batch_metas = chunks[i : i + batch_size]
        
        logger.info(f"Embedding FAISS batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}...")
        batch_embs = embeddings.embed_batch(batch_texts, batch_size=batch_size)
        faiss_mgr.add_embeddings(batch_embs, batch_metas)
        
    # 6. Save
    faiss_mgr.save()
    logger.info("✅ Unified Index (FAISS + BM25) rebuilt successfully!")

if __name__ == "__main__":
    rebuild()
