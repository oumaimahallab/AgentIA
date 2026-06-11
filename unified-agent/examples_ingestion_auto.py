#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EXEMPLE: Système Upload & Ingestion Auto avec Nettoyage

Usage: python examples_ingestion_auto.py
"""

import asyncio
import json
from pathlib import Path
from ingestion.unified_ingester import UnifiedIngester
from ingestion.text_cleaner import TextCleaner, BatchCleaner


# ============================================================================
# EXEMPLE 1: Ingestion Simple (Local)
# ============================================================================

def example_basic_ingestion():
    """Exemple basique d'ingestion avec nettoyage"""
    print("\n" + "="*60)
    print("EXEMPLE 1: Ingestion Simple Document PDF")
    print("="*60)
    
    # Créer ingester avec nettoyage activé
    ingester = UnifiedIngester(
        language="fr",
        clean_text=True,
        extract_entities=True
    )
    
    # Chemin du fichier (adapter selon votre cas)
    pdf_file = Path("exemple_document.pdf")
    
    if not pdf_file.exists():
        print(f"⚠️  Fichier {pdf_file} n'existe pas")
        print("   Créons un fichier texte pour la démo...")
        
        # Créer un fichier texte de test
        pdf_file = Path("test_demo.txt")
        pdf_file.write_text("""
        Bonjour, ceci est un document de test.
        Email de contact: john.doe@example.com
        Téléphone: +33 1 23 45 67 89
        Site web: https://example.com
        
        Le nettoyage va supprimer les URLs, emails et bruit.
        Processing time total: 42 secondes.
        """)
    
    # Ingérer le fichier
    result = ingester.ingest(
        pdf_file,
        user_email="demo@example.com",
        session_id="session_123"
    )
    
    if result:
        chunks, metadata = result
        
        print(f"\n✅ Ingestion réussie!")
        print(f"   Fichier: {metadata.file_name}")
        print(f"   Type: {metadata.source_type.value}")
        print(f"   Chunks générés: {len(chunks)}")
        print(f"   Temps processing: {metadata.processing_time:.2f}s")
        print(f"   Langue: {metadata.language}")
        
        # Afficher nettoyage stats
        if metadata.cleaning_stats:
            stats = metadata.cleaning_stats
            print(f"\n📊 Stats Nettoyage:")
            print(f"   Texte original: {stats['original_length']} chars")
            print(f"   Texte nettoyé: {stats['cleaned_length']} chars")
            print(f"   Bruit supprimé: {stats['removed_chars']} chars")
            print(f"   Doublons supprimés: {stats['removed_duplicates']}")
        
        # Afficher entités
        if metadata.extracted_entities:
            entities = metadata.extracted_entities
            print(f"\n🔍 Entités Extraites:")
            print(f"   Emails: {entities.get('emails', [])}")
            print(f"   URLs: {entities.get('urls', [])}")
            print(f"   Téléphones: {entities.get('phone_numbers', [])}")
            print(f"   Nombres: {entities.get('numbers', [])}")
        
        # Afficher keywords
        if metadata.keywords:
            print(f"\n🏷️  Top Keywords:")
            print(f"   {', '.join(metadata.keywords[:10])}")
        
        # Premier chunk
        if chunks:
            print(f"\n📄 Premier chunk (premiers 200 chars):")
            print(f"   {chunks[0][:200]}...")
    else:
        print("❌ Ingestion échouée")


# ============================================================================
# EXEMPLE 2: Nettoyage Texte Standalone
# ============================================================================

def example_text_cleaning():
    """Exemple nettoyage texte seul"""
    print("\n" + "="*60)
    print("EXEMPLE 2: Nettoyage Texte Standalone")
    print("="*60)
    
    cleaner = TextCleaner("fr")
    
    # Texte brut avec bruit
    raw_text = """
    Bonjour à tous! 👋👋👋
    
    Voici nos contacts:
    - Email: support@company.com
    - Site: https://www.company.com
    - Tél: +33 1 23 45 67 89
    
    Nous avons traité 1000 documents en 42.5 secondes!!!
    """
    
    print(f"\n📝 Texte original ({len(raw_text)} chars):")
    print(raw_text)
    
    # Nettoyer
    cleaned = cleaner.clean_text(raw_text)
    
    print(f"\n✨ Texte nettoyé ({len(cleaned)} chars):")
    print(cleaned)
    
    # Extraire entités
    entities = cleaner.extract_entities(raw_text)
    print(f"\n🔍 Entités trouvées:")
    print(json.dumps(entities, indent=2, ensure_ascii=False))
    
    # Extraire keywords
    keywords = cleaner.extract_keywords(raw_text)
    print(f"\n🏷️  Keywords (top 5):")
    print(f"   {', '.join(keywords[:5])}")


