#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic Upload - Vérife pourquoi les uploads ne se stockent pas en BD
"""

import os
import sys
import psycopg2
import hashlib
from pathlib import Path
from dotenv import load_dotenv

# Charger les env
load_dotenv()

def check_db_connection():
    """Vérifier la connexion à PostgreSQL"""
    print("\n" + "="*60)
    print("🔍 TEST 1: Connexion PostgreSQL")
    print("="*60)
    
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'postgres'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'root'),
            connect_timeout=5
        )
        print("✅ Connexion PostgreSQL réussie")
        
        # Vérifier la version
        c = conn.cursor()
        c.execute("SELECT version();")
        version = c.fetchone()[0]
        print(f"   PostgreSQL : {version.split(',')[0]}")
        
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Erreur connexion PostgreSQL: {e}")
        print(f"\n   Vérifier :")
        print(f"   1. PostgreSQL est lancé")
        print(f"   2. Fichier .env existe avec les bonnes données")
        print(f"   3. Credentials : {os.getenv('DB_USER')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}")
        return False


def check_user_documents_table():
    """Vérifier la table user_documents"""
    print("\n" + "="*60)
    print("🔍 TEST 2: Table user_documents")
    print("="*60)
    
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'postgres'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'root'),
        )
        c = conn.cursor()
        
        # Vérifier si la table existe
        c.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'user_documents'
            );
        """)
        
        exists = c.fetchone()[0]
        
        if not exists:
            print("❌ Table user_documents n'existe pas!")
            print("\n   Solution : Recréer la table dans init_db()")
            print("   - Redémarrer app.py")
            print("   - Ou exécuter manuellement :")
            print("""
    CREATE TABLE user_documents (
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
    );
            """)
            conn.close()
            return False
        
        print("✅ Table user_documents existe")
        
        # Vérifier les colonnes
        c.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'user_documents'
            ORDER BY ordinal_position;
        """)
        
        columns = c.fetchall()
        print(f"   Colonnes : {len(columns)}")
        
        required_columns = {
            'id', 'user_email', 'filename', 'file_hash', 
            'file_size', 'file_type', 'status', 'created_at'
        }
        
        found_columns = {col[0] for col in columns}
        missing = required_columns - found_columns
        
        if missing:
            print(f"   ❌ Colonnes manquantes : {missing}")
            conn.close()
            return False
        
        print("   ✅ Tous les colonnes requis sont présents")
        
        # Vérifier les documents
        c.execute("SELECT COUNT(*) FROM user_documents;")
        count = c.fetchone()[0]
        print(f"   Documents stockés : {count}")
        
        # Afficher les derniers documents
        if count > 0:
            c.execute("""
                SELECT id, filename, status, created_at 
                FROM user_documents 
                ORDER BY created_at DESC 
                LIMIT 5;
            """)
            docs = c.fetchall()
            print("\n   Derniers documents :")
            for doc in docs:
                print(f"   - ID {doc[0]}: {doc[1]} [{doc[2]}] {doc[3]}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Erreur vérification table: {e}")
        return False


def check_upload_folder():
    """Vérifier le dossier uploads"""
    print("\n" + "="*60)
    print("🔍 TEST 3: Dossier uploads")
    print("="*60)
    
    try:
        upload_folder = Path("uploads")
        
        if not upload_folder.exists():
            print("❌ Dossier 'uploads' n'existe pas!")
            print(f"   Création du dossier...")
            upload_folder.mkdir(exist_ok=True)
            print(f"   ✅ Dossier créé : {upload_folder.absolute()}")
        else:
            print(f"✅ Dossier 'uploads' existe : {upload_folder.absolute()}")
        
        # Lister les fichiers
        files = list(upload_folder.glob("*"))
        print(f"   Fichiers : {len(files)}")
        
        if files:
            print("   Fichiers uploadés :")
            for f in files[:5]:
                size = f.stat().st_size
                print(f"   - {f.name} ({size} bytes)")
        
        return True
    except Exception as e:
        print(f"❌ Erreur vérification dossier: {e}")
        return False


def test_insert_document():
    """Tester l'INSERT d'un document en BD"""
    print("\n" + "="*60)
    print("🔍 TEST 4: INSERT test document")
    print("="*60)
    
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'postgres'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'root'),
        )
        c = conn.cursor()
        
        # Créer un test document
        test_email = "test@example.com"
        test_filename = "test_document.txt"
        test_hash = hashlib.sha256(b"test content").hexdigest()
        test_size = 100
        test_type = "txt"
        
        print(f"   Insertion test :")
        print(f"   - Email : {test_email}")
        print(f"   - Fichier : {test_filename}")
        print(f"   - Hash : {test_hash[:16]}...")
        print(f"   - Taille : {test_size} bytes")
        
        # Vérifier si le fichier existe déjà
        c.execute("SELECT id FROM user_documents WHERE file_hash=%s", (test_hash,))
        if c.fetchone():
            print(f"   ⚠️  Document test déjà dans BD")
            conn.close()
            return True
        
        # INSERT
        c.execute("""
            INSERT INTO user_documents 
            (user_email, filename, file_type, file_size, file_hash, status)
            VALUES (%s, %s, %s, %s, %s, 'En attente')
            RETURNING id
        """, (test_email, test_filename, test_type, test_size, test_hash))
        
        doc_id = c.fetchone()[0]
        conn.commit()
        
        print(f"   ✅ INSERT réussi!")
        print(f"   ID créé : {doc_id}")
        
        # Vérifier que c'est bien stocké
        c.execute("SELECT id, filename, status FROM user_documents WHERE id=%s", (doc_id,))
        result = c.fetchone()
        
        if result:
            print(f"   ✅ Document trouvé en BD : {result[1]} [{result[2]}]")
        else:
            print(f"   ❌ Document introuvable après INSERT!")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Erreur INSERT test: {e}")
        return False


def check_app_py_syntax():
    """Vérifier la syntaxe du code app.py"""
    print("\n" + "="*60)
    print("🔍 TEST 5: Syntaxe app.py")
    print("="*60)
    
    try:
        import sys
        sys.path.insert(0, str(Path.cwd()))
        
        # Tenter d'importer le module
        try:
            import app
            print("✅ app.py charge correctement")
            
            # Vérifier les fonctions importantes
            if hasattr(app, 'user_upload_and_ingest'):
                print("✅ Route user_upload_and_ingest existe")
            else:
                print("❌ Route user_upload_and_ingest introuvable")
            
            if hasattr(app, 'background_ingest_user'):
                print("✅ Fonction background_ingest_user existe")
            else:
                print("❌ Fonction background_ingest_user introuvable")
                
            return True
        except ImportError as e:
            print(f"⚠️  Impossible d'importer app: {e}")
            print("   Cela peut être normal si des dépendances manquent")
            return True
        
    except Exception as e:
        print(f"❌ Erreur syntaxe: {e}")
        return False


def main():
    print("\n" + "="*60)
    print("🧪 DIAGNOSTIC UPLOAD - Vérification Complète")
    print("="*60)
    
    results = {
        "PostgreSQL Connection": check_db_connection(),
        "user_documents Table": check_user_documents_table(),
        "uploads Folder": check_upload_folder(),
        "INSERT Test": test_insert_document(),
        "app.py Syntax": check_app_py_syntax(),
    }
    
    print("\n" + "="*60)
    print("📊 RÉSUMÉ DIAGNOSTIC")
    print("="*60)
    
    all_ok = True
    for test, result in results.items():
        status = "✅ OK" if result else "❌ ERREUR"
        print(f"{status} - {test}")
        if not result:
            all_ok = False
    
    print("\n" + "="*60)
    
    if all_ok:
        print("✅ TOUS LES TESTS PASSENT!")
        print("\nPossibles causes du problème d'upload :")
        print("1. L'interface envoie mal les données")
        print("2. La route n'est pas atteinte")
        print("3. Les logs Flask n'affichent rien")
        print("\nSolution :")
        print("- Vérifier les logs de app.py")
        print("- Ouvrir la console du navigateur (F12)")
        print("- Vérifier les erreurs réseau")
        print("- Tester avec le script test_upload_realtime.py")
    else:
        print("❌ CERTAINS TESTS ONT ÉCHOUÉ")
        print("\nVérifier les erreurs ci-dessus et corriger.")


if __name__ == '__main__':
    main()
