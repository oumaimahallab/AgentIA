# 🧪 Guide de Test - Upload & Ingestion

## Préparation

### 1. Vérifier que PostgreSQL est en cours d'exécution

```powershell
# Vérifier si PostgreSQL écoute sur le port 5432
Test-NetConnection -ComputerName localhost -Port 5432

# OU via PowerShell
netstat -ano | findstr :5432
```

Si pas de PostgreSQL, vous devez l'installer ou utiliser une base de données alternative.

### 2. Démarrer le serveur Flask

```powershell
# Se positionner dans le dossier du projet
cd C:\Users\maup10458\Desktop\AG

# Activer venv
& .\.venv\Scripts\Activate.ps1

# Vérifier que Python fonctionne
python --version
# Résultat attendu: Python 3.14.3

# Démarrer le serveur
cd unified-agent\ui
python app.py
```

**Résultat attendu:**
```
 * Running on http://localhost:5005
 * Press CTRL+C to quit
```

## Test 1: Upload Simple (PDF)

### Étape 1: Se connecter à l'interface admin

1. Ouvrir navigateur: `http://localhost:5005/admin`
2. Email: `admin@inetum.com`
3. Password: *(vérifier dans `users.db` ou `.env`)*

### Étape 2: Accéder à la section Documents

1. Cliquer sur l'onglet "Documents" dans la navigation de gauche
2. Voir la zone de dépôt avec "Glissez-déposez un fichier ici"

### Étape 3: Upload un fichier test

**Option 1: Drag-drop**
- Ouvrir l'Explorateur de fichiers
- Trouver un PDF de test
- Glisser-déposer dans la zone

**Option 2: Clic bouton**
- Cliquer "Sélectionner un fichier"
- Choisir un PDF
- Confirmer

### Étape 4: Vérifier la progression

**Console serveur:**
```
[INFO] Fichier reçu: test.pdf
[INFO] Record BD créé: id=123
[INFO] Thread ingestion lancé
[INFO] ✓ PDF parsé: test.pdf (5 pages, 12 chunks)
[INFO] ✅ Ingestion de test.pdf terminée
```

**Interface admin:**
- Zone show: "Upload de test.pdf en cours..."
- Barre de progression

### Étape 5: Vérifier le statut final

1. Attendre quelques secondes
2. Table "Documents Inscrits" show:
   - Nom: `test.pdf`
   - Statut: ✅ **Ingéré** (badge vert)
3. Toast notification: "Fichier uploadé avec succès"

## Test 2: Upload Fichier Non Supporté

### Étape 1: Essayer upload format interdit

- Uploader un fichier `.exe`, `.zip`, etc.
- Observer l'erreur

**Résultat attendu:**
```
Toast: "Erreur réseau: ..."
OU
Statut: ❌ "Erreur"
Message: "Format de fichier non supporté: .xyz"
```

## Test 3: Upload Doublon (Même fichier deux fois)

### Étape 1: Upload un fichier

- Uploader `rapport.pdf`
- Attendre que le statut soit "Ingéré"

### Étape 2: Réessayer upload du même fichier

- Uploader `rapport.pdf` à nouveau
- Observer le rejet

**Résultat attendu:**
```
Toast Error: "Le fichier 'rapport.pdf' est déjà uploadé. L'ingestion est annulée."
HTTP: 409 Conflict
```

## Test 4: Upload Fichier Multipage (PDF)

### Étape 1: Uploader un PDF avec plusieurs pages

- Utiliser un PDF avec 10+ pages
- Observer la progression

### Étape 2: Vérifier les logs

**Console serveur:**
```
[INFO] ✓ PDF parsé: rapport.pdf (15 pages, 35 chunks)
```

### Étape 3: Vérifier l'indexation

```sql
-- Vérifier que les chunks sont dans FAISS
SELECT COUNT(*) FROM vectors WHERE source='rapport.pdf';
-- Résultat attendu: ~35 rows

-- Vérifier dans BM25
SELECT COUNT(*) FROM documents_indexed WHERE source='rapport.pdf';
-- Résultat attendu: ~35 rows
```

## Test 5: Upload Fichier Word (.docx)

### Étape 1: Uploader un fichier Word

- Créer un fichier `.docx` test
- Uploader via l'interface

### Étape 2: Vérifier le traitement

**Console:**
```
[INFO] ✓ Word parsé: document.docx
[INFO] ✅ Ingestion de document.docx terminée
```

## Test 6: Upload PowerPoint (.pptx)

### Étape 1: Uploader une présentation

- Créer un fichier `.pptx` test (3-5 slides)
- Uploader

### Étape 2: Vérifier le traitement

**Console:**
```
[INFO] ✓ PowerPoint parsé: presentation.pptx (5 slides)
```

**Résultat:** 1 chunk par slide

## Test 7: Upload Audio/Vidéo (Transcription)

### Étape 1: Uploader un MP3 ou MP4

- Trouver un fichier audio/vidéo court (< 5 min)
- Uploader

### Étape 2: Attendre la transcription

⚠️ **Attention:** La transcription prend du temps!

```
[INFO] Transcribing audio: demo.mp3
[INFO] Transcription completed
[INFO] ✓ Transcription chunk généré
```

### Étape 3: Vérifier le résultat

- Statut: "Ingéré"
- Chunks indexés dans FAISS/BM25

## Test 8: Vérifier Base de Données

### Ouvrir PostgreSQL

