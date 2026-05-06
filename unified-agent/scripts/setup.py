#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Setup script - Initialize development environment
"""

import os
import sys
import subprocess
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s | %(message)s"
)

logger = logging.getLogger(__name__)


def print_header(text):
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70 + "\n")


def check_python_version():
    """Verify Python version >= 3.8"""
    print_header("✓ Checking Python Version")
    
    version = sys.version_info
    print(f"Python {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        logger.error("Python 3.8+ required!")
        return False
    
    logger.info("✅ Python version OK")
    return True


def check_virtual_env():
    """Check if running in virtual environment"""
    print_header("✓ Checking Virtual Environment")
    
    in_venv = hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    )
    
    if not in_venv:
        logger.warning("Not in virtual environment!")
        logger.info("Recommended: Create venv with 'python -m venv venv'")
        logger.info("Then activate: 'venv\\Scripts\\activate' (Windows)")
        return False
    
    logger.info("✅ Running in virtual environment")
    return True


def check_requirements():
    """Install required packages"""
    print_header("✓ Installing Requirements")
    
    req_file = Path(__file__).parent.parent / "requirements.txt"
    
    if not req_file.exists():
        logger.error(f"requirements.txt not found at {req_file}")
        return False
    
    try:
        logger.info("Running: pip install -r requirements.txt")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info("✅ Requirements installed")
        return True
    
    except Exception as e:
        logger.error(f"Failed to install requirements: {e}")
        return False


def check_api_keys():
    """Check for required API keys"""
    print_header("✓ Checking API Keys")
    
    groq_key = os.getenv("GROQ_API_KEY")
    
    if not groq_key:
        logger.warning("GROQ_API_KEY not set!")
        logger.info("Get one from: https://console.groq.com")
        logger.info("Set with: export GROQ_API_KEY=your_key (Linux/Mac)")
        logger.info("Or: set GROQ_API_KEY=your_key (Windows)")
        return False
    
    logger.info("✅ GROQ_API_KEY configured")
    return True


def check_imports():
    """Test critical imports"""
    print_header("✓ Testing Imports")
    
    imports_to_test = [
        ("torch", "PyTorch"),
        ("sentence_transformers", "Sentence Transformers"),
        ("faiss", "FAISS"),
        ("rank_bm25", "BM25"),
        ("groq", "Groq"),
        ("llama_index", "Llama Index"),
    ]
    
    failed = []
    
    for module, name in imports_to_test:
        try:
            __import__(module)
            logger.info(f"✓ {name}")
        except ImportError:
            logger.warning(f"✗ {name} - Not installed")
            failed.append(name)
    
    if failed:
        logger.error(f"Missing: {', '.join(failed)}")
        return False
    
    logger.info("✅ All imports OK")
    return True


def validate_indices():
    """Check if indices exist and are valid"""
    print_header("✓ Checking Indices")
    
    from config import get_config
    config = get_config()
    
    faiss_dir = Path(config.paths.FAISS_INDEX_DIR)
    bm25_dir = Path(config.paths.BM25_INDEX_DIR)
    
    faiss_exists = (faiss_dir / "index.faiss").exists()
    bm25_exists = (bm25_dir / "index.pkl").exists()
    
    if faiss_exists:
        logger.info("✓ FAISS index found")
    else:
        logger.warning("⚠ FAISS index not found - will be created on first run")
    
    if bm25_exists:
        logger.info("✓ BM25 index found")
    else:
        logger.warning("⚠ BM25 index not found - will be created on first run")
    
    return True


def create_env_file():
    """Create .env template if missing"""
    print_header("✓ Creating .env Template")
    
    env_file = Path(__file__).parent.parent / ".env"
    
    if env_file.exists():
        logger.info("✓ .env already exists")
        return True
    
    template = """\
# Groq API Configuration
GROQ_API_KEY=your_api_key_here

# Ollama Configuration (optional)
OLLAMA_ENDPOINT=http://localhost:11434
OLLAMA_MODEL=llama2

# Paths Configuration (usually OK as is)
WORKSPACE_ROOT=.
FAISS_INDEX_DIR=./data/indices/faiss
BM25_INDEX_DIR=./data/indices/bm25

# Model Configuration
EMBEDDINGS_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DEVICE=cpu
"""
    
    env_file.write_text(template)
    logger.info(f"✓ Created .env template at {env_file}")
    logger.info("⚠ Please fill in GROQ_API_KEY before running")
    
    return True


def run_setup():
    """Run complete setup"""
    
    print("\n")
    logger.info("🚀 UNIFIED AGENT SETUP")
    
    checks = [
        ("Python version", check_python_version),
        ("Virtual environment", check_virtual_env),
        ("Requirements", check_requirements),
        ("Imports", check_imports),
        ("API keys", check_api_keys),
        ("Indices", validate_indices),
        ("Env template", create_env_file),
    ]
    
    results = []
    
    for name, check_fn in checks:
        try:
            result = check_fn()
            results.append((name, result))
        except Exception as e:
            logger.error(f"Exception in {name}: {e}")
            results.append((name, False))
    
    # Summary
    print_header("📊 Setup Summary")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {name}")
    
    print(f"\n{passed}/{total} checks passed")
    
    if passed == total:
        logger.info("\n✅ Setup complete! Ready to use.")
        logger.info("Run: python scripts/demo.py")
        return True
    else:
        logger.error("\n⚠️  Some checks failed. Please fix issues above.")
        return False


if __name__ == "__main__":
    success = run_setup()
    sys.exit(0 if success else 1)
