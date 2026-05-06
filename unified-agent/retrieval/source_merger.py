#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Source Merger - Fusionne et Déduplique les Sources de Retrieval
Combine documents + transcriptions intelligemment
"""

import logging
from typing import List, Dict, Optional, Any, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MergedSource:
    """Représente une source fusionnée"""
    merged_id: str
    content: str
    primary_sources: List[Dict[str, Any]]
    secondary_sources: List[Dict[str, Any]]
    combined_score: float
    dedup_note: Optional[str] = None
    
    @property
    def all_sources(self) -> List[Dict[str, Any]]:
        return self.primary_sources + self.secondary_sources
    
    @property
    def source_files(self) -> Set[str]:
        """Retourne les fichiers sources uniques"""
        files = set()
        for source in self.all_sources:
            if "source" in source:
                files.add(source["source"])
        return files
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return {
            "merged_id": self.merged_id,
            "content": self.content,
            "combined_score": self.combined_score,
            "source_count": len(self.all_sources),
            "source_files": list(self.source_files),
            "dedup_note": self.dedup_note,
            "primary_sources": self.primary_sources,
            "secondary_sources": self.secondary_sources,
        }


class SourceMerger:
    """Fusionne et déduplique les sources de retrieval"""
    
    def __init__(
        self,
        dedup_threshold: float = 0.85,
    ):
        """
        Initialize Source Merger
        
        Args:
            dedup_threshold: Threshold for deduplication (0-1)
        """
        self.dedup_threshold = dedup_threshold
    
    def merge(
        self,
        retrieval_results: List[Dict[str, Any]],
        deduplication_engine=None,
    ) -> List[MergedSource]:
        """
        Fusionne et déduplique les résultats de retrieval
        
        Args:
            retrieval_results: Résultats du hybrid retriever
            deduplication_engine: Engine dedup optionnel
            
        Returns:
            Liste de MergedSource
        """
        
        if not retrieval_results:
            logger.warning("Pas de résultats à merger")
            return []
        
        # Grouper par fingerprint/contenu similaire
        groups = self._group_by_similarity(retrieval_results, deduplication_engine)
        
        # Convertir en MergedSource
        merged_sources = []
        for group_id, group_results in groups.items():
            merged = self._create_merged_source(group_id, group_results)
            merged_sources.append(merged)
        
        logger.info(
            f"Merged: {len(retrieval_results)} → {len(merged_sources)} "
            f"(duplicates: {len(retrieval_results) - len(merged_sources)})"
        )
        
        return merged_sources
    
    def _group_by_similarity(
        self,
        results: List[Dict[str, Any]],
        dedup_engine=None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Groupe les résultats par similarité
        
        Utilise fingerprints si disponibles, sinon chunk_id
        """
        groups = {}
        
        for result in results:
            # Clé de groupement (priorité: fingerprint > chunk_id > index)
            if "fingerprint" in result:
                key = result["fingerprint"]
            elif "chunk_id" in result:
                key = result["chunk_id"]
            else:
                key = str(result.get("index", id(result)))
            
            if key not in groups:
                groups[key] = []
            
            groups[key].append(result)
        
        return groups
    
    def _create_merged_source(
        self,
        group_id: str,
        group_results: List[Dict[str, Any]],
    ) -> MergedSource:
        """
        Crée une MergedSource à partir d'un groupe
        
        Stratégie:
        1. Prendre le résultat avec le meilleur score comme primary
        2. Autres = secondary
        3. Calculer score combiné
        """
        
        # Trie par score
        sorted_results = sorted(
            group_results,
            key=lambda x: x.get("combined_score", x.get("score", 0)),
            reverse=True
        )
        
        # Primary = meilleur score
        primary = sorted_results[0]
        secondary = sorted_results[1:]
        
        # Score combiné: moyenne des scores
        combined_score = sum(
            r.get("combined_score", r.get("score", 0)) for r in sorted_results
        ) / len(sorted_results)
        
        # Dedup note
        dedup_note = None
        if len(secondary) > 0:
            sources = ", ".join({
                f"{s.get('source', 'unknown')}"
                for s in secondary
            })
            dedup_note = f"Deduplicated {len(secondary)} secondary sources: {sources}"
        
        # Crée MergedSource
        merged = MergedSource(
            merged_id=group_id,
            content=primary.get("text", primary.get("content", "")),
            primary_sources=[primary],
            secondary_sources=secondary,
            combined_score=float(combined_score),
            dedup_note=dedup_note,
        )
        
        return merged
    
    def rank_and_reorder(
        self,
        merged_sources: List[MergedSource],
        top_k: int = 5,
    ) -> List[MergedSource]:
        """
        Rerank et retourne top-K sources
        
        Critères:
        1. Score combiné (principal)
        2. Nombre de sources (signal de consensus)
        3. Diversité (évite trop de mêmes sources)
        """
        
        # Ajoute score "consensus" (nombre de sources)
        for source in merged_sources:
            consensus_boost = min(len(source.all_sources) / 3.0, 0.1)
            source.combined_score += consensus_boost
        
        # Trie
        sorted_sources = sorted(
            merged_sources,
            key=lambda x: x.combined_score,
            reverse=True
        )
        
        return sorted_sources[:top_k]
    
    def build_context(
        self,
        merged_sources: List[MergedSource],
        max_tokens: int = 3000,
    ) -> Dict[str, Any]:
        """
        Construit un contexte formaté pour le LLM
        
        Args:
            merged_sources: Sources fusionnées
            max_tokens: Limite en tokens (approximatif: 4 chars = 1 token)
            
        Returns:
            Dict avec contexte formaté + métadonnées
        """
        
        context_parts = []
        total_length = 0
        used_sources = []
        
        for source in merged_sources:
            # Ajoute le contenu
            content = source.content.strip()
            if not content:
                continue
            
            # Vérifie limite tokens
            content_length = len(content)
            if total_length + content_length > max_tokens * 4:
                logger.warning(f"Limite tokens atteinte après {len(used_sources)} sources")
                break
            
            # Format avec source
            sources_text = ", ".join(source.source_files)
            formatted = f"[Source: {sources_text}]\n{content}\n"
            
            context_parts.append(formatted)
            total_length += content_length
            used_sources.append(source.to_dict())
        
        context_text = "\n".join(context_parts)
        
        return {
            "context": context_text,
            "total_chars": total_length,
            "sources_count": len(used_sources),
            "sources": used_sources,
        }
    
    def get_provenance_text(
        self,
        merged_sources: List[MergedSource],
    ) -> str:
        """Retourne un texte de provenance formaté"""
        
        provenance_lines = []
        
        for i, source in enumerate(merged_sources, 1):
            sources_list = "\n  ".join(
                f"- {f}" for f in source.source_files
            )
            
            line = f"{i}. Score: {source.combined_score:.2f}, Sources:\n  {sources_list}"
            provenance_lines.append(line)
        
        return "\n".join(provenance_lines)


# Test simple
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    merger = SourceMerger()
    
    # Test data
    retrieval_results = [
        {
            "chunk_id": "doc1",
            "text": "Procédure d'approbation des congés",
            "source": "policy.pdf",
            "combined_score": 0.95,
        },
        {
            "chunk_id": "doc1",  # Duplicate!
            "text": "Procédure d'approbation des congés",
            "source": "meeting.mp3",
            "combined_score": 0.92,
        },
        {
            "chunk_id": "doc2",
            "text": "Comment demander un congé",
            "source": "faq.txt",
            "combined_score": 0.85,
        },
    ]
    
    # Merge
    merged = merger.merge(retrieval_results)
    print(f"✓ Merged: {len(merged)} sources")
    
    for source in merged:
        print(f"  - {source.merged_id}: {len(source.all_sources)} sources")
    
    # Context
    context = merger.build_context(merged, max_tokens=500)
    print(f"✓ Context: {context['total_chars']} chars, {context['sources_count']} sources")
    
    # Provenance
    print("\n📝 Provenance:")
    print(merger.get_provenance_text(merged))
