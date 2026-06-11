#!/usr/bin/env python3
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', '5432'),
    database=os.getenv('DB_NAME', 'postgres'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD', 'root'),
)

c = conn.cursor()

# Chercher la vidéo MP4
c.execute("""
    SELECT id, filename, status, error_msg, created_at 
    FROM documents 
    WHERE filename LIKE '%mp4%' OR filename LIKE '%Accompagnement%'
    ORDER BY created_at DESC
""")

results = c.fetchall()

print("\n" + "="*100)
print("DOCUMENTS VIDEO/AUDIO TROUVÉS")
print("="*100)

if not results:
    print("Aucun document MP4/Accompagnement trouvé")
else:
    for row in results:
        doc_id, filename, status, error_msg, created_at = row
        print(f"\nID: {doc_id}")
        print(f"Fichier: {filename}")
        print(f"Statut: {status}")
        print(f"Créé: {created_at}")
        if error_msg:
            print(f"ERROR MESSAGE:\n{error_msg}")
        print("-"*100)

conn.close()
