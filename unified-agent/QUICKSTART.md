# 🚀 DÉMARRAGE RAPIDE - Unified Intelligent Agent

Fusez ChronoBrain + DataCl en 5 minutes!

## 1️⃣ Installation (2 min)

```bash
# Accédez au dossier
cd c:\Users\maup10458\Desktop\AG\unified-agent

# Créez venv
python -m venv venv
venv\Scripts\activate

# Installez dépendances
pip install -r requirements.txt

# Configurez les secrets
copy .env.template .env
# Éditez .env et remplissez GROQ_API_KEY
```

## 2️⃣ Test des Modules (1 min)

```bash
# Test déduplication
python -m core.deduplication

# Test détection d'intent
python -m core.intent_detector

# Test ingestion
python -m ingestion.unified_ingester
```

## 3️⃣ Architecture Clés (1 min)

### Configuration Centralisée
```python
from config import get_config
config = get_config()
print(config.llm.groq_model)  # "llama-3.1-8b-instant"
```

### Déduplication Cross-Source
```python
from core import DeduplicationEngine, SourceType

engine = DeduplicationEngine()
engine.add_chunk("doc1", "Texte", SourceType.DOCUMENT, "file1.pdf")
engine.add_chunk("doc2", "Texte", SourceType.TRANSCRIPTION, "audio.mp3")
# Merge automatique!

stats = engine.get_stats()
print(stats)  # {"duplicates_eliminated": 1, ...}
```

### Détection d'Intent Intelligente
```python
from core import IntentDetector, QueryIntent

detector = IntentDetector()
result = detector.detect("c'est quoi une habilitation?")
print(result.intent)  # QueryIntent.DEFINITION
print(result.confidence)  # 0.95

# System prompt adapté
prompt = detector.get_system_prompt(result.intent)
```

### Ingestion Unifiée
```python
from ingestion import UnifiedIngester
from pathlib import Path

ingester = UnifiedIngester()

# Documents
chunks, metadata = ingester.ingest(Path("doc.pdf"))

# Audio/Vidéo
chunks, metadata = ingester.ingest(Path("audio.mp3"))

stats = ingester.get_stats()
print(stats)
```

## 4️⃣ Prochaines Étapes

### Court terme (Prochains jours)
- [ ] Phase 2: Implémentation retrieval hybride (FAISS + BM25)
- [ ] Phase 3: Intégration LLM (Groq + Ollama fallback)
- [ ] Phase 4: Orchestration agent principal

### Moyen terme (2-3 semaines)
- [ ] Tests unitaires complets
- [ ] CLI interactive
- [ ] FastAPI REST

### Long terme (1 mois)
- [ ] Deployment production
- [ ] Monitoring
- [ ] Documentation API

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [README.md](./README.md) | Documentation complète |
| [../ARCHITECTURE_UNIFIÉE.md](../ARCHITECTURE_UNIFIÉE.md) | Design complet + diagrammes |
| [../GUIDE_IMPLEMENTATION.md](../GUIDE_IMPLEMENTATION.md) | Phases + checklist détaillée |
| [config/settings.py](./config/settings.py) | Configuration avec commentaires |
| [core/](./core/) | Modules clés (dedup, intent) |

## 🐛 Troubleshooting

**Erreur: ModuleNotFoundError**
```bash
# Assurez-vous d'être dans venv
venv\Scripts\activate

# Réinstallez
pip install -r requirements.txt
```

**Erreur: GROQ_API_KEY not found**
```bash
# Créez .env depuis template
copy .env.template .env

# Ajoutez votre clé
# GROQ_API_KEY=sk_live_...
```

**Tests non trouvés**
```bash
# Run depuis la racine du projet
cd c:\Users\maup10458\Desktop\AG\unified-agent
python -m core.deduplication
```

## ✅ Vérification Installation

```python
# Testez tous les imports
python -c "
from config import get_config
from core import DeduplicationEngine, IntentDetector
from ingestion import UnifiedIngester
print('✅ All imports OK!')
"
```

## 💡 Prochain Module à Coder

### Phase 2: Retrieval Hybride

```python
# À implémenter dans retrieval/hybrid_retriever.py

class HybridRetriever:
    def __init__(self):
        self.faiss_manager = FAISSManager()
        self.bm25_manager = BM25Manager()
    
    def search(self, query):
        # 1. Semantic search (FAISS)
        semantic_results = self.faiss_manager.search(query, top_k=8)
        
        # 2. Keyword search (BM25)
        keyword_results = self.bm25_manager.search(query, top_k=8)
        
        # 3. Fusion + deduplication
        merged = self._merge_results(semantic_results, keyword_results)
        
        return merged
```

---

**Status**: ✅ Foundation complète, prêt Phase 2

**Questions?** Consultez les documentations ci-dessus ou examinez les commentaires code.

**Bon coding!** 🚀
