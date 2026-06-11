# 📤 Système Upload & Ingestion Temps Réel

**Version** : 1.0  
**Date** : 26/05/2026  
**Status** : ✅ Production Ready

## 🎯 Objectif

Permettre aux utilisateurs de voir **en temps réel** l'état du processus d'ingestion de leurs fichiers :

```
Upload fichier → ⏳ En attente → 🔄 En cours → ✅ Ingéré
```

## 📁 Fichiers Créés/Modifiés

### Créés
1. **`ui/upload_realtime.html`** (500+ lignes)
   - Interface d'upload améliorée
   - Affichage temps réel du statut
   - Animations et progressions visuelles

2. **`ui/UPLOAD_REALTIME_GUIDE.md`** (250+ lignes)
   - Guide complet d'utilisation
   - Explications du flux
   - Personnalisation

3. **`test_upload_realtime.py`** (200+ lignes)
   - Script de test automatisé
   - Polling temps réel
   - Affichage des statuts

### Non Modifiés (Déjà OK)
- ✅ `ui/app.py` - Routes API fonctionnelles
- ✅ `ingestion/unified_ingester.py` - Ingestion OK

## 🚀 Démarrage Rapide

### 1. Lancer le Serveur

```bash
# Option A: Direct
cd unified-agent/ui
python app.py

# Option B: Avec logs détaillés
cd unified-agent/ui
python app.py --debug
```

Le serveur démarre sur `http://localhost:5005`

### 2. Accéder à l'Interface

```
http://localhost:5005/upload_realtime.html
```

### 3. Uploader un Fichier

```
1. Email : demo@inetum.com (ou votre email)
2. Session ID : (optionnel)
3. Sélectionner fichier
4. Cliquer "🚀 Upload & Ingérer"
5. Observer le statut en temps réel
```

## 📊 États du Processus

### Timeline Complète

```
t=0s      : Upload du fichier
            ↓
            Status = "En attente"
            Interface : ⏳ Préparation...

t+0.1s    : Thread démarre
            ↓
            Status = "En cours"
            Interface : 🔄 Ingestion en cours
                        Barre de progression animée

t+5-30s   : Extraction, nettoyage, indexation
            Interface : Temps écoulé augmente
                        Animation continue

t+final   : Traitement terminé
            ↓
            Status = "Ingéré"
            Interface : ✅ Ingéré avec succès!
                        Affiche number de chunks
```

### Statuts Possibles

| Statut | Icône | Couleur | Signification |
|--------|-------|--------|---|
| **En attente** | ⏳ | Jaune | Fichier uploadé, en attente de traitement |
| **En cours** | 🔄 | Bleu | Extraction + Nettoyage + Indexation |
| **Ingéré** | ✅ | Vert | Traitement terminé, prêt pour l'agent |
| **Erreur** | ❌ | Rouge | Une erreur s'est produite (details affichés) |

## 🔍 Détails du Flux

### Backend (app.py)

```python
@app.route('/api/user/upload_and_ingest', methods=['POST'])
def user_upload_and_ingest():
    """
    1. Validation du fichier
    2. Hash du fichier (vérifier duplicata)
    3. Sauvegarde du fichier
    4. INSERT dans BD : user_documents(status='En attente')
    5. Retour document_id
    6. Lance thread background_ingest_user()
    """
    # Retour immédiat au client
    return {
        'success': True,
        'document_id': db_doc_id,
        'status': 'processing'
    }

def background_ingest_user(filepath, filename, user_email, session_id, db_doc_id):
    """
    Exécuté dans un thread séparé
    """
    # Phase 1 : UPDATE status = 'En cours'
    # → Le client voit le changement au prochain polling
    
    # Phase 2 : Extraction
    ingester = UnifiedIngester(language="fr", clean_text=True, extract_entities=True)
    chunks_text, metadata = ingester.ingest(filepath)
    
    # Phase 3 : Indexation
    # - FAISS (recherche vectorielle)
    # - BM25 (recherche textuelle)
    
    # Phase 4 : Sauvegarde
    # - Stockage BD : chunks, keywords, entities
    
    # Phase 5 : UPDATE status = 'Ingéré'
    # → Le client reçoit le statut final
```

