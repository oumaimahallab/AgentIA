# 📐 Diagrammes UML du Système (Agent RAG Unifié)

Ces diagrammes (Cas d'Utilisation, Classes et Séquence) modélisent le système sous l'angle de l'ingénierie logicielle (UML). Ils sont idéaux pour illustrer la conception orientée objet et les interactions dynamiques lors de votre soutenance.

---

## 1️⃣ Diagramme de Cas d'Utilisation (Use Case Diagram)
```mermaid
flowchart LR
    %% Définition des Acteurs
    User([Utilisateur / Employé])
    Admin([Administrateur Système])

    %% ----------------------------------------------------
    %% PACKAGE : Module Conversationnel (Chat & Interaction)
    %% ----------------------------------------------------
    subgraph "Module Conversationnel"
        F1([Poser une question métier])
        F2([Consulter l'historique des discussions])
        F3([Afficher les sources justificatives])
    end

    %% ----------------------------------------------------
    %% PACKAGE : Module de Traitement en Lot (Batch)
    %% ----------------------------------------------------
    subgraph "Module de Traitement en Lot"
        F4([Soumettre un fichier de requêtes])
        F5([Télécharger le rapport de réponses])
    end

    %% ----------------------------------------------------
    %% PACKAGE : Module d'Administration RAG
    %% ----------------------------------------------------
    subgraph "Module d'Administration RAG"
        F6([Téléverser de nouveaux documents RH])
        F7([Déclencher la reconstruction de l'Index])
        F8([Configurer les modèles IA - Groq/Ollama])
    end

    %% ----------------------------------------------------
    %% PACKAGE : Module de Monitoring
    %% ----------------------------------------------------
    subgraph "Module de Monitoring"
        F9([Visualiser les métriques de performance])
        F10([Évaluer la fidélité des réponses / Anti-Hallucination])
    end

    %% ----------------------------------------------------
    %% MAPPING ACTEURS -> FONCTIONNALITÉS
    %% ----------------------------------------------------
    User --- F1
    User --- F2
    User --- F4
    
    F1 -. "<<extend>>" .-> F3

    Admin --- F6
    Admin --- F7
    Admin --- F8
    Admin --- F9
    Admin --- F10
    
    %% L'Admin a aussi accès aux modules basiques
    Admin --- F4
    Admin --- F5

    %% ----------------------------------------------------
    %% DÉPENDANCES FONCTIONNELLES (INCLUDES CACHÉS)
    %% ----------------------------------------------------
    %% Le traitement de la question inclut l'orchestration interne
    subgraph "Moteur RAG Interne (Automatique)"
        I1([Détection d'Intention])
        I2([Recherche Hybride FAISS+BM25])
    end
    F1 -. "<<include>>" .-> I1
    F1 -. "<<include>>" .-> I2
    F4 -. "<<include>>" .-> I2
```

---

## 2️⃣ Diagramme de Classes (Class Diagram)
Ce diagramme met en évidence l'architecture orientée objet du composant `unified-agent`, le respect des principes **SOLID** et l'utilisation des Design Patterns (Factory, Strategy).

```mermaid
classDiagram
    class Dispatcher {
        +dispatch(query: String, mode: Enum)
        +batch_process(queries: List)
    }

    class Agent {
        -intent_detector: IntentDetector
        -retriever: HybridRetriever
        -llm: LLMOrchestrator
        +answer_question(query: String) Response
    }

    class IntentDetector {
        +detect_intent(query: String) IntentType
    }

    class HybridRetriever {
        -faiss: FAISSManager
        -bm25: BM25Manager
        -merger: SourceMerger
        +retrieve(query: String, top_k: int) List~Document~
    }

    class FAISSManager {
        +search_dense(vector: FloatArray) List~Result~
    }

    class BM25Manager {
        +search_sparse(tokens: List~String~) List~Result~
    }

    class LLMOrchestrator {
        -client: BaseLLMClient
        +generate_response(prompt: String) String
    }

    class BaseLLMClient {
        <<interface>>
        +complete(prompt: String)* String
    }

    class GroqClient {
        +complete(prompt: String) String
    }

    class OllamaClient {
        +complete(prompt: String) String
    }

    class PerformanceTracker {
        +record_metrics(latency: Float, faithful: Bool)
    }

    %% Relations
    Dispatcher --> Agent : "Utilise"
    Agent --> IntentDetector : "Délègue à"
    Agent --> HybridRetriever : "Délègue à"
    Agent --> LLMOrchestrator : "Délègue à"
    Agent --> PerformanceTracker : "Log métriques"

    HybridRetriever *-- FAISSManager : "Composition"
    HybridRetriever *-- BM25Manager : "Composition"
    
    LLMOrchestrator o-- BaseLLMClient : "Agrégation (Strategy Pattern)"
    BaseLLMClient <|-- GroqClient : "Implémente"
    BaseLLMClient <|-- OllamaClient : "Implémente"
```

---

## 3️⃣ Diagramme de Séquence (Sequence Diagram)
Ce diagramme modélise le flux d'exécution temporel complexe lorsqu'un utilisateur pose une question. Il met en évidence le parallélisme et la logique conditionnelle du pipeline RAG Hybride.

```mermaid
sequenceDiagram
    autonumber
    actor User as Utilisateur
    participant UI as API / Interface
    participant Agent as Core Agent
    participant Intent as IntentDetector
    participant Hybrid as HybridRetriever
    participant DB as Vector/BM25 Stores
    participant LLM as LLM Orchestrator
    participant Eval as Evaluator

    User->>UI: Pose une question (ex: "Comment faire X ?")
    activate UI
    UI->>Agent: process_query(question)
    activate Agent

    %% 1. Détection de l'intention
    Agent->>Intent: detect(question)
    activate Intent
    Intent-->>Agent: retourne type (Procédure)
    deactivate Intent

    %% 2. Phase de Retrieval (Recherche)
    Agent->>Hybrid: retrieve(question)
    activate Hybrid
    
    par Recherche Parallèle
        Hybrid->>DB: FAISS_Search(dense_vector)
        DB-->>Hybrid: résultats sémantiques
    and
        Hybrid->>DB: BM25_Search(tokens)
        DB-->>Hybrid: résultats mots-clés
    end
    
    Hybrid->>Hybrid: Fusion, Reranking & MMR Deduplication
    Hybrid-->>Agent: Contexte Top-K optimal
    deactivate Hybrid

    %% 3. Construction du prompt et LLM
    Agent->>Agent: Build_Prompt(Context, Intent)
    Agent->>LLM: generate_answer(prompt)
    activate LLM
    LLM-->>Agent: Raw_Response (LLM Output)
    deactivate LLM

    %% 4. Évaluation post-génération
    Agent->>Eval: check_faithfulness(Context, Answer)
    activate Eval
    Eval-->>Agent: Score de fidélité (Valide/Invalide)
    deactivate Eval

    Agent-->>UI: Final_Response + Sources + Score
    deactivate Agent
    UI-->>User: Affichage formatté
    deactivate UI
```

### 💡 Points Forts à souligner à l'oral
- **Séparation des préoccupations (Class Diagram)** : Montrez comment le "Strategy Pattern" utilisé pour le LLM (`BaseLLMClient`, `GroqClient`, `OllamaClient`) permet de changer d'Intelligence Artificielle en une ligne de code sans toucher à la logique métier.
- **RAG Hybride Parallélisé (Sequence Diagram)** : Mettez en avant le bloc "par" (parallèle) où FAISS et BM25 cherchent en même temps, maximisant la vitesse (réduction du goulot d'étranglement).
- **Évaluation Continue (Sequence Diagram)** : La dernière étape avec l'`Evaluator` prouve la robustesse du système face aux hallucinations, un argument critique dans les systèmes d'IA de production.
