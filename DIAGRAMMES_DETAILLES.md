# 📊 Évolution et Diagrammes Détaillés des Architectures

Ce document détaille l'architecture des deux projets initiaux (`ChronoBrain-main` et `DataCl`), puis montre comment leurs concepts ont été fusionnés pour créer l'architecture finale et robuste de `unified-agent`.

---

## 1️⃣ Projet : ChronoBrain-main (L'approche locale & Llama-Index)
**Objectif initial** : Un agent 100% local, très scripté (ex: `v11.py`), utilisant `llama-index` et `ollama`.

**Caractéristiques clés :**
- **LLM** : Ollama (modèle Llama3 en local).
- **Vector Store** : ChromaDB (stockage persistant).
- **Embedding** : HuggingFace (`BAAI/bge-small-en-v1.5`).
- **Hybridation basique** : Fusion manuelle de ChromaDB (sémantique) et BM25 (mots-clés).
- **Outils intégrés** : Cache simple en mémoire, traqueur de performance, et vérificateur de fidélité (anti-hallucination).

```mermaid
graph TD
    subgraph "ChronoBrain-main (Ex: v11.py)"
        User([Utilisateur]) --> CLI[Terminal CLI]
        
        CLI --> Cache{SimpleCache}
        Cache -- "Hit" --> User
        Cache -- "Miss" --> Hybrid[Hybrid Retrieval]
        
        Hybrid --> Chroma[(ChromaDB)]
        Hybrid --> BM25[(Fichier BM25 .pkl)]
        
        Chroma -- "Recherche Sémantique" --> Hybrid
        BM25 -- "Recherche Mots-Clés" --> Hybrid
        
        Hybrid --> Prompt[Prompt Builder]
        
        Prompt --> Ollama[[Ollama (Llama3 Local)]]
        
        Ollama --> PostProc[Hallucination Stripper & Faithfulness Check]
        PostProc --> Tracker[Performance Tracker]
        Tracker --> Cache
        Tracker --> User
    end
```

---

## 2️⃣ Projet : DataCl (L'approche Cloud, Groq & Intentions)
**Objectif initial** : Un agent extrêmement rapide et intelligent, prêt pour la production, basé sur la classification des intentions et l'API Groq.

**Caractéristiques clés :**
- **LLM** : Groq API (`llama-3.1-8b-instant`), extrêmement rapide.
- **Vector Store** : FAISS (CPU, en mémoire/fichiers).
- **Embedding** : Sentence-Transformers (`all-MiniLM-L6-v2`).
- **Intelligence** : Module de détection d'intention (Procédure, Définition, Énumération, Explication).
- **Adaptabilité** : Le prompt change dynamiquement en fonction de l'intention détectée.

```mermaid
graph TD
    subgraph "DataCl (Agent Universel V2)"
        User([Utilisateur]) --> Input[ask_agent()]
        
        Input --> Intent[Détection d'Intention]
        
        Intent -- "Type de question ?" --> FAISSRetriever[FAISS Search]
        
        FAISSRetriever --> FAISS[(FAISS Index)]
        FAISS --> Chunks[Classification des Chunks]
        
        Chunks --> PromptBuilder[Adaptive Prompt Builder]
        
        PromptBuilder -- "Prompt spécifique (ex: Procédure)" --> Groq[[Groq API]]
        
        Groq --> Fallback[Fallback & Error Handling]
        Fallback --> User
    end
```

---

## 3️⃣ Projet : Unified-Agent (La Fusion Parfaite)
**Objectif final** : Prendre la robustesse du code de `DataCl`, la recherche hybride de `ChronoBrain`, et englober le tout dans une architecture logicielle moderne, modulaire (SOLID), avec une interface web (Flask).

**Comment ça combine les deux ?**
1. **Multi-LLM (`llm_orchestrator`)** : Permet de choisir entre Groq (venant de DataCl) et Ollama (venant de ChronoBrain).
2. **Hybrid RAG (`hybrid_retriever`)** : Combine la vitesse de FAISS (DataCl) avec la précision mot-clé de BM25 (ChronoBrain).
3. **Core Intelligence** : Récupère le détecteur d'intention de DataCl (`intent_detector.py`) et l'évaluateur/tracker de ChronoBrain (`evaluator.py`, `performance_tracker.py`).
4. **Interface** : Ajoute une surcouche Web (`ui/app.py`) et une API, remplaçant les scripts CLI monolithiques.

```mermaid
graph TD
    User([Utilisateurs]) --> UI[Interface Web Flask]
    Admin([Admin]) --> CLI[CLI main.py]
    
    UI --> API[API Server]
    CLI --> Dispatcher[Dispatcher]
    API --> Dispatcher
    
    subgraph "unified-agent (L'Architecture Combinée)"
        Dispatcher --> Agent[Agent Principal]
        
        %% Core Intelligence (Mix des deux)
        Agent --> Intent[Intent Detector (de DataCl)]
        Agent --> Tracker[Performance Tracker (de ChronoBrain)]
        
        %% Retrieval Hybride Avancé
        Agent --> HybridRetriever[Hybrid Retriever]
        HybridRetriever --> FAISSManager[(FAISS - de DataCl)]
        HybridRetriever --> BM25Manager[(BM25 - de ChronoBrain)]
        FAISSManager --> Merger[Source Merger & Reranker]
        BM25Manager --> Merger
        Merger --> Dedup[Deduplication]
        Dedup --> Agent
        
        %% Abstraction LLM
        Agent --> LLMOrchestrator[LLM Orchestrator]
        LLMOrchestrator --> Groq[[Groq Client (de DataCl)]]
        LLMOrchestrator --> Ollama[[Ollama Client (de ChronoBrain)]]
    end
    
    LLMOrchestrator --> Agent
    Agent --> UI
```

### 💡 Résumé de la fusion
- **`ChronoBrain`** a apporté l'hybridation (Sémantique + BM25), l'anti-hallucination et les métriques de performance.
- **`DataCl`** a apporté la vitesse (Groq, FAISS), la détection d'intention (règles métier) et des prompts adaptatifs.
- **`unified-agent`** a pris ces briques, les a isolées dans des dossiers propres (`llm/`, `retrieval/`, `core/`), et a ajouté une interface UI et un système de routage (`dispatcher`).
