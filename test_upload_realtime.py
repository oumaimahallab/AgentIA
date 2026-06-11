#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Upload Temps Réel - Démontre le système d'ingestion avec statut en temps réel
"""

import requests
import time
import json
from pathlib import Path

BASE_URL = "http://localhost:5005"

def test_realtime_upload():
    """Teste l'upload avec suivi du statut en temps réel"""
    
    print("\n" + "="*60)
    print("🧪 TEST UPLOAD TEMPS RÉEL")
    print("="*60)
    
    # Configuration
    email = "demo@inetum.com"
    session_id = "test-session-" + str(int(time.time()))
    
    # Créer un fichier test
    test_file_path = Path("test_document.txt")
    test_content = """
    # Document de Test
    
    Ceci est un document de test pour vérifier le système d'ingestion en temps réel.
    
    Le processus devrait :
    1. Upload le fichier
    2. Afficher "En attente"
    3. Passer à "En cours"
    4. Extraire et nettoyer le contenu
    5. Indexer en FAISS et BM25
    6. Finaliser avec "Ingéré"
    
    Durée estimée : 5-30 secondes selon la taille du fichier.
    """
    
    test_file_path.write_text(test_content)
    print(f"\n✅ Fichier de test créé : {test_file_path}")
    
    # 1. Upload du fichier
    print(f"\n📤 Upload en cours...")
    print(f"   Email : {email}")
    print(f"   Session : {session_id}")
    
    with open(test_file_path, 'rb') as f:
        files = {'file': f}
        data = {
            'email': email,
            'session_id': session_id
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/user/upload_and_ingest",
                files=files,
                data=data,
                timeout=30
            )
        except requests.exceptions.ConnectionError:
            print(f"\n❌ Impossible de se connecter à {BASE_URL}")
            print(f"   Vérifiez que le serveur Flask est lancé :")
            print(f"   cd unified-agent/ui && python app.py")
            return
    
    if response.status_code != 200:
        print(f"\n❌ Erreur upload : {response.status_code}")
        print(f"   {response.json()}")
        return
    
    result = response.json()
    if not result.get('success'):
        print(f"\n❌ Erreur : {result.get('error')}")
        return
    
    doc_id = result['document_id']
    print(f"\n✅ Upload réussi!")
    print(f"   Document ID : {doc_id}")
    print(f"   Message : {result['message']}")
    
    # 2. Polling du statut
    print(f"\n🔄 Suivi du statut en temps réel...")
    print(f"   (polling chaque 2 secondes)\n")
    
    start_time = time.time()
    attempts = 0
    max_attempts = 60  # 2 minutes max
    last_status = None
    
    while attempts < max_attempts:
        attempts += 1
        elapsed = int(time.time() - start_time)
        
        try:
            response = requests.get(
                f"{BASE_URL}/api/user/documents/{doc_id}",
                params={'email': email},
                timeout=10
            )
            
            if response.status_code != 200:
                print(f"[{elapsed}s] ⚠️  Erreur récupération statut")
                time.sleep(2)
                continue
            
            doc = response.json()
            status = doc.get('status')
            
            # Afficher si le statut a changé
            if status != last_status:
                last_status = status
                
                if status == 'En attente':
                    print(f"[{elapsed}s] ⏳ En attente...")
                elif status == 'En cours':
                    print(f"[{elapsed}s] 🔄 Ingestion en cours")
                    print(f"         Extraction et traitement du contenu...")
                elif status == 'Ingéré':
                    processing_time = doc.get('processing_time', 0)
                    total_chunks = doc.get('total_chunks', 0)
                    print(f"[{elapsed}s] ✅ Ingéré avec succès!")
                    print(f"         Chunks : {total_chunks}")
                    print(f"         Temps : {processing_time:.2f}s")
                    break
                elif status == 'Erreur':
                    error_msg = doc.get('error_msg', 'Erreur inconnue')
                    print(f"[{elapsed}s] ❌ Erreur : {error_msg}")
                    break
            
            time.sleep(2)
            
        except Exception as e:
            print(f"[{elapsed}s] ⚠️  Erreur polling : {e}")
            time.sleep(2)
    
    if attempts >= max_attempts:
        print(f"\n⏱️  Timeout : ingestion trop longue (>2 minutes)")
    
    # 3. Récupérer les détails finaux
    print(f"\n📊 Détails du document :")
    print("-" * 60)
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/user/documents/{doc_id}",
            params={'email': email},
            timeout=10
        )
        
        if response.status_code == 200:
            doc = response.json()
            print(f"   Fichier : {doc.get('filename')}")
            print(f"   Type : {doc.get('file_type')}")
            print(f"   Taille : {doc.get('file_size')} bytes")
            print(f"   Statut : {doc.get('status')}")
            print(f"   Chunks : {doc.get('total_chunks')}")
            print(f"   Temps : {doc.get('processing_time', 0):.2f}s")
            print(f"   Langue : {doc.get('language')}")
            
            if doc.get('keywords'):
                print(f"   Keywords : {', '.join(doc['keywords'][:5])}...")
    
    except Exception as e:
        print(f"   ⚠️  Erreur récupération détails : {e}")
    
    # Cleanup
    print(f"\n🧹 Nettoyage...")
    test_file_path.unlink()
    print(f"   Fichier de test supprimé")
    
    print("\n" + "="*60)
    print("✅ TEST TERMINÉ")
    print("="*60)


def test_document_listing():
    """Teste la récupération de tous les documents de l'utilisateur"""
    
    print("\n" + "="*60)
    print("📋 RÉCUPÉRATION DOCUMENTS UTILISATEUR")
    print("="*60)
    
    email = "demo@inetum.com"
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/user/documents",
            params={'email': email},
            timeout=10
        )
        
        if response.status_code == 200:
            documents = response.json()
            print(f"\n✅ Trouvé {len(documents)} document(s)\n")
            
            for doc in documents:
                print(f"📄 {doc['filename']}")
                print(f"   ID : {doc['id']}")
                print(f"   Statut : {doc['status']}")
                print(f"   Chunks : {doc['total_chunks']}")
                print(f"   Taille : {doc['file_size']} bytes")
                print(f"   Créé : {doc['created_at']}")
                print()
    
    except Exception as e:
        print(f"❌ Erreur : {e}")


if __name__ == '__main__':
    import sys
    
    print("\n🚀 Script de Test Upload Temps Réel\n")
    print("Options :")
    print("  1. test_upload       - Teste l'upload avec suivi temps réel")
    print("  2. test_documents    - Récupère les documents de l'utilisateur")
    print("  3. both              - Lance les deux tests\n")
    
    choice = input("Choisissez une option (1, 2, ou 3) : ").strip() or "1"
    
    if choice in ['1', 'both']:
        test_realtime_upload()
    
    if choice in ['2', 'both']:
        test_document_listing()
