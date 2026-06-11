# 🔐 Admin Upload & Ingestion Temps Réel

**Configuration** : ADMIN UNIQUEMENT  
**Date** : 26/05/2026  
**Status** : ✅ Prêt

## 🎯 Objectif

Admin peut uploader des fichiers et voir l'ingestion **en temps réel** :
- ⏳ **En attente** → Fichier uploadé
- 🔄 **En cours** → Extraction + Indexation
- ✅ **Ingéré** → Prêt à utiliser

## 🚀 Démarrage Rapide

### Étape 1 : Lancer le serveur
```bash
cd unified-agent/ui
python app.py
```

### Étape 2 : Accéder à l'interface admin
```
http://localhost:5005/admin_upload_realtime.html
```

### Étape 3 : Upload un fichier
```
1. Vérifier email : admin@inetum.com ✓
2. Sélectionner fichier (drag-drop ou clic)
3. Cliquer "🚀 Upload & Ingérer"
4. Observer l'ingestion en temps réel
```

## 📊 Flux Complet

```
ADMIN
  ↓
Upload fichier
  ↓
POST /api/admin/upload_and_ingest
  ↓
✓ Fichier sauvegardé
✓ INSERT INTO documents (status = 'En attente')
✓ Thread démarre background_ingest()
✓ Retour document_id
  ↓
Interface ADMIN affiche :
  ⏳ En attente (1-2s)
    ↓
  🔄 En cours (avec animation)
    ↓
  ✅ Ingéré (après 10-30s)
  ↓
📋 Liste actualise automatiquement
```

## 💾 Base de Données

### Table utilisée
**Table** : `documents`

```sql
Colonnes :
- id (PRIMARY KEY)
- filename
- status ('En attente', 'En cours', 'Ingéré', 'Erreur')
- error_msg
- created_at
```

### Exemple données
```
id | filename      | status   | created_at
1  | rapport.pdf   | Ingéré   | 2026-05-26
2  | data.txt      | En cours | 2026-05-26
3  | image.png     | Erreur   | 2026-05-26
```

## 🔌 API Endpoints

### Upload & Ingest
```
POST /api/admin/upload_and_ingest

Request:
  - file: fichier
  - email: admin@inetum.com

Response:
  {
    "success": true,
    "message": "Fichier uploadé et ingestion démarrée..."
  }
```

### Récupérer les documents
```
GET /api/admin/documents?email=admin@inetum.com

Response:
  [
    { id, filename, status, error_msg, created_at },
    ...
  ]
```

## ✨ Fonctionnalités

- ✅ Upload fichiers (PDF, PPT, DOCX, TXT, Audio, Vidéo)
- ✅ Polling temps réel (1.5s)
- ✅ Animations visuelles
- ✅ Affichage de la liste des documents
- ✅ Actualisation automatique
- ✅ Gestion des erreurs
- ✅ Timeout 2 minutes

## 📱 Interface

### Upload Section
- Zone drag-drop ou clic pour sélectionner
- Affichage du fichier sélectionné
- Bouton Upload + Réinitialiser

### Status Section (pendant traitement)
```
🔄 Ingestion en cours
Extraction et traitement du contenu...

[████░░░░░░░] (animation)

Fichier: document.pdf
ID: 123
Temps: 15s
```

### Documents List
- Affiche tous les documents ingérés
- Statut avec couleur
- Date d'upload
- ID Document
- Messages d'erreur si applicable

## 🎨 Animations

- 🔄 **Icon pulsante** pendant "En cours"
- ✅ **Checkmark** animé au final
- 📊 **Barre de progression** indéterminée
- ⚡ **Transitions fluides**

## 🧪 Test Rapide

### Fichier de Test
```bash
# Créer un fichier test
echo "Test ingestion admin" > test.txt

# Ou utiliser un PDF/PPT existant
```

### Observation
1. Upload le fichier
2. Observez : ⏳ → 🔄 → ✅
3. Temps total : 5-30s (selon taille)

## 🔍 Dépannage

### Le statut ne change pas
- Vérifier PostgreSQL lancé
- Vérifier logs de app.py
- Vérifier email = `admin@inetum.com`

### Timeout après 2 min
- Normal pour gros fichiers
- Fichier vidéo = plus longtemps

### Erreur "Format non supporté"
- Essayer TXT ou PDF
- Vérifier format du fichier
- Vérifier dépendances installées

## 📚 Fichiers

- **Interface** : `ui/admin_upload_realtime.html`
- **Backend** : `ui/app.py`
- **Ingestion** : `ingestion/unified_ingester.py`

## ✅ Résumé

**C'est simple pour l'admin** :
1. ✅ Upload un fichier
2. ✅ Voir l'ingestion en temps réel
3. ✅ Voir la liste des documents
4. ✅ Prêt pour l'agent

**Aucune table supplémentaire nécessaire** - On utilise juste `documents` 🎯

---

**Créé le** : 26/05/2026  
**Version** : 1.0  
**Status** : ✅ Admin Ready
