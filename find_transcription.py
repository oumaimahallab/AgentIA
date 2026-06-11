#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, r'c:\Users\maup10458\Desktop\AG\unified-agent\ui')
os.chdir(r'c:\Users\maup10458\Desktop\AG\unified-agent\ui')

from app import get_db_connection
import psycopg2

print("🔍 Cherchant les transcriptions en base de données...\n")

conn = get_db_connection()
if not conn:
    print("❌ Connexion BD échouée")
    sys.exit(1)

try:
    c = conn.cursor()
    
    # 1. Vérifier table documents
    print("=" * 70)
    print("📋 TABLE: documents (Admin uploads)")
    print("=" * 70)
    c.execute("""
        SELECT id, filename, status, created_at, progress_step, progress_percentage
        FROM documents 
        ORDER BY created_at DESC 
        LIMIT 10
    """)
    docs = c.fetchall()
    if docs:
        for row in docs:
            print(f"ID: {row[0]} | Fichier: {row[1]}")
            print(f"  Status: {row[2]} | Créé: {row[3]}")
            print(f"  Progression: {row[4]} ({row[5]}%)")
            print()
    else:
        print("❌ Aucun document trouvé\n")
    
    # 2. Vérifier document_chunks (si table existe)
    print("=" * 70)
    print("📦 TABLE: document_chunks (Chunks stockés)")
    print("=" * 70)
    try:
        c.execute("""
            SELECT document_id, COUNT(*) as nb_chunks
            FROM document_chunks
            GROUP BY document_id
            ORDER BY document_id DESC
            LIMIT 10
        """)
        chunks = c.fetchall()
        if chunks:
            for doc_id, nb in chunks:
                print(f"Document ID {doc_id}: {nb} chunks")
                # Afficher le contenu du premier chunk
                c.execute("SELECT chunk_content FROM document_chunks WHERE document_id=%s LIMIT 1", (doc_id,))
                chunk = c.fetchone()
                if chunk:
                    content = chunk[0][:150] + "..." if len(chunk[0]) > 150 else chunk[0]
                    print(f"  Contenu: {content}\n")
        else:
            print("❌ Aucun chunk trouvé\n")
    except psycopg2.ProgrammingError:
        print("⚠️  Table document_chunks n'existe pas\n")
    
    # 3. Vérifier user_documents (uploads utilisateurs)
    print("=" * 70)
    print("👤 TABLE: user_documents (Uploads utilisateurs)")
    print("=" * 70)
    try:
        c.execute("""
            SELECT id, filename, status, created_at, user_email
            FROM user_documents
            ORDER BY created_at DESC
            LIMIT 10
        """)
        user_docs = c.fetchall()
        if user_docs:
            for row in user_docs:
                print(f"ID: {row[0]} | Fichier: {row[1]}")
                print(f"  Status: {row[2]} | User: {row[4]} | Créé: {row[3]}")
                print()
        else:
            print("❌ Aucun document utilisateur trouvé\n")
    except psycopg2.ProgrammingError:
        print("⚠️  Table user_documents n'existe pas\n")
    
    # 4. Chercher fichier vidéo récent
    print("=" * 70)
    print("🎥 RECHERCHE: Documents vidéo récents")
    print("=" * 70)
    c.execute("""
        SELECT id, filename, status, created_at
        FROM documents
        WHERE filename ILIKE '%.mp4%' 
           OR filename ILIKE '%.avi%'
           OR filename ILIKE '%.mov%'
        ORDER BY created_at DESC
        LIMIT 5
    """)
    videos = c.fetchall()
    if videos:
        for row in videos:
            print(f"✓ Vidéo trouvée:")
            print(f"  ID: {row[0]} | Nom: {row[1]}")
            print(f"  Status: {row[2]} | Créé: {row[3]}")
            print()
            
            # Chercher ses chunks
            c.execute("SELECT COUNT(*) FROM document_chunks WHERE document_id=%s", (row[0],))
            count = c.fetchone()[0]
            if count > 0:
                print(f"  ✓ {count} chunks trouvés en BD")
                c.execute("SELECT chunk_content FROM document_chunks WHERE document_id=%s LIMIT 1", (row[0],))
                chunk = c.fetchone()
                if chunk:
                    content = chunk[0][:200] + "..." if len(chunk[0]) > 200 else chunk[0]
                    print(f"  Contenu (premiers 200 chars):\n    {content}\n")
            else:
                print(f"  ⚠️  Aucun chunk trouvé en BD (la transcription est peut-être seulement dans les indices FAISS/BM25)\n")
    else:
        print("❌ Aucune vidéo trouvée\n")
    
except Exception as e:
    print(f"❌ Erreur: {e}")
finally:
    if conn:
        conn.close()

print("=" * 70)
print("💡 RÉSUMÉ")
print("=" * 70)
msg = """
Les transcriptions peuvent être stockées à 3 endroits:

1. TABLE document_chunks
   -> Stockage BD explicite si ChunkManager activé
   -> Chercher par document_id

2. INDEX FAISS
   -> unified-agent/data/indices/faiss/index.faiss
   -> Index vectoriel (par vecteurs d'embedding)

3. INDEX BM25
   -> unified-agent/data/indices/bm25/bm25_index.pkl
   -> Index par mots-clés

Si la vidéo a status='Ingéré' mais pas de chunks en BD,
la transcription est SEULEMENT dans les indices FAISS/BM25
(ce qui est normal et plus efficace pour la recherche).
"""
print(msg)
