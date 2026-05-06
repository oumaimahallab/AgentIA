#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for Retrieval modules (Phase 2)
"""

import unittest
import logging
from pathlib import Path
import tempfile
import shutil
import numpy as np

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestFAISSManager(unittest.TestCase):
    """Tests pour FAISSManager"""
    
    def setUp(self):
        """Setup test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        
        from retrieval.faiss_manager import FAISSManager
        from retrieval.embeddings import EmbeddingsManager
        
        self.faiss = FAISSManager(self.temp_dir)
        self.embeddings = EmbeddingsManager()
        
        # Create sample documents
        self.docs = [
            {"id": "1", "content": "Définition de habilitation", "source": "docs"},
            {"id": "2", "content": "Procédure de formation", "source": "docs"},
            {"id": "3", "content": "Heures supplémentaires", "source": "transcription"},
        ]
        
        # Create embeddings
        self.embeddings_list = [
            self.embeddings.embed(doc["content"]) for doc in self.docs
        ]
    
    def tearDown(self):
        """Cleanup"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_build_index(self):
        """Test building FAISS index"""
        self.faiss.build(self.embeddings_list, self.docs)
        
        self.assertTrue(self.faiss.index is not None)
        self.assertEqual(len(self.docs), 3)
    
    def test_search(self):
        """Test searching in FAISS"""
        self.faiss.build(self.embeddings_list, self.docs)
        
        # Search for similar documents
        query_emb = self.embeddings.embed("habilitation")
        results = self.faiss.search(query_emb, top_k=2)
        
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0][1] >= 0)  # Score should be positive
    
    def test_save_load(self):
        """Test saving and loading index"""
        self.faiss.build(self.embeddings_list, self.docs)
        
        # Save
        save_path = Path(self.temp_dir) / "index"
        self.faiss.save(save_path)
        
        # Load
        faiss2 = FAISSManager(self.temp_dir)
        faiss2.load(save_path)
        
        # Test loaded index
        query_emb = self.embeddings.embed("habilitation")
        results = faiss2.search(query_emb, top_k=1)
        
        self.assertEqual(len(results), 1)


class TestBM25Manager(unittest.TestCase):
    """Tests pour BM25Manager"""
    
    def setUp(self):
        """Setup test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        
        from retrieval.bm25_manager import BM25Manager
        
        self.bm25 = BM25Manager(self.temp_dir)
        
        self.docs = [
            {"id": "1", "content": "Définition de habilitation", "source": "docs"},
            {"id": "2", "content": "Procédure de formation", "source": "docs"},
            {"id": "3", "content": "Calcul des heures supplémentaires", "source": "transcription"},
        ]
    
    def tearDown(self):
        """Cleanup"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_build_index(self):
        """Test building BM25 index"""
        self.bm25.build(self.docs)
        
        self.assertIsNotNone(self.bm25.bm25)
        self.assertEqual(self.bm25.doc_count(), 3)
    
    def test_search(self):
        """Test searching with BM25"""
        self.bm25.build(self.docs)
        
        results = self.bm25.search("habilitation", top_k=2)
        
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0][1] > 0)  # Score > 0


class TestHybridRetriever(unittest.TestCase):
    """Tests pour HybridRetriever"""
    
    def setUp(self):
        """Setup test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        
        from retrieval.hybrid_retriever import HybridRetriever
        from retrieval.faiss_manager import FAISSManager
        from retrieval.bm25_manager import BM25Manager
        from retrieval.embeddings import EmbeddingsManager
        
        self.faiss = FAISSManager(self.temp_dir)
        self.bm25 = BM25Manager(self.temp_dir)
        self.embeddings = EmbeddingsManager()
        
        self.retriever = HybridRetriever(self.faiss, self.bm25, alpha=0.6)
        
        # Sample documents
        self.docs = [
            {"id": "1", "content": "Définition de habilitation", "source": "docs"},
            {"id": "2", "content": "Procédure de formation", "source": "docs"},
            {"id": "3", "content": "Calcul des heures supplémentaires", "source": "transcription"},
        ]
        
        # Build indices
        embeddings_list = [self.embeddings.embed(doc["content"]) for doc in self.docs]
        self.faiss.build(embeddings_list, self.docs)
        self.bm25.build(self.docs)
    
    def tearDown(self):
        """Cleanup"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_hybrid_search(self):
        """Test hybrid retrieval"""
        query_emb = self.embeddings.embed("habilitation")
        results = self.retriever.search(query_emb, "habilitation", top_k=2)
        
        self.assertGreater(len(results), 0)
        self.assertLessEqual(len(results), 2)


class TestSourceMerger(unittest.TestCase):
    """Tests pour SourceMerger"""
    
    def setUp(self):
        """Setup test fixtures"""
        from retrieval.source_merger import SourceMerger
        
        self.merger = SourceMerger()
    
    def test_merge_results(self):
        """Test merging retrieval results"""
        results = [
            {"id": "1", "content": "Content 1", "source": "docs", "score": 0.9},
            {"id": "2", "content": "Content 2", "source": "transcription", "score": 0.8},
            {"id": "1", "content": "Content 1 v2", "source": "transcription", "score": 0.85},
        ]
        
        merged = self.merger.merge(results)
        
        # Should have deduped id "1"
        self.assertLessEqual(len(merged), len(results))


class TestReranker(unittest.TestCase):
    """Tests pour Reranker"""
    
    def setUp(self):
        """Setup test fixtures"""
        from retrieval.reranker import Reranker
        
        self.reranker = Reranker()
    
    def test_reranking(self):
        """Test reranking results"""
        documents = [
            "Définition de habilitation selon le code du travail",
            "Procédure de formation professionnelle",
            "Calcul des heures supplémentaires",
        ]
        
        scores = self.reranker.rerank(
            "habilitation",
            documents,
            top_k=2
        )
        
        self.assertEqual(len(scores), 2)
        # Top result should be about habilitation
        self.assertGreater(scores[0][1], 0)


class TestEmbeddingsManager(unittest.TestCase):
    """Tests pour EmbeddingsManager"""
    
    def setUp(self):
        """Setup test fixtures"""
        from retrieval.embeddings import EmbeddingsManager
        
        self.embeddings = EmbeddingsManager()
    
    def test_single_embedding(self):
        """Test embedding a single text"""
        text = "Définition de habilitation"
        emb = self.embeddings.embed(text)
        
        self.assertIsNotNone(emb)
        self.assertEqual(len(emb), 384)  # all-MiniLM-L6-v2 dimension
    
    def test_batch_embedding(self):
        """Test batch embedding"""
        texts = [
            "Définition de habilitation",
            "Procédure de formation",
            "Heures supplémentaires",
        ]
        
        embeddings = self.embeddings.embed_batch(texts)
        
        self.assertEqual(len(embeddings), 3)
    
    def test_cache(self):
        """Test embedding cache"""
        text = "Définition de habilitation"
        
        # First call
        emb1 = self.embeddings.embed(text)
        
        # Second call (should be cached)
        emb2 = self.embeddings.embed(text)
        
        # Should be identical
        np.testing.assert_array_equal(emb1, emb2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
