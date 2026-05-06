# 📋 Guide d'Implémentation - Fusion des Projets

## 📍 Situation Actuelle

Vous avez **2 projets distincts** :

### 1. **ChronoBrain-main** ✅
- **Spécialité**: Transcriptions audio/vidéo (Whisper)
- **LLM**: Ollama (llama3 local)
- **Framework**: LlamaIndex + ReActAgent
- **Tools**: HR spécifiques (calcul congés, jours ouvrables)
- **Index**: ChromaDB
- **Force**: Agent réactif avec tools HR intégrés

### 2. **DataCl** ✅
- **Spécialité**: Documents généraux (PDF, PPT, images)
- **LLM**: Groq (llama-3.1-8b-instant cloud)
- **Framework**: RAG universel personnalisé
- **Intelligence**: Détection d'intent adaptative
- **Index**: FAISS + BM25
- **Force**: Agent universel très flexible

---

## 🎯 Objectif de la Fusion

Créer un **AGENT UNIQUE INTELLIGENT** qui:
1. ✅ Traite documents ET transcriptions sans duplication
2. ✅ Détecte intelligemment le type de question
3. ✅ Adapte la réponse selon le contexte
4. ✅ Maintient une architecture propre et scalable
5. ✅ Évite les conflits de sources
6. ✅ Utilise les meilleurs outils de chaque projet

---

## 🛠️ Architecture Cible

```
unified-agent/
├── config/              ← Configuration centralisée
├── core/                ← Cœur logique (dedup, intent, classification)
├── ingestion/           ← Documents + Transcriptions
├── retrieval/           ← Hybrid search (semantic + keyword)
├── llm/                 ← Groq + Ollama (fallback)
├── tools/               ← HR + Procédural + Définitions
├── orchestration/       ← Agent dispatcher
├── storage/             ← FAISS + cache
├── cli/                 ← CLI interactive
├── api/                 ← REST API FastAPI
└── tests/               ← Tests unitaires
```

---

## 📊 Phase d'Implémentation

### **PHASE 1: Foundation (Semaine 1)**

#### 1.1 Setup Structure
```bash
# Créer la structure
cd c:\Users\maup10458\Desktop\AG
mkdir -p unified-agent/{config,core,ingestion,retrieval,llm,tools,orchestration,storage,cli,api,tests,data}
```

#### 1.2 Configuration Centralisée ✅ FAIT
- [config/settings.py](./unified-agent/config/settings.py) - Configuration complète

#### 1.3 Modules Clés ✅ FAIT
- [core/deduplication.py](./unified-agent/core/deduplication.py) - Élimine doublons
- [core/intent_detector.py](./unified-agent/core/intent_detector.py) - Reconnaît type de question

#### 1.4 À faire pour Phase 1
- [ ] core/chunk_classifier.py - Classification chunks (proc/def/list)
- [ ] ingestion/ - Adaptateurs pour documents + transcriptions
- [ ] storage/ - Gestion FAISS + cache

### **PHASE 2: Integration (Semaine 2)**

#### 2.1 Ingestion Unifiée
```python
# unified-agent/ingestion/unified_ingester.py

class UnifiedIngester:
    # Traite les deux types de sources
    ingest_document(file_path)    # → PDF/PPT/Images
    ingest_transcription(file_path)  # → MP3/MP4/TXT
    
    # Utilise la déduplication automatique
    process_chunk(chunk_text, source_type)
```

#### 2.2 Hybrid Retrieval
```python
# unified-agent/retrieval/hybrid_retriever.py

class HybridRetriever:
    # Combine FAISS (DataCl) + semantic search
    semantic_search(query)
    
    # Combine BM25 (DataCl)
    keyword_search(query)
    
    # Fusionne intelligemment
    search(query) → contexte unifié
```

#### 2.3 Source Merging
```python
# Combine résultats multiples sources
- Deduplique par fingerprint
- Regroupe par thème
- Priorise par qualité source
```

### **PHASE 3: Intelligence (Semaine 3)**

