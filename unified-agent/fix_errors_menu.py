#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Menu: Gestion rapide des erreurs d'ingestion
Outils pour nettoyer et relancer les documents en erreur
"""

import os
import sys
import subprocess
from pathlib import Path


def clear_screen():
    """Effacer l'écran"""
    os.system('cls' if os.name == 'nt' else 'clear')


def show_banner():
    """Afficher bannière"""
    print("""
╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║   🛠️  MENU GESTION ERREURS D'INGESTION                           ║
║                                                                    ║
║   Nettoyage, diagnostic, relance documents en erreur             ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝
    """)


def show_menu():
    """Menu principal"""
    print("""
📋 OPTIONS DISPONIBLES:

  1️⃣  Voir résumé correction Whisper
  2️⃣  Lister documents en erreur
  3️⃣  Voir détails d'un document
  4️⃣  Supprimer un document en erreur
  5️⃣  Relancer traitement d'un document
  6️⃣  Supprimer TOUS les documents en erreur
  
  7️⃣  Ouvrir interface web
  8️⃣  Consulter guide complet
  
  0️⃣  Quitter

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """)


def option_1():
    """Voir résumé"""
    print("\n📄 Affichage du résumé de correction...\n")
    subprocess.run([sys.executable, "CORRECTION_WHISPER_SUMMARY.py"])


def option_2():
    """Lister documents en erreur"""
    print("\n📋 Documents en erreur:\n")
    subprocess.run([sys.executable, "cleanup_failed_documents.py", "list"])


def option_3():
    """Voir détails d'un document"""
    try:
        doc_id = input("\n🔍 ID du document: ").strip()
        if not doc_id:
            print("❌ ID requis")
            return
        subprocess.run([sys.executable, "cleanup_failed_documents.py", "info", doc_id])
    except KeyboardInterrupt:
        print("\n⏸️  Annulé")


def option_4():
    """Supprimer un document"""
    try:
        doc_id = input("\n🗑️  ID du document à supprimer: ").strip()
        if not doc_id:
            print("❌ ID requis")
            return
        
        confirm = input(f"⚠️  Êtes-vous sûr de vouloir supprimer le document #{doc_id}? (y/n): ").lower()
        if confirm == 'y':
            subprocess.run([sys.executable, "cleanup_failed_documents.py", "clean", doc_id])
        else:
            print("❌ Annulé")
    except KeyboardInterrupt:
        print("\n⏸️  Annulé")


def option_5():
    """Relancer traitement"""
    try:
        doc_id = input("\n🔄 ID du document à relancer: ").strip()
        if not doc_id:
            print("❌ ID requis")
            return
        
        print(f"\n⏳ Relance du traitement du document #{doc_id}...\n")
        subprocess.run([sys.executable, "retry_failed_document.py", doc_id])
    except KeyboardInterrupt:
        print("\n⏸️  Annulé")


def option_6():
    """Supprimer tous les documents en erreur"""
    try:
        confirm = input("\n⚠️  ATTENTION: Supprimer TOUS les documents en erreur? (y/n): ").lower()
        if confirm == 'y':
            confirm2 = input("     Êtes-vous vraiment sûr? (y/n): ").lower()
            if confirm2 == 'y':
                subprocess.run([sys.executable, "cleanup_failed_documents.py", "clean-all"])
            else:
                print("❌ Annulé")
        else:
            print("❌ Annulé")
    except KeyboardInterrupt:
        print("\n⏸️  Annulé")


def option_7():
    """Ouvrir interface web"""
    import webbrowser
    print("\n🌐 Ouverture interface web...\n")
    webbrowser.open("http://localhost:5005/upload_demo.html")
    print("✅ Interface ouverte dans le navigateur")
    print("   URL: http://localhost:5005/upload_demo.html")


def option_8():
    """Consulter guide"""
    print("\n📖 Guides disponibles:\n")
    print("  1. FIX_WHISPER_ERROR.md - Guide complet correction Whisper")
    print("  2. INGESTION_AUTO_GUIDE.md - Guide complet système ingestion")
    print("  3. UPLOAD_INGESTION_SYSTEM.md - Quick reference")
    print("\n💡 Fichiers situés dans: c:\\Users\\maup10458\\Desktop\\AG\\unified-agent\\")
    print("\nOuverture avec éditeur par défaut...")
    
    choice = input("\n📖 Quel guide? (1/2/3): ").strip()
    
    guides = {
        '1': 'FIX_WHISPER_ERROR.md',
        '2': 'INGESTION_AUTO_GUIDE.md',
        '3': 'UPLOAD_INGESTION_SYSTEM.md',
    }
    
    guide = guides.get(choice)
    if guide:
        os.system(f'start {guide}' if os.name == 'nt' else f'open {guide}')
        print(f"✅ Ouverture de {guide}...")
    else:
        print("❌ Choix invalide")


def main():
    """Boucle principale"""
    
    while True:
        clear_screen()
        show_banner()
        show_menu()
        
        try:
            choice = input("👉 Votre choix: ").strip()
            
            if choice == '0':
                print("\n👋 Au revoir!\n")
                break
            elif choice == '1':
                option_1()
            elif choice == '2':
                option_2()
            elif choice == '3':
                option_3()
            elif choice == '4':
                option_4()
            elif choice == '5':
                option_5()
            elif choice == '6':
                option_6()
            elif choice == '7':
                option_7()
            elif choice == '8':
                option_8()
            else:
                print("\n❌ Choix invalide")
            
            if choice not in ['0']:
                input("\n👉 Appuyez sur ENTRÉE pour continuer...")
        
        except KeyboardInterrupt:
            print("\n\n👋 Au revoir!\n")
            break
        except Exception as e:
            print(f"\n❌ Erreur: {e}")
            input("\n👉 Appuyez sur ENTRÉE pour continuer...")


if __name__ == "__main__":
    main()
