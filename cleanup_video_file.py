#!/usr/bin/env python3
import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

video_filename = "[Accompagnement DEV et Support CTIME]-20260512_100450-Enregistrement de la réunion.mp4"

print("="*80)
print("NETTOYAGE DE LA VIDÉO")
print("="*80)

# Supprime de la BD
try:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        database=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "root")
    )
    
    c = conn.cursor()
    
    # Compte combien de fois le fichier apparaît
    c.execute("SELECT COUNT(*) FROM documents WHERE filename=%s", (video_filename,))
    count = c.fetchone()[0]
    
    print(f"\n✓ Fichier trouvé {count} fois dans la BD")
    
    # Supprime tous les enregistrements
    c.execute("DELETE FROM documents WHERE filename=%s", (video_filename,))
    conn.commit()
    
    print(f"✓ Supprimé de la BD\n")
    conn.close()
    
except Exception as e:
    print(f"❌ Erreur BD: {e}")

# Supprime du dossier uploads
video_path = Path("unified-agent/ui/uploads") / video_filename

if video_path.exists():
    try:
        video_path.unlink()
        print(f"✓ Fichier supprimé des uploads")
    except Exception as e:
        print(f"❌ Erreur suppression fichier: {e}")
else:
    print(f"⚠️  Fichier pas trouvé dans uploads")

print(f"\n{'='*80}")
print(f"✅ Nettoyage terminé!")
print(f"{'='*80}")
print(f"\nVous pouvez maintenant re-uploader la vidéo via l'interface admin ✓")
