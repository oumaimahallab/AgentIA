#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dispatcher - Route les requêtes vers le bon pipeline
Orchestre l'ensemble du système
"""

import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class UnifiedAgent:
    """Agent Principal Unifié - Combine tous les modules"""
    
    def __init__(
        self,
        config=None,
    ):
        """
        Initialize Unified Agent
        
        Args:
            config: Configuration (UnifiedAgentConfig ou None for defaults)
        """
        if config is None:
            from config import get_config
            config = get_config()
        
        self.config = config
        
        # Initialize components
        self._init_embeddings()
        self._init_indices()
        self._init_retrievers()
        self._init_llm()
        
        logger.info("✅ Unified Agent initialized")
    
    def _init_embeddings(self):
        """Initialize embeddings manager"""
        from retrieval.embeddings import EmbeddingsManager
        
        self.embeddings = EmbeddingsManager(
            model_name=self.config.embeddings.MODEL_NAME,
            device=self.config.embeddings.DEVICE,
        )
        logger.info("✓ Embeddings initialized")
    
    def _init_indices(self):
        """Initialize vector indices"""
        from retrieval.faiss_manager import FAISSManager
        from retrieval.bm25_manager import BM25Manager
        
        self.faiss = FAISSManager(
            self.config.paths.FAISS_INDEX_DIR,
        )
        self.bm25 = BM25Manager(
            self.config.paths.BM25_INDEX_DIR,
        )
        logger.info("✓ Indices initialized")
    
    def _init_retrievers(self):
        """Initialize retrieval components"""
        from retrieval.hybrid_retriever import HybridRetriever
        from retrieval.source_merger import SourceMerger
        from retrieval.reranker import Reranker
        
        self.retriever = HybridRetriever(
            self.faiss,
            self.bm25,
            alpha=self.config.retrieval.ALPHA,
        )
        
        self.merger = SourceMerger(
            dedup_threshold=self.config.deduplication.SIMILARITY_THRESHOLD,
        )
        
        self.reranker = Reranker()
        
        logger.info("✓ Retrievers initialized")
    
    def _init_llm(self):
        """Initialize LLM orchestrator"""
        from llm.llm_orchestrator import LLMOrchestrator
        
        self.llm = LLMOrchestrator()
        
        logger.info("✓ LLM orchestrator initialized")
    
    def answer(self, question: str) -> Dict[str, Any]:
        """
        Répond à une question
        
        Args:
            question: La question de l'utilisateur
            
        Returns:
            Dict avec réponse + métadonnées
        """
        
        # 1. DETECT INTENT
        from core.intent_detector import IntentDetector, QueryIntent
        
        intent_detector = IntentDetector()
        intent_result = intent_detector.detect(question)
        
        logger.info(f"Intent: {intent_result.intent.value} ({intent_result.confidence:.0%})")
        
        # 2. EMBED QUERY
        query_embedding = self.embeddings.embed(question)
        
        # 3. HYBRID RETRIEVAL
        retrieval_results = self.retriever.search(
            query_embedding,
            question,
            top_k=self.config.retrieval.SEMANTIC_TOP_K,
        )
        
        logger.info(f"Retrieved: {len(retrieval_results)} results")
        
        # 4. MERGE & DEDUPLICATE
        merged_sources = self.merger.merge(retrieval_results)
        
        logger.info(f"Merged: {len(merged_sources)} unique sources")
        
        # 5. BUILD CONTEXT
        context_info = self.merger.build_context(
            merged_sources,
            max_tokens=self.config.retrieval.MAX_CONTEXT_TOKENS,
        )
        
        context = context_info["context"]
        
        # 6. SELECT SYSTEM PROMPT
        system_prompt = IntentDetector.get_system_prompt(intent_result.intent)
        
        # 7. BUILD FINAL PROMPT
        final_prompt = f"""CONTEXT:
{context}

---

QUESTION: {question}

RESPONSE:"""
        
        # 8. GENERATE RESPONSE
        llm_result = self.llm.generate(final_prompt, system_prompt)
        
        response_text = llm_result["text"]
        llm_source = llm_result["source"]
        
        # 9. FORMAT FINAL ANSWER
        answer = {
            "question": question,
            "answer": response_text,
            "intent": intent_result.intent.value,
            "intent_confidence": float(intent_result.confidence),
            "llm_source": llm_source,
            "sources": context_info["sources"],
            "retrieval_count": len(retrieval_results),
            "merged_count": len(merged_sources),
            "context_chars": context_info["total_chars"],
        }
        
        logger.info(f"✓ Generated response ({len(response_text)} chars)")
        
        return answer
    
    def batch_answer(self, questions: List[str]) -> List[Dict[str, Any]]:
        """
        Répond à un batch de questions
        
        Args:
            questions: Liste de questions
            
        Returns:
            Liste de réponses
        """
        
        answers = []
        for question in questions:
            try:
                answer = self.answer(question)
                answers.append(answer)
            except Exception as e:
                logger.error(f"Error answering question: {e}")
                answers.append({
                    "question": question,
                    "answer": f"Error: {str(e)}",
                    "error": True,
                })
        
        return answers
    
    def get_system_status(self) -> Dict[str, Any]:
        """Retourne le statut du système"""
        
        return {
            "embeddings": self.embeddings.get_cache_stats(),
            "indices": {
                "faiss": self.faiss.get_stats(),
                "bm25": self.bm25.get_stats(),
            },
            "llm": self.llm.get_status(),
            "retriever": self.retriever.get_stats(),
        }


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)
    
    print("\n" + "="*50)
    print("🤖 UNIFIED AGENT - MODE CONSOLE")
    print("="*50)
    
    try:
        agent = UnifiedAgent()
        print("\n✅ Système prêt ! (Tapez 'exit' pour quitter)")
        
        while True:
            question = input("\n❓ Votre question : ")
            if question.lower() in ['exit', 'quit', 'q']:
                break
            
            if not question.strip():
                continue
                
            print("\n🔄 L'agent réfléchit...")
            result = agent.answer(question)
            
            print(f"\n✨ RÉPONSE ({result['llm_source']}):")
            print("-" * 30)
            print(result['answer'])
            print("-" * 30)
            
            if result.get("sources"):
                print("\n📚 SOURCES :")
                for s in result["sources"][:3]:
                    fname = os.path.basename(s.get('source_files', ['Inconnu'])[0])
                    print(f"  - {fname}")
                    
    except Exception as e:
        print(f"❌ Erreur critique : {e}")
