# 🎯 Architecture Agent IA Intelligent Complet

## Vue d'ensemble

```
                        INPUT UTILISATEUR
                              ↓
                        AGENT DISPATCHER
                        /            \
                       /              \
            DOCUMENTS PIPELINE    TRANSCRIPTIONS PIPELINE
            (PDF, PPT, Images)    (Audio/Vidéo → Text)
                   ↓                       ↓
        [Document Ingestion]      [Whisper Transcription]
                   ↓                       ↓
        ┌─────────────────────────────────┐
        │   UNIFIED DEDUPLICATION LAYER   │  ← Évite conflits/doublons
        └─────────────────────────────────┘
                   ↓
        ┌─────────────────────────────────┐
        │    CHUNK CLASSIFICATION         │  ← Type de contenu
        │  (Définition/Procédure/List)    │
        └─────────────────────────────────┘
                   ↓
        ┌─────────────────────────────────┐
        │   UNIFIED EMBEDDING ENGINE      │  ← FAISS Index
        │ (all-MiniLM-L6-v2 - 384 dims)  │
        └─────────────────────────────────┘
                   ↓
        ┌─────────────────────────────────┐
        │   INTENT DETECTION              │  ← Questions/Procédures/Listes
        │   + QUERY EXPANSION             │
        └─────────────────────────────────┘
                   ↓
        ┌─────────────────────────────────┐
        │   HYBRID RETRIEVAL              │  ← BM25 + Semantic
        │   (Documents + Transcriptions)  │
        └─────────────────────────────────┘
                   ↓
        ┌─────────────────────────────────┐
        │   CONTEXT RANKING & FUSION      │  ← Combiner sources
        │   (Deduplicate + Rerank)        │
        └─────────────────────────────────┘
                   ↓
        ┌─────────────────────────────────┐
        │   ADAPTIVE PROMPT BUILDER       │  ← Contextualisé
        │   (Selon intent + sources)      │
        └─────────────────────────────────┘
                   ↓
        ┌─────────────────────────────────┐
        │   LLM ENGINE                    │  ← Groq (primary)
        │   (Groq/Ollama avec fallback)   │    Ollama (fallback)
        └─────────────────────────────────┘
                   ↓
        ┌─────────────────────────────────┐
        │   CITATION & PROVENANCE         │  ← Tracer sources
        │   + Confidence Score            │
        └─────────────────────────────────┘
                   ↓
                FINAL ANSWER
         (Text + Sources + Type + Confidence)
```

---

## Structure de Fichiers Proposée

