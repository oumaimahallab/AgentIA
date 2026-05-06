#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main entry point - CLI for unified agent
"""

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)

logger = logging.getLogger(__name__)


def main():
    """Main CLI"""
    
    parser = argparse.ArgumentParser(
        description="Unified Agent - Combined HR + Document RAG System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py answer "Qu'est-ce qu'une habilitation?"
  python main.py batch questions.txt
  python main.py demo
  python main.py setup
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # ANSWER command
    answer_parser = subparsers.add_parser("answer", help="Answer a single question")
    answer_parser.add_argument("question", help="Question to answer")
    answer_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    # BATCH command
    batch_parser = subparsers.add_parser("batch", help="Answer questions from file")
    batch_parser.add_argument("file", help="Questions file (one per line)")
    batch_parser.add_argument("--output", "-o", help="Output file for results")
    
    # DEMO command
    demo_parser = subparsers.add_parser("demo", help="Run interactive demo")
    demo_parser.add_argument("--mode", choices=["interactive", "batch", "performance"],
                            default="interactive", help="Demo mode")
    
    # SETUP command
    setup_parser = subparsers.add_parser("setup", help="Setup environment")
    
    # STATUS command
    status_parser = subparsers.add_parser("status", help="Show system status")
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Run tests")
    test_parser.add_argument("--suite", choices=["retrieval", "llm", "integration"],
                            help="Test suite to run")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    # Handle SETUP
    if args.command == "setup":
        from scripts.setup import run_setup
        return run_setup()
    
    # Handle DEMO
    if args.command == "demo":
        from scripts.demo import demo_main, demo_batch, demo_performance
        
        if args.mode == "batch":
            demo_batch()
        elif args.mode == "performance":
            demo_performance()
        else:
            return 0 if demo_main() else 1
    
    # Handle STATUS
    if args.command == "status":
        try:
            from orchestration.dispatcher import Dispatcher
            dispatcher = Dispatcher()
            status = dispatcher.agent.get_system_status()
            
            print("\n📊 System Status:")
            for key, value in status.items():
                print(f"  {key}: {value}")
            
            return 0
        except Exception as e:
            logger.error(f"Error: {e}")
            return 1
    
    # Handle ANSWER
    if args.command == "answer":
        try:
            from orchestration.dispatcher import Dispatcher, DispatcherMode
            
            logger.info("Initializing agent...")
            dispatcher = Dispatcher()
            
            logger.info(f"Question: {args.question}")
            result = dispatcher.dispatch(args.question, DispatcherMode.SINGLE)
            
            if result.get("success"):
                print("\n" + "="*70)
                print(f"✓ Answer ({result.get('llm_source', 'unknown')}):")
                print("="*70)
                print(result.get("answer", "No answer"))
                print("="*70)
                
                if args.verbose:
                    print(f"\nIntent: {result.get('intent')}")
                    print(f"Sources: {len(result.get('sources', []))}")
                    print(f"Confidence: {result.get('intent_confidence', 0):.0%}")
                
                return 0
            else:
                logger.error(f"Error: {result.get('error')}")
                return 1
        
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return 1
    
    # Handle BATCH
    if args.command == "batch":
        try:
            batch_file = Path(args.file)
            
            if not batch_file.exists():
                logger.error(f"File not found: {batch_file}")
                return 1
            
            questions = batch_file.read_text().strip().split("\n")
            questions = [q.strip() for q in questions if q.strip()]
            
            logger.info(f"Processing {len(questions)} questions...")
            
            from orchestration.dispatcher import Dispatcher
            
            dispatcher = Dispatcher()
            results = dispatcher.agent.batch_answer(questions)
            
            # Output results
            output = Path(args.output) if args.output else None
            
            lines = []
            for q, r in zip(questions, results):
                lines.append(f"Q: {q}")
                lines.append(f"A: {r.get('answer', 'Error')}")
                lines.append("")
            
            output_text = "\n".join(lines)
            
            if output:
                output.write_text(output_text)
                logger.info(f"Results saved to {output}")
            else:
                print(output_text)
            
            return 0
        
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return 1
    
    # Handle TEST
    if args.command == "test":
        import unittest
        
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        
        if args.suite == "retrieval":
            suite = loader.discover("tests", pattern="test_retrieval.py")
        elif args.suite == "llm":
            suite = loader.discover("tests", pattern="test_llm.py")
        elif args.suite == "integration":
            try:
                from tests.test_llm import TestIntegration
                suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
            except ImportError:
                logger.warning("Integration tests not available")
        else:
            suite = loader.discover("tests", pattern="test_*.py")
        
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        return 0 if result.wasSuccessful() else 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
