#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find where transcriptions are actually stored"""

import faiss
import pickle
from pathlib import Path
import numpy as np

print("\n" + "="*70)
print("🔍 RECHERCHE STOCKAGE TRANSCRIPTIONS")
print("="*70)

# FAISS index
print("\n📊 FAISS Index:")
faiss_path = Path('data/indices/faiss/index.faiss')
if faiss_path.exists():
    index = faiss.read_index(str(faiss_path))
    print(f'  ✓ Vecteurs stockés: {index.ntotal}')
    print(f'  ✓ Dimensions: {index.d}')
else:
    print("  ✗ FAISS index not found")

# BM25 index
print("\n📊 BM25 Index:")
bm25_path = Path('data/indices/bm25/bm25_index.pkl')
if bm25_path.exists():
    with open(bm25_path, 'rb') as f:
        bm25_data = pickle.load(f)
    print(f'  ✓ Type: {type(bm25_data).__name__}')
    if isinstance(bm25_data, dict):
        print(f'  ✓ Nombre de documents: {len(bm25_data)}')
        # Afficher les premières clés
        keys = list(bm25_data.keys())[:3]
        for k in keys:
            doc_data = bm25_data[k]
            if isinstance(doc_data, dict):
                text = doc_data.get('text', '')[:100] if 'text' in doc_data else str(doc_data)[:100]
                print(f'    - {k}: {text}...')
else:
    print("  ✗ BM25 index not found")

# Métadonnées
print("\n📁 Fichiers de stockage:")
data_files = {
    'JSON': list(Path('data').rglob('*.json')),
    'TXT': list(Path('data').rglob('*.txt')),
    'PKL': list(Path('data').rglob('*.pkl')),
    'NRRD': list(Path('data').rglob('*.nrrd')),
    'DB': list(Path('data').rglob('*.db')),
}

for ext, files in data_files.items():
    if files:
        print(f'  ✓ {ext} files: {len(files)}')
        for f in files[:3]:
            size_mb = f.stat().st_size / 1024 / 1024
            print(f'    - {f.relative_to(".")}: {size_mb:.2f} MB')

# Logs
print("\n📋 Logs récents:")
log_files = list(Path('.').glob('*.log')) + list(Path('logs').glob('*.log') if Path('logs').exists() else [])
for f in log_files[:3]:
    print(f'  - {f}')

# Vérifier si les métadonnées BM25 contiennent le document #53
print("\n🎬 DOCUMENT #53 DANS LES INDICES:")
if bm25_path.exists():
    with open(bm25_path, 'rb') as f:
        bm25_data = pickle.load(f)
    
    if isinstance(bm25_data, dict):
        doc53_found = False
        for key, doc in bm25_data.items():
            if '53' in str(key) or ('filename' in doc if isinstance(doc, dict) else False):
                if isinstance(doc, dict) and 'filename' in doc:
                    if '53' in doc['filename'] or 'Accompagnement' in doc.get('filename', ''):
                        print(f"  ✓ Trouvé: {key}")
                        print(f"    - Filename: {doc.get('filename', 'N/A')}")
                        text_preview = doc.get('text', '')[:200] if 'text' in doc else 'N/A'
                        print(f"    - Text: {text_preview}...")
                        doc53_found = True
        
        if not doc53_found:
            print("  ✗ Document #53 pas trouvé dans les indices")

print("\n" + "="*70)