# ============================================================================
# EXEMPLE 3: Batch Processing avec Déduplication
# ============================================================================

def example_batch_processing():
    """Exemple traitement batch avec déduplication"""
    print("\n" + "="*60)
    print("EXEMPLE 3: Batch Processing & Déduplication")
    print("="*60)
    
    batch_cleaner = BatchCleaner("fr")
    
    # Textes avec doublons/similitudes
    texts = [
        "Ceci est un texte d'exemple très important",
        "Ceci est un texte d'exemple très important",  # Doublon exact
        "Ceci est un texte d'exemple assez important",  # Similaire 95%+
        "Complètement différent et unique",
        "Nouveau texte sans ressemblance",
    ]
    
    print(f"\n📋 Textes originaux ({len(texts)} items):")
    for i, t in enumerate(texts, 1):
        print(f"   {i}. {t}")
    
    # Traiter pipeline
    processed = batch_cleaner.process_pipeline(
        texts,
        remove_stopwords=False,
        deduplicate=True
    )
    
    print(f"\n✨ Après déduplication ({len(processed)} items):")
    for i, t in enumerate(processed, 1):
        print(f"   {i}. {t}")


# ============================================================================
# EXEMPLE 4: Chunking chevauchant
# ============================================================================

def example_chunking():
    """Exemple chunking avec chevauchement"""
    print("\n" + "="*60)
    print("EXEMPLE 4: Chunking Chevauchant")
    print("="*60)
    
    cleaner = TextCleaner("fr")
    
    # Long texte
    long_text = " ".join([
        f"Ceci est la phrase numéro {i}. Elle contient des informations importantes."
        for i in range(1, 20)
    ])
    
    print(f"\n📝 Texte long ({len(long_text)} chars)")
    
    # Chunker avec overlap
    chunks = cleaner.chunk_text(long_text, chunk_size=150, overlap=30)
    
    print(f"\n✨ Chunks générés ({len(chunks)} items):")
    for i, chunk in enumerate(chunks, 1):
        print(f"   Chunk {i} ({len(chunk)} chars):")
        print(f"   {chunk}")
        print()


# ============================================================================
# EXEMPLE 5: Simulation Requête API
# ============================================================================

async def example_api_simulation():
    """Simule requête API upload_and_ingest"""
    print("\n" + "="*60)
    print("EXEMPLE 5: Simulation API Upload & Ingestion")
    print("="*60)
    
    # Créer fichier test
    test_file = Path("test_upload.txt")
    test_file.write_text("""
    RAPPORT MENSUEL - Mai 2025
    
    Contact: alice@company.com
    Téléphone: +33 9 87 65 43 21
    
    Résumé exécutif:
    - Nous avons traité 5000 documents
    - Temps moyen: 2.3 secondes par document
    - Taux de succès: 99.8%
    
    Prochaines étapes:
    - Optimisation infrastructure
    - Formation utilisateurs
    - Documentation complète
    """)
    
    print(f"\n📤 Upload simulation: {test_file.name}")
    
    # Simulate API call
    ingester = UnifiedIngester()
    result = ingester.ingest(
        test_file,
        user_email="alice@company.com",
        session_id="session_abc123"
    )
    
    if result:
        chunks, metadata = result
        
        print(f"\n✅ Response API:")
        print(json.dumps({
            "success": True,
            "document_id": 42,
            "message": "Fichier uploadé. Extraction + nettoyage en cours...",
            "status": "processing",
            "metadata": {
                "filename": metadata.file_name,
                "file_type": metadata.source_type.value,
                "chunks": len(chunks),
                "user_email": metadata.user_email,
                "session_id": metadata.session_id,
            }
        }, indent=2, ensure_ascii=False))


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║   EXEMPLES: INGESTION AUTO AVEC NETTOYAGE               ║
║                                                            ║
║   Démonstration complète du système:                      ║
║   - Ingestion fichiers                                    ║
║   - Nettoyage texte                                       ║
║   - Extraction entités                                    ║
║   - Batch processing                                      ║
║   - Chunking chevauchant                                 ║
╚════════════════════════════════════════════════════════════╝
    """)
    
    # Exécuter exemples
    try:
        example_basic_ingestion()
        example_text_cleaning()
        example_batch_processing()
        example_chunking()
        
        # Async example
        print("\n" + "="*60)
        print("EXEMPLE 5: Simulation API Upload")
        print("="*60)
        asyncio.run(example_api_simulation())
        
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Tous les exemples complétés!")
    print("\n💡 Consultez INGESTION_AUTO_GUIDE.md pour la documentation complète")
