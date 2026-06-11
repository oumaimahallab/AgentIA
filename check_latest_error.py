#!/usr/bin/env python3
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        database=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "root")
    )
    
    c = conn.cursor()
    
    # Récupère les derniers documents avec erreur
    c.execute("""
        SELECT id, filename, status, error_msg, created_at 
        FROM documents 
        WHERE status='Erreur' 
        ORDER BY created_at DESC 
        LIMIT 5
    """)
    
    records = c.fetchall()
    
    print("=" * 100)
    print("DOCUMENTS EN ERREUR (5 derniers)")
    print("=" * 100)
    
    for record in records:
        print(f"\nID: {record[0]}")
        print(f"Fichier: {record[1]}")
        print(f"Status: {record[2]}")
        print(f"Créé: {record[4]}")
        print(f"\n🔴 MESSAGE D'ERREUR:")
        print(f"{record[3]}")
        print("-" * 100)
    
    conn.close()
    
except Exception as e:
    print(f"❌ Erreur: {e}")
