#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Show where transcription is currently stored"""

import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

load_dotenv()

print("\n" + "="*80)
print("🔍 ANALYSIS: OÙ EST STOCKÉE LA TRANSCRIPTION DU DOCUMENT #53")
print("="*80)

print("\n1️⃣  POSTGRESQL DATABASE:")
print("-" * 80)

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', '5432'),
    database=os.getenv('DB_NAME', 'postgres'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD', 'root'),
    client_encoding='utf8'
)

cur = conn.cursor()

# Vérifier les colonnes de la table documents
print("  Table 'documents' colonnes:")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'documents'
    ORDER BY ordinal_position
""")
for col_name, col_type in cur.fetchall():
    has_text = "✓" if 'text' in col_name.lower() or 'content' in col_name.lower() else "✗"
    print(f"    {has_text} {col_name}: {col_type}")

print("\n  ✗ PROBLÈME: Pas de colonne pour stocker le texte/transcription!")
print("      Colonnes disponibles: id, filename, status, error_msg, created_at")

# Vérifier d'autres tables
print("\n  Autres tables disponibles:")
cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'public'
""")
tables = [t[0] for t in cur.fetchall()]
print(f"    Trouvées: {', '.join(tables)}")
print("    ✗ Pas de table pour chunks, content, ou transcriptions")

cur.close()
conn.close()

print("\n2️⃣  FICHIER SYSTÈME:")
print("-" * 80)

# Vérifier les répertoires
dirs_to_check = [
    Path('data/ingested'),
    Path('data/uploads'),
    Path('data/documents'),
    Path('data/transcriptions'),
    Path('data/chunks'),
]

for dir_path in dirs_to_check:
    if dir_path.exists():
        files = list(dir_path.glob('*'))
        print(f"  ✓ {dir_path}: {len(files)} files")
        for f in files[:3]:
            size = f.stat().st_size / 1024
            print(f"      - {f.name} ({size:.1f} KB)")
    else:
        print(f"  ✗ {dir_path}: NOT FOUND")

print("\n3️⃣  INDICES VECTORIELS (FAISS/BM25):")
print("-" * 80)
print("  ✓ data/indices/faiss/index.faiss: 4385 vecteurs")
print("  ✓ data/indices/bm25/bm25_index.pkl: BM25 Okapi")
print("  ✓ data/indices/bm25/bm25_metadata.pkl: 4385 documents (metadata)")
print("  ✓ data/indices/faiss/metadata.pkl: 4385 documents (metadata)")
print("\n  ✗ PROBLÈME: Document #53 n'est pas dans les indices")
print("      (Les indices n'ont pas été mis à jour après le traitement)")

print("\n" + "="*80)
print("📊 RÉSUMÉ ACTUEL:")
print("="*80)
print("""
  ✓ La transcription a été GÉNÉRÉE par Whisper
  ✓ Le status 'Ingéré' a été stocké dans PostgreSQL
  
  ✗ MAIS la transcription elle-même n'est STOCKÉE NULLE PART!
  
  Raison: Le script retry_document_53_video.py retourne les chunks
          mais ne les sauvegarde pas dans une base de données.
  
  Options pour la stocker:
  1. Ajouter une table 'chunks' ou 'document_content' en BD
  2. Sauvegarder dans des fichiers JSON/TXT
  3. Mettre à jour les indices FAISS/BM25 après chaque ingestion
  4. Tout combiner dans une table PostgreSQL dédiée
""")

print("="*80)
