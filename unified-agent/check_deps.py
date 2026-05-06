#!/usr/bin/env python3
"""Check if all critical dependencies are installed"""

import sys

print("\n" + "="*60)
print("  CHECKING DEPENDENCIES")
print("="*60 + "\n")

deps = {
    'groq': 'Groq API',
    'sentence_transformers': 'Sentence Transformers',
    'faiss': 'FAISS',
    'rank_bm25': 'BM25',
    'torch': 'PyTorch',
    'pydantic': 'Pydantic',
    'dotenv': 'python-dotenv',
    'numpy': 'NumPy',
    'requests': 'Requests',
    'PyPDF2': 'PyPDF2',
}

ok_count = 0
missing = []

for module, name in deps.items():
    try:
        __import__(module)
        print(f"✅ {name}")
        ok_count += 1
    except ImportError as e:
        print(f"❌ {name} - MISSING")
        missing.append(name)

print(f"\n{ok_count}/{len(deps)} dependencies OK\n")

if missing:
    print(f"Missing: {', '.join(missing)}")
    sys.exit(1)
else:
    print("✅ All critical dependencies installed!")
    sys.exit(0)
