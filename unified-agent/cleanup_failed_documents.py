#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script: Nettoyer et relancer traitement documents en erreur
Supprime les documents avec status 'Erreur' pour les re-traiter
"""

import logging
import psycopg2
from pathlib import Path
from datetime import datetime

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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


def list_failed_documents():
    """Liste les documents en erreur"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT id, user_email, filename, file_type, status, error_msg, created_at
            FROM user_documents
            WHERE status = 'Erreur'
            ORDER BY created_at DESC
        """)
        
        failed = cur.fetchall()
        
        if not failed:
            logger.info("✅ Aucun document en erreur")
            return []
        
        logger.info(f"\n📋 Documents en erreur ({len(failed)}):")
        logger.info("=" * 100)
        
        for row in failed:
            doc_id, email, filename, ftype, status, error, created = row
            logger.info(f"  ID #{doc_id}")
            logger.info(f"    Fichier: {filename}")
            logger.info(f"    Type: {ftype}")
            logger.info(f"    Email: {email}")
            logger.info(f"    Erreur: {error}")
            logger.info(f"    Créé: {created}")
            logger.info("-" * 100)
        
        return failed
        
    finally:
        cur.close()
        conn.close()


def clean_failed_document(doc_id: int, also_delete_file: bool = False):
    """Supprime un document en erreur"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Récupérer les infos
        cur.execute("""
            SELECT filename, file_path FROM user_documents WHERE id = %s
        """, (doc_id,))
        
        result = cur.fetchone()
        if not result:
            logger.warning(f"⚠️ Document #{doc_id} introuvable")
            return False
        
        filename, file_path = result
        
        # Soft delete (mettre à jour le status)
        cur.execute("""
            UPDATE user_documents 
            SET status = 'Supprimé', updated_at = NOW()
            WHERE id = %s
        """, (doc_id,))
        
        conn.commit()
        logger.info(f"✅ Document #{doc_id} marqué comme supprimé")
        
        # Optionnellement supprimer le fichier
        if also_delete_file and file_path:
            try:
                Path(file_path).unlink()
                logger.info(f"✅ Fichier supprimé: {file_path}")
            except Exception as e:
                logger.warning(f"⚠️ Impossible de supprimer fichier: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur suppression document #{doc_id}: {e}")
        conn.rollback()
        return False
        
    finally:
        cur.close()
        conn.close()


def clean_all_failed(also_delete_files: bool = False):
    """Nettoie tous les documents en erreur"""
    failed = list_failed_documents()
    
    if not failed:
        return 0
    
    logger.info(f"\n🧹 Nettoyage de {len(failed)} document(s) en erreur...")
    
    success_count = 0
    for doc_id, *_ in failed:
        if clean_failed_document(doc_id, also_delete_files):
            success_count += 1
    
    logger.info(f"\n✅ {success_count}/{len(failed)} document(s) nettoyé(s)")
    return success_count


def get_document_info(doc_id: int):
    """Détails d'un document"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT 
                id, user_email, session_id, filename, file_type, file_size,
                status, error_msg, total_chunks, processing_time, language,
                keywords, extracted_entities, cleaning_stats,
                ingestion_timestamp, created_at, updated_at
            FROM user_documents
            WHERE id = %s
        """, (doc_id,))
        
        result = cur.fetchone()
        if not result:
            logger.error(f"❌ Document #{doc_id} introuvable")
            return None
        
        cols = [
            "id", "user_email", "session_id", "filename", "file_type", "file_size",
            "status", "error_msg", "total_chunks", "processing_time", "language",
            "keywords", "extracted_entities", "cleaning_stats",
            "ingestion_timestamp", "created_at", "updated_at"
        ]
        
        info = dict(zip(cols, result))
        return info
        
    finally:
        cur.close()
        conn.close()


def print_document_info(doc_id: int):
    """Affiche les infos d'un document"""
    info = get_document_info(doc_id)
    
    if not info:
        return
    
    logger.info(f"\n📄 Détails Document #{doc_id}:")
    logger.info("=" * 100)
    
    for key, value in info.items():
        if value is None:
            logger.info(f"  {key}: <NULL>")
        else:
            logger.info(f"  {key}: {value}")
    
    logger.info("=" * 100)


def main():
    """Menu principal"""
    import sys
    
    print("\n" + "=" * 100)
    print("🧹 NETTOYAGE ET RELANCE DOCUMENTS EN ERREUR")
    print("=" * 100 + "\n")
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "list":
            list_failed_documents()
            
        elif command == "clean-all":
            confirm = input("\n⚠️  Supprimer TOUS les documents en erreur? (y/n): ").lower()
            if confirm == 'y':
                clean_all_failed(also_delete_files=False)
            else:
                logger.info("❌ Annulé")
                
        elif command == "clean":
            try:
                doc_id = int(sys.argv[2])
                confirm = input(f"\n⚠️  Supprimer document #{doc_id}? (y/n): ").lower()
                if confirm == 'y':
                    clean_failed_document(doc_id, also_delete_files=False)
                else:
                    logger.info("❌ Annulé")
            except (IndexError, ValueError):
                logger.error("Usage: python cleanup_failed.py clean <doc_id>")
                
        elif command == "info":
            try:
                doc_id = int(sys.argv[2])
                print_document_info(doc_id)
            except (IndexError, ValueError):
                logger.error("Usage: python cleanup_failed.py info <doc_id>")
                
        else:
            print_help()
    else:
        print_help()


def print_help():
    """Affiche l'aide"""
    help_text = """
📖 COMMANDES DISPONIBLES:

  python cleanup_failed.py list
    → Lister tous les documents en erreur

  python cleanup_failed.py info <doc_id>
    → Afficher détails d'un document
    → Ex: python cleanup_failed.py info 52

  python cleanup_failed.py clean <doc_id>
    → Supprimer UN document en erreur
    → Ex: python cleanup_failed.py clean 52

  python cleanup_failed.py clean-all
    → Supprimer TOUS les documents en erreur

🔄 APRÈS NETTOYAGE:

  1. Re-ouvrir l'interface: http://localhost:5005/upload_demo.html
  2. Aller à l'onglet "Upload"
  3. Re-uploader le fichier

📋 EXEMPLE COMPLET:

  # 1. Lister les erreurs
  python cleanup_failed.py list

  # 2. Voir détails de l'erreur
  python cleanup_failed.py info 52

  # 3. Supprimer le document en erreur
  python cleanup_failed.py clean 52

  # 4. Re-uploader le fichier
  # (via interface web)
    """
    print(help_text)


if __name__ == "__main__":
    main()
