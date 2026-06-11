#!/usr/bin/env python3
import os
import psycopg2
from dotenv import load_dotenv

# Charge les variables d'env
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
    
    # Supprime l'enregistrement avec erreur (doc #48)
    c.execute("SELECT id, filename, status FROM documents WHERE id=48")
    record = c.fetchone()
    
    if record:
        print(f"Enregistrement actuel #48: {record[1]} ({record[2]})")
        
        c.execute("DELETE FROM documents WHERE id=48")
        conn.commit()
        
        print(f"✓ Enregistrement #48 supprimé\n")
    else:
        print("Enregistrement #48 pas trouvé\n")
    
    # Affiche le nombre total de documents
    c.execute("SELECT COUNT(*) FROM documents")
    total = c.fetchone()[0]
    print(f"Total de documents: {total}")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Erreur: {e}")
