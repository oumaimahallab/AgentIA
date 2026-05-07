# Guide de Fonctionnement du Projet

Ce guide explique l'organisation réelle des fichiers et la logique du code dans le dossier `unified-agent`.

## 1. Organisation des Dossiers

- **`config/`** : Centralisation de tous les paramètres (chemins, modèles, seuils de score).
- **`core/`** : Intelligence de base, notamment le `intent_detector.py` qui classe les questions par type (Définition, Procédure, etc.).
- **`retrieval/`** : Le moteur de recherche.
    - `embeddings.py` : Transforme le texte en vecteurs.
    - `faiss_manager.py` : Gère la base de données vectorielle.
    - `bm25_manager.py` : Gère la recherche par mots-clés.
    - `hybrid_retriever.py` : Fusionne les deux types de recherche.
    - `source_merger.py` : Nettoie et groupe les résultats trouvés.
- **`llm/`** : Communication avec l'IA.
    - `groq_client.py` : Client principal avec gestion automatique des erreurs 429.
    - `llm_orchestrator.py` : Prépare les prompts et choisit le modèle.
- **`scripts/`** : Outils de maintenance.
    - `rebuild_unified_index.py` : Le script à lancer pour mettre à jour la base de connaissances.

## 2. Processus d'Interrogation (Étape par Étape)

Quand vous posez une question :

1. **Détection** : L'agent identifie si vous voulez une définition ou une procédure (`IntentDetector`).
2. **Recherche** : Il cherche dans FAISS et BM25 simultanément pour trouver les extraits les plus pertinents.
3. **Fusion** : Il supprime les doublons en utilisant les fingerprints SHA-256 (`SourceMerger`).
4. **Réflexion** : Il envoie le contexte au modèle Llama-3 via Groq.
5. **Réponse** : Il vous affiche la réponse en citant les sources trouvées.

## 3. Maintenance de la Base de Données

Pour mettre à jour les connaissances de l'agent :
1. Placez vos nouveaux documents dans les dossiers sources.
2. Lancez `python scripts/rebuild_unified_index.py`.
3. Le script va automatiquement :
    - Filtrer les textes trop courts.
    - Extraire les sujets des fichiers.
    - Reconstruire les deux index (Vecteurs et Mots-clés).

## 4. Outils HR (Tools)

Le fichier `tools/hr_tools.py` contient des fonctions mathématiques pour les calculs de congés et de jours ouvrés. Bien que l'agent soit capable de les utiliser, il privilégie actuellement la réponse basée sur les documents pour garantir la fidélité aux sources Chronotime.
