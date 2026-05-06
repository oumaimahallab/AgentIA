#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAISS Manager - Gestion du Vector Index
Indexation et recherche sémantique avec FAISS
"""

import logging
import pickle
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
import numpy as np

logger = logging.getLogger(__name__)


class FAISSManager:
    """Gère l'index FAISS pour recherche sémantique"""
    
    def __init__(self, index_dir: Path, embedding_dim: int = 384):
        """
        Initialize FAISS Manager
        
        Args:
            index_dir: Répertoire où stocker l'index
            embedding_dim: Dimension des embeddings (défaut: 384 pour all-MiniLM)
        """
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        
        self.embedding_dim = embedding_dim
        self.index_path = self.index_dir / "index.faiss"
        self.metadata_path = self.index_dir / "metadata.pkl"
        self.embeddings_path = self.index_dir / "embeddings.npy"
        
        self.index = None
        self.metadata: List[Dict[str, Any]] = []
        self.embeddings = None
        
        self._load_or_create_index()
    
    def _load_or_create_index(self):
        """Charge l'index existant ou crée un nouveau"""
        try:
            import faiss
            
            if self.index_path.exists():
                logger.info(f"Chargement index FAISS de: {self.index_path}")
                self.index = faiss.read_index(str(self.index_path))
                
                with open(self.metadata_path, 'rb') as f:
                    self.metadata = pickle.load(f)
                
                if self.embeddings_path.exists():
                    self.embeddings = np.load(self.embeddings_path)
                
                logger.info(f"✓ Index chargé: {len(self.metadata)} vecteurs")
            else:
                logger.info(f"Création nouvel index FAISS (dim={self.embedding_dim})")
                self.index = faiss.IndexFlatIP(self.embedding_dim)
                self.metadata = []
                self.embeddings = np.zeros((0, self.embedding_dim), dtype=np.float32)
        
        except ImportError:
            logger.error("FAISS not installed. Install with: pip install faiss-cpu")
            raise
    
    def add_embeddings(
        self,
        embeddings: np.ndarray,
        metadatas: List[Dict[str, Any]],
    ) -> int:
        """
        Ajoute des embeddings à l'index
        
        Args:
            embeddings: Array (N, embedding_dim)
            metadatas: Liste de dictionnaires avec métadonnées
            
        Returns:
            Nombre d'embeddings ajoutés
        """
        if len(embeddings) == 0:
            logger.warning("Pas d'embeddings à ajouter")
            return 0
        
        if len(embeddings) != len(metadatas):
            raise ValueError(f"Mismatch: {len(embeddings)} embeddings vs {len(metadatas)} metadatas")
        
        # Normalise les embeddings (important pour IndexFlatIP)
        embeddings = embeddings.astype(np.float32)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / (norms + 1e-10)
        
        # Ajoute à l'index
        self.index.add(embeddings)
        self.metadata.extend(metadatas)
        
        # Accumule les embeddings
        if self.embeddings is None:
            self.embeddings = embeddings
        else:
            self.embeddings = np.vstack([self.embeddings, embeddings])
        
        logger.info(f"✓ Ajouté {len(embeddings)} embeddings (total: {self.index.ntotal})")
        
        return len(embeddings)
    
    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 8,
        score_threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        Recherche dans l'index
        
        Args:
            query_embedding: Embedding de la query (1, embedding_dim)
            top_k: Nombre de résultats
            score_threshold: Score minimum (0-1 pour cosine similarity)
            
        Returns:
            Liste de résultats {metadata, score, index}
        """
        if self.index.ntotal == 0:
            logger.warning("Index est vide!")
            return []
        
        # Normalise la query
        query_embedding = query_embedding.astype(np.float32).reshape(1, -1)
        norms = np.linalg.norm(query_embedding, axis=1, keepdims=True)
        query_embedding = query_embedding / (norms + 1e-10)
        
        # Recherche
        distances, indices = self.index.search(query_embedding, min(top_k, self.index.ntotal))
        
        # Formate les résultats
        results = []
        for i, (distance, idx) in enumerate(zip(distances[0], indices[0])):
            if distance >= score_threshold and idx != -1:
                result = {
                    **self.metadata[idx],
                    "score": float(distance),  # Cosine similarity (0-1)
                    "index": int(idx),
                    "rank": i + 1,
                }
                results.append(result)
        
        logger.debug(f"Search query: {len(results)}/{top_k} résultats (threshold: {score_threshold})")
        
        return results
    
    def search_batch(
        self,
        query_embeddings: np.ndarray,
        top_k: int = 8,
        score_threshold: float = 0.3,
    ) -> List[List[Dict[str, Any]]]:
        """
        Recherche batch
        
        Args:
            query_embeddings: Array (N, embedding_dim)
            top_k: Nombre de résultats par query
            score_threshold: Score minimum
            
        Returns:
            Liste de listes de résultats
        """
        batch_results = []
        for query in query_embeddings:
            results = self.search(query, top_k, score_threshold)
            batch_results.append(results)
        
        return batch_results
    
    def save(self):
        """Sauvegarde l'index"""
        if self.index is None:
            logger.warning("Pas d'index à sauvegarder")
            return
        
        import faiss
        
        try:
            faiss.write_index(self.index, str(self.index_path))
            
            with open(self.metadata_path, 'wb') as f:
                pickle.dump(self.metadata, f)
            
            if self.embeddings is not None:
                np.save(self.embeddings_path, self.embeddings)
            
            logger.info(f"✓ Index sauvegardé en: {self.index_path}")
        except Exception as e:
            logger.error(f"✗ Erreur sauvegarde: {e}")
            raise
    
    def clear(self):
        """Vide l'index"""
        import faiss
        
        self.index = faiss.IndexFlatIP(self.embedding_dim)
        self.metadata = []
        self.embeddings = np.zeros((0, self.embedding_dim), dtype=np.float32)
        
        logger.info("✓ Index vidé")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques"""
        index_size_mb = 0
        if self.index_path.exists():
            index_size_mb = self.index_path.stat().st_size / (1024 * 1024)
        
        return {
            "total_vectors": self.index.ntotal,
            "embedding_dim": self.embedding_dim,
            "index_size_mb": index_size_mb,
            "metadata_count": len(self.metadata),
        }
    
    def rebuild_from_scratch(self):
        """Reconstruit l'index (supprime ancien)"""
        import faiss
        
        logger.warning("Reconstruction de l'index (suppression ancien)")
        
        # Supprime fichiers
        for path in [self.index_path, self.metadata_path, self.embeddings_path]:
            if path.exists():
                path.unlink()
        
        # Crée nouveau
        self.index = faiss.IndexFlatIP(self.embedding_dim)
        self.metadata = []
        self.embeddings = np.zeros((0, self.embedding_dim), dtype=np.float32)
        
        logger.info("✓ Index rebuilt")


# Test simple
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    manager = FAISSManager(Path("/tmp/faiss_test"))
    
    # Crée embeddings test
    embeddings = np.random.randn(10, 384).astype(np.float32)
    metadatas = [
        {"chunk_id": f"chunk_{i}", "text": f"Texte {i}", "source": "test.pdf"}
        for i in range(10)
    ]
    
    manager.add_embeddings(embeddings, metadatas)
    manager.save()
    
    # Search
    query = np.random.randn(1, 384).astype(np.float32)
    results = manager.search(query, top_k=3)
    print(f"✓ Results: {len(results)} found")
    
    print("📊 Stats:", manager.get_stats())
