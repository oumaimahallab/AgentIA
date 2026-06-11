# 📤 Interface Upload Temps Réel - Guide Complet

## Vue d'ensemble

Une **nouvelle interface d'upload améliorée** qui affiche en **temps réel** l'état du processus d'ingestion :

- **✅ "En attente"** → Le fichier vient d'être uploadé
- **🔄 "En cours"** → Extraction, nettoyage et indexation en arrière-plan
- **✅ "Ingéré"** → Fichier traité et prêt pour les requêtes
- **❌ "Erreur"** → Affichage du message d'erreur

## Fichier

- **Interface** : [upload_realtime.html](../ui/upload_realtime.html)
- **URL** : `http://localhost:5005/upload_realtime.html`

## Fonctionnalités

### 1. **Visualisation en Temps Réel** ⏱️

```
État du processus :
┌─────────────────────────────────────────┐
│ 🔄 Ingestion en cours                   │
│ Extraction et traitement du contenu...  │
│                                         │
│ [████░░░░░░░░░░░░░░░░░░░░░] (animation)│
│                                         │
│ Fichier: document.pdf                   │
│ Taille: 256.5 KB                        │
│ Chunks: -                               │
│ Temps: 12s                              │
└─────────────────────────────────────────┘
```

### 2. **Animations Visuelles**

- **Icône pulsante** 🔄 pendant l'ingestion "En cours"
- **Barre de progression** animée
- **Checkmark** ✅ qui se déploie quand c'est terminé
- **Transitions fluides** entre les états

### 3. **Polling Automatique**

- Vérifie l'état **toutes les 1.5 secondes**
- Affiche les mises à jour progressives
- Timeout après **2 minutes** max

### 4. **Détails en Temps Réel**

Affiche pendant le traitement :
- 📄 **Nom du fichier**
- 📊 **Taille du fichier**
- 🔗 **Nombre de chunks** (mis à jour à la fin)
- ⏱️ **Temps écoulé** (en secondes)

## Processus Complet

### Backend (app.py)

```python
@app.route('/api/user/upload_and_ingest', methods=['POST'])
def user_upload_and_ingest():
    # 1. Validation et hash du fichier
    # 2. Insertion BD : status = 'En attente'
    # 3. Retour document_id
    # 4. Lance thread background_ingest_user()
    
def background_ingest_user(...):
    # Phase 1: UPDATE status = 'En cours' ← Polling voit cela
    # Phase 2: Extraction du contenu
    # Phase 3: Nettoyage texte
    # Phase 4: Indexation FAISS + BM25
    # Phase 5: UPDATE status = 'Ingéré' ← Polling voit cela
```

### Frontend (upload_realtime.html)

```javascript
// 1. Upload le fichier
fetch('/api/user/upload_and_ingest', { method: 'POST', body: formData })

// 2. Reçoit document_id
// 3. Lance pollStatus() chaque 1.5s

async function pollStatus(email) {
    const doc = await fetch(`/api/user/documents/${docId}?email=${email}`)
    
    if (doc.status === 'En cours')
        → Affiche 🔄 avec animation
    else if (doc.status === 'Ingéré')
        → Affiche ✅ avec details finaux
    else if (doc.status === 'Erreur')
        → Affiche ❌ avec message d'erreur
}
```

## Utilisation

### 1. **Accéder à l'Interface**

```
http://localhost:5005/upload_realtime.html
```

### 2. **Uploder un Fichier**

```
1. Entrer email : demo@inetum.com
2. (Optionnel) Entrer session_id
3. Sélectionner un fichier (drag-drop ou clic)
4. Cliquer "🚀 Upload & Ingérer"
5. Observer le statut en temps réel
```

### 3. **États Possibles**

| Statut | Icône | Couleur | Action |
|--------|-------|--------|--------|
| En attente | ⏳ | Jaune | Attend le traitement |
| En cours | 🔄 | Bleu | Extraction + nettoyage |
| Ingéré | ✅ | Vert | Fichier prêt |
| Erreur | ❌ | Rouge | Affiche erreur |

## Formats Supportés

### Documents
- ✅ PDF
- ✅ PPT / PPTX
- ✅ DOCX
- ✅ TXT
- ✅ Markdown

### Media
- ✅ MP4 / AVI / MOV (vidéo)
- ✅ MP3 / WAV / M4A (audio)
- ✅ Images (PNG, JPG, etc.)

## Informations Affichées

### Pendant le traitement
```
✓ Nom du fichier
✓ Taille du fichier
✓ Temps écoulé (en secondes)
✓ État du statut
```

### Après traitement
```
✓ Tous les éléments ci-dessus +
✓ Nombre total de chunks
✓ Temps de traitement total
✓ Keywords extraits (dans API)
```

## Flux Complet Timeline

```
t=0s    : Upload fichier → status = "En attente"
t+0.1s  : Thread démarre → status = "En cours"
          Interface affiche 🔄 avec animation
          
t+5-30s : Extraction + Nettoyage + Indexation
          Barre de progression animée
          Temps écoulé augmente
          
t+30s   : Fin du traitement → status = "Ingéré"
          Interface affiche ✅ avec checkmark animé
          Affiche nombre total de chunks
          Affiche temps total
```

## Personnalisation

### Changer l'intervalle de polling

```javascript
// Dans upload_realtime.html, ligne ~450
pollInterval = setTimeout(() => pollStatus(email, attempts + 1), 1500); // 1.5s
// Changer 1500 à une autre valeur en ms
```

### Changer le timeout

```javascript
// Dans upload_realtime.html, ligne ~426
if (attempts > 60) { // 2 minutes max
    // Changer 60 à un autre nombre
    // 60 * 1.5s = 90s (1.5 minutes)
}
```

## Intégration avec l'Agent

Les documents uploadés sont automatiquement :
1. ✅ Indexés en FAISS (recherche vectorielle)
2. ✅ Indexés en BM25 (recherche textuelle)
3. ✅ Stockés en PostgreSQL avec métadonnées
4. ✅ Disponibles pour les requêtes de l'agent

L'agent peut utiliser `user_documents` table pour :
- Récupérer les chunks filtrés par utilisateur
- Extraire les keywords et entités
- Afficher les sources des réponses

## Dépannage

### Le statut reste "En attente"

→ Vérifier que la base de données PostgreSQL est accessible
→ Vérifier les logs de l'application Flask

### Le polling s'arrête avant "Ingéré"

→ Augmenter le timeout (voir "Personnalisation")
→ Vérifier la taille du fichier (fichiers très gros prennent plus de temps)

### Erreur "Format non supporté"

→ Vérifier que le format du fichier est dans la liste supportée
→ Essayer avec un PDF ou TXT d'abord

## API Endpoints Utilisés

```
POST /api/user/upload_and_ingest
- Input: file, email, session_id (optionnel)
- Output: { success, document_id, status }

GET /api/user/documents/<doc_id>
- Input: email (query param)
- Output: { id, filename, status, total_chunks, ... }
```

## Fonctionnalités Futures Possibles

- [ ] Barre de progression basée sur le nombre de fichiers
- [ ] WebSocket pour les mises à jour en push (plus rapide que polling)
- [ ] Historique des uploads
- [ ] Prévisualisation du contenu
- [ ] Pause/Reprise d'ingestion
- [ ] Bulk upload multiple fichiers
- [ ] Importation depuis Google Drive / OneDrive

---

**Date de création** : 26/05/2026  
**Version** : 1.0  
**Status** : ✅ Prêt pour test