```
unified-agent/
├── config/
│   ├── __init__.py
│   ├── settings.py              ← Configuration centrale (paths, models, API keys)
│   ├── embeddings_config.py     ← Config embeddings
│   └── llm_config.py            ← Config LLMs (Groq/Ollama)
│
├── core/
│   ├── __init__.py
│   ├── deduplication.py         ← Élimine doublons, gère conflits
│   ├── chunk_classifier.py      ← Classification (Procédure/Définition/List)
│   ├── intent_detector.py       ← Détecte le type de question
│   ├── query_expander.py        ← Expansion de requête
│   └── document_metadata.py     ← Métadonnées sources
│
├── ingestion/
│   ├── __init__.py
│   ├── document_ingester.py     ← PDF/PPT/Images/Text
│   ├── transcription_ingester.py← Audio/Vidéo (Whisper)
│   ├── text_processor.py        ← Nettoyage/normalisation
│   └── chunking_strategy.py     ← Stratégies de découpe
│
├── retrieval/
│   ├── __init__.py
│   ├── embeddings.py            ← Wrapper embedding
│   ├── faiss_manager.py         ← Gestion index FAISS
│   ├── bm25_manager.py          ← Gestion BM25
│   ├── hybrid_retriever.py      ← Retrieval hybride
│   ├── reranker.py              ← Reranking contextuel
│   └── source_merger.py         ← Fusion contexte multiple sources
│
├── llm/
│   ├── __init__.py
│   ├── groq_client.py           ← Client Groq
│   ├── ollama_client.py         ← Client Ollama (fallback)
│   ├── prompt_builder.py        ← Construction adaptative
│   ├── context_limiter.py       ← Gestion tokens
│   └── response_parser.py       ← Parse + citation tracking
│
├── tools/
│   ├── __init__.py
│   ├── hr_tools.py              ← Calculs HR (leave, workdays)
│   ├── procedural_tools.py      ← Génération procédures
│   ├── definition_tools.py      ← Extraction définitions
│   └── list_tools.py            ← Génération listes
│
├── orchestration/
│   ├── __init__.py
│   ├── agent.py                 ← Agent principal
│   ├── dispatcher.py            ← Route vers bon pipeline
│   ├── workflow_manager.py      ← Orchestration multi-étape
│   └── error_handler.py         ← Gestion erreurs robuste
│
├── storage/
│   ├── __init__.py
│   ├── vector_store.py          ← Abstraction stockage vecteurs
│   ├── cache_manager.py         ← Cache results/embeddings
│   └── persistence.py           ← Sauvegardes
│
├── cli/
│   ├── __init__.py
│   └── main.py                  ← Interface CLI
│
├── api/
│   ├── __init__.py
│   └── rest_api.py              ← FastAPI endpoints
│
├── tests/
│   ├── __init__.py
│   ├── test_deduplication.py
│   ├── test_retrieval.py
│   ├── test_intent_detection.py
│   ├── test_end_to_end.py
│   └── fixtures/
│
├── data/
│   ├── documents/               ← Documents source
│   ├── transcriptions/          ← Transcriptions
│   ├── indices/
│   │   ├── faiss_index/
│   │   └── bm25_index/
│   ├── cache/
│   └── metadata/
│
├── logs/
│   ├── agent.log
│   ├── retrieval.log
│   └── errors.log
│
├── .env                         ← Secrets (API keys)
├── requirements.txt
├── README.md
└── main.py                      ← Point d'entrée
```

---

## Modules Clés - Détails

### 1. **DEDUPLICATION ENGINE** (`core/deduplication.py`)

```python
# Problème: Même contenu peut venir de:
#   - Document 1: "Procédure approuvée de congés"
#   - Transcription 1: "Procédure approuvée de congés (audio)"
#   - Résultat: Duplication 100%

# Solution:
class DeduplicationEngine:
    - fingerprint_content()   ← Hash contenu normalisé
    - merge_duplicates()      ← Combine sources
    - track_provenance()      ← "De doc1.pdf + transcription2.mp3"
    - conflict_resolution()   ← Gère versions différentes
```

### 2. **INTENT DETECTION** (`core/intent_detector.py`)

```python
# Type Questions:
class QueryIntent:
    DEFINITION    = "c'est quoi une habilitation?"
    PROCEDURE     = "comment approuver un congé?"
    ENUMERATION   = "quels sont les types d'heures?"
    EXPLANATION   = "pourquoi faut-il approuver?"
    HR_CALCULATION= "combien de jours restants?"
    
# Optimise traitement:
- DEFINITION/LIST    → Restitution directe (réponse exacte)
- PROCEDURE/EXPLAIN  → LLM+raisonnement
- HR_CALC           → Tools spécialisés
```

### 3. **HYBRID RETRIEVAL** (`retrieval/hybrid_retriever.py`)

```python
# Combine deux stratégies:
class HybridRetriever:
    
    # 1. Semantic Search (FAISS)
    semantic_search(query, top_k=8)
    
    # 2. BM25 Keyword Search
    keyword_search(query, top_k=8)
    
    # 3. Fusion & Deduplication
    fuse_results(semantic, keyword)
    
    # 4. Reranking contextuel
    rerank(results, query_intent)
```

### 4. **SOURCE MERGING** (`retrieval/source_merger.py`)

```python
# Problème: Même question → 12 chunks possibles
#   - 5 de documents
#   - 7 de transcriptions
# Solution:

class SourceMerger:
    - Deduplicate par fingerprint
    - Regroup par thème/contexte
    - Prioriser qualité source (doc > transcrip)
    - Garder traces complètes de provenance
```

