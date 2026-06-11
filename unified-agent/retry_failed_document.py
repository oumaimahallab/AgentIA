#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script: Relancer traitement document en erreur
Re-traite un document pour lequel le traitement a échoué
"""

import sys
import logging
import psycopg2
from pathlib import Path
from datetime import datetime
import os

# Ajouter le chemin du projet
sys.path.insert(0, str(Path(__file__).parent))

from ingestion.unified_ingester import UnifiedIngester

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def update_retry_progress(cur, doc_id: int, step: str, percentage: int, status: str = None):
    """Met à jour la progression dans documents en tolérant les schémas incomplets."""
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'documents'
          AND column_name IN ('status', 'progress_step', 'progress_percentage')
    """)
    existing = {r[0] for r in cur.fetchall()}

    sets = []
    params = []

    if status is not None and 'status' in existing:
        sets.append("status = %s")
        params.append(status)
    if 'progress_step' in existing:
        sets.append("progress_step = %s")
        params.append(step)
    if 'progress_percentage' in existing:
        sets.append("progress_percentage = %s")
        params.append(percentage)

    if sets:
        sql = f"UPDATE documents SET {', '.join(sets)} WHERE id = %s"
        params.append(doc_id)
        cur.execute(sql, tuple(params))


def get_db_connection():
    """Connexion PostgreSQL"""
    try:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
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


