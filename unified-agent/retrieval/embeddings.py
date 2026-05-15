#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Embeddings Manager - Wrapper pour modèles d'embedding
Gère cache + batch processing
"""

import logging
from typing import List, Dict, Optional, Any
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)


class EmbeddingsManager:
    """Gère la génération et caching d'embeddings"""
    
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        cache_dir: Optional[Path] = None,
        device: str = "cpu",
    ):
        """
        Initialize Embeddings Manager
        
        Args:
            model_name: Nom du modèle
            cache_dir: Répertoire cache (optionnel)
            device: "cpu" ou "cuda"
        """
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.device = device
        self.model = None
        self.embedding_cache = {}
        
        self._load_model()
    
    def _load_model(self):
        """Charge le modèle d'embedding"""
        try:
            from sentence_transformers import SentenceTransformer
            
            logger.info(f"Chargement {self.model_name}...")
            try:
                self.model = SentenceTransformer(
                    self.model_name,
                    device=self.device,
                    local_files_only=True
                )
            except Exception as e:
                logger.warning(f"Modèle non trouvé en local, tentative de téléchargement... ({e})")
                self.model = SentenceTransformer(
                    self.model_name,
                    device=self.device
                )
            logger.info(f"✓ Model chargé ({self.get_embedding_dim()} dims)")
        except ImportError:
            logger.error(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
            raise
    
    def get_embedding_dim(self) -> int:
        """Retourne la dimension des embeddings"""
        if self.model is None:
            return 384  # Default
        
        return self.model.get_sentence_embedding_dimension()
    
    def embed(self, text: str, is_query: bool = False) -> np.ndarray:
        """
        Génère un embedding pour un texte
        
        Args:
            text: Texte à embedder
            is_query: Si True, ajoute le préfixe 'query: ' (pour E5)
            
        Returns:
            Array (embedding_dim,)
        """
        # Préfixe pour E5
        if "e5" in self.model_name.lower():
            text = f"query: {text}" if is_query else f"passage: {text}"
            
        # Check cache
        text_hash = hash(text) % (10 ** 10)
        if text_hash in self.embedding_cache:
            logger.debug("Cache hit")
            return self.embedding_cache[text_hash]
        
        # Generate
        embedding = self.model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        embedding = embedding.astype(np.float32)
        
        # Cache
        self.embedding_cache[text_hash] = embedding
        
        return embedding
    
    def embed_batch(self, texts: List[str], batch_size: int = 32, is_queries: bool = False) -> np.ndarray:
        """
        Génère des embeddings batch
        
        Args:
            texts: Liste de textes
            batch_size: Taille du batch
            is_queries: Si True, ajoute le préfixe 'query: ' (pour E5)
            
        Returns:
            Array (N, embedding_dim)
        """
        # Préfixe pour E5
        if "e5" in self.model_name.lower():
            processed_texts = [
                f"query: {t}" if is_queries else f"passage: {t}"
                for t in texts
            ]
        else:
            processed_texts = texts
            
        embeddings = self.model.encode(
            processed_texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 10,
        )
        
        embeddings = embeddings.astype(np.float32)
        
        logger.info(f"✓ Embedded {len(texts)} texts (as {'queries' if is_queries else 'passages'})")
        
        return embeddings
    
    def clear_cache(self):
        """Vide le cache"""
        self.embedding_cache.clear()
        logger.info("✓ Embedding cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Retourne les stats du cache"""
        return {
            "cache_size": len(self.embedding_cache),
            "model_name": self.model_name,
            "device": self.device,
        }


# Test simple
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    manager = EmbeddingsManager(device="cpu")
    
    # Single embed
    text = "Ceci est un texte de test"
    embedding = manager.embed(text)
    print(f"✓ Embedding shape: {embedding.shape}")
    
    # Batch embed
    texts = [
        "Procédure d'approbation",
        "Comment faire une demande",
        "Types d'heures supplémentaires",
    ]
    embeddings = manager.embed_batch(texts)
    print(f"✓ Batch embeddings shape: {embeddings.shape}")
    
    # Cache stats
    print("📊 Cache stats:", manager.get_cache_stats())
