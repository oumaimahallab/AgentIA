# Architecture Technique : Unified Chronotime Agent

Ce document présente l'architecture "A à Z" du système RAG (Retrieval-Augmented Generation) unifié, tel qu'il est implémenté dans le dossier `unified-agent`.

## 1. Vue d'Ensemble du Flux de Données

Le système suit une architecture en pipeline, de la donnée brute jusqu'à la réponse générée par l'IA.

```mermaid
graph TD
    subgraph "Phase 1 : Ingestion (scripts/)"
        A[Documents PDF/PPTX] --> C[Filtrage & Nettoyage]
        B[Transcriptions JSON] --> C
        C --> D[Extractions de Topics]
        D --> E[Génération SHA-256 Fingerprints]
    end

    subgraph "Phase 2 : Stockage (data/indices/)"
        E --> F1[(FAISS : Index Sémantique)]
        E --> F2[(BM25 : Index Mots-clés)]
        E --> F3[(Metadata : Mapping complet)]
    end

    subgraph "Phase 3 : Retrieval (retrieval/)"
        Q[Question Utilisateur] --> Q1[Détection d'Intention]
        Q1 --> Q2[Recherche Hybride]
        Q2 --> F1
        Q2 --> F2
        Q2 --> Q3[Fusion & Déduplication]
    end

    subgraph "Phase 4 : Génération (llm/)"
        Q3 --> G1[Formatage du Contexte]
        G1 --> G2[Groq / Llama 3]
        G2 --> G3[Retry Logic - Error 429]
        G3 --> ANS[Réponse finale sourcée]
    end
```

## 2. Composants Clés

### 2.1 Moteur de Recherche Hybride (`HybridRetriever`)
Le système ne se contente pas d'une recherche par "sens" (sémantique). Il combine deux mondes :
- **FAISS** : Compréhension sémantique (vecteurs de 384 dimensions).
- **BM25** : Précision lexicale (recherche par mots-clés exacts).
*Avantage : Meilleure précision sur les termes techniques de Chronotime.*

### 2.2 Déduplication Intelligente (`SourceMerger`)
Pour éviter que l'IA ne lise plusieurs fois la même information, le système utilise des **SHA-256 Fingerprints**. Chaque bloc de texte a une empreinte unique. Si une information est présente dans deux fichiers différents, elle est fusionnée.

### 2.3 Robustesse API (`GroqClient`)
L'intégration avec Groq inclut une logique de **Retry avec Backoff Exponentiel**. Si l'API est saturée (Erreur 429), le système attend quelques secondes avant de retenter, garantissant une continuité de service.

## 3. Schéma de l'Infrastucture Logicielle

```mermaid
classDiagram
    class UnifiedAgent {
        +answer(question)
        +batch_answer(questions)
    }
    class HybridRetriever {
        +search(query)
    }
    class SourceMerger {
        +merge(results)
        +build_context(sources)
    }
    class IntentDetector {
        +detect(text)
    }
    class GroqClient {
        +generate(prompt)
    }

    UnifiedAgent *-- IntentDetector
    UnifiedAgent *-- HybridRetriever
    UnifiedAgent *-- SourceMerger
    UnifiedAgent *-- GroqClient
```