def retry_document(doc_id: int):
    """Relance le traitement d'un document"""
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Récupérer le document (certaines bases n'ont pas la colonne file_path)
        cur.execute("""
            SELECT id, filename, status
            FROM documents
            WHERE id = %s
        """, (doc_id,))
        result = cur.fetchone()
        if not result:
            logger.error(f"❌ Document #{doc_id} introuvable")
            return False
        
        doc_id, filename, status = result
        # Construire le chemin de fichier à partir du dossier uploads dans ui
        file_path = Path(__file__).parent.joinpath('ui', 'uploads', filename).resolve()
        user_email = None
        session_id = None
        
        logger.info(f"\n📄 Document trouvé: {filename}")
        logger.info(f"   Status actuel: {status}")
        logger.info(f"   Chemin: {file_path}")
        
        # Vérifier que le fichier existe
        if not Path(file_path).exists():
            logger.error(f"❌ Fichier introuvable: {file_path}")
            return False
        
        logger.info(f"✅ Fichier trouvé ({Path(file_path).stat().st_size} bytes)")
        
        # Réinitialiser le status dans la table documents
        cur.execute("""
            UPDATE documents
            SET status = 'En attente', error_msg = NULL
            WHERE id = %s
        """, (doc_id,))
        try:
            update_retry_progress(cur, doc_id, "Validation fichier", 5, status="En cours")
        except Exception:
            pass
        conn.commit()
        logger.info(f"✅ Status réinitialisé à 'En attente' dans documents")
        
        cur.close()
        conn.close()
        
        # Lancer l'ingestion
        logger.info(f"\n🔄 Relance du traitement...")
        
        try:
            # Configuration par défaut
            ingester = UnifiedIngester(
                language='fr',
                clean_text=True,
                extract_entities=True,
            )

            # Etape longue pour les médias: extraction/transcription
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                update_retry_progress(cur, doc_id, "Extraction du texte", 35, status="En cours")
                conn.commit()
            finally:
                cur.close()
                conn.close()
            
            # Traiter le fichier
            chunks, metadata = ingester.ingest(
                file_path=Path(file_path),
                user_email=user_email,
                session_id=session_id
            )
            
            logger.info(f"✅ Traitement complété!")
            logger.info(f"   Chunks générés: {len(chunks)}")
            logger.info(f"   Temps: {metadata.processing_time:.2f}s")
            
            # Sauvegarder les chunks en DB si possible
            try:
                from ingestion.chunk_manager import ChunkManager
                cm = ChunkManager()
                cm.save_chunks(doc_id, chunks)
                logger.info(f"✓ {len(chunks)} chunks sauvegardés en BD pour documents id={doc_id}")
            except Exception as e:
                logger.warning(f"⚠ Impossible de sauvegarder les chunks en BD: {e}")

            # Mettre à jour la BD — construire dynamiquement la requête en
            # fonction des colonnes réellement présentes pour éviter les erreurs
            import json

            conn = get_db_connection()
            cur = conn.cursor()

            try:
                update_retry_progress(cur, doc_id, "Finalisation et vérification", 95, status="En cours")
                conn.commit()
            except Exception:
                conn.rollback()

            keywords_json = json.dumps(metadata.keywords) if metadata.keywords else None
            entities_json = json.dumps(metadata.extracted_entities) if metadata.extracted_entities else None
            stats_json = json.dumps(metadata.cleaning_stats) if metadata.cleaning_stats else None

            # Colonnes candidates et leurs valeurs
            candidate_cols = [
                ('status', 'Ingéré'),
                ('total_chunks', len(chunks)),
                ('processing_time', metadata.processing_time),
                ('language', metadata.language),
                ('keywords', keywords_json),
                ('extracted_entities', entities_json),
                ('cleaning_stats', stats_json),
                ('ingestion_timestamp', 'NOW()'),
                ('error_msg', None),
            ]

            # Lire les colonnes existantes
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'documents'
            """)
            existing = {r[0] for r in cur.fetchall()}

            sets = []
            params = []
            for col, val in candidate_cols:
                if col in existing:
                    if val == 'NOW()':
                        sets.append(f"{col} = NOW()")
                    else:
                        sets.append(f"{col} = %s")
                        params.append(val)

            if not sets:
                logger.warning("Aucune colonne mise à jour trouvée dans documents, saut de l'UPDATE")
            else:
                sql = f"UPDATE documents SET {', '.join(sets)} WHERE id = %s"
                params.append(doc_id)
                cur.execute(sql, tuple(params))
                try:
                    update_retry_progress(cur, doc_id, "Ingéré avec succès", 100, status="Ingéré")
                except Exception:
                    pass
                conn.commit()
                logger.info("✅ Base de données mise à jour (colonnes présentes: %s)" % ",".join(sorted(existing & {c for c, _ in candidate_cols})))

            logger.info(f"\n🎉 Document #{doc_id} re-traité avec succès!")

            cur.close()
            conn.close()

            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur pendant le traitement: {e}", exc_info=True)
            
            # Mettre à jour l'erreur dans la BD (tolérant aux colonnes manquantes)
            conn = get_db_connection()
            cur = conn.cursor()

            # Vérifier présence des colonnes
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'documents' AND column_name IN ('status', 'error_msg')
            """)
            existing = {r[0] for r in cur.fetchall()}

            sets = []
            params = []
            if 'status' in existing:
                sets.append("status = 'Erreur'")
            if 'error_msg' in existing:
                sets.append("error_msg = %s")
                params.append(str(e))

            if sets:
                sql = f"UPDATE documents SET {', '.join(sets)} WHERE id = %s"
                params.append(doc_id)
                cur.execute(sql, tuple(params))
                conn.commit()

            cur.close()
            conn.close()
            
            return False
    
    except Exception as e:
        logger.error(f"❌ Erreur: {e}", exc_info=True)
        return False


def main():
    """Menu principal"""
    
    print("\n" + "=" * 100)
    print("🔄 RELANCE TRAITEMENT DOCUMENT EN ERREUR")
    print("=" * 100 + "\n")
    
    if len(sys.argv) < 2:
        print("Usage: python retry_failed_document.py <doc_id>")
        print("\nExemple:")
        print("  python retry_failed_document.py 52")
        print("\nPour lister les documents en erreur:")
        print("  python cleanup_failed_documents.py list")
        return
    
    try:
        doc_id = int(sys.argv[1])
        success = retry_document(doc_id)
        
        if success:
            logger.info("\n✅ Succès! Le document a été re-traité.")
        else:
            logger.error("\n❌ Échec. Consultez les logs ci-dessus.")
            sys.exit(1)
            
    except ValueError:
        logger.error(f"❌ ID invalide: {sys.argv[1]}")
        logger.error("Usage: python retry_failed_document.py <doc_id>")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Erreur: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
