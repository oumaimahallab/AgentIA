# 📤 Fonctionnalité Upload & Ingestion de Documents

## Vue d'Ensemble

La fonctionnalité d'upload et ingestion de documents permet à l'administrateur du système ChronoBrain d'importer des fichiers (PDF, Word, PowerPoint, texte, audio, vidéo) directement via l'interface web. Ces fichiers sont automatiquement traités et intégrés dans les indices de recherche (FAISS et BM25).

## Architecture

### 1. Frontend (Interface Admin)

**Fichier:** `unified-agent/ui/admin.html` et `admin.js`

- **Zone de dépôt (Drop Zone)**: Accepte les fichiers via drag-and-drop
- **Sélecteur de fichier**: Bouton pour sélectionner manuellement
- **Formats supportés**: PDF, TXT, DOCX, PPTX, MP3, WAV, M4A, MP4, AVI, MOV
- **Affichage du statut**: Tableau avec liste des documents et leurs statuts

**États de document:**
- ⏳ **En attente**: Fichier uploadé, attente de traitement
- ⏳ **En cours**: Ingestion en cours
- ✅ **Ingéré**: Succès
- ❌ **Erreur**: Échec avec message détaillé

### 2. Backend API

**Endpoint:** `POST /api/admin/upload_and_ingest`

```python
# Paramètres
- file: MultipartFile (le fichier à uploader)
- email: string (email admin pour autorisation)

# Réponse Succès (200)
{
    "success": true,
    "message": "Fichier uploadé et ingestion démarrée en arrière-plan."
}

# Réponse Erreur (4xx)
{
    "error": "Description de l'erreur"
}
```

**Validations:**
- Email doit être `admin@inetum.com`
- Fichier ne peut pas être duplicaté (même nom)
- Format de fichier doit être supporté

### 3. Processus d'Ingestion (Background)

**Fonction:** `background_ingest(filepath, filename, db_doc_id)`

**Étapes:**

1. **Mise à jour BD**: Statut → "En cours"

2. **Parsing du fichier**:
   ```
   PDF → PyMuPDF (page par page)
   PowerPoint → python-pptx (slide par slide)
   Word → python-docx (paragraphe)
   Texte → lecture directe
   Audio/Vidéo → Whisper (transcription)
   ```

3. **Chunking**: Le contenu est divisé en fragments (chunks)

4. **Extraction de métadonnées**:
   ```python
   {
       "file_path": str,
       "source_type": SourceType enum,
       "file_name": str,
       "file_size": int,
       "file_hash": SHA256,
       "created_at": datetime,
       "modified_at": datetime,
       "total_pages": int,
       "total_chunks": int,
       "processing_time": float
   }
   ```

5. **Indexation**:
   
   a) **FAISS** (Vector Search)
   ```python
   embeddings = embedder.embed_batch(chunks)  # 384 dimensions
   faiss.add_embeddings(embeddings, metadatas)
   ```
   
   b) **BM25** (Keyword Search)
   ```python
   bm25.add_documents(chunks, metadatas)
   ```

6. **Sauvegarde BD**: Statut → "Ingéré"

7. **Gestion d'erreurs**:
   ```python
   if error:
       Status → "Erreur"
       error_message → BD (truncated à 500 caractères)
   ```

### 4. Base de Données

**Table:** `documents`

```sql
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    filename TEXT,
    status TEXT DEFAULT 'En attente',
    error_msg TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Types de Documents Supportés

| Format | Parser | Notes |
|--------|--------|-------|
| `.pdf` | PyMuPDF | Page par page |
| `.docx` | python-docx | Extraction de texte |
| `.ppt`, `.pptx` | python-pptx | Slide par slide |
| `.txt`, `.md` | Built-in | Lecture directe |
| `.mp3`, `.wav`, `.m4a` | Whisper | Transcription audio |
| `.mp4`, `.avi`, `.mov` | Whisper | Transcription vidéo |

## Flux Complet

```
[Utilisateur Admin]
    ↓
[Interface Admin (admin.html)]
    ↓ Drag-drop ou sélection
[POST /api/admin/upload_and_ingest]
    ↓
[Flask Backend (app.py)]
    ├→ Validation email
    ├→ Vérification doublon
    ├→ Sauvegarde fichier
    ├→ Créer record BD
    └→ Lancer thread
         ↓
    [background_ingest()]
         ├→ Update BD: "En cours"
         ├→ UnifiedIngester.ingest()
         │   ├→ Parse fichier
         │   └→ Retourne chunks + metadata
         ├→ Embeddings (FAISS)
         ├→ Indexation (BM25)
         ├→ Sauvegarde indices
         └→ Update BD: "Ingéré"
         
[Response au client: success]
    ↓
[Affichage en temps réel]
    └→ Tableau docs + statuts
