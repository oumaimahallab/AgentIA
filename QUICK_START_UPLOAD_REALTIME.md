# ✅ Checklist - Démarrage Rapide Upload Temps Réel

## 📋 Avant de Commencer

- [ ] Python 3.10+ installé
- [ ] PostgreSQL lancé
- [ ] Variables d'env configurées (.env file)
- [ ] Dependencies installées (`pip install -r requirements.txt`)

## 🚀 Démarrage en 5 Minutes

### Étape 1 : Lancer le Serveur Flask (30 secondes)
```bash
cd unified-agent/ui
python app.py
```

**Résultat attendu** :
```
 * Running on http://localhost:5005
 * WARNING: This is a development server. Do not use it in production.
```

✓ Si vous voyez ceci, passez à l'étape 2.

### Étape 2 : Ouvrir l'Interface (30 secondes)
```
http://localhost:5005/upload_realtime.html
```

**Vous devriez voir** :
- En-tête : "📤 Upload & Ingestion Automatique"
- Formulaire avec email et zone d'upload
- Bouton "🚀 Upload & Ingérer"

✓ Si vous voyez ceci, passez à l'étape 3.

### Étape 3 : Tester un Upload (5 minutes)

**Fichier de test recommandé** :
- Un fichier TXT ou PDF petit (< 10 MB)
- Ou créer un fichier test avec du texte

**Actions** :
1. [ ] Entrer email : `demo@inetum.com`
2. [ ] Sélectionner un fichier test
3. [ ] Cliquer "🚀 Upload & Ingérer"
4. [ ] Observer l'interface

**État 1 - Immédiatement** (< 1 seconde) :
- [ ] Zone de statut apparaît
- [ ] Affiche : "⏳ En attente..."

**État 2 - Après 1-2 secondes** :
- [ ] Statut change à "🔄 En cours"
- [ ] Animation pulsante commence
- [ ] Temps écoulé augmente

**État 3 - Après 10-30 secondes** :
- [ ] Statut change à "✅ Ingéré avec succès!"
- [ ] Affiche nombre de chunks
- [ ] Affiche temps total de traitement

✓ Si vous avez vu ces 3 étapes, ça marche parfaitement! 🎉

## 🧪 Tester Avec le Script Python

Si vous voulez tester automatiquement :

```bash
python test_upload_realtime.py
```

**Menu** :
```
Options :
  1. test_upload       - Teste l'upload avec suivi temps réel
  2. test_documents    - Récupère les documents de l'utilisateur
  3. both              - Lance les deux tests
```

Choisissez `1` ou `3` pour voir le polling en action.

## 📱 Troubleshooting Rapide

### Le serveur ne démarre pas
```
Error: Port 5005 already in use
```
**Solution** : Changer le port dans app.py ou tuer le processus

```bash
# Trouver le processus
netstat -ano | findstr :5005

# Tuer le processus (remplacer PID)
taskkill /PID [PID] /F
```

### L'interface ne s'affiche pas
```
Erreur 404 ou page blanche
```
**Solution** : Vérifier que vous êtes à la bonne URL
- ✓ Correct : `http://localhost:5005/upload_realtime.html`
- ✗ Incorrect : `http://localhost:5005/`

### Le statut ne change pas (reste "En attente")
```
Upload reçu mais rien ne se passe
```
**Solution** :
1. [ ] Vérifier PostgreSQL : `psql -U postgres -c "SELECT 1"`
2. [ ] Vérifier les logs de app.py pour les erreurs
3. [ ] Vérifier que le fichier n'est pas en doublon

### Timeout après 2 minutes
```
Affichage "Timeout" après 120 secondes
```
**Solution** :
- Pour fichiers volumineux, c'est normal
- Augmenter le timeout dans `upload_realtime.html` :
  - Chercher : `if (attempts > 60)`
  - Changer 60 à 120 (4 minutes)

## 📊 Cas de Test Recommandés

### Test 1 : Fichier Texte (Rapide)
```
Fichier : test.txt
Contenu : "Bonjour. Ceci est un test d'ingestion."
Temps attendu : 2-5 secondes
Chunks attendus : 1-2
```