### Frontend (upload_realtime.html)

```javascript
// 1. Upload
const response = await fetch('/api/user/upload_and_ingest', {
    method: 'POST',
    body: formData
});

const result = response.json();
document.getElementById('document_id') = result.document_id;

// 2. Polling (chaque 1.5 secondes)
async function pollStatus(email, attempts = 0) {
    const doc = await fetch(`/api/user/documents/${docId}?email=${email}`);
    
    if (doc.status === 'En attente')
        setStatus('⏳ En attente', 'pending');
    
    if (doc.status === 'En cours')
        setStatus('🔄 En cours', 'processing');
        // Affiche animation pulsante
    
    if (doc.status === 'Ingéré')
        setStatus('✅ Ingéré!', 'success');
        // Affiche checkmark animé
        // Affiche total chunks et temps
    
    if (doc.status === 'Erreur')
        setStatus('❌ Erreur', 'error');
        // Affiche message d'erreur
}

// 3. Continue polling toutes les 1.5s
setTimeout(() => pollStatus(email, attempts + 1), 1500);
```

## 🧪 Testing

### Via Interface Web (Recommandé)

```
1. http://localhost:5005/upload_realtime.html
2. Entrer email et sélectionner fichier
3. Cliquer Upload
4. Observer l'évolution du statut
```

### Via Script Python

```bash
# Lancer le test automatisé
python test_upload_realtime.py

# Choix au menu :
# 1. Test upload avec suivi temps réel
# 2. Lister tous les documents
# 3. Les deux
```

### Via cURL

```bash
# Upload
curl -X POST http://localhost:5005/api/user/upload_and_ingest \
  -F "file=@document.pdf" \
  -F "email=demo@inetum.com" \
  -F "session_id=test-123"

# Récupérer statut
curl http://localhost:5005/api/user/documents/1?email=demo@inetum.com
```

## 📈 Performance et Paramètres

### Intervalle de Polling
- **Défaut** : 1.5 secondes
- **Peut être changé** dans `upload_realtime.html`
- Moins = Plus réactif mais plus de charge
- Plus = Moins de requêtes mais moins réactif

### Timeout
- **Défaut** : 2 minutes (60 tentatives × 1.5s)
- Après 2 minutes : Abandon et affichage "Timeout"
- Peut être augmenté pour fichiers très volumineux

### Formats Supportés

#### Documents
```
✓ PDF
✓ PPT, PPTX
✓ DOCX
✓ TXT
✓ Markdown (.md)
```

#### Média
```
✓ Vidéo : MP4, AVI, MOV
✓ Audio : MP3, WAV, M4A
✓ Images : PNG, JPG, BMP, etc.
```

## 📡 API Endpoints

### Upload & Ingest
```
POST /api/user/upload_and_ingest

Request:
  - file: fichier à traiter
  - email: utilisateur@email.com
  - session_id: (optionnel) uuid-session

Response:
  {
    "success": true,
    "document_id": 123,
    "message": "Fichier uploadé. Extraction en cours...",
    "status": "processing"
  }
```

### Récupérer un Document
```
GET /api/user/documents/{doc_id}?email=utilisateur@email.com

Response:
  {
    "id": 123,
    "filename": "document.pdf",
    "file_type": "pdf",
    "file_size": 256000,
    "status": "En cours",
    "total_chunks": 15,
    "processing_time": 12.5,
    "language": "fr",
    "keywords": ["keyword1", "keyword2", ...],
    "extracted_entities": { "emails": [...], "urls": [...] },
    "error_msg": null,
    ...
  }
```

### Lister les Documents
```
GET /api/user/documents?email=utilisateur@email.com&session_id=uuid

Response: Array of documents
  [
    { id, filename, status, total_chunks, ... },
    ...
  ]
```

## 🎨 Animations et UX

### Icônes Animées
- **🔄 En cours** : Rotation continue (pulse)
- **✅ Ingéré** : Checkmark déployé avec zoom
- **⏳ En attente** : Statique
- **❌ Erreur** : Statique avec couleur rouge

### Barre de Progression
- **Pendant En cours** : Animation indéterminée
- **Après Ingéré** : Remplit à 100%

