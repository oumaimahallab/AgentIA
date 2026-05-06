import sys
from pathlib import Path
import logging

PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.append(str(PROJECT_ROOT))

from config.settings import get_config
from retrieval.embeddings import EmbeddingsManager
from retrieval.faiss_manager import FAISSManager

logging.basicConfig(level=logging.INFO)

def debug_query(query):
    config = get_config()
    embeddings = EmbeddingsManager(config.embeddings.MODEL_NAME)
    faiss_mgr = FAISSManager(config.paths.FAISS_INDEX_DIR)
    
    query_emb = embeddings.embed(query)
    results = faiss_mgr.search(query_emb, top_k=3)
    
    print(f"\nResults for: {query}")
    print("-" * 50)
    for i, res in enumerate(results):
        print(f"[{i+1}] Score: {res['score']:.4f} | Source: {res.get('source')}")
        print(f"Content: {res.get('content')}")
        print("-" * 30)

if __name__ == "__main__":
    debug_query("Définition habilitation")