### Test 2 : PDF Petit (Moyen)
```
Fichier : document.pdf (< 1 MB)
Temps attendu : 5-15 secondes
Chunks attendus : 5-10
```

### Test 3 : Vidéo Courte (Complexe)
```
Fichier : video.mp4 (< 50 MB)
Temps attendu : 30-60 secondes
Chunks attendus : 20-50
```

## 🎯 Métriques à Observer

### Performance Attendue
- **Upload** : 0.5-1 secondes
- **Détection statut "En cours"** : 1-2 secondes
- **Indexation** : 5-30 secondes (selon taille)
- **Total** : 10-40 secondes

### Signes Que Ça Marche
- ✅ Icône change de ⏳ à 🔄
- ✅ Animation pulsante visible
- ✅ Temps écoulé augmente régulièrement
- ✅ Final : ✅ avec checkmark animé
- ✅ Chunks affichés au final

### Signes d'Erreur
- ❌ Reste "En attente" > 5 minutes
- ❌ Timeout sans message d'erreur
- ❌ Affichage "❌ Erreur" avec message
- ❌ Pas d'animation

## 🔍 Vérifier les Logs

### Logs Flask (Terminal)
```
Chercher les lignes :
[timestamp] Ingestion utilisateur complète
[timestamp] UPDATE status='En cours'
[timestamp] UPDATE status='Ingéré'
```

### Logs PostgreSQL
```bash
# Vérifier les documents uploadés
psql -U postgres -d postgres -c \
  "SELECT id, filename, status FROM user_documents ORDER BY created_at DESC;"
```

## 📚 Ressources

| Document | Contenu |
|----------|---------|
| [UPLOAD_REALTIME_README.md](./UPLOAD_REALTIME_README.md) | Guide complet |
| [UPLOAD_REALTIME_SUMMARY.md](./UPLOAD_REALTIME_SUMMARY.md) | Résumé visuel |
| [UPLOAD_REALTIME_GUIDE.md](./unified-agent/ui/UPLOAD_REALTIME_GUIDE.md) | Détails techniques |
| [upload_realtime.html](./unified-agent/ui/upload_realtime.html) | Source de l'interface |
| [test_upload_realtime.py](./test_upload_realtime.py) | Script de test |

## 🎓 Prochaines Étapes

Après que ça marche :

1. [ ] Lire [UPLOAD_REALTIME_README.md](./UPLOAD_REALTIME_README.md) pour les détails
2. [ ] Tester avec différents types de fichiers
3. [ ] Comprendre comment l'agent utilise les documents
4. [ ] Personnaliser l'interface si souhaité (voir GUIDE)
5. [ ] Intégrer avec votre système de production

## ❓ Questions Fréquentes

**Q: Ça marche avec quel navigateur?**  
A: Chrome, Firefox, Edge, Safari (tous modernes)

**Q: Ça marche en production?**  
A: Oui, mais remplacer le serveur Flask par Gunicorn/uWSGI

**Q: Les uploads sont sauvegardés?**  
A: Oui, dans `unified-agent/ui/uploads/` et en BD PostgreSQL

**Q: Comment utiliser les documents avec l'agent?**  
A: L'agent les récupère automatiquement de la BD lors des requêtes

**Q: Peut-on uploader plusieurs fichiers?**  
A: Actuellement un par un, mais multi-upload est possible à ajouter

**Q: Combien de temps pour les vidéos?**  
A: Dépend de la durée. Whisper transcrit en quasi-temps-réel.

## ✅ Checklist Finale

- [ ] Serveur Flask lancé
- [ ] Interface accessible
- [ ] Upload test réussi
- [ ] Statut passe de "En attente" à "En cours" à "Ingéré"
- [ ] Animation pulsante visible
- [ ] Chunks affichés
- [ ] Temps total affiché

**Si tous les checkboxes sont cochés : SUCCÈS! 🎉**

---

**Créé le** : 26/05/2026  
**Durée estimée** : 5-10 minutes  
**Difficulté** : ⭐ Très facile  
**Support** : Voir UPLOAD_REALTIME_README.md
