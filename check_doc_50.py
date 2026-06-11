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
    
    # Récupère le document #50 avec tous les détails
    c.execute("""
        SELECT id, filename, status, error_msg, created_at 
        FROM documents 
        WHERE id=50
    """)
    
    record = c.fetchone()
    
    if record:
        print("="*100)
        print(f"DOCUMENT #{record[0]}")
        print("="*100)
        print(f"\nFilename: {record[1]}")
        print(f"Status: {record[2]}")
        print(f"Created: {record[4]}")
        print(f"\n🔴 ERROR MESSAGE:\n")
        print(record[3])
        print("\n" + "="*100)
    else:
        print("Document #50 not found")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
