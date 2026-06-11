#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reprocess document #53 with chunk storage - simplified version
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# Change to correct directory
os.chdir(Path(__file__).parent)

# Add to path
sys.path.insert(0, str(Path(__file__).parent))

import psycopg2
from dotenv import load_dotenv
from ingestion.unified_ingester import UnifiedIngester
from ingestion.chunk_manager import ChunkManager

load_dotenv()

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'postgres'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'root'),
        client_encoding='utf8'
    )

def find_file_path(filename):
    """Find file in common locations"""
    search_paths = [
        Path.home() / 'Downloads',
        Path('uploads'),
        Path('data/documents'),
        Path('data/uploads'),
        Path(__file__).parent,
    ]
    
    for base_path in search_paths:
        file_path = base_path / filename
        if file_path.exists():
            return file_path
    return None

def main():
    print("\n" + "="*100)
    print("📄 RELANCE DOCUMENT #53 AVEC STOCKAGE DES CHUNKS")
    print("="*100 + "\n")
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get document info
        cur.execute('SELECT filename, status FROM documents WHERE id = 53')
        result = cur.fetchone()
        
        if not result:
            print("❌ Document #53 not found")
            return
        
        filename, status = result
        print(f"📄 Document trouvé: {filename}")
        print(f"   Status actuel: {status}")
        
        # Find file
        file_path = find_file_path(filename)
        if not file_path:
            print(f"❌ File not found: {filename}")
            return
        
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        print(f"✅ Fichier trouvé: {file_path}")
        print(f"   Taille: {file_size_mb:.2f} MB")
        
        # Reset status
        cur.execute('UPDATE documents SET status = %s, error_msg = NULL WHERE id = 53',
                   ('En attente',))
        conn.commit()
        print(f"✅ Status réinitialisé à 'En attente'")
        
        cur.close()
        conn.close()
        
        print("\n🔄 Traitement avec stockage BD...")
        
        # Process with unified ingester
        ingester = UnifiedIngester(
            language='fr',
            clean_text=True,
            extract_entities=True,
            save_chunks_to_db=True  # Save chunks to database
        )
        
        print(f"   Type: Vidéo (Whisper)")
        print(f"   Modèle: small")
        print(f"\n⏳ Transcription en cours... (cela peut prendre 45-60 minutes)")
        print(f"   Fichier: {file_path.name}")
        
        # Ingest
        start_time = time.time()
        chunks, metadata = ingester.ingest(file_path)
        elapsed = time.time() - start_time
        
        print(f"\n✅ Transcription réussie!")
        print(f"   Durée: {elapsed/60:.1f} minutes")
        print(f"   Chunks générés: {len(chunks)}")
        print(f"   Total caractères: {sum(len(c) for c in chunks)}")
        
        # Save to DB
        print(f"\n💾 Sauvegarde en base de données...")
        chunk_manager = ChunkManager()
        saved_count = chunk_manager.save_chunks(53, chunks, overwrite=True)
        print(f"✅ {saved_count} chunks sauvegardés")
        
        # Get stats
        stats = chunk_manager.get_statistics(53)
        print(f"\n📊 Statistiques:")
        print(f"   Chunks: {stats['chunk_count']}")
        print(f"   Total chars: {stats['total_characters']}")
        print(f"   Avg chunk: {stats['avg_chunk_size']:.0f} chars")
        print(f"   Created: {stats['created_at']}")
        
        # Update status
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('UPDATE documents SET status = %s WHERE id = 53', ('Ingéré',))
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"\n✅ Status mis à jour: Ingéré")
        print(f"\n🎉 Document #53 re-traité avec stockage réussi!")
        print(f"\n📍 Test API:")
        print(f"   GET /api/documents/53/content")
        print(f"   GET /api/documents/53/stats")
        
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
