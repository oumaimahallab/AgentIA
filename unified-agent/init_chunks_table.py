#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Initialize document chunks table in PostgreSQL"""

import os
import sys
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

def create_chunks_table():
    """Create document_chunks table"""
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'postgres'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'root'),
        client_encoding='utf8'
    )
    
    cur = conn.cursor()
    
    # Créer la table document_chunks
    cur.execute("""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_number INTEGER NOT NULL,
            text TEXT NOT NULL,
            text_length INTEGER,
            hash VARCHAR(64),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT unique_doc_chunk UNIQUE(document_id, chunk_number)
        );
    """)
    
    # Index pour recherche rapide
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_document_chunks_doc_id 
        ON document_chunks(document_id);
    """)
    
    conn.commit()
    cur.close()
    conn.close()
    
    print("✅ Table 'document_chunks' créée avec succès!")

if __name__ == "__main__":
    try:
        create_chunks_table()
    except Exception as e:
        print(f"❌ Erreur: {e}")
        sys.exit(1)