```powershell
# Vérifier les documents
psql -U postgres -d postgres -c "SELECT * FROM documents ORDER BY created_at DESC LIMIT 10;"

# Voir les statuts
psql -U postgres -d postgres -c "SELECT status, COUNT(*) FROM documents GROUP BY status;"

# Voir les erreurs
psql -U postgres -d postgres -c "SELECT filename, status, error_msg FROM documents WHERE status='Erreur';"
```

## Test 9: Vérifier les Indices FAISS/BM25

### Vérifier les fichiers

```powershell
# Vérifier FAISS
Get-Item "unified-agent\data\indices\faiss\index.faiss"
# Résultat attendu: Fichier existe, taille > 0

# Vérifier BM25
Get-Item "unified-agent\data\indices\bm25\bm25_index.pkl"
# Résultat attendu: Fichier existe, taille > 0
```

### Vérifier la taille des indices

```powershell
# FAISS avant upload
(Get-Item "unified-agent\data\indices\faiss\index.faiss").Length

# FAISS après upload
(Get-Item "unified-agent\data\indices\faiss\index.faiss").Length
# Résultat attendu: Taille augmente après chaque upload
```

## Test 10: Vérifier les Uploads Physiques

```powershell
# Voir les fichiers uploadés
Get-ChildItem "unified-agent\ui\uploads\"

# Résultat attendu:
# - test.pdf
# - rapport.pdf
# - presentation.pptx
# etc.
```

## Test 11: Montrer les Fichiers Uploads dans l'Interface

1. Aller à l'interface admin
2. Tab "Documents"
3. Observer le tableau "Documents Inscrits"

**Colones:**
- ID: ID de base de données
- Nom du fichier: Nom exact du fichier
- Date d'ajout: Timestamp d'upload
- Statut: Ingéré/En cours/Erreur

## Test 12: Test de Performance

### Upload multiple rapide

```powershell
# Uploader 5 fichiers rapidement
# (Attendre que chacun soit "Ingéré" avant le suivant)

1. upload1.pdf → Ingéré
2. upload2.pdf → Ingéré
3. upload3.txt → Ingéré
4. upload4.docx → Ingéré
5. upload5.pptx → Ingéré
```

**Vérifier:**
- Les uploads n'interfèrent pas les uns avec les autres
- Chaque fichier a un ID unique
- Les indices sont corrects à la fin

## Commandes de Debug

### Voir les logs complèts

```powershell
# Redirection vers fichier
cd unified-agent\ui
python app.py 2>&1 | Tee-Object -FilePath debug.log
```

### Vérifier les chunks ingérés

```python
# Dans un script Python
import pickle
from pathlib import Path

bm25_path = Path("unified-agent/data/indices/bm25/bm25_index.pkl")
with open(bm25_path, 'rb') as f:
    bm25_index = pickle.load(f)

print(f"Total docs in BM25: {bm25_index.corpus_size}")
# Résultat attendu: 4385+ (augmente à chaque upload)
```

### Vérifier FAISS

```python
import faiss

faiss_path = "unified-agent/data/indices/faiss/index.faiss"
index = faiss.read_index(faiss_path)
print(f"Total vectors in FAISS: {index.ntotal}")
# Résultat attendu: 4385+ (augmente à chaque upload)
```

## Checklist de Test Complète

- [ ] Serveur démarre sans erreur
- [ ] Interface admin accessible
- [ ] Login admin fonctionne
- [ ] Tab Documents visible
- [ ] Upload PDF fonctionne
- [ ] Upload Word fonctionne
- [ ] Upload PowerPoint fonctionne
- [ ] Upload TXT fonctionne
- [ ] Upload Audio fonctionne
- [ ] Upload Vidéo fonctionne
- [ ] Rejet format non-supporté
- [ ] Rejet doublon
- [ ] Statuts mise à jour correctement
- [ ] BD enregistre les documents
- [ ] FAISS index augmente
- [ ] BM25 index augmente
- [ ] Erreurs s'affichent correctement
- [ ] Console logs sont clairs

## Résolution de Problèmes

### Problème: Serveur ne démarre pas

```
Solution:
1. Vérifier que venv est activée
2. Vérifier python --version = 3.14.3
3. Vérifier que pip list montre les packages
4. Relancer: pip install -r requirements.txt
```

### Problème: "Cannot connect to database"

```
Solution:
1. Vérifier que PostgreSQL est en cours d'exécution
2. Vérifier credentials dans .env
3. psql -U postgres pour tester connexion
4. Si pas de PostgreSQL, installer ou configurer SQLite
```

### Problème: Upload réussit mais pas d'ingestion

```
Solution:
1. Vérifier les logs console pour erreurs
2. Vérifier table documents (SELECT * FROM documents)
3. Vérifier permissions répertoire uploads/
4. Vérifier disque dur pas plein
5. Vérifier fichier n'est pas corrompu
```

### Problème: PDF protégé par mot de passe

```
Solution:
1. Le système rejettera les PDFs protégés
2. Résultat attendu:
   Statut: "Erreur"
   Message: "PDF protégé par mot de passe"
```

## Métriques de Succès

✅ **Upload**: Fichier reçu et sauvegardé
✅ **Parsing**: Fichier parsé en chunks
✅ **Embedding**: Chunks convertis en vecteurs
✅ **Indexation**: Chunks ajoutés à FAISS + BM25
✅ **BD**: Record créé avec statut "Ingéré"
✅ **Interface**: Utilisateur voit le fichier en liste

---

**Pour chaque test réussi, marquer la date et l'heure dans la checklist**

---

**Version:** 1.0  
**Date:** Mai 2026
