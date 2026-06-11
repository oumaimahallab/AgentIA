# 🎯 Correction Erreur Whisper

## 📌 Le Problème

Erreur lors du traitement de la vidéo:
```
ERROR:ingestion.unified_ingester:✗ Erreur transcription [...].mp4: No module named 'whisper'
```

## ✅ Solution Appliquée

Le module `openai-whisper` a été installé avec succès:

```bash
pip install openai-whisper
```

## 🔄 Relancer le Traitement

### Option 1: Supprimer et Re-uploader le document

1. Aller à l'interface web: `http://localhost:5005/upload_demo.html`
2. Cliquer sur l'onglet **Documents**
3. Cliquer sur le document avec erreur (ID #52)
4. Cliquer **Supprimer**
5. Retourner à l'onglet **Upload**
6. Re-uploader le fichier MP4

### Option 2: Effacer manuellement et re-traiter

```python
# Script pour nettoyer et relancer
import psycopg2
from pathlib import Path

# Connexion BD
conn = psycopg2.connect(
    dbname="agent_db",
    user="postgres",
    password="root",
    host="localhost"
)
cur = conn.cursor()

# Effacer le document en erreur
cur.execute("DELETE FROM user_documents WHERE id = 52")
conn.commit()
cur.close()
conn.close()

print("Document supprimé ✅")

# Ensuite re-uploader via interface
```

### Option 3: Utiliser l'API directement

```bash
curl -X POST http://localhost:5005/api/user/upload_and_ingest \
  -F 'file=@[Accompagnement DEV et Support CTIME]-20260512_100450-Enregistrement de la réunion.mp4' \
  -F 'email=admin@inetum.com' \
  -F 'session_id=session_admin'
```

## 🧪 Tester Whisper Localement

```python
import whisper

# Tester import
print("✅ Whisper installé correctement")

# Tester avec un fichier
model = whisper.load_model("base")  # ou "small", "medium", "large"
result = model.transcribe("video.mp4")
print(result["text"])
```

## 📋 Modèles Whisper Disponibles

| Modèle | Taille | RAM Required | Speed | Quality |
|--------|--------|--------------|-------|---------|
| tiny   | 39 MB  | 1 GB         | ⚡⚡⚡  | ⭐    |
| base   | 140 MB | 1 GB         | ⚡⚡   | ⭐⭐   |
| small  | 466 MB | 2 GB         | ⚡    | ⭐⭐⭐ |
| medium | 1.5 GB | 5 GB         | ~5min | ⭐⭐⭐⭐|
| large  | 2.9 GB | 10 GB        | ~15min| ⭐⭐⭐⭐⭐|

**Défaut utilisé**: `small` (meilleur rapport qualité/vitesse)

## 🛠️ Configuration des Modèles

Dans `config/settings.py`:

```python
WHISPER_CONFIG = {
    'model': 'small',  # Changez à 'base', 'medium', 'large' selon besoin
    'device': 'cuda',  # ou 'cpu'
    'language': 'fr',  # Force la langue française
}
```

## 💡 Conseils Performance

### Pour fichiers courts (< 5 min):
Utiliser modèle **tiny** ou **base** (très rapide)

### Pour fichiers moyens (5-30 min):
Utiliser modèle **small** ou **medium** (qualité/vitesse)

### Pour longs fichiers (> 30 min):
Utiliser modèle **small** avec segmentation

### Accélérer avec GPU:
```bash
pip install torch
# Ensuite Whisper utilisera GPU automatiquement
```

## 🐛 Dépannage

### Erreur: "CUDA not found"
```bash
# Utiliser CPU à la place
CUDA_VISIBLE_DEVICES="" python app.py
```

### Erreur: "OutOfMemoryError"
Réduire la taille du modèle:
- Passer de `medium` à `small`
- Passer de `small` à `base`

### Erreur: "Téléchargement modèle interrompu"
```bash
# Forcer le téléchargement
python -c "import whisper; whisper.load_model('small')"
```

## ✅ Vérification

Après installation, vérifier:

```bash
python -c "import whisper; print('✅ Whisper OK')"
```

Devrait afficher:
```
✅ Whisper OK
```

## 📞 Support

Si le problème persiste:

1. Vérifier Python version: `python --version` (3.8+)
2. Vérifier installation: `pip list | grep whisper`
3. Vérifier connectivité internet (pour télécharger modèles)
4. Consulter: https://github.com/openai/whisper

---

**Status**: ✅ Whisper installé et prêt à l'emploi
**Date**: 25/05/2026
