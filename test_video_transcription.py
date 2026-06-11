#!/usr/bin/env python3
import sys
from pathlib import Path

video_file = Path("unified-agent/ui/uploads/[Accompagnement DEV et Support CTIME]-20260512_100450-Enregistrement de la réunion.mp4")

print(f"Fichier: {video_file}")
print(f"Existe: {video_file.exists()}")

if video_file.exists():
    size_mb = video_file.stat().st_size / (1024*1024)
    print(f"Taille: {size_mb:.2f} MB")
    
    print("\nTest d'importation de Whisper...")
    try:
        import whisper
        print("[OK] Whisper importé")
        
        print("\nListe des modèles disponibles:")
        print("- tiny (39M)")
        print("- base (74M)")
        print("- small (244M)")
        print("- medium (769M)")
        print("- large (1550M)")
        
        print("\nTentative de transcription avec le modèle 'base'...")
        print("(Cela peut prendre plusieurs minutes...)")
        
        model = whisper.load_model("base")
        result = model.transcribe(str(video_file))
        
        print("\n✅ Transcription réussie!")
        print(f"Texte: {result['text'][:200]}...")
        
    except ImportError as e:
        print(f"[ERROR] Whisper pas disponible: {e}")
    except Exception as e:
        print(f"[ERROR] Erreur lors de la transcription: {e}")
        import traceback
        traceback.print_exc()
else:
    print("[ERROR] Fichier not found!")
