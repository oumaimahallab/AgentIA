#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Moteur de Déduplication - Élimine conflits et doublons
Combine sources (documents + transcriptions) intelligemment
"""

import hashlib
import logging
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import re

logger = logging.getLogger(__name__)


class SourceType(Enum):
    """Type de source"""
    DOCUMENT = "document"
    TRANSCRIPTION = "transcription"
    MIXED = "mixed"


@dataclass
class ChunkMetadata:
    """Métadonnées d'un chunk"""
    chunk_id: str
    source_type: SourceType
    source_file: str
    source_page: Optional[int] = None
    confidence: float = 1.0
    fingerprint: Optional[str] = None
    content: str = ""
    embedding: Optional[List[float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return {
            "chunk_id": self.chunk_id,
            "source_type": self.source_type.value,
            "source_file": self.source_file,
            "source_page": self.source_page,
            "confidence": self.confidence,
            "fingerprint": self.fingerprint,
        }


@dataclass
class MergedChunk:
    """Chunk après fusion/déduplication"""
    merged_id: str
    content: str
    primary_sources: List[ChunkMetadata] = field(default_factory=list)
    secondary_sources: List[ChunkMetadata] = field(default_factory=list)
    is_deduplicated: bool = False
    conflict_info: Optional[Dict[str, Any]] = None
    combined_confidence: float = 1.0
    
    @property
    def all_sources(self) -> List[ChunkMetadata]:
        return self.primary_sources + self.secondary_sources
    
    @property
    def source_count(self) -> int:
        return len(self.all_sources)
    
    @property
    def source_types(self) -> set:
        return {s.source_type for s in self.all_sources}
    
    def get_provenance_text(self) -> str:
        """Retourne un texte de provenance"""
        if not self.all_sources:
            return "Source inconnue"
        
        sources = []
        for source in self.all_sources:
            if source.source_page:
                sources.append(f"{source.source_file} (p.{source.source_page})")
            else:
                sources.append(source.source_file)
        
        return " + ".join(set(sources))


class TextNormalizer:
    """Normalise le texte pour comparaison"""
    
    @staticmethod
    def normalize(text: str) -> str:
        """Normalise un texte"""
        # Minuscule
        text = text.lower()
        
        # Supprime espaces multiples
        text = re.sub(r'\s+', ' ', text)
        
        # Supprime ponctuation sauf essentielles
        text = re.sub(r'[^\w\s\.\-]', '', text)
        
        # Strip
        text = text.strip()
        
        return text
    
    @staticmethod
    def create_fingerprint(text: str) -> str:
        """Crée un fingerprint (hash) du texte normalisé"""
        normalized = TextNormalizer.normalize(text)
        return hashlib.sha256(normalized.encode()).hexdigest()


class DeduplicationEngine:
    """Moteur de déduplication"""
    
    def __init__(
        self,
        similarity_threshold: float = 0.85,
        normalize_text: bool = True,
        use_semantic_fingerprint: bool = True,
        prefer_source: str = "document",
        keep_both_on_conflict: bool = True,
    ):
        self.similarity_threshold = similarity_threshold
        self.normalize_text = normalize_text
        self.use_semantic_fingerprint = use_semantic_fingerprint
        self.prefer_source = prefer_source
        self.keep_both_on_conflict = keep_both_on_conflict
        
        self.chunks: Dict[str, ChunkMetadata] = {}
        self.fingerprints: Dict[str, List[str]] = {}  # fingerprint -> chunk_ids
        self.merged_chunks: Dict[str, MergedChunk] = {}
    
    def add_chunk(
        self,
        chunk_id: str,
        content: str,
        source_type: SourceType,
        source_file: str,
        source_page: Optional[int] = None,
        confidence: float = 1.0,
    ) -> str:
        """Ajoute un chunk et retourne son ID (original ou mergé)"""
        
        # Crée les métadonnées
        metadata = ChunkMetadata(
            chunk_id=chunk_id,
            source_type=source_type,
            source_file=source_file,
            source_page=source_page,
            confidence=confidence,
            content=content,
        )
        
        # Calcule le fingerprint si nécessaire
        if self.use_semantic_fingerprint:
            metadata.fingerprint = TextNormalizer.create_fingerprint(content)
        
        # Cherche duplicata
        duplicate_ids = self._find_duplicates(metadata)
        
        if not duplicate_ids:
            # Pas de duplicate - ajoute normalement
            self.chunks[chunk_id] = metadata
            if metadata.fingerprint:
                if metadata.fingerprint not in self.fingerprints:
                    self.fingerprints[metadata.fingerprint] = []
                self.fingerprints[metadata.fingerprint].append(chunk_id)
            logger.debug(f"✓ Chunk ajouté: {chunk_id} ({source_type.value})")
            return chunk_id
        
        else:
            # Duplicata trouvé - merge
            return self._merge_duplicates(metadata, duplicate_ids)
    
    def _find_duplicates(self, metadata: ChunkMetadata) -> List[str]:
        """Trouve les duplicata potentiels"""
        duplicates = []
        
        # Search par fingerprint
        if metadata.fingerprint and metadata.fingerprint in self.fingerprints:
            duplicates.extend(self.fingerprints[metadata.fingerprint])
        
        # Search par similarité textuelle si pas de fingerprint match
        if not duplicates:
            for chunk_id, existing in self.chunks.items():
                if self._similarity(metadata.content, existing.content) >= self.similarity_threshold:
                    duplicates.append(chunk_id)
        
        return duplicates
    
    def _similarity(self, text1: str, text2: str) -> float:
        """Calcule similarité entre deux textes"""
        # Simple Jaccard similarity
        if self.normalize_text:
            text1 = TextNormalizer.normalize(text1)
            text2 = TextNormalizer.normalize(text2)
        
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    def _merge_duplicates(
        self,
        new_metadata: ChunkMetadata,
        duplicate_ids: List[str],
    ) -> str:
        """Merge un nouveau chunk avec ses duplicata"""
        
        # Récupère les métadonnées des duplicata
        duplicates = [self.chunks.get(did) for did in duplicate_ids if did in self.chunks]
        
        if not duplicates:
            # Pas trouvé dans chunks, c'est un merged chunk
            merged_id = duplicate_ids[0]
            merged = self.merged_chunks[merged_id]
        else:
            # Crée un merged chunk
            primary_dup = duplicates[0]
            merged_id = f"{primary_dup.chunk_id}_merged"
            
            merged = MergedChunk(
                merged_id=merged_id,
                content=primary_dup.content,
                primary_sources=[primary_dup],
                is_deduplicated=True,
            )
        
        # Décide où ajouter le nouveau chunk
        if self._should_prefer(new_metadata, merged.primary_sources[0] if merged.primary_sources else None):
            # Remplace le contenu principal
            old_content = merged.content
            merged.content = new_metadata.content
            merged.secondary_sources = [merged.primary_sources[0]] if merged.primary_sources else []
            merged.primary_sources = [new_metadata]
            
            merged.conflict_info = {
                "conflict_type": "content_differs",
                "old_content_from": merged.secondary_sources[0].source_file if merged.secondary_sources else None,
                "new_content_from": new_metadata.source_file,
                "old_length": len(old_content),
                "new_length": len(new_metadata.content),
            }
            logger.info(f"✓ Conflit résolu: Préféré {new_metadata.source_file}")
        else:
            # Ajoute comme source secondaire
            merged.secondary_sources.append(new_metadata)
        
        # Update combined confidence
        all_sources = merged.all_sources
        merged.combined_confidence = sum(s.confidence for s in all_sources) / len(all_sources)
        
        # Update global mappings
        self.merged_chunks[merged_id] = merged
        
        logger.info(
            f"✓ Merged {len(merged.all_sources)} sources → {merged_id} "
            f"(Provenance: {merged.get_provenance_text()})"
        )
        
        return merged_id
    
    def _should_prefer(
        self,
        new: ChunkMetadata,
        existing: Optional[ChunkMetadata],
    ) -> bool:
        """Décide si on préfère le nouveau chunk au existant"""
        
        if not existing:
            return True
        
        # Préfère selon source config
        if self.prefer_source == "document":
            return new.source_type == SourceType.DOCUMENT and existing.source_type == SourceType.TRANSCRIPTION
        elif self.prefer_source == "transcription":
            return new.source_type == SourceType.TRANSCRIPTION and existing.source_type == SourceType.DOCUMENT
        
        # Sinon préfère celle avec plus haute confidence
        return new.confidence > existing.confidence
    
    def get_all_chunks(self) -> Dict[str, MergedChunk]:
        """Retourne tous les chunks (y compris merged)"""
        result = {}
        
        # Non-merged chunks
        for chunk_id, metadata in self.chunks.items():
            merged = MergedChunk(
                merged_id=chunk_id,
                content=metadata.content,
                primary_sources=[metadata],
                is_deduplicated=False,
            )
            result[chunk_id] = merged
        
        # Merged chunks
        result.update(self.merged_chunks)
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de déduplication"""
        original_count = len(self.chunks)
        merged_count = len(self.merged_chunks)
        
        sources_by_type = {}
        for chunk in self.chunks.values():
            key = chunk.source_type.value
            sources_by_type[key] = sources_by_type.get(key, 0) + 1
        
        for merged in self.merged_chunks.values():
            for source in merged.all_sources:
                key = source.source_type.value
                sources_by_type[key] = sources_by_type.get(key, 0) + 1
        
        return {
            "original_chunks": original_count,
            "merged_chunks": merged_count,
            "total_unique_chunks": original_count + merged_count,
            "duplicates_eliminated": sum(
                len(m.all_sources) - 1 for m in self.merged_chunks.values()
            ),
            "sources_by_type": sources_by_type,
            "conflicts_resolved": sum(
                1 for m in self.merged_chunks.values() if m.conflict_info
            ),
        }
    
    def clear(self):
        """Vide le moteur"""
        self.chunks.clear()
        self.fingerprints.clear()
        self.merged_chunks.clear()


# Test simple
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    engine = DeduplicationEngine()
    
    # Test 1: Exact duplicate
    engine.add_chunk(
        "doc_1", "Procédure d'approbation des congés",
        SourceType.DOCUMENT, "policy.pdf"
    )
    engine.add_chunk(
        "trans_1", "Procédure d'approbation des congés",
        SourceType.TRANSCRIPTION, "meeting.mp3"
    )
    
    # Test 2: Nouvel chunk
    engine.add_chunk(
        "doc_2", "Demande de congé doit être faite 30 jours avant",
        SourceType.DOCUMENT, "policy.pdf", source_page=2
    )
    
    print("\n📊 STATS:", engine.get_stats())
