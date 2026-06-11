troubleshooting.md# 🆘 Guide de Dépannage - Erreurs d'Ingestion

## 📍 Problème: Erreur Whisper (Transcription Vidéo)

### 🔴 Symptôme
```
ERROR:ingestion.unified_ingester:✗ Erreur transcription [...].mp4: No module named 'whisper'
Status du document: 🔴 Erreur
```

### ✅ Solution Complète

#### Étape 1: Installation (Déjà fait ✅)
```bash
pip install openai-whisper
```

#### Étape 2: Relancer le traitement

**OPTION A - Menu interactif (Plus simple) 👍**
```bash
cd c:\Users\maup10458\Desktop\AG\unified-agent
python fix_errors_menu.py
```

Puis sélectionner option `5️⃣ Relancer traitement d'un document`

---

**OPTION B - En ligne de commande**
```bash
# Voir documents en erreur
python cleanup_failed_documents.py list

# Relancer document #52
python retry_failed_document.py 52

# Vérifier status passé à "Ingéré"
```

---

**OPTION C - Interface web**
1. Aller à: http://localhost:5005/upload_demo.html
2. Onglet "Documents" → Trouver #52
3. Cliquer "Supprimer"
4. Onglet "Upload" → Re-uploader le fichier

---

### 🎯 Résultat Attendu
```
Status: 🔴 Erreur  →  🟡 En cours  →  🟢 Ingéré

Document #52: [Accompagnement DEV et Support CTIME]-20260512_100450...
Chunks: 45
Keywords: data, reunion, support, ...
Entities: alice@company.com, https://example.com
```

---

## 🔧 Outils de Gestion

### 1. Menu Principal
```bash
python fix_errors_menu.py
```
Interface interactive avec 8 options

### 2. Voir les Erreurs
```bash
python cleanup_failed_documents.py list
```

### 3. Détails d'une Erreur
```bash
python cleanup_failed_documents.py info 52
```

### 4. Relancer Traitement
```bash
python retry_failed_document.py 52
```

### 5. Supprimer Document
```bash
python cleanup_failed_documents.py clean 52
```

### 6. Nettoyer Tous les Erreurs
```bash
python cleanup_failed_documents.py clean-all
```

---

## 🧪 Vérification Whisper

### Vérifier Installation
```bash
python -c "import whisper; print('✅ Whisper OK')"
```

### Vérifier Modèles Téléchargés
```bash
python -c "
import whisper
try:
    model = whisper.load_model('small')
    print('✅ Modèle small disponible')
except:
    print('❌ Modèle non trouvé')
"
```

### Tester Transcription
```bash
python -c "
import whisper
result = whisper.transcribe('video.mp4', model='small')
print('Transcription:', result['text'][:100])
"
```

---

## ⏱️ Durée de Traitement

### Par Modèle (vidéo 10 min)
| Modèle | RAM  | Vitesse | Qualité |
|--------|------|---------|---------|
| tiny   | 1GB  | ⚡⚡⚡    | ⭐     |
| base   | 1GB  | ⚡⚡     | ⭐⭐    |
| small  | 2GB  | ⚡      | ⭐⭐⭐  | ← Défaut
| medium | 5GB  | 🐌      | ⭐⭐⭐⭐ |
| large  | 10GB | 🐢      | ⭐⭐⭐⭐⭐|

### Temps Réel (vidéo 10 min, modèle small)
- ⚡ Téléchargement modèle: 30-60s (1ère fois seulement)
- ⚡ Transcription: 15-30 secondes
- ⚡ Nettoyage texte: 1-2 secondes
- ⚡ Extraction keywords: 0.5 secondes
- ⚡ Indexation: 2-3 secondes

**Total: 30-60 secondes** (comprend téléchargement modèle première fois)

---

## 🚀 Optimiser Performance

### Pour Plus Rapide
```python
# Dans config/settings.py
WHISPER_CONFIG = {
    'model': 'tiny',  # Plus rapide
    'device': 'cpu'   # (ou 'cuda' si GPU disponible)
}
```

### Pour Meilleure Qualité
```python
WHISPER_CONFIG = {
    'model': 'medium',  # Plus précis
    'device': 'cuda'    # Nécessite GPU
}
```

### Avec GPU (Plus Rapide)
```bash
# Installer PyTorch avec CUDA
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Whisper utilisera GPU automatiquement
```

---

## 🔍 Diagnostic Avancé

### 1. Vérifier Fichier Vidéo
```bash
# Windows
wmic datafile where name="C:\\path\\to\\video.mp4" get Description,Version

# Linux/Mac
file video.mp4
ffprobe video.mp4
```

### 2. Vérifier Espace Disque
```bash
# Windows
dir C:\Users\maup10458\Desktop\AG
# (chercher ~5GB libre pour modèles Whisper)

# Linux/Mac
df -h
```

