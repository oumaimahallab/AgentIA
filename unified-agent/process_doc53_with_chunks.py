#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Relance du traitement document #53 avec sauvegarde des chunks
"""

import os
import sys
import logging
import psycopg2
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Configuration
sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from ingestion.unified_ingester import UnifiedIngester
from ingestion.chunk_manager import ChunkManager


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
    
    raise FileNotFoundError(f"Fichier non trouvé: {filename}")


def process_document_53_with_storage():
    """Traite le document #53 et sauvegarde les chunks"""
    
    doc_id = 53
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        print("\n" + "="*100)
        print("📄 RELANCE DOCUMENT #53 AVEC STOCKAGE DES CHUNKS")
        print("="*100 + "\n")
        
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
        
        logger.info(f"📄 Document trouvé: {filename}")
        logger.info(f"   Status actuel: {status}")
        
        # Chercher le fichier
        try:
            file_path = find_file_path(filename)
            logger.info(f"✅ Fichier trouvé: {file_path}")
            logger.info(f"   Taille: {file_path.stat().st_size / 1024 / 1024:.2f} MB")
        except FileNotFoundError as e:
            logger.error(f"❌ {e}")
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
        
        # Lancer l'ingestion AVEC sauvegarde des chunks
        logger.info(f"\n🔄 Traitement avec stockage BD...")
        logger.info(f"   Type: Vidéo (Whisper)")
        logger.info(f"   Modèle: small")
        
        try:
            # Créer l'ingester SANS sauvegarde auto (on va le faire manuellement)
            ingester = UnifiedIngester(
                language='fr',
                clean_text=True,
                extract_entities=True,
                save_chunks_to_db=False  # Faire manuellement pour plus de contrôle
            )
            
            # Traiter le fichier
            result = ingester.ingest(
                file_path=file_path,
                user_email='admin@inetum.com',
                session_id='admin_session'
            )
            
            if not result:
                raise Exception("Erreur lors de l'ingestion")
            
            chunks, metadata = result
            
            logger.info(f"✅ Traitement complété!")
            logger.info(f"   Chunks générés: {len(chunks)}")
            logger.info(f"   Texte total: {sum(len(c) for c in chunks)} caractères")
            logger.info(f"   Temps: {metadata.processing_time:.2f}s")
            logger.info(f"   Langue: {metadata.language}")
            
            # Sauvegarder les chunks en BD
            logger.info(f"\n💾 Sauvegarde des chunks...")
            chunk_manager = ChunkManager()
            saved_count = chunk_manager.save_chunks(doc_id, chunks, overwrite=True)
            logger.info(f"✅ {saved_count} chunks sauvegardés en BD")
            
            # Vérifier les stats
            stats = chunk_manager.get_statistics(doc_id)
            logger.info(f"\n📊 Statistiques sauvegardées:")
            logger.info(f"   - Total chunks: {stats['chunk_count']}")
            logger.info(f"   - Total caractères: {stats['total_characters']}")
            logger.info(f"   - Taille moyenne chunk: {stats['avg_chunk_size']} chars")
            
            # Mettre à jour la BD
            conn = get_db_connection()
            cur = conn.cursor()
            
            cur.execute("""
                UPDATE documents
                SET status = 'Ingéré', error_msg = NULL
                WHERE id = %s
            """, (doc_id,))
            conn.commit()
            
            logger.info(f"✅ Status mis à jour à 'Ingéré'")
            logger.info(f"\n🎉 Document #{doc_id} re-traité avec stockage réussi!")
            
            # Afficher les endpoints disponibles
            logger.info(f"\n🔗 API ENDPOINTS DISPONIBLES:")
            logger.info(f"   GET /api/documents/{doc_id}/chunks")
            logger.info(f"   GET /api/documents/{doc_id}/content")
            logger.info(f"   GET /api/documents/{doc_id}/stats")
            
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
        try:
            cur.close()
            conn.close()
        except:
            pass


if __name__ == "__main__":
    success = process_document_53_with_storage()
    
    if success:
        logger.info("\n✅ Succès! Le document #53 est maintenant sauvegardé avec ses chunks.")
        logger.info("\n📋 Prochaines étapes:")
        logger.info("  1. Redémarrer l'API Flask")
        logger.info("  2. Tester les endpoints: curl http://localhost:5005/api/documents/53/content")
        logger.info("  3. Consulter l'interface web: http://localhost:5005/upload_demo.html")
    else:
        logger.error("\n❌ Échec. Consultez les logs ci-dessus.")
        sys.exit(1)
