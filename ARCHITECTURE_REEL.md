# 🏗️ Architecture Réelle du Projet (Unified Agent)

Après analyse approfondie de votre code source réel, il apparaît que les dossiers `DataCl` et `ChronoBrain-main` sont des itérations précédentes ou des environnements de test. Le cœur fonctionnel et structuré de votre application réside dans le dossier **`unified-agent`**. 

Voici l'architecture réelle et technique de votre système actuel.

---

## 🧩 1. Structure Globale

Le système est un **Agent RAG (Retrieval-Augmented Generation) Hybride** conçu spécifiquement pour des cas d'usage RH et Documentaires. Il est modulaire, supporte plusieurs LLMs et dispose d'une interface web et CLI.

```mermaid
graph TD
    User([Utilisateur]) --> UI[Interface Web (Flask/app.py)]
    User --> CLI[CLI (main.py)]
    
    UI --> API[API/Orchestrateur]
    CLI --> API
    
    API --> Dispatcher[Dispatcher (orchestration/dispatcher.py)]
    Dispatcher --> Agent[Agent Principal (orchestration/agent.py)]
    
    Agent --> Intent[Détecteur d'Intention (core/intent_detector.py)]
    Agent --> Retrieval[Système de Recherche (retrieval/)]
    Agent --> LLM[Orchestrateur LLM (llm/)]
    Agent --> Tools[Outils Spécifiques (tools/hr_tools.py)]
    
    Retrieval --> BM25[Recherche Mot-Clé (BM25)]
    Retrieval --> FAISS[Recherche Sémantique (FAISS)]
    BM25 --> Merger[Source Merger & Reranker]
    FAISS --> Merger
    
    Merger --> Agent
    
    LLM --> Groq[Client Groq]
    LLM --> Ollama[Client Ollama]
```

---

## 📂 2. Détail des Composants (Dossier `unified-agent`)

### 🎮 A. Points d'Entrée
- **`main.py`** : Interface en ligne de commande (CLI) très complète permettant de lancer l'agent en mode `answer` (question unique), `batch` (fichier de questions), `demo`, ou `setup`.
- **`ui/app.py`** : L'interface graphique web basée sur Flask, accompagnée de ses assets (`index.html`, `script.js`, `style.css`) et sa base d'utilisateurs (`users.db`).

### 🧠 B. Orchestration (`orchestration/`)
- **`dispatcher.py`** : Reçoit les requêtes et décide comment les traiter (mode batch vs single).
- **`agent.py`** : Le cerveau central. Il coordonne la compréhension de la question, la récupération d'informations et la génération de la réponse.

### ⚙️ C. Moteur d'Intelligence (`core/`)
- **`intent_detector.py`** : Analyse la question de l'utilisateur pour comprendre son intention (ex: "Est-ce une question RH ?", "Est-ce une demande de résumé ?").
- **`deduplication.py`** : S'assure que les informations récupérées ne sont pas redondantes avant de les envoyer au LLM.
- **`performance_tracker.py` & `evaluator.py`** : Outils de monitoring pour mesurer les temps de réponse et la qualité.

### 🔎 D. Moteur de Recherche Hybride (`retrieval/`)
Votre système utilise une approche RAG avancée combinant deux méthodes :
- **`faiss_manager.py` & `embeddings.py`** : Recherche dense/sémantique via des vecteurs. Comprend le sens de la phrase.
- **`bm25_manager.py`** : Recherche creuse/par mots-clés. Idéal pour les termes spécifiques ou les acronymes.
- **`hybrid_retriever.py` & `source_merger.py` & `reranker.py`** : Fusionne les résultats de FAISS et BM25, puis les réorganise (reranking) pour ne garder que le contexte le plus pertinent.

### 🤖 E. Couche Modèles de Langage (`llm/`)
- **`llm_orchestrator.py`** : Gère la communication avec les IAs génératives.
- **Support Multi-Modèles** : Implémentations spécifiques pour **Groq** (`groq_client.py`, très rapide via LPU) et **Ollama** (`ollama_client.py`, pour faire tourner des modèles en local).

### 📥 F. Ingestion des Données (`ingestion/` & `storage/`)
- **`unified_ingester.py`** : Logique pour lire, nettoyer et découper (chunking) les documents sources avant de les injecter dans FAISS et BM25.

---

## 💡 3. Analyse et Constatations

1. **Code très propre et professionnel** : Contrairement aux anciens dossiers (`DataCl` qui contient énormément de scripts de debug/tests), `unified-agent` applique le principe de responsabilité unique (SOLID).
2. **Architecture RAG Avancée** : L'utilisation d'un *Hybrid Retriever* avec *Reranking* et *Deduplication* vous place au niveau des standards de production actuels.
3. **Legacy Code** : Les dossiers `ChronoBrain-main` et `DataCl` semblent être des brouillons/archives. Ils ne font plus partie de la boucle d'exécution principale.