#### 3.1 Intent Routing ✅ FAIT
```python
# Détecte: DEFINITION, PROCEDURE, ENUMERATION, EXPLANATION, HR_CALCULATION

dispatcher.route_query(query)
    ↓
    DEFINITION → retrieve + restitution directe
    PROCEDURE → retrieve + LLM structuré
    ENUMERATION → retrieve + restitution directe
    HR_CALCULATION → retrieve + tools spécialisés
    EXPLANATION → retrieve + LLM détaillé
```

#### 3.2 Adaptive Prompting
```python
# Prompt optimisé selon intent
prompt = build_adaptive_prompt(
    query,
    intent,           # Ce que détecte le detector
    context_chunks,
    sources,
    tools_available
)
```

#### 3.3 LLM Integration
```python
# unified-agent/llm/llm_orchestrator.py

class LLMOrchestrator:
    # Primary: Groq (DataCl) - rapide, fiable
    generate_with_groq(prompt, context)
    
    # Fallback: Ollama (ChronoBrain) - local, pas de limites
    generate_with_ollama(prompt, context)
    
    # Retry logic avec fallback gracieux
    generate(prompt) → Groq ou Ollama
```

### **PHASE 4: Tools & Orchestration (Semaine 3-4)**

#### 4.1 HR Tools Integration
```python
# Du projet ChronoBrain
tools/hr_tools.py:
    - calculate_leave_balance()
    - working_days_between()
    - check_habilitation()
```

#### 4.2 Procedural Tools
```python
tools/procedural_tools.py:
    - generate_step_by_step()
    - structure_procedure()
```

#### 4.3 Agent Orchestrator
```python
# unified-agent/orchestration/agent.py

class UnifiedAgent:
    def answer(self, question):
        1. detect_intent(question)
        2. retrieve_context(question, intent)
        3. select_tools(intent)
        4. generate_response(context, tools)
        5. format_with_sources(response)
```

### **PHASE 5: Optimization & Testing**

#### 5.1 Performance
- Cache multicouche (embeddings, retrievals)
- Indexing incrémental
- Parallel ingestion

#### 5.2 Testing
```python
tests/test_end_to_end.py:
    - test_definition_question()
    - test_procedure_question()
    - test_enumeration_question()
    - test_hr_calculation()
    - test_deduplication()
    - test_conflict_resolution()
```

#### 5.3 API REST
```python
# api/main.py - FastAPI
POST /api/query
{
    "question": "...",
    "include_context": true,
    "include_sources": true,
    "intent_override": null
}
```

---

## 🔧 Intégration des Composants

### De **DataCl** à récupérer:
- ✅ Détection d'intent (déjà créé)
- [ ] Retrieval FAISS hybride
- [ ] BM25 keyword search
- [ ] Adaptive prompt building
- [ ] Groq LLM integration
- ✅ Intent-based restitution directe (pour def/enum)

### De **ChronoBrain** à récupérer:
- [ ] Whisper transcription pipeline
- [ ] HR tools (leave_balance, working_days)
- [ ] Ollama LLM integration (fallback)
- [ ] ChromaDB integration (optionnel, peut basculer FAISS)
- [ ] ReActAgent pattern (optional)

### Nouveaux développements:
- ✅ Déduplication engine (élimine doublons cross-source)
- [ ] Conflict resolution (doc vs transcription)
- [ ] Chunk classification (def/proc/list)
- [ ] Source merging intelligente
- [ ] Provenance tracking
- [ ] Caching multicouche

---

## 📝 Checklist Fusion

### Partie 1: Préparation
- [ ] Lire architecture complète
- [ ] Setup structure unified-agent/
- [ ] Installer dépendances unified (voir requirements.txt)
- [ ] Configurer .env (GROQ_API_KEY, etc.)

### Partie 2: Modules Core
- [ ] ✅ Deduplication engine
- [ ] ✅ Intent detector
- [ ] Chunk classifier
- [ ] Query expander

### Partie 3: Ingestion
- [ ] Document ingester (PDF, PPT, TXT, Images)
- [ ] Transcription ingester (Audio, Video)
- [ ] Text normalizer + chunker
- [ ] Metadata extraction

### Partie 4: Retrieval
- [ ] FAISS index manager
- [ ] BM25 manager
- [ ] Hybrid retriever
- [ ] Reranker
- [ ] Source merger

