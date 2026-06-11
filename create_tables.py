#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crée les tables PostgreSQL manquantes
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def create_tables():
    """Crée la table user_documents et autres tables manquantes"""
    
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'postgres'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'root'),
        )
        c = conn.cursor()
        
        print("\n" + "="*60)
        print("🔧 CRÉATION DES TABLES MANQUANTES")
        print("="*60)
        
        # 1. Table users
        print("\n1️⃣  Création table 'users'...")
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (id SERIAL PRIMARY KEY, email TEXT UNIQUE, name TEXT, password TEXT,
                      role VARCHAR(20) DEFAULT 'user')''')
        print("   ✅ Table 'users' créée")
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user'")
        c.execute("UPDATE users SET role = 'user' WHERE role IS NULL")
        c.execute("UPDATE users SET role = 'admin' WHERE email = 'admin@inetum.com'")
        
        # 2. Table sessions
        print("\n2️⃣  Création table 'sessions'...")
        c.execute('''CREATE TABLE IF NOT EXISTS sessions 
                     (session_id TEXT PRIMARY KEY, user_email TEXT, title TEXT, messages TEXT, timestamp TEXT, is_pinned INTEGER DEFAULT 0, is_archived INTEGER DEFAULT 0, is_deleted INTEGER DEFAULT 0)''')
        print("   ✅ Table 'sessions' créée")
        
        # 3. Table documents
        print("\n3️⃣  Création table 'documents'...")
        c.execute('''CREATE TABLE IF NOT EXISTS documents 
                     (id SERIAL PRIMARY KEY, filename TEXT UNIQUE, status TEXT, error_msg TEXT,
                      user_id INTEGER REFERENCES users(id),
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('ALTER TABLE documents ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)')
        print("   ✅ Table 'documents' créée")
        
        # 4. Table user_documents (LA PLUS IMPORTANTE!)
        print("\n4️⃣  Création table 'user_documents'...")
        c.execute('''CREATE TABLE IF NOT EXISTS user_documents 
                     (id SERIAL PRIMARY KEY, 
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
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('ALTER TABLE user_documents ADD COLUMN IF NOT EXISTS document_id INTEGER REFERENCES documents(id)')
        print("   ✅ Table 'user_documents' créée")
        
        # 5. Créer les indices
        print("\n5️⃣  Création des indices...")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_documents_email ON user_documents(user_email)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_documents_session ON user_documents(session_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_documents_status ON user_documents(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_documents_document_id ON user_documents(document_id)")
        print("   ✅ Indices créés")
        
        # 6. Ajouter les utilisateurs de test
        print("\n6️⃣  Ajout des utilisateurs de test...")
        users = [
            ('admin@inetum.com', 'Oumaima Hallab', 'admin123', 'admin'),
            ('demo@inetum.com', 'Imane Benzegunine', 'demo123', 'user'),
        ]
        for email, name, pwd, role in users:
            c.execute("""
                INSERT INTO users (email, name, password, role) 
                VALUES (%s, %s, %s, %s) 
                ON CONFLICT (email) DO UPDATE SET
                    name = EXCLUDED.name,
                    password = EXCLUDED.password,
                    role = EXCLUDED.role
            """, (email, name, pwd, role))
        print("   ✅ Utilisateurs de test ajoutés")
        
        # Commit
        conn.commit()
        
        print("\n" + "="*60)
        print("✅ TOUTES LES TABLES ONT ÉTÉ CRÉÉES!")
        print("="*60)
        
        # Vérifier
        print("\n📊 Vérification :")
        c.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = c.fetchall()
        print(f"   Tables créées : {len(tables)}")
        for table in tables:
            print(f"   - {table[0]}")
        
        conn.close()
        print("\n✅ PRÊT À UTILISER!")
        print("\nProchaines étapes :")
        print("1. Redémarrer app.py")
        print("2. Tester l'upload via http://localhost:5005/upload_realtime.html")
        print("3. Vérifier que les documents s'ajoutent à la BD")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        return False


if __name__ == '__main__':
    import sys
    
    print("\n🔧 CRÉATION DES TABLES POSTGRESQL")
    print("="*60)
    print("Cet script crée toutes les tables nécessaires pour l'upload.")
    print("\nLa table principale 'user_documents' sera créée.")
    
    response = input("\nContinuer ? (o/n) : ").strip().lower()
    if response != 'o':
        print("Annulé.")
        sys.exit(0)
    
    if create_tables():
        print("\n✅ Succès!")
        sys.exit(0)
    else:
        print("\n❌ Échec!")
        sys.exit(1)