### 3. Vérifier Permissions
```bash
# Linux/Mac
ls -la video.mp4

# Windows
icacls video.mp4
```

### 4. Vérifier Connexion Réseau
```bash
# Important pour télécharger modèles Whisper
ping github.com
ping huggingface.co
```

### 5. Consulter Logs Détaillés
```bash
# Voir dernières erreurs
tail -f logs/ingestion.log

# Windows (simule tail)
Get-Content logs/ingestion.log -Tail 50 -Wait
```

---

## ❌ Erreurs Courantes

### "No module named 'whisper'"
**Cause**: Module non installé  
**Solution**: `pip install openai-whisper`

### "CUDA not found" / "torch not installed"
**Cause**: PyTorch CUDA non installé  
**Solution**: 
```bash
# Utiliser CPU
set CUDA_VISIBLE_DEVICES=""
python retry_failed_document.py 52
```

### "OutOfMemoryError"
**Cause**: Pas assez de RAM  
**Solution**: Utiliser modèle plus petit
```python
WHISPER_CONFIG = {'model': 'base'}  # au lieu de 'medium'
```

### "Model not found / download interrupted"
**Cause**: Téléchargement interrompu  
**Solution**:
```bash
# Forcer re-téléchargement
python -c "import whisper; whisper.load_model('small')"
```

### "ffmpeg not found"
**Cause**: ffmpeg non installé (dépendance whisper)  
**Solution**:
```bash
# Windows
choco install ffmpeg

# Linux
sudo apt-get install ffmpeg

# Mac
brew install ffmpeg
```

### "Invalid audio file"
**Cause**: Fichier vidéo corrompu  
**Solution**: 
```bash
# Vérifier avec ffprobe
ffprobe video.mp4
# Ou convertir
ffmpeg -i video.mp4 -codec copy video_fixed.mp4
```

---

## 📊 Monitoring

### Vérifier Status Ingestion
```bash
# Voir tous les documents
python cleanup_failed_documents.py list

# Voir un document
python cleanup_failed_documents.py info 52
```

### Statistiques BD
```python
import psycopg2

conn = psycopg2.connect(...)
cur = conn.cursor()

# Nombre documents par status
cur.execute("""
    SELECT status, COUNT(*) 
    FROM user_documents 
    GROUP BY status
""")
print(cur.fetchall())

# Documents en erreur
cur.execute("""
    SELECT id, filename, error_msg 
    FROM user_documents 
    WHERE status = 'Erreur'
""")
print(cur.fetchall())
```

---

## 💡 Bonnes Pratiques

### ✅ À FAIRE
- Uploader vidéos < 1h (segmenter sinon)
- Vérifier connectivité avant upload
- Monitorer les logs pendant traitement
- Utiliser modèle `small` (défaut) comme base
- Relancer avec `retry_failed_document.py` (plus rapide)

### ❌ À ÉVITER
- Ne pas uploader trop de fichiers simultanément
- Ne pas fermer navigateur pendant traitement
- Ne pas modifier fichier pendant ingestion
- Ne pas supprimer documents sans vérifier erreur
- Ne pas utiliser modèle `large` sur CPU

---

## 🔗 Ressources

### Documentation Projet
- [FIX_WHISPER_ERROR.md](FIX_WHISPER_ERROR.md) - Guide Whisper
- [INGESTION_AUTO_GUIDE.md](INGESTION_AUTO_GUIDE.md) - Guide complet
- [CORRECTION_WHISPER_SUMMARY.py](CORRECTION_WHISPER_SUMMARY.py) - Résumé

### Documentation Externes
- [OpenAI Whisper](https://github.com/openai/whisper)
- [Whisper Models](https://github.com/openai/whisper#available-models)
- [PyTorch CUDA](https://pytorch.org/get-started/locally/)

---

## 📞 Support

### Menu Interactif (Recommended)
```bash
python fix_errors_menu.py
```

### Scripts Directs
```bash
# Voir erreurs
python cleanup_failed_documents.py list

# Relancer
python retry_failed_document.py 52

# Nettoyer
python cleanup_failed_documents.py clean 52
```

### Interface Web
http://localhost:5005/upload_demo.html

---

## ✨ Résumé Rapide

| Problème | Solution | Commande |
|----------|----------|----------|
| Whisper non installé | Installer module | `pip install openai-whisper` |
| Vidéo en erreur | Relancer traitement | `python retry_failed_document.py 52` |
| Voir les erreurs | Lister documents | `python cleanup_failed_documents.py list` |
| Supprimer erreur | Nettoyer BD | `python cleanup_failed_documents.py clean 52` |
| Menu interactif | Tous les outils | `python fix_errors_menu.py` |

---

**Créé**: 25/05/2026  
**Status**: ✅ Opérationnel  
**Version**: 2.0
