#!/usr/bin/env python3
"""
Script simple pour redémarrer Flask (sans tuer le script lui-même!)
"""
import os
import time
import subprocess

print("=" * 60)
print("🔄 RESTART Flask SERVER")
print("=" * 60)

# Kill existing Flask processes (sauf celui-ci)
print("\n1️⃣  Arrêt des serveurs Flask existants...")
# Use wmic pour tuer seulement les app.py
subprocess.run('wmic process where "commandline like \'%app.py%\'" delete /nointeractive', 
               shell=True, capture_output=True, timeout=5)
time.sleep(2)

# Start Flask in foreground
print("\n2️⃣  Démarrage du serveur Flask...")
print("   URL: http://localhost:5005/api/admin")
print("   Email: admin@inetum.com")
print("=" * 60 + "\n")

os.chdir('unified-agent/ui')
os.system('python app.py')
