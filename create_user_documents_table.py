#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Créer la table user_documents manquante dans PostgreSQL
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def create_user_documents_table():
    """Crée la table user_documents si elle n'existe pas"""
    
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'postgres'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'root'),
        connect_timeout=5
    )
    
    try:
        c = conn.cursor()
        
        print("🔄 Création de la table user_documents...")
        
        # Créer la table
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_documents 
            (
                id SERIAL PRIMARY KEY,
                user_email TEXT NOT NULL,
                session_id TEXT,
                filename TEXT NOT NULL,
                file_type TEXT,
                file_size INTEGER,
                file_hash TEXT UNIQUE,
                source_type TEXT,
                status TEXT DEFAULT 'En attente',
                error_msg TEXT,
                total_chunks INTEGER DEFAULT 0,
                processing_time FLOAT,
                language TEXT DEFAULT 'fr',
                keywords TEXT,
                extracted_entities TEXT,
                cleaning_stats TEXT,
                ingestion_timestamp TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Créer les indexes
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_documents_email ON user_documents(user_email)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_documents_session ON user_documents(session_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_documents_status ON user_documents(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_documents_hash ON user_documents(file_hash)")
        
        conn.commit()
        
        print("✅ Table user_documents créée avec succès!")
        print("✅ Indexes créés")
        
        # Vérifier que la table existe
        c.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'user_documents'
        """)
        
        columns = c.fetchall()
        print(f"\n📊 Colonnes de la table ({len(columns)}) :")
        for col_name, col_type in columns:
            print(f"   • {col_name} ({col_type})")
        
    except Exception as e:
        print(f"❌ Erreur : {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🔧 CRÉATION TABLE USER_DOCUMENTS")
    print("="*60 + "\n")
    
    create_user_documents_table()
    
    print("\n" + "="*60)
    print("✅ COMPLÉTÉ")
    print("="*60)
