#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BM25 Manager - Gestion de la recherche par mots-clés
Indexation et recherche keyword avec BM25
"""

import logging
import pickle
from pathlib import Path
from typing import List, Dict, Optional, Any
import re

logger = logging.getLogger(__name__)


class BM25Manager:
    """Gère l'index BM25 pour recherche par mots-clés"""
    
    def __init__(self, index_dir: Path):
        """
        Initialize BM25 Manager
        
        Args:
            index_dir: Répertoire où stocker l'index
        """
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        
        self.index_path = self.index_dir / "bm25_index.pkl"
        self.metadata_path = self.index_dir / "bm25_metadata.pkl"
        
        self.bm25 = None
        self.metadata: List[Dict[str, Any]] = []
        self.corpus = []
        
        self._load_or_create_index()
    
    def _load_or_create_index(self):
        """Charge l'index existant ou crée un nouveau"""
        try:
            from rank_bm25 import BM25Okapi
            
            if self.index_path.exists():
                logger.info(f"Chargement index BM25 de: {self.index_path}")
                
                with open(self.index_path, 'rb') as f:
                    self.bm25 = pickle.load(f)
                
                with open(self.metadata_path, 'rb') as f:
                    self.metadata = pickle.load(f)
                
                logger.info(f"✓ Index BM25 chargé: {len(self.metadata)} documents")
            else:
                logger.info("Création nouvel index BM25")
                self.bm25 = None  # Sera créé lors du premier add
                self.metadata = []
        
        except ImportError:
            logger.error("rank-bm25 not installed. Install with: pip install rank-bm25")
            raise
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize simple: minuscule + split + stopwords français"""
        
        # Minuscule
        text = text.lower()
        
        # Split par mots
        tokens = re.findall(r'\b\w+\b', text)
        
        # Stopwords français simples
        stopwords = {
            'le', 'la', 'les', 'de', 'des', 'du', 'un', 'une', 'et', 'ou',
            'est', 'sont', 'a', 'an', 'à', 'au', 'aux', 'par', 'pour', 'avec',
            'en', 'que', 'qu', 'qui', 'ce', 'cet', 'cette', 'ces', 'mon', 'son',
            'ma', 'sa', 'mes', 'ses', 'notre', 'votre', 'nos', 'vos', 'si',
            'ne', 'pas', 'plus', 'moins', 'très', 'ça', 'c', 'l', 'd', 's',
        }
        
        # Filtre stopwords et mots courts
        tokens = [t for t in tokens if t not in stopwords and len(t) > 2]
        
        return tokens
    
    def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> int:
        """
        Ajoute des documents à l'index BM25
        
        Args:
            documents: Liste de textes
            metadatas: Liste de dictionnaires avec métadonnées
            
        Returns:
            Nombre de documents ajoutés
        """
        from rank_bm25 import BM25Okapi
        
        if len(documents) == 0:
            logger.warning("Pas de documents à ajouter")
            return 0
        
        if len(documents) != len(metadatas):
            raise ValueError(f"Mismatch: {len(documents)} docs vs {len(metadatas)} metadatas")
        
        # Tokenize tous les documents
        tokenized_docs = [self._tokenize(doc) for doc in documents]
        
        # Ajoute aux corpus existants
        self.corpus.extend(tokenized_docs)
        self.metadata.extend(metadatas)
        
        # Rebuild BM25 avec tous les documents
        self.bm25 = BM25Okapi(self.corpus)
        
        logger.info(f"✓ Ajouté {len(documents)} documents BM25 (total: {len(self.metadata)})")
        
        return len(documents)
    
    def search(
        self,
        query: str,
        top_k: int = 8,
        score_threshold: float = 0.1,
    ) -> List[Dict[str, Any]]:
        """
        Recherche par mots-clés
        
        Args:
            query: Texte de recherche
            top_k: Nombre de résultats
            score_threshold: Score minimum
            
        Returns:
            Liste de résultats {metadata, score, rank}
        """
        if self.bm25 is None or len(self.metadata) == 0:
            logger.warning("Index BM25 est vide!")
            return []
        
        # Tokenize la query
        query_tokens = self._tokenize(query)
        
        if not query_tokens:
            logger.warning(f"Query après tokenization est vide: {query}")
            return []
        
        # Search avec BM25
        scores = self.bm25.get_scores(query_tokens)
        
        # Top-K
        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True
        )[:top_k]
        
        # Formate les résultats
        results = []
        for rank, idx in enumerate(top_indices):
            score = scores[idx]
            
            if score >= score_threshold:
                result = {
                    **self.metadata[idx],
                    "score": float(score),
                    "index": int(idx),
                    "rank": rank + 1,
                }
                results.append(result)
        
        logger.debug(f"BM25 search: {len(results)}/{top_k} résultats (threshold: {score_threshold})")
        
        return results
    
    def search_batch(
        self,
        queries: List[str],
        top_k: int = 8,
        score_threshold: float = 0.1,
    ) -> List[List[Dict[str, Any]]]:
        """
        Recherche batch
        
        Args:
            queries: Liste de requêtes
            top_k: Nombre de résultats par query
            score_threshold: Score minimum
            
        Returns:
            Liste de listes de résultats
        """
        batch_results = []
        for query in queries:
            results = self.search(query, top_k, score_threshold)
            batch_results.append(results)
        
        return batch_results
    
    def save(self):
        """Sauvegarde l'index"""
        if self.bm25 is None:
            logger.warning("Pas d'index à sauvegarder")
            return
        
        try:
            with open(self.index_path, 'wb') as f:
                pickle.dump(self.bm25, f)
            
            with open(self.metadata_path, 'wb') as f:
                pickle.dump(self.metadata, f)
            
            logger.info(f"✓ Index BM25 sauvegardé en: {self.index_path}")
        except Exception as e:
            logger.error(f"✗ Erreur sauvegarde: {e}")
            raise
    
    def clear(self):
        """Vide l'index"""
        self.bm25 = None
        self.metadata = []
        self.corpus = []
        
        logger.info("✓ Index BM25 vidé")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques"""
        index_size_mb = 0
        if self.index_path.exists():
            index_size_mb = self.index_path.stat().st_size / (1024 * 1024)
        
        return {
            "total_documents": len(self.metadata),
            "corpus_size": len(self.corpus),
            "index_size_mb": index_size_mb,
        }
    
    def rebuild_from_scratch(self):
        """Reconstruit l'index (supprime ancien)"""
        logger.warning("Reconstruction de l'index BM25 (suppression ancien)")
        
        # Supprime fichiers
        for path in [self.index_path, self.metadata_path]:
            if path.exists():
                path.unlink()
        
        # Clear
        self.clear()
        
        logger.info("✓ Index BM25 rebuilt")


# Test simple
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    manager = BM25Manager(Path("/tmp/bm25_test"))
    
    # Crée documents test
    documents = [
        "Procédure d'approbation des congés pour tous les employés",
        "Comment créer un profil utilisateur dans le système",
        "Les types d'heures supplémentaires autorisées",
        "Gestion des habilitations et permissions utilisateur",
    ]
    metadatas = [
        {"chunk_id": f"doc_{i}", "source": f"doc_{i}.pdf"}
        for i in range(len(documents))
    ]
    
    manager.add_documents(documents, metadatas)
    manager.save()
    
    # Search
    results = manager.search("congés approbation", top_k=3)
    print(f"✓ Results: {len(results)} found")
    for r in results:
        print(f"  - Score: {r['score']:.2f} | {r['chunk_id']}")
    
    print("📊 Stats:", manager.get_stats())
