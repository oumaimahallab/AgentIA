"""
Configuration Example - Ingestion Automatique
============================================

Adapter ces settings dans config/settings.py ou variables d'env
"""

# ============================================================================
# INGESTION TEXT CLEANING
# ============================================================================

INGESTION_SETTINGS = {
    # Activation du nettoyage
    'CLEAN_TEXT': True,  # Activer nettoyage auto
    'EXTRACT_ENTITIES': True,  # Extraire entités (emails, URLs, etc)
    'LANGUAGE': 'fr',  # 'fr' ou 'en'
    
    # Déduplication
    'DEDUPLICATE': True,  # Supprimer doublons
    'SIMILARITY_THRESHOLD': 0.95,  # 0-1, plus élevé = moins de suppression
    'MIN_TEXT_LENGTH': 10,  # Chars minimum pour garder un texte
    
    # Chunking
    'CHUNK_SIZE': 500,  # Caractères par chunk
    'CHUNK_OVERLAP': 100,  # Chevauchement entre chunks
    
    # Keywords extraction
    'TOP_KEYWORDS': 20,  # Nombre de keywords à extraire
    'MIN_KEYWORD_LENGTH': 3,  # Longueur minimum mot-clé
    
    # Stopwords
    'REMOVE_STOPWORDS': False,  # Supprimer stopwords (peut affecter contexte)
    'REMOVE_NUMBERS': False,  # Supprimer nombres
}


# ============================================================================
# EMBEDDINGS & INDEXATION
# ============================================================================

EMBEDDINGS_SETTINGS = {
    # Model configuration
    'MODEL_NAME': 'sentence-transformers/distiluse-base-multilingual-v3-v2',
    'MODEL_DEVICE': 'cuda',  # 'cpu' ou 'cuda'
    'BATCH_SIZE': 32,  # Batch size for embedding
    'DIMENSION': 512,  # Embedding dimension
    
    # Caching
    'CACHE_EMBEDDINGS': True,
    'CACHE_DIR': './cache/embeddings',
}

FAISS_SETTINGS = {
    'INDEX_TYPE': 'Flat',  # 'Flat', 'IVF', 'HNSW'
    'SAVE_PATH': './storage/faiss_index',
    'BACKUP_ENABLED': True,
    'BACKUP_INTERVAL': 3600,  # Secondes
}

BM25_SETTINGS = {
    'INDEX_TYPE': 'BM25',
    'SAVE_PATH': './storage/bm25_index',
    'K1': 1.5,  # BM25 parameter
    'B': 0.75,  # BM25 parameter
}


# ============================================================================
# UPLOAD & FILE HANDLING
# ============================================================================

UPLOAD_SETTINGS = {
    # Directories
    'UPLOAD_DIR': './ui/uploads',
    'TEMP_DIR': './tmp',
    'MAX_RETENTION_DAYS': 30,  # Delete old files
    
    # File size limits
    'MAX_FILE_SIZE_MB': 500,
    'MAX_FILE_SIZE_VIDEO_MB': 2000,
    
    # Supported formats
    'ALLOWED_EXTENSIONS': {
        'documents': ['pdf', 'txt', 'md', 'docx', 'ppt', 'pptx'],
        'media': ['mp3', 'wav', 'm4a', 'mp4', 'avi', 'mov'],
    },
    
    # Keep original file after ingestion?
    'KEEP_ORIGINAL': False,
    'ARCHIVE_DIR': './archive',
}


# ============================================================================
# TRANSCRIPTION (WHISPER)
# ============================================================================

TRANSCRIPTION_SETTINGS = {
    'MODEL_SIZE': 'small',  # tiny, base, small, medium, large
    'LANGUAGE': 'fr',  # French
    'DEVICE': 'cuda',  # 'cpu' or 'cuda'
    'TEMPERATURE': 0,  # 0 = deterministic
    'TIMEOUT': 3600,  # Max 1 hour per file
}


# ============================================================================
# DATABASE
# ============================================================================

DATABASE_SETTINGS = {
    'HOST': 'localhost',
    'PORT': 5432,
    'NAME': 'postgres',
    'USER': 'postgres',
    'PASSWORD': 'root',
    
    # Connection pool
    'POOL_SIZE': 10,
    'MAX_OVERFLOW': 20,
    'POOL_TIMEOUT': 30,
    
    # Performance
    'ENABLE_INDEXES': True,
    'QUERY_TIMEOUT': 30,  # seconds
}


# ============================================================================
# LOGGING
# ============================================================================

LOGGING_SETTINGS = {
    'LEVEL': 'INFO',  # DEBUG, INFO, WARNING, ERROR
    'FORMAT': '%(asctime)s | %(levelname)-8s | %(message)s',
    'FILE': './logs/ingestion.log',
    'MAX_SIZE_MB': 100,
    'BACKUP_COUNT': 5,
}


# ============================================================================
# PERFORMANCE & MONITORING
# ============================================================================

PERFORMANCE_SETTINGS = {
    # Async/threading
    'NUM_WORKERS': 4,  # Background threads
    'QUEUE_SIZE': 100,  # Max queued tasks
    
    # Monitoring
    'ENABLE_METRICS': True,
    'METRICS_INTERVAL': 300,  # seconds
    'METRICS_FILE': './metrics/ingestion_metrics.json',
    
    # Timeouts
    'INGEST_TIMEOUT': 600,  # 10 minutes
    'INDEX_TIMEOUT': 120,  # 2 minutes
    'QUERY_TIMEOUT': 30,  # 30 seconds
}


# ============================================================================
# SECURITY
# ============================================================================

SECURITY_SETTINGS = {
    # File upload validation
    'VALIDATE_FILE_HEADERS': True,
    'SCAN_FOR_MALWARE': False,  # Requires external service
    
    # Data privacy
    'ENCRYPT_SENSITIVE_DATA': False,
    'ANONYMIZE_EMAILS': False,
    
    # Rate limiting
    'RATE_LIMIT_ENABLED': True,
    'RATE_LIMIT_PER_USER': 10,  # uploads per hour
    'RATE_LIMIT_WINDOW': 3600,  # seconds
}


# ============================================================================
# EXPORT CONFIGURATION
# ============================================================================

if __name__ == "__main__":
    import json
    
    CONFIG = {
        'INGESTION': INGESTION_SETTINGS,
        'EMBEDDINGS': EMBEDDINGS_SETTINGS,
        'FAISS': FAISS_SETTINGS,
        'BM25': BM25_SETTINGS,
        'UPLOAD': UPLOAD_SETTINGS,
        'TRANSCRIPTION': TRANSCRIPTION_SETTINGS,
        'DATABASE': DATABASE_SETTINGS,
        'LOGGING': LOGGING_SETTINGS,
        'PERFORMANCE': PERFORMANCE_SETTINGS,
        'SECURITY': SECURITY_SETTINGS,
    }
    
    print(json.dumps(CONFIG, indent=2))
