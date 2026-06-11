#!/usr/bin/env python3
from pathlib import Path

video_file = Path("unified-agent/ui/uploads/[Accompagnement DEV et Support CTIME]-20260512_100450-Enregistrement de la réunion.mp4")

print(f"Fichier: {video_file}")
print(f"Existe: {video_file.exists()}")

if video_file.exists():
    size_mb = video_file.stat().st_size / (1024*1024)
    print(f"Taille: {size_mb:.2f} MB\n")
    
    try:
        print("✓ Import faster_whisper...")
        from faster_whisper import WhisperModel
        
        print("✓ Initialisation du modèle 'small' (CPU)...")
        model = WhisperModel("small", device="cpu", compute_type="int8")
        
        print("✓ Transcription en cours...")
        print("  (Cela peut prendre 5-10 minutes pour une vidéo de 360MB)...\n")
        
        segments, info = model.transcribe(str(video_file), language="fr")
        
        print("✅ Transcription réussie!\n")
        print(f"Langue détectée: {info.language}")
        print(f"Durée: {info.duration:.1f}s")
        print(f"Nombre de segments: {len(list(info))}\n")
        
        # Affiche un aperçu
        text_parts = []
        for segment in model.transcribe(str(video_file), language="fr")[0]:
            text_parts.append(segment.text)
        
        full_text = " ".join(text_parts)
        print(f"Texte transcrit ({len(full_text)} caractères):\n")
        print(full_text[:500] + "..." if len(full_text) > 500 else full_text)
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
else:
    print("❌ Fichier pas trouvé!")
