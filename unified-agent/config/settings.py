#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration centralisée pour l'Agent Intelligent Unifié
Gère tous les paramètres: paths, models, API keys, hyperparameters
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any
from dotenv import load_dotenv


# Charger variables d'environnement
load_dotenv()


@dataclass
class PathConfig:
    """Configuration des chemins"""
    
    # Racine du projet
    PROJECT_ROOT: Path = Path(__file__).parent.parent.absolute()
    
    # Données
    DATA_DIR: Path = PROJECT_ROOT / "data"
    DOCUMENTS_DIR: Path = DATA_DIR / "documents"
    TRANSCRIPTIONS_DIR: Path = DATA_DIR / "transcriptions"
    CHUNKS_DIR: Path = DATA_DIR / "chunks"
    
    # Indices
    INDICES_DIR: Path = DATA_DIR / "indices"
    FAISS_INDEX_DIR: Path = INDICES_DIR / "faiss"
    BM25_INDEX_DIR: Path = INDICES_DIR / "bm25"
    METADATA_DIR: Path = INDICES_DIR / "metadata"
    
    # Cache
    CACHE_DIR: Path = DATA_DIR / "cache"
    
    # Logs
    LOGS_DIR: Path = PROJECT_ROOT / "logs"
    
    def __post_init__(self):
        """Crée les répertoires s'ils n'existent pas"""
        for path in [
            self.DOCUMENTS_DIR, self.TRANSCRIPTIONS_DIR, self.CHUNKS_DIR,
            self.FAISS_INDEX_DIR, self.BM25_INDEX_DIR, self.METADATA_DIR,
            self.CACHE_DIR, self.LOGS_DIR
        ]:
            path.mkdir(parents=True, exist_ok=True)


@dataclass
class EmbeddingConfig:
    """Configuration du modèle d'embedding"""
    
    # Modèle
    MODEL_NAME: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_DIM: int = 384
    
    # Performance
    BATCH_SIZE: int = 64
    MAX_LENGTH: int = 512
    
    # Cache
    CACHE_EMBEDDINGS: bool = True
    CACHE_DIR: str = field(default_factory=lambda: str(PathConfig().CACHE_DIR / "embeddings"))
    
    # Hardware
    DEVICE: str = "cpu"  # "cuda" ou "cpu"
    PRECISION: str = "float32"  # "float32" ou "float16"


@dataclass
class RetrievalConfig:
    """Configuration du retrieval"""
    
    # Semantic search (FAISS)
    SEMANTIC_TOP_K: int = 20
    SEMANTIC_SCORE_THRESHOLD: float = 0.25
    
    # Keyword search (BM25)
    KEYWORD_TOP_K: int = 15
    KEYWORD_SCORE_THRESHOLD: float = 0.1
    
    # Hybrid fusion
    ALPHA: float = 0.5  # 0.5 = weight égale semantic + keyword
    DEDUP_THRESHOLD: float = 0.85  # Cosine similarity pour dedup
    
    # Reranking
    USE_RERANKER: bool = True
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"
    RERANKER_TOP_K: int = 8
    
    # Context limiting
    MAX_CONTEXT_TOKENS: int = 1500
    MAX_CONTEXT_CHUNKS: int = 15
    
    # Fallback
    FALLBACK_TOP_K: int = 20
    MIN_RESULTS_THRESHOLD: int = 3


@dataclass
class LLMConfig:
    """Configuration des LLMs"""
    
    # Primary LLM: Groq
    PRIMARY_LLM: str = "groq"
    GROQ_API_KEY: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    GROQ_TIMEOUT: int = 30
    
    # Fallback LLM: Ollama
    FALLBACK_LLM: str = "ollama"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama2"
    OLLAMA_TIMEOUT: int = 60
    
    # Generation params
    TEMPERATURE: float = 0.0  # Factuel, peu créatif
    MAX_TOKENS: int = 1024
    TOP_P: float = 0.9
    
    # System prompts par type
    SYSTEM_PROMPTS: Dict[str, str] = field(default_factory=lambda: {
        "definition": (
            "Tu es un expert en definitions. "
            "Fournis une definition PRECISE, CONCISE et FACTUELLE. "
            "Cite toujours tes sources."
        ),
        "procedure": (
            "Tu es un expert en procedures. "
            "Fournis une reponse ETAPE PAR ETAPE avec numeros. "
            "Sois clair et detaille. Cite les sources."
        ),
        "enumeration": (
            "Tu es un expert en listes. "
            "Enumere TOUS les elements de maniere structuree. "
            "Cite les sources."
        ),
        "explanation": (
            "Tu es un expert pedagogique. "
            "Explique le concept en detail, de maniere claire. "
            "Utilise les extraits fournis. Cite les sources."
        ),
        "default": (
            "Tu es un assistant IA competent et honnete. "
            "Reponds en utilisant les contextes fournis. "
            "Si information non trouvee, dis-le clairement. "
            "Cite toujours tes sources."
        ),
    })


