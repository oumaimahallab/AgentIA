"""
hybrid_retriever.py — Hybrid retrieval (FAISS + BM25) for ChronoBrain

Pipeline:
  1. FAISS semantic search  → top-K candidates
  2. BM25 keyword search    → top-K candidates
  3. Reciprocal Rank Fusion → normalise + weight scores
  4. Score threshold filter (MIN_SCORE)
  5. MMR deduplication
  6. Soft-floor fallback    → keep top-2 raw if all filtered
"""

import os
import re
import pickle
import logging
import numpy as np
from typing import Optional
from dataclasses import dataclass

import faiss
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

from config import (
    FAISS_DIR, BM25_PATH,
    TOP_K, MIN_SCORE, FALLBACK_TOP_K,
    SEMANTIC_WEIGHT, BM25_WEIGHT,
    MMR_THRESHOLD, EMBED_MODEL,
)

log = logging.getLogger("chronobrain.retriever")


@dataclass
class RetrievedChunk:
    chunk_id:       str
    source:         str
    start_time:     str
    end_time:       str
    start_sec:      float
    end_sec:        float
    text:           str
    word_count:     int
    has_asr_warning: bool
    score:          float
    used_fallback:  bool = False


class HybridRetriever:
    """
    Loads a pre-built FAISS index + BM25 index and performs hybrid retrieval.
    Call HybridRetriever.load() to instantiate from saved indices.
    """

    def __init__(
        self,
        faiss_index: faiss.Index,
        bm25_index:  BM25Okapi,
        chunks:      list[dict],
        embedder:    SentenceTransformer,
    ):
        self._faiss   = faiss_index
        self._bm25    = bm25_index
        self._chunks  = chunks          # list of raw chunk dicts
        self._embedder = embedder

    @classmethod
    def load(cls) -> "HybridRetriever":
        """Load all indices from disk."""
        index_path   = os.path.join(FAISS_DIR, "index.faiss")
        chunks_path  = os.path.join(FAISS_DIR, "chunks.pkl")

        if not os.path.exists(index_path):
            raise FileNotFoundError(
                f"FAISS index not found at {index_path}.\n"
                "Run: python ingest.py"
            )
        if not os.path.exists(BM25_PATH):
            raise FileNotFoundError(
                f"BM25 index not found at {BM25_PATH}.\n"
                "Run: python ingest.py"
            )

        faiss_index = faiss.read_index(index_path)
        with open(chunks_path,  "rb") as f:
            chunks = pickle.load(f)
        with open(BM25_PATH, "rb") as f:
            bm25_index = pickle.load(f)

        embedder = SentenceTransformer(EMBED_MODEL)
        log.warning("Loaded FAISS (%d vectors) + BM25 + %d chunks.", faiss_index.ntotal, len(chunks))
        return cls(faiss_index, bm25_index, chunks, embedder)

    # ── Public API ────────────────────────────────────────────────────────────

    def retrieve(
        self,
        query:    str,
        debug:    bool = False,
    ) -> tuple[list[RetrievedChunk], bool]:
        """
        Run hybrid retrieval for `query`.
        Returns (chunks, used_fallback).
        """
        if not self._chunks:
            return [], False

        k = min(TOP_K, len(self._chunks))

        # 1. FAISS — semantic search
        faiss_scores, faiss_indices = self._faiss_search(query, k)

        # 2. BM25 — keyword search
        bm25_scores, bm25_indices = self._bm25_search(query, k)

        # 3. Hybrid fusion with Reciprocal Rank Fusion normalisation
        fused = self._fuse(faiss_scores, faiss_indices, bm25_scores, bm25_indices)

        if debug:
            print("\n[DEBUG] Hybrid scores (pre-filter):")
            for idx, score in sorted(fused.items(), key=lambda x: -x[1])[:10]:
                c = self._chunks[idx]
                print(f"  [{idx}] {score:.3f} | {c['source']} [{c['start_time']}] | "
                      f"{c['text'][:70].replace(chr(10),' ')}…")

        # 4. Sort by fused score
        ranked = sorted(fused.items(), key=lambda x: -x[1])

        # 5. Metadata boost: prefer chunks with no ASR warning + higher word count
        ranked = self._metadata_boost(ranked)

        # 6. Score threshold filter
        filtered = [(idx, score) for idx, score in ranked if score >= MIN_SCORE]

        used_fallback = False
        if not filtered:
            # Soft floor: keep top-FALLBACK_TOP_K regardless of score
            filtered      = ranked[:FALLBACK_TOP_K]
            used_fallback = True
            log.warning(
                "All nodes below MIN_SCORE=%.2f — soft fallback top-%d (best=%.3f)",
                MIN_SCORE, FALLBACK_TOP_K,
                ranked[0][1] if ranked else 0,
            )

        # 7. MMR deduplication
        final_indices = self._mmr_deduplicate([idx for idx, _ in filtered])

        results = []
        for idx in final_indices:
            score = fused.get(idx, 0.0)
            c     = self._chunks[idx]
            results.append(RetrievedChunk(
                chunk_id        = c["chunk_id"],
                source          = c["source"],
                start_time      = c["start_time"],
                end_time        = c["end_time"],
                start_sec       = c.get("start_sec", 0),
                end_sec         = c.get("end_sec", 0),
                text            = c["text"],
                word_count      = c.get("word_count", 0),
                has_asr_warning = c.get("has_asr_warning", False),
                score           = round(score, 4),
                used_fallback   = used_fallback,
            ))

        return results, used_fallback

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _faiss_search(self, query: str, k: int) -> tuple[np.ndarray, np.ndarray]:
        """Embed query and search FAISS. Returns (scores, indices)."""
        q_vec = self._embedder.encode([query], normalize_embeddings=True).astype("float32")
        distances, indices = self._faiss.search(q_vec, k)
        # FAISS inner-product on normalised vectors → cosine similarity in [0,1]
        scores  = np.clip(distances[0], 0, 1)
        indices = indices[0]
        return scores, indices

    def _bm25_search(self, query: str, k: int) -> tuple[np.ndarray, np.ndarray]:
        """Tokenise query and score with BM25. Returns (normalised scores, indices)."""
        tokens = _tokenize(query)
        raw_scores = np.array(self._bm25.get_scores(tokens))

        # Normalise to [0, 1]
        max_s = raw_scores.max()
        if max_s > 0:
            raw_scores = raw_scores / max_s

        top_indices = np.argsort(raw_scores)[::-1][:k]
        return raw_scores[top_indices], top_indices

    def _fuse(
        self,
        faiss_scores:   np.ndarray,
        faiss_indices:  np.ndarray,
        bm25_scores:    np.ndarray,
        bm25_indices:   np.ndarray,
    ) -> dict[int, float]:
        """
        Hybrid score fusion:
          final = SEMANTIC_WEIGHT * semantic + BM25_WEIGHT * bm25
        Uses Reciprocal Rank Fusion to normalise rank contributions.
        """
        scores: dict[int, float] = {}

        # Add semantic scores
        for rank, (idx, score) in enumerate(zip(faiss_indices, faiss_scores)):
            if idx < 0 or idx >= len(self._chunks):
                continue
            rrf_sem = 1.0 / (60 + rank + 1)
            scores[idx] = scores.get(idx, 0.0) + SEMANTIC_WEIGHT * (score + rrf_sem)

        # Add BM25 scores
        for rank, (idx, score) in enumerate(zip(bm25_indices, bm25_scores)):
            if idx < 0 or idx >= len(self._chunks):
                continue
            rrf_bm25 = 1.0 / (60 + rank + 1)
            scores[idx] = scores.get(idx, 0.0) + BM25_WEIGHT * (score + rrf_bm25)

        # Normalise final scores to [0, 1]
        if scores:
            max_s = max(scores.values())
            if max_s > 0:
                scores = {k: v / max_s for k, v in scores.items()}

        return scores

    def _metadata_boost(
        self,
        ranked: list[tuple[int, float]],
    ) -> list[tuple[int, float]]:
        """
        Apply small metadata-based score adjustments:
          +0.05 if has_asr_warning = False
          +0.02 * (word_count / 100) capped at +0.04
        """
        boosted = []
        for idx, score in ranked:
            c     = self._chunks[idx]
            boost = 0.0
            if not c.get("has_asr_warning", True):
                boost += 0.05
            wc     = c.get("word_count", 0)
            boost += min(0.04, 0.02 * (wc / 100))
            boosted.append((idx, min(1.0, score + boost)))
        return sorted(boosted, key=lambda x: -x[1])

    def _mmr_deduplicate(self, indices: list[int]) -> list[int]:
        """
        Remove near-duplicate chunks (word-overlap > MMR_THRESHOLD).
        Keeps the highest-scored one when duplicates are found.
        """
        kept: list[int] = []
        for idx in indices:
            words_a = set(self._chunks[idx]["text"].lower().split())
            is_dup  = False
            for kept_idx in kept:
                words_b = set(self._chunks[kept_idx]["text"].lower().split())
                if not words_a or not words_b:
                    continue
                overlap = len(words_a & words_b) / max(1, min(len(words_a), len(words_b)))
                if overlap > MMR_THRESHOLD:
                    is_dup = True
                    break
            if not is_dup:
                kept.append(idx)
        return kept


# ── Shared tokeniser ──────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Simple French-friendly tokeniser for BM25."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return [t for t in text.split() if len(t) > 1]
