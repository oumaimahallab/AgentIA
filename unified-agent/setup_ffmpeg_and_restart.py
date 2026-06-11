#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script: Configuration automatique FFmpeg + API Restart
Après téléchargement FFmpeg, configure le PATH et relance l'API
"""

import os
import sys
import subprocess
from pathlib import Path


def check_ffmpeg_installed():
    """Vérifier si FFmpeg est accessible"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        return result.returncode == 0
    except:
        return False


def setup_ffmpeg_path():
    """Ajouter FFmpeg au PATH si téléchargé"""
    ffmpeg_path = Path("C:\\ffmpeg-master-latest-win64-gpl\\bin")
    
    if ffmpeg_path.exists():
        print(f"✅ FFmpeg trouvé: {ffmpeg_path}")
        
        # Ajouter au PATH Windows
        os.environ['PATH'] = str(ffmpeg_path) + os.pathsep + os.environ['PATH']
        print(f"✅ Ajouté au PATH")
        
        return True
    else:
        print(f"❌ FFmpeg non trouvé à {ffmpeg_path}")
        return False


def verify_ffmpeg():
    """Vérifier que FFmpeg fonctionne"""
    if check_ffmpeg_installed():
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        lines = result.stdout.split('\n')
        print("\n✅ FFmpeg disponible:")
        print(f"   {lines[0]}")
        return True
    else:
        print("\n❌ FFmpeg n'est pas accessible")
        return False


def restart_api():
    """Redémarrer l'API Flask"""
    print("\n🔄 Redémarrage de l'API...")
    
    api_script = Path(__file__).parent / "ui" / "app.py"
    
    if not api_script.exists():
        print(f"❌ App.py non trouvé: {api_script}")
        return False
    
    # Lancer dans un nouveau terminal
    if os.name == 'nt':  # Windows
        cmd = f'start cmd /k "cd {Path(__file__).parent} && python ui\\app.py"'
        os.system(cmd)
        print("✅ API relancée dans nouveau terminal")
        return True
    else:
        # Linux/Mac
        subprocess.Popen([sys.executable, str(api_script)])
        print("✅ API relancée")
        return True


def main():
    """Menu principal"""
    
    print("\n" + "="*70)
    print("🔧 CONFIGURATION FFMPEG + REDÉMARRAGE API")
    print("="*70 + "\n")
    
    # Vérifier FFmpeg
    print("1️⃣  Vérification FFmpeg...")
    if setup_ffmpeg_path():
        if verify_ffmpeg():
            print("\n✅ FFmpeg correctement configuré!")
            
            # Redémarrer API
            print("\n2️⃣  Redémarrage de l'API...")
            restart_api()
            
            print("\n" + "="*70)
            print("🎉 Configuration complétée!")
            print("="*70)
            print("\n📋 Prochaines étapes:")
            print("  1. Attendre que la nouvelle API se lance")
            print("  2. Aller à: http://localhost:5005/upload_demo.html")
            print("  3. Relancer le traitement du document en erreur")
            print("\n💡 Ou utiliser:")
            print("  python retry_failed_document.py 44")
            
            return True
        else:
            print("\n❌ FFmpeg non fonctionnel après configuration")
            return False
    else:
        print("\n❌ FFmpeg n'a pas pu être configuré")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
