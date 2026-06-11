#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract transcription from metadata files"""

import pickle
from pathlib import Path

print("\n" + "="*70)
print("📄 TRANSCRIPTION DOCUMENT #53")
print("="*70)

# Charger les métadonnées
metadata_files = [
    'data/indices/bm25/bm25_metadata.pkl',
    'data/indices/faiss/metadata.pkl'
]

for metadata_file in metadata_files:
    path = Path(metadata_file)
    if not path.exists():
        continue
    
    print(f"\n📂 Fichier: {metadata_file}")
    print("-" * 70)
    
    with open(path, 'rb') as f:
        try:
            data = pickle.load(f)
        except:
            print("  ✗ Erreur lors du chargement")
            continue
    
    # Chercher le document #53
    doc53_found = False
    
    if isinstance(data, list):
        print(f"  ✓ Type: List ({len(data)} items)")
        for i, item in enumerate(data):
            if isinstance(item, dict):
                # Chercher par ID ou filename
                if item.get('id') == 53 or '53' in str(item.get('filename', '')):
                    doc53_found = True
                    print(f"\n  ✓ FOUND AT INDEX {i}:")
                    print(f"    - ID: {item.get('id', 'N/A')}")
                    print(f"    - Filename: {item.get('filename', 'N/A')}")
                    print(f"    - Status: {item.get('status', 'N/A')}")
                    
                    # Afficher la transcription
                    if 'text' in item:
                        text = item['text']
                        if isinstance(text, str):
                            print(f"    - Text length: {len(text)} chars")
                            print(f"    - Preview: {text[:300]}...")
                            
                            # Sauvegarder dans un fichier
                            output_file = Path('document_53_transcription.txt')
                            with open(output_file, 'w', encoding='utf-8') as out:
                                out.write(f"DOCUMENT: {item.get('filename', 'N/A')}\n")
                                out.write(f"STATUS: {item.get('status', 'N/A')}\n")
                                out.write(f"LENGTH: {len(text)} characters\n")
                                out.write("="*70 + "\n\n")
                                out.write(text)
                            print(f"\n  ✓ Transcription sauvegardée: {output_file}")
                    
                    # Afficher les autres clés
                    for key in item.keys():
                        if key not in ['text', 'id', 'filename', 'status']:
                            val = item[key]
                            if isinstance(val, (str, int, float, bool)):
                                print(f"    - {key}: {val}")
                            elif isinstance(val, (list, dict)):
                                print(f"    - {key}: {type(val).__name__} ({len(val)} items)")
    
    elif isinstance(data, dict):
        print(f"  ✓ Type: Dict ({len(data)} keys)")
        for key, item in data.items():
            if '53' in str(key) or (isinstance(item, dict) and '53' in str(item.get('filename', ''))):
                doc53_found = True
                print(f"\n  ✓ FOUND AT KEY: {key}")
                if isinstance(item, dict):
                    for k, v in item.items():
                        if k == 'text' and isinstance(v, str):
                            print(f"    - {k}: {len(v)} chars")
                            print(f"    - Preview: {v[:300]}...")
                        elif not isinstance(v, (list, dict)):
                            print(f"    - {k}: {v}")

print("\n" + "="*70)
