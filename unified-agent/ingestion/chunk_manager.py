#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module pour sauvegarder et gérer les chunks de documents
"""

import os
import hashlib
import logging
import psycopg2
from pathlib import Path
from typing import List, Dict, Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()


class ChunkManager:
    """Gère la sauvegarde et récupération des chunks"""
    
    def __init__(self):
        self.conn_params = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'postgres'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'root'),
            'client_encoding': 'utf8'
        }
    
    def get_connection(self):
        """Retourne une connexion PostgreSQL"""
        return psycopg2.connect(**self.conn_params)
    
    def save_chunks(self, document_id: int, chunks: List[str], 
                   overwrite: bool = True) -> int:
        """
        Sauvegarde les chunks d'un document en BD
        
        Args:
            document_id: ID du document
            chunks: Liste des chunks de texte
            overwrite: Si True, supprime les chunks existants
            
        Returns:
            Nombre de chunks sauvegardés
        """
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            # Supprimer les chunks existants si demandé
            if overwrite:
                cur.execute('DELETE FROM document_chunks WHERE document_id = %s', 
                           (document_id,))
                logger.info(f"✓ Chunks existants supprimés pour doc {document_id}")
            
            # Insérer les nouveaux chunks
            saved_count = 0
            for chunk_number, text in enumerate(chunks, start=1):
                text_hash = hashlib.sha256(text.encode()).hexdigest()
                
                cur.execute("""
                    INSERT INTO document_chunks 
                    (document_id, chunk_number, text, text_length, hash)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (document_id, chunk_number) 
                    DO UPDATE SET text = %s, text_length = %s, hash = %s
                """, (document_id, chunk_number, text, len(text), text_hash,
                      text, len(text), text_hash))
                saved_count += 1
            
            conn.commit()
            logger.info(f"✓ {saved_count} chunks sauvegardés pour doc {document_id}")
            return saved_count
            
        except Exception as e:
            logger.error(f"✗ Erreur lors de la sauvegarde des chunks: {e}")
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()
    
    def get_chunks(self, document_id: int) -> List[Dict[str, any]]:
        """Récupère tous les chunks d'un document"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                SELECT id, chunk_number, text, text_length, hash, created_at
                FROM document_chunks
                WHERE document_id = %s
                ORDER BY chunk_number
            """, (document_id,))
            
            chunks = []
            for row in cur.fetchall():
                chunks.append({
                    'id': row[0],
                    'chunk_number': row[1],
                    'text': row[2],
                    'text_length': row[3],
                    'hash': row[4],
                    'created_at': row[5]
                })
            
            return chunks
            
        finally:
            cur.close()
            conn.close()
    
    def get_full_text(self, document_id: int) -> str:
        """Récupère le texte complet d'un document à partir des chunks"""
        chunks = self.get_chunks(document_id)
        return " ".join([c['text'] for c in chunks])
    
    def delete_chunks(self, document_id: int) -> int:
        """Supprime tous les chunks d'un document"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('DELETE FROM document_chunks WHERE document_id = %s', 
                       (document_id,))
            conn.commit()
            deleted = cur.rowcount
            logger.info(f"✓ {deleted} chunks supprimés pour doc {document_id}")
            return deleted
        finally:
            cur.close()
            conn.close()
    
    def get_statistics(self, document_id: int) -> Dict[str, any]:
        """Retourne des statistiques sur les chunks d'un document"""
        chunks = self.get_chunks(document_id)
        
        total_text = sum(c['text_length'] for c in chunks)
        
        return {
            'document_id': document_id,
            'chunk_count': len(chunks),
            'total_characters': total_text,
            'avg_chunk_size': total_text // len(chunks) if chunks else 0,
            'created_at': chunks[0]['created_at'] if chunks else None,
            'last_chunk_date': chunks[-1]['created_at'] if chunks else None
        }

    def update_chunk(self, chunk_id: int, new_text: str) -> bool:
        """Met à jour le texte d'un chunk spécifique dans la base PostgreSQL"""
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            text_hash = hashlib.sha256(new_text.encode()).hexdigest()
            cur.execute("""
                UPDATE document_chunks 
                SET text = %s, text_length = %s, hash = %s, updated_at = NOW()
                WHERE id = %s
            """, (new_text, len(new_text), text_hash, chunk_id))
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating chunk {chunk_id}: {e}")
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

