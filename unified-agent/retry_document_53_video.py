#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script: Relancer traitement document #53 (vidéo MP4 en erreur)
"""

import sys
import logging
import psycopg2
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Ajouter le chemin du projet
sys.path.insert(0, str(Path(__file__).parent))

from ingestion.unified_ingester import UnifiedIngester
from ingestion.chunk_manager import ChunkManager

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()


def get_db_connection():
    """Connexion PostgreSQL"""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'postgres'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'root'),
            client_encoding='utf8'
        )
        return conn
    except Exception as e:
        logger.error(f"❌ Erreur connexion BD: {e}")
        raise


def find_file_path(filename: str) -> Path:
    """Cherche le fichier sur le disque"""
    
    # Chemins possibles d'upload
    search_paths = [
        Path(__file__).parent / "uploads" / filename,
        Path(__file__).parent / "data" / "uploads" / filename,
        Path(__file__).parent / "data" / "documents" / filename,
        Path.home() / "Downloads" / filename,
        Path(__file__).parent / filename,
    ]
    
    for path in search_paths:
        if path.exists():
            return path
    
    raise FileNotFoundError(f"Fichier not found: {filename}\nSearched in: {search_paths}")


def retry_document_53():
    """Relance le traitement du document #53"""
    
    doc_id = 53
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Récupérer le document
        cur.execute("""
            SELECT id, filename, status, error_msg
            FROM documents
            WHERE id = %s
        """, (doc_id,))
        
        result = cur.fetchone()
        if not result:
            logger.error(f"❌ Document #{doc_id} introuvable")
            return False
        
        doc_id, filename, status, error_msg = result
        
        logger.info(f"\n📄 Document trouvé: {filename}")
        logger.info(f"   Status actuel: {status}")
        logger.info(f"   Erreur: {error_msg}")
        
        # Chercher le fichier
        try:
            file_path = find_file_path(filename)
            logger.info(f"✅ Fichier trouvé: {file_path}")
            logger.info(f"   Taille: {file_path.stat().st_size / 1024 / 1024:.2f} MB")
        except FileNotFoundError as e:
            logger.error(f"❌ {e}")
            logger.info("   Vérifiez que le fichier a bien été uploadé")
            cur.close()
            conn.close()
            return False
        
        # Réinitialiser le status
        cur.execute("""
            UPDATE documents
            SET status = 'En attente', error_msg = NULL
            WHERE id = %s
        """, (doc_id,))
        conn.commit()
        logger.info(f"✅ Status réinitialisé à 'En attente'")
        
        cur.close()
        conn.close()
        
        # Lancer l'ingestion
        logger.info(f"\n🔄 Relance du traitement...")
        logger.info(f"   Type: Vidéo (Whisper)")
        logger.info(f"   Modèle: small")
        
        try:
            ingester = UnifiedIngester(
                language='fr',
                clean_text=True,
                extract_entities=True,
            )
            
            # Traiter le fichier
            chunks, metadata = ingester.ingest(
                file_path=file_path,
                user_email='admin@inetum.com',
                session_id='admin_session'
            )
            
            logger.info(f"✅ Traitement complété!")
            logger.info(f"   Chunks générés: {len(chunks)}")
            logger.info(f"   Temps: {metadata.processing_time:.2f}s")
            logger.info(f"   Langue: {metadata.language}")
            
            # Sauvegarder les chunks en BD
            chunk_manager = ChunkManager()
            saved_count = chunk_manager.save_chunks(doc_id, chunks, overwrite=True)
            logger.info(f"✅ {saved_count} chunks sauvegardés en BD")
            
            # Mettre à jour la BD
            import json
            
            conn = get_db_connection()
            cur = conn.cursor()
            
            keywords_json = json.dumps(metadata.keywords) if metadata.keywords else None
            entities_json = json.dumps(metadata.extracted_entities) if metadata.extracted_entities else None
            stats_json = json.dumps(metadata.cleaning_stats) if metadata.cleaning_stats else None
            
            cur.execute("""
                UPDATE documents
                SET status = 'Ingéré', error_msg = NULL
                WHERE id = %s
            """, (doc_id,))
            conn.commit()
            
            logger.info(f"✅ Status mis à jour à 'Ingéré'")
            logger.info(f"\n🎉 Document #{doc_id} re-traité avec succès!")
            
            cur.close()
            conn.close()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur pendant le traitement: {e}", exc_info=True)
            
            # Mettre à jour l'erreur dans la BD
            conn = get_db_connection()
            cur = conn.cursor()
            
            cur.execute("""
                UPDATE documents
                SET status = 'Erreur', error_msg = %s
                WHERE id = %s
            """, (str(e), doc_id))
            conn.commit()
            
            cur.close()
            conn.close()
            
            return False
    
    except Exception as e:
        logger.error(f"❌ Erreur: {e}", exc_info=True)
        return False
    finally:
        cur.close()
        conn.close()


def main():
    """Menu principal"""
    
    print("\n" + "="*100)
    print("🎬 RELANCE TRAITEMENT VIDÉO MP4 - DOCUMENT #53")
    print("="*100 + "\n")
    
    success = retry_document_53()
    
    if success:
        logger.info("\n✅ Succès! Le document a été re-traité.")
        logger.info("\n📋 Prochaines étapes:")
        logger.info("  1. Vérifier l'interface web: http://localhost:5005/upload_demo.html")
        logger.info("  2. Aller à l'onglet 'Documents'")
        logger.info("  3. Voir le document #53 avec status 'Ingéré'")
    else:
        logger.error("\n❌ Échec. Consultez les logs ci-dessus.")
        sys.exit(1)


if __name__ == "__main__":
    main()
