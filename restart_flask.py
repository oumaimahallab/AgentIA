#!/usr/bin/env python3
"""
Script pour redémarrer le serveur Flask avec la nouvelle configuration
"""
import os
import time
import subprocess
import psycopg2
from dotenv import load_dotenv

load_dotenv('unified-agent/.env')

print("=" * 60)
print("🔄 RESTART Flask SERVER")
print("=" * 60)

# Nettoyer document #50
print("\n1️⃣  Nettoyage du document #50...")
DB_NAME = os.getenv('DB_NAME', 'chronobrain')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')

try:
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )
    c = conn.cursor()
    c.execute("DELETE FROM documents WHERE id=50")
    conn.commit()
    print("   ✅ Document #50 supprimé")
    conn.close()
except Exception as e:
    print(f"   ⚠️  Erreur: {e}")

# Kill any existing Flask processes
print("\n2️⃣  Arrêt des serveurs Flask existants...")
os.system("taskkill /F /IM python.exe /FI \"WINDOWTITLE eq *app.py*\" >nul 2>&1")
time.sleep(2)

# Start new Flask server
print("\n3️⃣  Démarrage du serveur Flask...")
print("   Commande: python unified-agent/ui/app.py")
print("   URL: http://localhost:5005/api/admin")
print("   " + "=" * 50)

os.chdir('unified-agent/ui')
subprocess.Popen(['python', 'app.py'])

print("\n✅ Serveur lancé!")
print("Attendez 3 secondes puis ouvrez: http://localhost:5005/api/admin")