### 5. **PROMPT ADAPTATION** (`llm/prompt_builder.py`)

```python
# Adapte prompt selon:
class AdaptivePromptBuilder:
    
    build_prompt(
        question,
        intent,           # DEFINITION, PROCEDURE, etc.
        context_chunks,
        sources,
        constraints
    )
    
    # Résultat: Prompt spécifique et optimisé
```

---

## Workflow Complet

### Example 1: Question HR Multi-Sources

```
Q: "Combien de jours de congés restants pour l'année?"

1. INTENT DETECTION → HR_CALCULATION
2. RETRIEVE:
   - Document: "Base = 25 jours/an"
   - Transcription: "2023 politique = 2 jours/an bonus"
3. DEDUPLICATE → Fusion: "25 + 2 = 27"
4. TOOLS → HR Calculator (start_date, taken, carryover)
5. ANSWER: "27 jours restants
   Sources:
   - doc/policy.pdf (base: 25 jours)
   - transcription/board_meeting_2023.mp3 (bonus: 2 jours)"
```

### Example 2: Question Procédure

```
Q: "Comment approuver des heures supplémentaires?"

1. INTENT DETECTION → PROCEDURE
2. RETRIEVE:
   - Documents: 6 chunks (procédure écrite)
   - Transcriptions: 3 chunks (pas pertinent)
3. DEDUPLICATE → Garder 6 (mieux que 3)
4. LLM → Génère étapes structurées
5. ANSWER: "Étape 1: ... Étape 2: ...
   Basé sur: doc/procedures.pdf"
```

### Example 3: Définition

```
Q: "C'est quoi une habilitation?"

1. INTENT DETECTION → DEFINITION
2. RETRIEVE → 4 chunks relevants
3. RESTITUTION DIRECTE (pas LLM)
4. ANSWER: "[Texte exact du chunk]
   Source: doc/definitions.pdf"
```

---

## Points Clés de Scalabilité

### ✅ Pas de Duplication
- Fingerprinting + deduplication systématique
- Tracking complet de provenance

### ✅ Pas de Conflits
- Conflict resolution engine
- Priorité intelligente (doc vs transcription)
- Versionning des sources

### ✅ Architecture Propre
- Separation of concerns (ingestion ≠ retrieval ≠ generation)
- Modules découplés et réutilisables
- Configuration centralisée

### ✅ Extensibilité
- Ajouter nouvelles sources: Plugin ingester
- Ajouter LLMs: Plugin client
- Ajouter tools: Module tools/
- Ajouter formats: Plugin parser

### ✅ Performance
- Caching multicouche (embeddings, retrievals, LLM)
- Indexing incrémental
- Parallel processing (documents + transcriptions)

---

## Prochaines Étapes

1. **Phase 1 - Foundation**
   - [ ] Setup structure de projet
   - [ ] Configuration centralisée
   - [ ] Deduplication engine

2. **Phase 2 - Integration**
   - [ ] Document ingestion (DataCl) + Transcription (ChronoBrain)
   - [ ] Unified embeddings + FAISS
   - [ ] Hybrid retrieval

3. **Phase 3 - Intelligence**
   - [ ] Intent detection
   - [ ] Adaptive prompts
   - [ ] LLM integration

4. **Phase 4 - Optimization**
   - [ ] Testing complet
   - [ ] Performance tuning
   - [ ] Deployment

5. **Phase 5 - Production**
   - [ ] Monitoring
   - [ ] Logging
   - [ ] API REST

---

## Benefits de cette Approche

| Aspect | Avant | Après |
|--------|-------|-------|
| Sources | 1 type max | Documents + Transcriptions |
| Duplication | Possible | Éliminée |
| Conflits | Risqué | Géré intelligemment |
| Scalabilité | Limité | Haute extensibilité |
| Performance | ~2 sec | ~1-2 sec (grâce cache) |
| Maintenance | Complexe (2 projets) | Simple (1 architecture) |
| Deployment | 2 instances | 1 instance |
