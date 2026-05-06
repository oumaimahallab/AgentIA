#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hybrid Retriever - Combine Semantic + Keyword Search
Fusionne FAISS + BM25 intelligemment
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Combine FAISS (semantic) + BM25 (keyword) search"""
    
    def __init__(
        self,
        faiss_manager,
        bm25_manager,
        alpha: float = 0.5,
        semantic_top_k: int = 8,
        keyword_top_k: int = 8,
    ):
        """
        Initialize Hybrid Retriever
        
        Args:
            faiss_manager: FAISS manager instance
            bm25_manager: BM25 manager instance
            alpha: Weight pour fusion (0.5 = poids égal)
            semantic_top_k: Top-K pour semantic search
            keyword_top_k: Top-K pour keyword search
        """
        self.faiss = faiss_manager
        self.bm25 = bm25_manager
        self.alpha = alpha
        self.semantic_top_k = semantic_top_k
        self.keyword_top_k = keyword_top_k
    
    def search(
        self,
        query_embedding: np.ndarray,
        query_text: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Recherche hybride: semantic + keyword
        
        Args:
            query_embedding: Embedding de la query (1, embedding_dim)
            query_text: Texte de la query
            top_k: Nombre de résultats finaux
            
        Returns:
            Liste de résultats fusionnés et rerank
        """
        
        # 1. SEMANTIC SEARCH (FAISS)
        semantic_results = self.faiss.search(
            query_embedding,
            top_k=self.semantic_top_k,
        )
        logger.debug(f"Semantic: {len(semantic_results)} résultats")
        
        # 2. KEYWORD SEARCH (BM25)
        keyword_results = self.bm25.search(
            query_text,
            top_k=self.keyword_top_k,
        )
        logger.debug(f"Keyword: {len(keyword_results)} résultats")
        
        # 3. FUSION
        merged = self._merge_results(semantic_results, keyword_results, top_k)
        
        logger.info(
            f"Hybrid search: {len(semantic_results)} semantic + "
            f"{len(keyword_results)} keyword → {len(merged)} merged (top-{top_k})"
        )
        
        return merged
    
    def _merge_results(
        self,
        semantic_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        Fusionne les résultats semantic et keyword
        
        Stratégie:
        1. Normalise les scores (0-1)
        2. Combine avec alpha: alpha*semantic + (1-alpha)*keyword
        3. Déduplique
        4. Rerank par score combiné
        """
        
        # Map: chunk_id → (semantic_score, semantic_result)
        semantic_map = {}
        for result in semantic_results:
            chunk_id = result.get("chunk_id") or result.get("id")
            semantic_map[chunk_id] = result
        
        # Map: chunk_id → (keyword_score, keyword_result)
        keyword_map = {}
        for result in keyword_results:
            chunk_id = result.get("chunk_id") or result.get("id")
            keyword_map[chunk_id] = result
        
        # Combine les scores
        combined_scores = {}
        all_chunk_ids = set(semantic_map.keys()) | set(keyword_map.keys())
        
        # Max semantic score for normalization
        max_semantic_score = max(
            (r["score"] for r in semantic_results),
            default=1.0
        )
        max_keyword_score = max(
            (r["score"] for r in keyword_results),
            default=1.0
        )
        
        for chunk_id in all_chunk_ids:
            semantic_score = 0.0
            keyword_score = 0.0
            
            if chunk_id in semantic_map:
                # Normalize semantic (déjà 0-1 pour cosine)
                semantic_score = semantic_map[chunk_id]["score"]
            
            if chunk_id in keyword_map:
                # Normalize keyword
                keyword_score = (
                    keyword_map[chunk_id]["score"] / max_keyword_score
                    if max_keyword_score > 0 else 0
                )
            
            # Combine
            combined_score = (
                self.alpha * semantic_score +
                (1 - self.alpha) * keyword_score
            )
            
            combined_scores[chunk_id] = combined_score
        
        # Trie par score combiné
        sorted_items = sorted(
            combined_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]
        
        # Formate résultats finaux
        results = []
        for rank, (chunk_id, combined_score) in enumerate(sorted_items):
            # Prend la meilleure source (semantic ou keyword)
            if chunk_id in semantic_map:
                result = semantic_map[chunk_id].copy()
            else:
                result = keyword_map[chunk_id].copy()
            
            # Ajoute le score combiné
            result["combined_score"] = float(combined_score)
            result["semantic_score"] = float(semantic_map.get(chunk_id, {}).get("score", 0))
            result["keyword_score"] = float(keyword_map.get(chunk_id, {}).get("score", 0))
            result["rank"] = rank + 1
            
            results.append(result)
        
        return results
    
    def search_batch(
        self,
        query_embeddings: np.ndarray,
        query_texts: List[str],
        top_k: int = 5,
    ) -> List[List[Dict[str, Any]]]:
        """
        Recherche batch hybride
        
        Args:
            query_embeddings: Array (N, embedding_dim)
            query_texts: Liste de textes
            top_k: Nombre de résultats par query
            
        Returns:
            Liste de listes de résultats
        """
        batch_results = []
        
        for embedding, text in zip(query_embeddings, query_texts):
            results = self.search(embedding, text, top_k)
            batch_results.append(results)
        
        return batch_results
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques"""
        return {
            "faiss_vectors": self.faiss.get_stats()["total_vectors"],
            "bm25_documents": self.bm25.get_stats()["total_documents"],
            "alpha": self.alpha,
            "semantic_top_k": self.semantic_top_k,
            "keyword_top_k": self.keyword_top_k,
        }


# Test simple
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    from faiss_manager import FAISSManager
    from bm25_manager import BM25Manager
    
    # Setup managers
    faiss_mgr = FAISSManager(Path("/tmp/faiss_test"))
    bm25_mgr = BM25Manager(Path("/tmp/bm25_test"))
    
    # Add test data
    embeddings = np.random.randn(3, 384).astype(np.float32)
    documents = [
        "Congés et vacances pour employés",
        "Procédure de demande de congé",
        "Calcul du solde de congés",
    ]
    metadatas = [
        {"chunk_id": f"chunk_{i}", "text": documents[i], "source": "policy.pdf"}
        for i in range(3)
    ]
    
    faiss_mgr.add_embeddings(embeddings, metadatas)
    bm25_mgr.add_documents(documents, metadatas)
    
    # Create hybrid retriever
    retriever = HybridRetriever(faiss_mgr, bm25_mgr, alpha=0.5)
    
    # Test search
    query_emb = np.random.randn(1, 384).astype(np.float32)
    results = retriever.search(query_emb, "congés vacances", top_k=2)
    
    print(f"✓ Hybrid results: {len(results)}")
    for r in results:
        print(f"  - Rank {r['rank']}: combined={r['combined_score']:.2f}")
    
    print("📊 Stats:", retriever.get_stats())
