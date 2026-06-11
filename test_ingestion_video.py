#!/usr/bin/env python3
import sys
from pathlib import Path

# Ajoute le chemin au projet
sys.path.insert(0, str(Path(__file__).parent / "unified-agent"))

from ingestion.unified_ingester import UnifiedIngester

video_path = Path("unified-agent/ui/uploads") / "[Accompagnement DEV et Support CTIME]-20260512_100450-Enregistrement de la réunion.mp4"

print(f"Test d'ingestion vidéo...")
print(f"Fichier: {video_path}")
print(f"Existe: {video_path.exists()}\n")

if video_path.exists():
    ingester = UnifiedIngester()
    
    try:
        result = ingester.ingest(video_path)
        
        if result:
            chunks, metadata = result
            print(f"✅ Ingestion réussie!\n")
            print(f"Chunks créés: {len(chunks)}")
            print(f"Langue détectée: {metadata.language}")
            print(f"Taille fichier: {metadata.file_size / (1024*1024):.2f} MB")
            print(f"Type source: {metadata.source_type.value}\n")
            
            # Affiche les chunks
            for i, chunk in enumerate(chunks[:3]):
                print(f"--- Chunk {i+1} ---")
                print(chunk[:200] + "...\n" if len(chunk) > 200 else chunk + "\n")
        else:
            print("❌ Ingestion retourné None")
    except Exception as e:
        print(f"❌ Erreur d'ingestion: {e}")
        import traceback
        traceback.print_exc()
else:
    print("❌ Fichier pas trouvé!")
