#!/usr/bin/env python3
"""
Script de démarrage du serveur Flask d'administration
Inclut la fonctionnalité upload & ingestion de documents
"""

import os
import sys
import subprocess

def start_server():
    # Activer la venv
    venv_path = os.path.join(os.path.dirname(__file__), '.venv')
    ui_path = os.path.join(os.path.dirname(__file__), 'unified-agent', 'ui')
    
    print("[*] Démarrage du serveur d'administration ChronoBrain")
    print(f"[*] Répertoire UI: {ui_path}")
    print(f"[*] Venv: {venv_path}")
    
    # Changer le répertoire de travail
    os.chdir(ui_path)
    
    # Lancer Flask
    cmd = [
        sys.executable,
        'app.py'
    ]
    
    print(f"\n[*] Commande: {' '.join(cmd)}")
    print("[*] Le serveur devrait être accessible à: http://localhost:5005")
    print("[*] Admin: http://localhost:5005/admin")
    print("[*] Credentials: admin@inetum.com\n")
    
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n\n[*] Serveur arrêté par l'utilisateur")
    except Exception as e:
        print(f"\n[ERROR] Erreur: {e}")
        sys.exit(1)

if __name__ == '__main__':
    start_server()