```

## Chemins Importants

- **Uploads**: `unified-agent/ui/uploads/`
- **FAISS Index**: `unified-agent/data/indices/faiss/index.faiss`
- **BM25 Index**: `unified-agent/data/indices/bm25/bm25_index.pkl`
- **Configuration BD**: `.env` (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD)

## Variables d'Environnement

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=root
GROQ_API_KEY=<votre_clé>
```

## Logs et Monitoring

### Console Logs

```
INFO:app:🚀 Chargement de l'Agent Unifié en cours au démarrage... (Patientez)
INFO:retrieval.embeddings:✓ Model chargé (384 dims)
INFO:retrieval.faiss_manager:✓ Index chargé: 4385 vecteurs
INFO:retrieval.bm25_manager:✓ Index BM25 chargé: 4385 documents
INFO:orchestration.agent:Unified Agent initialized
INFO:app:✅ Agent prêt !
```

### Lors d'un Upload

```
DEBUG: Fichier reçu: document.pdf
DEBUG: Sauvegardé dans: uploads/document.pdf
DEBUG: Record BD créé: id=42
DEBUG: Thread ingestion lancé
INFO: ✓ PDF parsé: document.pdf (10 pages, 25 chunks)
INFO: ✅ Ingestion de document.pdf terminée et sauvegardée dans l'index.
```

### En Cas d'Erreur

```
ERROR: ❌ Erreur lors du traitement du fichier
ERROR: ❌ Format de fichier non supporté: .xyz
ERROR: ❌ PDF protégé par mot de passe
ERROR: ❌ Ingestion error: [détail]
```

## Testing

### 1. Via l'Interface Web

1. Ouvrir: `http://localhost:5005/admin`
2. Login: `admin@inetum.com` (password: check `users.db`)
3. Tab: **Documents**
4. Zone de dépôt: Drag-drop un PDF
5. Vérifier statut → "Ingéré"

### 2. Via cURL

```bash
# Upload un fichier
curl -X POST \
  -F "file=@document.pdf" \
  -F "email=admin@inetum.com" \
  http://localhost:5005/api/admin/upload_and_ingest

# Récupérer la liste des documents
curl http://localhost:5005/api/admin/documents?email=admin@inetum.com
```

### 3. Via Base de Données

```sql
-- Vérifier les documents uploadés
SELECT id, filename, status, created_at FROM documents ORDER BY created_at DESC;

-- Voir les erreurs
SELECT id, filename, status, error_msg FROM documents WHERE status='Erreur';

-- Statistiques
SELECT status, COUNT(*) FROM documents GROUP BY status;
```

## Performance

- **FAISS**: ~4385 vecteurs actuellement (384 dimensions chacun)
- **BM25**: ~4385 documents indexés
- **Temps d'ingestion**: Dépend du fichier (généralement <10s pour PDF de 10 pages)
- **Threaded**: N'impacte pas l'interface utilisateur

## Limitations Actuelles

1. **Pas de compression**: Les fichiers volumineux ralentissent l'upload
2. **Pas de validation de contenu**: Les fichiers corrompus génèrent une erreur
3. **Pas de pause/reprendre**: L'ingestion ne peut pas être interrompue
4. **Pas de batch**: Les uploads doivent être faits un par un
5. **Pas de WebSocket**: Le statut n'est pas mis à jour en temps réel (polling nécessaire)

## Améliorations Futures

- [ ] Drag-drop multiple simultané
- [ ] WebSocket pour mise à jour en temps réel
- [ ] Validation de fichier avant upload
- [ ] Compression gzip pendant transmission
- [ ] Pause/reprendre ingestion
- [ ] OCR pour images et PDF scannés
- [ ] Support de formats supplémentaires (Excel, CSV)
- [ ] Chunking intelligent (par section/paragraphe)
- [ ] Deduplication basée sur hash
- [ ] Historique complet avec timestamps

## Troubleshooting

### "Fichier uploadé mais pas d'ingestion"
→ Vérifier les logs console (thread erreur)
→ Vérifier que PostgreSQL est accessible

### "Erreur: format non supporté"
→ Vérifier l'extension du fichier
→ Vérifier que l'outil de parsing est installé

### "PDF protégé par mot de passe"
→ Retirer la protection avant upload
→ Ou utiliser un outil pour déverrouiller

### "Chunks non ingérés dans FAISS/BM25"
→ Vérifier les dossiers `data/indices/`
→ Vérifier que les fichiers ne sont pas en lecture seule

## Fichiers Sources

- **Frontend**: [admin.html](unified-agent/ui/admin.html), [admin.js](unified-agent/ui/admin.js)
- **Backend**: [app.py](unified-agent/ui/app.py) - route `/api/admin/upload_and_ingest`
- **Ingestion**: [unified_ingester.py](unified-agent/ingestion/unified_ingester.py)
- **Database**: [app.py](unified-agent/ui/app.py) - `init_db()` & table `documents`

---

**Version:** 1.0  
**Dernière mise à jour:** Mai 2026  
**Status:** ✅ Production-Ready
