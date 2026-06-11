#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check where transcriptions are stored"""

import os
import sys
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', '5432'),
    database=os.getenv('DB_NAME', 'postgres'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD', 'root'),
    client_encoding='utf8'
)

# Voir les tables disponibles
cur = conn.cursor()
cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'public' 
    ORDER BY table_name
""")
tables = cur.fetchall()
print('\n📋 TABLES DISPONIBLES:')
for t in tables:
    print(f'  - {t[0]}')

# Voir la structure de la table documents
print('\n📊 STRUCTURE TABLE DOCUMENTS:')
cur.execute("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns 
    WHERE table_name = 'documents'
    ORDER BY ordinal_position
""")
cols = cur.fetchall()
for c in cols:
    nullable = "✓" if c[2] == 'YES' else "✗"
    print(f'  - {c[0]:20} {c[1]:20} (nullable: {nullable})')

# Voir le contenu pour doc #53
print('\n📄 CONTENU DOCUMENT #53:')
cur.execute('SELECT * FROM documents WHERE id = 53')
doc = cur.fetchone()
if doc:
    col_names = [desc[0] for desc in cur.description]
    for name, value in zip(col_names, doc):
        if value and len(str(value)) > 100:
            print(f'  - {name}: {str(value)[:100]}...')
        else:
            print(f'  - {name}: {value}')

# Chercher les autres tables qui pourraient contenir le texte
print('\n🔍 AUTRES TABLES:')
for table_name in ['chunks', 'content', 'transcriptions', 'text', 'ingested_documents', 'document_chunks']:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cur.fetchone()[0]
        print(f'  ✓ {table_name}: {count} rows')
    except:
        pass

# Vérifier les répertoires de fichiers
print('\n📁 STOCKAGE FICHIERS:')
storage_dirs = [
    Path(__file__).parent / 'data' / 'ingested',
    Path(__file__).parent / 'data' / 'uploads',
    Path(__file__).parent / 'data' / 'documents',
    Path(__file__).parent / 'data' / 'transcriptions',
    Path.home() / 'Downloads',
]

for dir_path in storage_dirs:
    if dir_path.exists():
        files = list(dir_path.glob('*'))
        print(f'  ✓ {dir_path} ({len(files)} files)')
        for f in files[:3]:
            print(f'    - {f.name}')
        if len(files) > 3:
            print(f'    ... et {len(files)-3} autres')
    else:
        print(f'  ✗ {dir_path} (not found)')

cur.close()
conn.close()