### Transitions
- Slide-in des statuts
- Fade des alertes
- Animations de couleur

## 🔧 Personnalisation

### Modifier l'Intervalle de Polling

```javascript
// Dans upload_realtime.html, function pollStatus()
// Chercher :
pollInterval = setTimeout(() => pollStatus(email, attempts + 1), 1500);
// 1500 ms = 1.5 secondes
// Changer à 1000 (1s) ou 3000 (3s) selon besoin
```

### Changer les Couleurs

```css
/* Dans les styles de upload_realtime.html */
.status-processing {
    border-left: 4px solid #007bff;  /* Couleur bleue */
    background: #e7f3ff;
}
```

### Ajouter des Statuts Supplémentaires

```javascript
if (doc.status === 'Validation')
    setStatus('🔍 Validation en cours...', 'processing');
```

## 📊 Stockage et Métadonnées

### Table `user_documents`
```sql
- id : PRIMARY KEY
- user_email : Utilisateur propriétaire
- session_id : Session associée
- filename : Nom du fichier
- file_type : Extension (pdf, txt, etc.)
- file_size : Taille en bytes
- file_hash : SHA256 pour déduplica
- status : 'En attente' | 'En cours' | 'Ingéré' | 'Erreur'
- total_chunks : Nombre de chunks générés
- processing_time : Temps de traitement
- keywords : JSON array
- extracted_entities : JSON object
- error_msg : Message d'erreur si applicable
```

## 🔐 Sécurité

- ✅ Vérification du hash de fichier (déduplica)
- ✅ Email requis pour tous les accès
- ✅ Séparation utilisateur-admin
- ✅ Vérification des formats de fichier
- ✅ Timeout de connexion

## 🐛 Dépannage

### Le statut ne change pas

**Symptôme** : Reste sur "En attente"

**Solutions** :
1. Vérifier que PostgreSQL est lancé
2. Vérifier les logs de app.py
3. Vérifier la taille du fichier
4. Vérifier la console du navigateur (F12)

### Timeout après 2 minutes

**Symptôme** : Affichage "Timeout"

**Solutions** :
1. Pour gros fichiers : augmenter le timeout
2. Vérifier les ressources système
3. Vérifier les logs du serveur

### Erreur "Format non supporté"

**Symptôme** : Status = "Erreur"

**Solutions** :
1. Essayer avec un PDF ou TXT
2. Vérifier l'extension du fichier
3. Vérifier que les dépendances sont installées (whisper, pdf2image, etc.)

### Fichier ne s'upload pas

**Symptôme** : Rien ne se passe après clic Upload

**Solutions** :
1. Vérifier la taille du fichier
2. Vérifier l'email est renseigné
3. Vérifier que le serveur est accessible
4. Ouvrir la console (F12) pour voir les erreurs

## 📈 Prochaines Améliorations Possibles

- [ ] **WebSocket** : Push updates au lieu de polling
- [ ] **Multi-upload** : Plusieurs fichiers simultanément
- [ ] **Progress détaillé** : Étapes du traitement
- [ ] **Historique** : Voir tous les uploads précédents
- [ ] **Prévisualisation** : Voir le contenu extrait
- [ ] **Export** : Télécharger les chunks/keywords
- [ ] **Retry** : Relancer les uploads échoués
- [ ] **Bulk actions** : Supprimer/rejouer plusieurs docs

## 📚 Documentation Supplémentaire

- [UPLOAD_REALTIME_GUIDE.md](./ui/UPLOAD_REALTIME_GUIDE.md) - Guide détaillé
- [app.py](./ui/app.py) - Routes API
- [unified_ingester.py](./ingestion/unified_ingester.py) - Moteur d'ingestion
- [text_cleaner.py](./ingestion/text_cleaner.py) - Nettoyage texte

## 👥 Support

Pour des questions ou signaler des bugs :
1. Ouvrir un issue sur le repo
2. Vérifier les logs : `unified-agent/ui/app.log`
3. Consulter la documentation
4. Tester avec le script `test_upload_realtime.py`

---

**Créé le** : 26/05/2026  
**Version** : 1.0  
**Statut** : ✅ Prêt pour production  
**Testé sur** : Python 3.10+, PostgreSQL 12+, Flask 2.3+