### Partie 5: LLM & Tools
- [ ] Groq client
- [ ] Ollama client (fallback)
- [ ] Prompt builder adaptatif
- [ ] HR tools integration
- [ ] Response parser + citation tracking

### Partie 6: Orchestration
- [ ] Agent dispatcher
- [ ] Workflow manager
- [ ] Error handler robust
- [ ] Logging infrastructure

### Partie 7: Interface
- [ ] CLI interactive
- [ ] FastAPI REST endpoints
- [ ] Cache management
- [ ] Monitoring

### Partie 8: Tests & Doc
- [ ] Unit tests complets
- [ ] Integration tests
- [ ] End-to-end tests
- [ ] Documentation
- [ ] Deployment guide

---

## 🚀 Commandes Démarrage

```bash
# Une fois tout fusionné:

# Mode interactif
python unified-agent/cli/main.py

# Ingestion documents
python unified-agent/ingestion/ingest.py --path /path/to/docs

# Ingestion transcriptions
python unified-agent/ingestion/ingest.py --type transcription --path /path/to/audio

# Rebuild index
python unified-agent/storage/rebuild_index.py

# Tests
pytest tests/

# API
python unified-agent/api/main.py
```

---

## 📊 Matrice Comparaison: Avant vs Après

| Aspect | Avant (2 projets) | Après (Unifié) |
|--------|------------------|----------------|
| Sources | Documents OU Transcriptions | Documents + Transcriptions |
| Duplication | ❌ Possible | ✅ Éliminée |
| Conflits | ❌ Risqué | ✅ Géré intelligemment |
| Intent | ❌ DataCl seulement | ✅ Détection universelle |
| Tools HR | ✅ ChronoBrain | ✅ ChronoBrain + plus |
| LLM | ❌ 2 LLMs fragiles | ✅ Groq + Ollama fallback |
| Scalabilité | ❌ Limitée | ✅ Hautement extensible |
| Maintenance | ❌ 2 instances | ✅ 1 instance |
| Performance | ~2 sec | ~1-2 sec (cache) |
| Code quality | ❌ Fragmenté | ✅ Modulaire propre |
| Documentation | ❌ Éclatée | ✅ Centralisée |
| Deployment | 2 services | 1 service |

---

## 🎓 Prochaines Étapes Immédiates

### 1️⃣ Créer la structure
```bash
mkdir -p c:\Users\maup10458\Desktop\AG\unified-agent\{config,core,ingestion,retrieval,llm,tools,orchestration,storage,cli,api,tests,data/{documents,transcriptions,chunks,indices,cache,metadata}}
```

### 2️⃣ Copier modules préparés
```bash
# config/settings.py - ✅ Déjà créé
# core/deduplication.py - ✅ Déjà créé
# core/intent_detector.py - ✅ Déjà créé
```

### 3️⃣ Implémenter ingestion unifiée

### 4️⃣ Implémenter retrieval hybride

### 5️⃣ Tester end-to-end

---

## 🤝 Questions à considérer

1. **LLM Primary**: Groq (cloud) ou Ollama (local)? 
   - **Recommandation**: Groq primary, Ollama fallback

2. **Vector Store**: FAISS (DataCl) ou ChromaDB (ChronoBrain)?
   - **Recommandation**: FAISS (plus léger) + Redis cache

3. **Async Processing**: Faut-il traiter async?
   - **Recommandation**: Oui, pour ingestion large volume

4. **Real-time vs Batch**: Mode opérationnel?
   - **Recommandation**: Real-time API + batch ingestion

---

## 📞 Support

- **Architecture questions**: Voir [ARCHITECTURE_UNIFIÉE.md](./ARCHITECTURE_UNIFIÉE.md)
- **Configuration**: Voir [config/settings.py](./unified-agent/config/settings.py)
- **Modules existants**: Voir [core/](./unified-agent/core/)
- **Tests d'exemple**: Voir [tests/](./unified-agent/tests/)

**Créé**: 5 Mai 2026
**Dernière mise à jour**: Maintenant
**Statut**: En cours d'implémentation 🚀
