#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demo - Interactive session with unified agent
Montre le système en action
"""

import logging
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s | %(message)s"
)

logger = logging.getLogger(__name__)


def print_header(title: str):
    """Print a nice header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def demo_main():
    """Run main demo"""
    
    print_header("🚀 UNIFIED AGENT - DEMO")
    
    print("""
Welcome! This demo shows the unified agent in action.

The agent combines:
  • ChronoBrain: HR transcriptions and voice processing
  • DataCl: Document RAG and universal retrieval
  
Into ONE intelligent system that handles:
  • Documents (PDF, PPT, etc.)
  • Transcriptions (audio, video)
  • Without duplication or conflicts
  
Ready? Let's go!
    """)
    
    # Initialize agent
    print("\n⏳ Initializing unified agent...")
    try:
        from orchestration.dispatcher import Dispatcher, DispatcherMode
        
        dispatcher = Dispatcher()
        print("✅ Agent initialized successfully!\n")
        
    except Exception as e:
        print(f"\n❌ Error initializing agent: {e}")
        print("\nTroubleshooting:")
        print("  1. Check that Python 3.8+ is installed")
        print("  2. Create virtual environment: python -m venv venv")
        print("  3. Activate it: venv\\Scripts\\activate (Windows)")
        print("  4. Install deps: pip install -r requirements.txt")
        print("  5. Set GROQ_API_KEY environment variable")
        return False
    
    # Show system status
    print_header("📊 System Status")
    try:
        status = dispatcher.agent.get_system_status()
        print(f"""
LLM Status: {status.get('llm', 'unknown')}
Indices:
  • FAISS: {status.get('indices', {}).get('faiss', {})}
  • BM25: {status.get('indices', {}).get('bm25', {})}
Embeddings Cache: {status.get('embeddings', {})}
        """)
    except Exception as e:
        logger.warning(f"Could not load system status: {e}")
    
    # Run sample questions
    print_header("🧪 Sample Questions")
    
    sample_questions = [
        "Qu'est-ce qu'une habilitation?",
        "Comment calculer les heures supplémentaires?",
        "Quelle est la procédure de formation?",
    ]
    
    for i, question in enumerate(sample_questions, 1):
        print(f"\n[{i}/{len(sample_questions)}] ❓ Question: {question}")
        print("-" * 70)
        
        try:
            result = dispatcher.dispatch(question, DispatcherMode.SINGLE)
            
            if result.get("success"):
                # Show answer
                answer = result.get("answer", "No answer")
                print(f"✓ Answer ({result.get('llm_source', 'unknown')}):")
                print(answer[:500])
                
                if len(answer) > 500:
                    print("... [truncated]")
                
                # Show sources
                sources = result.get("sources", [])
                if sources:
                    print(f"\n📚 Sources ({len(sources)} found):")
                    for j, source in enumerate(sources[:2], 1):
                        doc_type = source.get("type", "unknown")
                        content = source.get("content", "")[:60]
                        print(f"   {j}. [{doc_type}] {content}...")
                
                # Show stats
                print(f"\n📊 Stats:")
                print(f"   • Intent: {result.get('intent', 'unknown')} "
                      f"({result.get('intent_confidence', 0):.0%})")
                print(f"   • Retrieved: {result.get('retrieval_count', 0)} results")
                print(f"   • Context: {result.get('context_chars', 0)} chars")
                
            else:
                error = result.get("error", "Unknown error")
                print(f"❌ Error: {error}")
                
        except Exception as e:
            print(f"❌ Exception: {e}")
    
    # Interactive mode
    print_header("💬 Interactive Mode")
    print("\nEnter your own questions (type 'quit' to exit):\n")
    
    while True:
        try:
            question = input("❓ Question: ").strip()
            
            if not question:
                continue
            
            if question.lower() in ["quit", "exit", "q"]:
                print("\n✅ Thank you for trying the demo!\n")
                break
            
            if question.lower() == "status":
                try:
                    status = dispatcher.agent.get_system_status()
                    print(f"\n📊 Status: {status}\n")
                except Exception as e:
                    print(f"Error: {e}\n")
                continue
            
            # Process question
            print("\n⏳ Processing...\n")
            result = dispatcher.dispatch(question, DispatcherMode.SINGLE)
            
            if result.get("success"):
                print(f"✓ Answer ({result.get('llm_source', 'unknown')}):")
                print("-" * 70)
                print(result.get("answer", "No answer"))
                print("-" * 70)
                
                if result.get("sources"):
                    print(f"\n📚 Sources: {len(result['sources'])} found")
                
            else:
                print(f"❌ Error: {result.get('error', 'Unknown error')}")
            
            print()
            
        except KeyboardInterrupt:
            print("\n\n✅ Goodbye!\n")
            break
        except Exception as e:
            print(f"❌ Error: {e}\n")
    
    return True


def demo_batch():
    """Run batch demo - multiple questions at once"""
    
    print_header("📋 BATCH DEMO")
    
    from orchestration.dispatcher import Dispatcher, DispatcherMode
    
    dispatcher = Dispatcher()
    
    questions = [
        "Définir habilitation",
        "Comment calculer les congés?",
        "Procédure de formation",
    ]
    
    print(f"Processing {len(questions)} questions...\n")
    
    results = dispatcher.agent.batch_answer(questions)
    
    for i, (q, r) in enumerate(zip(questions, results), 1):
        print(f"\n[{i}] {q}")
        print(f"    → {r.get('answer', 'Error')[:100]}...")
    
    print(f"\n✅ Processed {len(results)} questions")


def demo_performance():
    """Demo performance metrics"""
    
    print_header("⚡ PERFORMANCE DEMO")
    
    import time
    from orchestration.dispatcher import Dispatcher
    
    dispatcher = Dispatcher()
    
    questions = [
        "Qu'est-ce qu'une habilitation?",
        "Comment calculer les heures?",
    ]
    
    times = []
    
    for question in questions:
        start = time.time()
        result = dispatcher.dispatch(question)
        elapsed = time.time() - start
        times.append(elapsed)
        
        print(f"\n❓ {question[:50]}...")
        print(f"   ⏱️  Time: {elapsed:.2f}s")
        print(f"   📊 Retrieved: {result.get('retrieval_count')} results")
        print(f"   📚 Sources: {len(result.get('sources', []))} used")
    
    avg_time = sum(times) / len(times)
    print(f"\n✓ Average response time: {avg_time:.2f}s")


if __name__ == "__main__":
    
    # Choose demo mode
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        
        if mode == "batch":
            demo_batch()
        elif mode == "performance":
            demo_performance()
        else:
            demo_main()
    else:
        # Default: interactive demo
        success = demo_main()
        sys.exit(0 if success else 1)
