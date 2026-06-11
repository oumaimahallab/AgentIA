#!/usr/bin/env python3
import sys
from pathlib import Path
import logging

# Setup logging détaillé
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Ajoute le chemin au projet
sys.path.insert(0, str(Path(__file__).parent / "unified-agent"))

video_path = Path("unified-agent/ui/uploads") / "[Accompagnement DEV et Support CTIME]-20260512_100450-Enregistrement de la réunion.mp4"

print("\n" + "="*80)
print("TEST DE TRANSCRIPTION AVEC ERREURS DÉTAILLÉES")
print("="*80)

print(f"\nFichier: {video_path}")
print(f"Existe: {video_path.exists()}")
print(f"Taille: {video_path.stat().st_size / (1024*1024):.2f} MB\n")

if not video_path.exists():
    print("❌ Fichier pas trouvé!")
    sys.exit(1)

try:
    print("Step 1: Import UnifiedIngester...")
    from ingestion.unified_ingester import UnifiedIngester
    print("✓ Importé\n")
    
    print("Step 2: Import AudioTranscriber...")
    from ingestion.unified_ingester import AudioTranscriber
    print("✓ Importé\n")
    
    print("Step 3: Test import faster_whisper...")
    try:
        from faster_whisper import WhisperModel
        print("✓ faster-whisper disponible\n")
    except ImportError as e:
        print(f"❌ faster-whisper NOT disponible: {e}\n")
        raise
    
    print("Step 4: Lancement de l'ingestion...")
    ingester = UnifiedIngester()
    result = ingester.ingest(video_path)
    
    if result:
        chunks, metadata = result
        print(f"✅ SUCCÈS!")
        print(f"   Chunks: {len(chunks)}")
        print(f"   Langue: {metadata.language}")
        print(f"   Premiers 200 chars du chunk 1:\n   {chunks[0][:200]}")
    else:
        print(f"❌ Ingestion a retourné None!")
        
except Exception as e:
    print(f"❌ ERREUR DÉTAILLÉE:\n")
    print(f"Type: {type(e).__name__}")
    print(f"Message: {str(e)}\n")
    
    import traceback
    print("Traceback complet:")
    traceback.print_exc()
