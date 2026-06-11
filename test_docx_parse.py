#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test parsing du fichier DOCX qui a l'erreur"""

from pathlib import Path
import sys

try:
    import docx
except ImportError:
    print("❌ python-docx n'est pas installé!")
    sys.exit(1)

# Test les deux fichiers
files = [
    "unified-agent/ui/uploads/SFD_CTIME_UX_Inetum_2.13_EN_FR 2 (1).docx",
    "unified-agent/ui/uploads/SFD_CTIME_UX_Inetum_2.13_EN_FR 2 (2).docx",
]

for file_path_str in files:
    file_path = Path(file_path_str)
    
    print(f"\n{'='*80}")
    print(f"📄 Test: {file_path.name}")
    print(f"{'='*80}")
    
    if not file_path.exists():
        print(f"❌ Fichier non trouvé: {file_path}")
        continue
    
    print(f"✓ Taille: {file_path.stat().st_size:,} bytes")
    
    try:
        doc = docx.Document(file_path)
        print(f"✓ Fichier ouvert avec succès")
        print(f"✓ Nombre de paragraphes: {len(doc.paragraphs)}")
        print(f"✓ Nombre de tables: {len(doc.tables)}")
        
        # Compter le texte
        text_chunks = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                text_chunks.append(text)
        
        print(f"✓ Paragraphes avec du texte: {len(text_chunks)}")
        
        if text_chunks:
            print(f"\n📝 Premiers textes extraits:")
            for i, chunk in enumerate(text_chunks[:3]):
                preview = chunk[:100].replace('\n', ' ')
                print(f"  {i+1}. {preview}...")
        else:
            print(f"\n⚠️  ATTENTION: Aucun texte trouvé dans les paragraphes!")
            if len(doc.tables) > 0:
                print(f"    → Fichier contient {len(doc.tables)} table(s)")
                print(f"    → Le DocxParser ne peut pas extraire les tables!")
            
    except Exception as e:
        print(f"❌ ERREUR lors du parsing: {type(e).__name__}")
        print(f"   Message: {str(e)}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*80}\n")
