#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reranker - Améliore le Ranking des Résultats
Utilise un modèle cross-encoder pour rerank
"""

import logging
from typing import List, Dict, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)


class Reranker:
    """Rerank les résultats de retrieval avec un cross-encoder"""
    
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2",
        use_gpu: bool = False,
    ):
        """
        Initialize Reranker
        
        Args:
            model_name: Nom du modèle cross-encoder
            use_gpu: Utiliser GPU si disponible
        """
        self.model_name = model_name
        self.use_gpu = use_gpu
        self.model = None
        
        try:
            from sentence_transformers import CrossEncoder
            
            logger.info(f"Chargement {model_name}...")
            self.model = CrossEncoder(
                model_name,
                max_length=512,
                device="cuda" if use_gpu else "cpu",
            )
            logger.info("✓ Reranker chargé")
        except ImportError:
            logger.warning(
                "sentence-transformers not available. "
                "Reranking will be disabled. "
                "Install with: pip install sentence-transformers"
            )
    
    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Rerank les documents selon la requête
        
        Args:
            query: Texte de la requête
            documents: Résultats de retrieval
            top_k: Nombre de résultats finaux
            
        Returns:
            Résultats reranked et triés
        """
        
        if self.model is None:
            logger.warning("Reranker non disponible, retour résultats originaux")
            return documents[:top_k]
        
        if not documents:
            return []
        
        # Prépare pairs (query, document)
        document_texts = [
            doc.get("text", doc.get("content", ""))
            for doc in documents
        ]
        
        # Predictions
        try:
            scores = self.model.predict(
                [[query, doc] for doc in document_texts]
            )
        except Exception as e:
            logger.error(f"Erreur reranking: {e}")
            return documents[:top_k]
        
        # Rerank
        scored_docs = [
            {**doc, "rerank_score": float(score)}
            for doc, score in zip(documents, scores)
        ]
        
        sorted_docs = sorted(
            scored_docs,
            key=lambda x: x["rerank_score"],
            reverse=True
        )
        
        logger.debug(
            f"Reranked {len(documents)} → top {min(top_k, len(sorted_docs))}"
        )
        
        return sorted_docs[:top_k]
    
    def rerank_batch(
        self,
        queries: List[str],
        documents_batch: List[List[Dict[str, Any]]],
        top_k: int = 5,
    ) -> List[List[Dict[str, Any]]]:
        """
        Rerank batch de documents
        
        Args:
            queries: Liste de requêtes
            documents_batch: Batch de listes de documents
            top_k: Nombre de résultats par query
            
        Returns:
            Résultats reranked
        """
        
        batch_results = []
        for query, documents in zip(queries, documents_batch):
            reranked = self.rerank(query, documents, top_k)
            batch_results.append(reranked)
        
        return batch_results
    
    def is_available(self) -> bool:
        """Check si le reranker est disponible"""
        return self.model is not None


# Test simple
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    reranker = Reranker(use_gpu=False)
    
    if not reranker.is_available():
        print("⚠️ Reranker non disponible (sentence-transformers not installed)")
        print("Install with: pip install sentence-transformers")
    else:
        # Test data
        query = "Quel est le processus d'approbation des congés?"
        
        documents = [
            {
                "chunk_id": "doc1",
                "text": "Les congés sont approuvés par le manager puis RH",
                "combined_score": 0.8,
            },
            {
                "chunk_id": "doc2",
                "text": "Un chat miaule dans la maison",
                "combined_score": 0.7,
            },
            {
                "chunk_id": "doc3",
                "text": "Demande de congé: 1) Remplir formulaire 2) Envoyer manager 3) Attendre",
                "combined_score": 0.75,
            },
        ]
        
        results = reranker.rerank(query, documents, top_k=2)
        
        print("✓ Original scores:")
        for d in documents:
            print(f"  {d['chunk_id']}: {d['combined_score']:.2f}")
        
        print("\n✓ Reranked results:")
        for r in results:
            print(f"  {r['chunk_id']}: {r.get('rerank_score', 'N/A'):.2f}")
