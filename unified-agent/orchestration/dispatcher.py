#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dispatcher - Classe principale pour orchestrer l'agent
"""

import logging
from typing import Dict, Any, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)


class DispatcherMode(Enum):
    """Modes d'opération du dispatcher"""
    SINGLE = "single"  # Une seule question
    BATCH = "batch"  # Batch de questions
    STREAM = "stream"  # Streaming (futur)
    INTERACTIVE = "interactive"  # Mode interactif CLI


class Dispatcher:
    """
    Point d'entrée principal pour l'agent unifié
    Gère le routage des requêtes vers l'agent
    """
    
    def __init__(self, config=None):
        """
        Initialize Dispatcher
        
        Args:
            config: Configuration (UnifiedAgentConfig ou None for defaults)
        """
        from orchestration.agent import UnifiedAgent
        
        self.config = config
        self.agent = UnifiedAgent(config)
        
        logger.info("✅ Dispatcher initialized")
    
    def dispatch(self, query: str, mode: DispatcherMode = DispatcherMode.SINGLE) -> Dict[str, Any]:
        """
        Traite une requête
        
        Args:
            query: La question/commande de l'utilisateur
            mode: Mode d'opération
            
        Returns:
            Résultat du traitement
        """
        
        logger.info(f"Dispatching query (mode={mode.value}): {query[:50]}...")
        
        # Validate input
        if not query or not isinstance(query, str):
            logger.error("Invalid query")
            return {"error": "Invalid query", "success": False}
        
        query = query.strip()
        if len(query) == 0:
            return {"error": "Empty query", "success": False}
        
        try:
            if mode == DispatcherMode.SINGLE:
                result = self.agent.answer(query)
                result["success"] = True
                return result
            
            elif mode == DispatcherMode.BATCH:
                # Treat as batch separator by semicolon or newline
                queries = [q.strip() for q in query.split('\n') if q.strip()]
                if len(queries) == 1:
                    queries = [q.strip() for q in query.split(';') if q.strip()]
                
                results = self.agent.batch_answer(queries)
                
                return {
                    "success": True,
                    "batch_size": len(results),
                    "results": results,
                }
            
            else:
                return {"error": f"Unknown mode: {mode}", "success": False}
        
        except Exception as e:
            logger.error(f"Dispatch error: {e}", exc_info=True)
            return {
                "error": str(e),
                "success": False,
                "query": query,
            }
    
    def interactive_session(self):
        """Démarre une session interactive"""
        
        print("\n" + "="*60)
        print("  UNIFIED AGENT - Interactive Session")
        print("="*60)
        print("\n📝 Commandes:")
        print("  - Tapez votre question directement")
        print("  - 'status' pour voir l'état du système")
        print("  - 'help' pour l'aide")
        print("  - 'quit' pour quitter")
        print("-"*60 + "\n")
        
        while True:
            try:
                query = input("❓ Question: ").strip()
                
                if not query:
                    continue
                
                if query.lower() == "quit":
                    print("✓ Goodbye!")
                    break
                
                if query.lower() == "status":
                    status = self.agent.get_system_status()
                    print("\n📊 System Status:")
                    print(f"  LLM: {status['llm']}")
                    print(f"  Indices: {status['indices']}")
                    print(f"  Embeddings Cache: {status['embeddings']}")
                    print()
                    continue
                
                if query.lower() == "help":
                    print("\n📚 Available commands:")
                    print("  status - Show system status")
                    print("  help - Show this help")
                    print("  quit - Exit")
                    print("\nJust type any question for the agent to answer\n")
                    continue
                
                # Process question
                print("\n⏳ Processing...\n")
                result = self.dispatch(query, DispatcherMode.SINGLE)
                
                print("\n" + "-"*60)
                print(f"✓ Answer ({result.get('llm_source', 'unknown')}):")
                print("-"*60)
                print(result['answer'])
                print("-"*60)
                
                if result.get('sources'):
                    print(f"\n📚 Sources ({len(result['sources'])} found):")
                    for i, source in enumerate(result['sources'][:3], 1):
                        doc_type = source.get('type', 'unknown')
                        snippet = source.get('content', '')[:80]
                        print(f"  {i}. [{doc_type}] {snippet}...")
                
                print()
                
            except KeyboardInterrupt:
                print("\n✓ Interrupted. Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}\n")
    
    def format_result_for_display(self, result: Dict[str, Any], verbose: bool = False) -> str:
        """
        Formate le résultat pour l'affichage
        
        Args:
            result: Résultat du dispatch
            verbose: Mode verbose
            
        Returns:
            Texte formaté
        """
        
        lines = []
        
        # Question
        lines.append(f"\n❓ Question: {result.get('question', 'N/A')}")
        
        # Intent
        if 'intent' in result:
            intent = result['intent']
            confidence = result.get('intent_confidence', 0)
            lines.append(f"🎯 Intent: {intent} ({confidence:.0%} confiance)")
        
        # Answer
        lines.append(f"\n✓ Answer ({result.get('llm_source', 'unknown')}):")
        lines.append("-"*60)
        lines.append(result.get('answer', 'N/A'))
        lines.append("-"*60)
        
        # Sources
        if result.get('sources'):
            lines.append(f"\n📚 Sources ({len(result['sources'])} found):")
            for i, source in enumerate(result['sources'][:5], 1):
                doc_type = source.get('type', 'unknown')
                snippet = source.get('content', '')[:100]
                lines.append(f"  {i}. [{doc_type}] {snippet}...")
        
        # Verbose info
        if verbose:
            lines.append(f"\n📊 Stats:")
            lines.append(f"  - Retrieval count: {result.get('retrieval_count', 'N/A')}")
            lines.append(f"  - Merged sources: {result.get('merged_count', 'N/A')}")
            lines.append(f"  - Context size: {result.get('context_chars', 'N/A')} chars")
        
        return "\n".join(lines)


# Test
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s - %(levelname)s - %(message)s"
    )
    
    dispatcher = Dispatcher()
    
    # If arguments provided, use them as question
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        result = dispatcher.dispatch(question)
        print(dispatcher.format_result_for_display(result, verbose=True))
    else:
        # Interactive mode
        dispatcher.interactive_session()