@dataclass
class IntentDetectionConfig:
    """Configuration de la détection d'intent"""
    
    # Patterns
    DEFINITION_PATTERNS: list = field(default_factory=lambda: [
        "c'est quoi", "qu'est-ce", "signifie", "definition",
        "c est quoi", "qu est ce", "signifie", "definition",
        "quel est", "explique le terme", "quelle est la definition"
    ])
    
    PROCEDURE_PATTERNS: list = field(default_factory=lambda: [
        "comment", "comment faire", "etapes", "demarche", "procedure",
        "procédure", "comment on", "a quoi", "a quoi ca sert",
        "comment ca marche", "instructions", "guide"
    ])
    
    ENUMERATION_PATTERNS: list = field(default_factory=lambda: [
        "quels", "quelles", "types", "liste", "lesquels", "enumere",
        "enumère", "combien de", "quels sont"
    ])
    
    HR_CALCULATION_PATTERNS: list = field(default_factory=lambda: [
        "congé", "congés", "vacance", "vacances", "jour",
        "heures", "heure", "solde", "reste", "restant"
    ])
    
    # Confidence threshold
    MIN_CONFIDENCE: float = 0.3


@dataclass
class ChunkingConfig:
    """Configuration du chunking"""
    
    # Taille des chunks
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 100
    
    # Stratégie
    STRATEGY: str = "semantic"  # "semantic", "size", "paragraph"
    
    # Metadata preservation
    PRESERVE_METADATA: bool = True
    KEEP_SOURCE_INFO: bool = True


@dataclass
class DeduplicationConfig:
    """Configuration de la déduplication"""
    
    # Sensitivity
    SIMILARITY_THRESHOLD: float = 0.85
    
    # Strategies
    NORMALIZE_TEXT: bool = True
    USE_SEMANTIC_FINGERPRINT: bool = True  # Hash du contenu normalisé
    
    # Conflict resolution
    PREFER_SOURCE: str = "document"  # "document" vs "transcription"
    KEEP_BOTH_ON_CONFLICT: bool = True  # Garder les deux avec flag
    
    # Provenance tracking
    TRACK_PROVENANCE: bool = True


@dataclass
class CachingConfig:
    """Configuration du caching"""
    
    ENABLED: bool = True
    
    # TTL (Time To Live) en secondes
    EMBEDDING_TTL: int = 86400 * 7  # 7 jours
    RETRIEVAL_TTL: int = 3600 * 24  # 24 heures
    LLM_RESPONSE_TTL: int = 3600 * 24  # 24 heures
    
    # Taille max du cache
    MAX_CACHE_SIZE_MB: int = 1000
    
    # Stockage
    STORAGE_TYPE: str = "disk"  # "disk" ou "redis"


@dataclass
class LoggingConfig:
    """Configuration du logging"""
    
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Files
    LOG_TO_FILE: bool = True
    LOG_DIR: Path = field(default_factory=lambda: PathConfig().LOGS_DIR)
    
    # Rotation
    MAX_LOG_SIZE: int = 10 * 1024 * 1024  # 10 MB
    BACKUP_COUNT: int = 5


@dataclass
class UnifiedAgentConfig:
    """Configuration complète de l'agent"""
    
    paths: PathConfig = field(default_factory=PathConfig)
    embeddings: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    intent: IntentDetectionConfig = field(default_factory=IntentDetectionConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    deduplication: DeduplicationConfig = field(default_factory=DeduplicationConfig)
    caching: CachingConfig = field(default_factory=CachingConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    # Debug mode
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    VERBOSE: bool = os.getenv("VERBOSE", "false").lower() == "true"
    
    @classmethod
    def from_env(cls) -> "UnifiedAgentConfig":
        """Crée une config depuis variables d'environnement"""
        return cls()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return {
            "paths": self.paths.__dict__,
            "embeddings": self.embeddings.__dict__,
            "retrieval": self.retrieval.__dict__,
            "llm": self.llm.__dict__,
            "intent": self.intent.__dict__,
            "chunking": self.chunking.__dict__,
            "deduplication": self.deduplication.__dict__,
            "caching": self.caching.__dict__,
            "logging": self.logging.__dict__,
            "debug": self.DEBUG,
            "verbose": self.VERBOSE,
        }


# Singleton global config
_config: UnifiedAgentConfig | None = None

def get_config() -> UnifiedAgentConfig:
    """Retourne la config globale"""
    global _config
    if _config is None:
        _config = UnifiedAgentConfig.from_env()
    return _config


def reset_config():
    """Reset la config globale"""
    global _config
    _config = None
