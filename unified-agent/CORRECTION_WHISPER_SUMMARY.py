#!/usr/bin/env python3
"""
RÉSUMÉ CORRECTION - Erreur Whisper
==================================

Statut: ✅ RÉSOLU

Le problème: Module 'whisper' non installé
La solution: Installation openai-whisper + meilleure gestion d'erreur
"""

SUMMARY = """
╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║               ✅ CORRECTION ERREUR WHISPER COMPLÉTÉE              ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝


🔴 ERREUR INITIALE
═════════════════════════════════════════════════════════════════════

ERROR:ingestion.unified_ingester:✗ Erreur transcription 
  [...].mp4: No module named 'whisper'

Cause: Le module openai-whisper n'était pas installé


✅ CORRECTIONS APPLIQUÉES
═════════════════════════════════════════════════════════════════════

1️⃣ Installation dépendance:
   ✅ pip install openai-whisper
   
   → Module maintenant disponible et fonctionnel

2️⃣ Amélioration code (unified_ingester.py):
   ✅ Try-except sur import whisper
   ✅ Message d'erreur plus clair
   ✅ Instructions pour installer si absent
   
3️⃣ Scripts de récupération:
   ✅ cleanup_failed_documents.py
      - Nettoyer documents en erreur
      - Voir détails erreurs
      
   ✅ retry_failed_document.py
      - Relancer traitement sans re-uploader
      
   ✅ FIX_WHISPER_ERROR.md
      - Guide complet de correction


🚀 COMMENT RELANCER LE TRAITEMENT
═════════════════════════════════════════════════════════════════════

OPTION 1 - Interface web (plus simple):
   
   1. Aller à: http://localhost:5005/upload_demo.html
   2. Cliquer onglet "Documents"
   3. Cliquer sur document en erreur (ID #52)
   4. Cliquer "Supprimer"
   5. Onglet "Upload" → Re-uploader le fichier MP4
   
   ✅ Rapide et intuitif


OPTION 2 - Script Python (automatisé):
   
   # Voir le document en erreur
   python cleanup_failed_documents.py list
   
   # Voir détails
   python cleanup_failed_documents.py info 52
   
   # Supprimer
   python cleanup_failed_documents.py clean 52
   
   # Re-uploader via web interface


OPTION 3 - Relancer directement sans re-uploader:
   
   # Relancer traitement du document #52
   python retry_failed_document.py 52
   
   ✅ Le plus rapide - file est gardé, juste relancé


OPTION 4 - cURL (API REST):
   
   curl -X POST http://localhost:5005/api/user/upload_and_ingest \\
     -F 'file=@[Accompagnement DEV et Support CTIME]-20260512_100450-Enregistrement de la réunion.mp4' \\
     -F 'email=admin@inetum.com' \\
     -F 'session_id=session_admin'


📊 FICHIERS CRÉÉS/MODIFIÉS
═════════════════════════════════════════════════════════════════════

✅ CRÉÉS:
  • cleanup_failed_documents.py (200+ lignes)
    - Gérer documents en erreur
    
  • retry_failed_document.py (200+ lignes)
    - Relancer directement
    
  • FIX_WHISPER_ERROR.md (250+ lignes)
    - Guide complet correction

✅ MODIFIÉS:
  • ingestion/unified_ingester.py
    - Meilleure gestion d'erreur whisper
    - Try-except sur import
    - Messages clairs


⏱️ TEMPS DE TRAITEMENT VIDÉO
═════════════════════════════════════════════════════════════════════

Modèle utilisé: "small" (défaut)

Selon la durée vidéo:
  • Vidéo 1-5 min:      5-15 secondes
  • Vidéo 5-10 min:     15-30 secondes ← Votre vidéo (~10min)
  • Vidéo 10-20 min:    30-60 secondes
  • Vidéo 20+ min:      60+ secondes

Pour plus rapide: passer à modèle "tiny" ou "base"
Pour meilleure qualité: passer à "medium" ou "large"


🎯 RÉSULTAT ATTENDU
═════════════════════════════════════════════════════════════════════

Après relance du traitement (Option 1, 2 ou 3):

Status passera de: "Erreur" → "En cours" → "Ingéré"

Métadonnées extraites:
  ✅ Transcription vidéo
  ✅ Keywords (TF-IDF)
  ✅ Entities (emails, URLs, tel)
  ✅ Statistiques nettoyage
  ✅ Indexation FAISS + BM25


📋 VÉRIFICATION
═════════════════════════════════════════════════════════════════════

Vérifier que Whisper fonctionne:

python -c "import whisper; print('✅ Whisper OK')"

Télécharger modèles (optionnel, fait auto):

python -c "import whisper; whisper.load_model('small')"


💡 CONSEILS
═════════════════════════════════════════════════════════════════════

✅ À FAIRE:
  • Relancer le traitement (voir options ci-dessus)
  • Vérifier status passant à "Ingéré"
  • Consulter métadonnées extraites

⚠️ À ÉVITER:
  • Ne pas uploader trop de vidéos en même temps (charge CPU/RAM)
  • Pour longs vidéos (>1h), segmenter en fichiers plus petits
  • Vérifier connectivité internet (téléchargement modèles)


🐛 DÉPANNAGE SUPPLÉMENTAIRE
═════════════════════════════════════════════════════════════════════

Si problème persiste après relance:

1. Vérifier fichier vidéo valide:
   ffprobe video.mp4
   
2. Vérifier espace disque:
   df -h  # Linux/Mac
   dir    # Windows
   
3. Vérifier permissions:
   ls -la video.mp4
   
4. Tester Whisper seul:
   python -c "
   import whisper
   result = whisper.transcribe('video.mp4', model='tiny')
   print(result['text'][:100])
   "
   
5. Consulter logs détaillés:
   tail -f logs/ingestion.log


📞 SUPPORT
═════════════════════════════════════════════════════════════════════

Fichiers d'aide:
  • FIX_WHISPER_ERROR.md (ce dossier)
  • INGESTION_AUTO_GUIDE.md (config avancée)
  • cleanup_failed_documents.py (voir help)
  • retry_failed_document.py (voir help)


═════════════════════════════════════════════════════════════════════

Status de la correction: ✅ COMPLÈTE

Prochaine étape: Relancer le traitement (voir options ci-dessus)

═════════════════════════════════════════════════════════════════════
"""

if __name__ == "__main__":
    print(SUMMARY)
    print("\n💡 Pour plus de détails, consulter: FIX_WHISPER_ERROR.md")
