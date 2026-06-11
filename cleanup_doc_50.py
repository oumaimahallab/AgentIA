#!/usr/bin/env python3
"""Nettoyer le document #50 de la base de données"""
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv('unified-agent/.env')

DB_NAME = os.getenv('DB_NAME', 'chronobrain')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')

conn = psycopg2.connect(
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT
)
c = conn.cursor()

# Delete document 50
c.execute("DELETE FROM documents WHERE id=50")
conn.commit()

# Show current documents
c.execute("SELECT id, filename, status FROM documents ORDER BY id DESC LIMIT 5")
docs = c.fetchall()

print("✅ Document #50 supprimé")
print("\nDerniers documents:")
for doc_id, filename, status in docs:
    print(f"  #{doc_id}: {filename[:50]}... | Status: {status}")

conn.close()
