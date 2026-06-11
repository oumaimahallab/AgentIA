#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Documentation: Système Upload & Ingestion Auto
avec Extraction, Nettoyage et Stockage en Base de Données

VERSION: 2.0 - Support Utilisateurs + Nettoyage Complet
"""

# ============================================================================
# 1. ARCHITECTURE GÉNÉRALE
# ============================================================================

"""
Flow d'une Session Utilisateur:

1. Utilisateur upload fichier/vidéo
   ↓
2. Extraction automatique du contenu (OCR, Transcription Whisper, Parsing)
   ↓
3. Nettoyage + Enrichissement:
   - Normalisation Unicode
   - Suppression URLs/emails/bruit
   - Déduplication intelligente
   - Extraction entités (emails, téléphones, etc)
   - Extraction keywords (TF-IDF)
   ↓
4. Indexation multi-moteur:
   - FAISS: Recherche vectorielle (embedding)
   - BM25: Recherche full-text (keywords)
   ↓
5. Stockage PostgreSQL:
   - table `user_documents`: Métadonnées enrichies
   - Statsde nettoyage
   - Info agent/session
   ↓
6. Utilisation par l'agent pour répondre aux questions
"""


# ============================================================================
# 2. FORMATS SUPPORTÉS
# ============================================================================

SUPPORTED_FORMATS = {
    # Documents texte
    "text": [".txt", ".md"],
    
    # Documents structurés
    "pdf": [".pdf"],
    "powerpoint": [".ppt", ".pptx"],
    "word": [".docx"],
    
    # Audio
    "audio": [".mp3", ".wav", ".m4a"],
    
    # Vidéo
    "video": [".mp4", ".avi", ".mov"],
}


# ============================================================================
# 3. API ROUTES - UTILISATION CLIENT
# ============================================================================

"""
A. UPLOAD & INGESTION AUTO
─────────────────────────────────────────

POST /api/user/upload_and_ingest
    Body: multipart/form-data
    - file: Fichier à uploader
    - email: Email utilisateur
    - session_id: (optionnel) ID session

    Response (201):
    {
        "success": true,
        "document_id": 42,
        "message": "Fichier uploadé. Extraction + nettoyage en cours...",
        "status": "processing"
    }

    Processus en arrière-plan:
    1. Détecte type de fichier
    2. Extrait contenu (OCR/Transcription/Parse)
    3. Nettoie texte (normalisation, suppression bruit)
    4. Index FAISS + BM25
    5. Stockage PostgreSQL avec métadonnées enrichies


B. LISTER DOCUMENTS UTILISATEUR
──────────────────────────────────────

GET /api/user/documents?email=user@test.com&session_id=xyz (optionnel)
    
    Response (200):
    [
        {
            "id": 42,
            "filename": "rapport.pdf",
            "file_type": "pdf",
            "file_size": 125000,
            "status": "Ingéré",  // "En attente" | "En cours" | "Ingéré" | "Erreur"
            "total_chunks": 15,
            "processing_time": 2.34,
            "language": "fr",
            "created_at": "2025-05-25T10:30:00",
            "ingestion_timestamp": "2025-05-25T10:32:45"
        },
        ...
    ]


C. DÉTAILS DOCUMENT AVEC MÉTADONNÉES ENRICHIES
────────────────────────────────────────────────

GET /api/user/documents/42?email=user@test.com
    
    Response (200):
    {
        "id": 42,
        "filename": "rapport.pdf",
        "file_type": "pdf",
        "file_size": 125000,
        "status": "Ingéré",
        "total_chunks": 15,
        "processing_time": 2.34,
        "language": "fr",
        
        // Métadonnées enrichies:
        "keywords": ["données", "analyse", "rapport", ...],  // Top 20 keywords
        
        "extracted_entities": {
            "emails": ["contact@example.com"],
            "urls": ["https://example.com"],
            "numbers": ["42", "123.45"],
            "phone_numbers": ["+33123456789"]
        },
        
        "cleaning_stats": {
            "original_length": 50000,
            "cleaned_length": 48000,
            "removed_chars": 2000,
            "removed_duplicates": 0
        },
        
        "error_msg": null,
        "created_at": "2025-05-25T10:30:00",
        "ingestion_timestamp": "2025-05-25T10:32:45"
    }


D. SUPPRIMER DOCUMENT
──────────────────────

DELETE /api/user/documents/42?email=user@test.com
    
    Response (200):
    {
        "success": true,
        "message": "Document supprimé"
    }
"""


# ============================================================================
# 4. EXEMPLE JAVASCRIPT/REACT
# ============================================================================

"""
// 1. Upload fichier avec ingestion auto
async function uploadDocument(file, userEmail, sessionId) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('email', userEmail);
    formData.append('session_id', sessionId);
    
    const response = await fetch('/api/user/upload_and_ingest', {
        method: 'POST',
        body: formData
    });
    
    if (!response.ok) {
        throw new Error(`Upload échoué: ${response.statusText}`);
    }
    
    const result = await response.json();
    console.log('Document ID:', result.document_id);
    return result;
}

// 2. Récupérer documents utilisateur
async function getUserDocuments(userEmail, sessionId = null) {
    const params = new URLSearchParams({ email: userEmail });
    if (sessionId) params.append('session_id', sessionId);
    
    const response = await fetch(`/api/user/documents?${params}`);
    const documents = await response.json();
    return documents;
}

// 3. Afficher métadonnées enrichies
async function showDocumentDetails(docId, userEmail) {
    const response = await fetch(`/api/user/documents/${docId}?email=${userEmail}`);
    const details = await response.json();
    
    console.log('Keywords:', details.keywords);
    console.log('Entities:', details.extracted_entities);
    console.log('Cleaning stats:', details.cleaning_stats);
}

// 4. Monitorer statut ingestion
async function pollDocumentStatus(docId, userEmail, maxAttempts = 30) {
    for (let i = 0; i < maxAttempts; i++) {
        const docs = await getUserDocuments(userEmail);
        const doc = docs.find(d => d.id === docId);
        
        if (doc.status === 'Ingéré') {
            console.log('✅ Document ingéré!');
            return doc;
        } else if (doc.status === 'Erreur') {
            throw new Error(doc.error_msg);
        }
        
        // Attendre 2 secondes avant vérification suivante
        await new Promise(resolve => setTimeout(resolve, 2000));
    }
    
    throw new Error('Timeout: ingestion trop longue');
}

// 5. Workflow complet
async function handleFileUpload(file, userEmail, sessionId) {
    try {
        // Upload
        const uploadResult = await uploadDocument(file, userEmail, sessionId);
        console.log('📤 Fichier uploadé');
        
        // Monitorer ingestion
        const finalDoc = await pollDocumentStatus(uploadResult.document_id, userEmail);
        console.log('✅ Ingestion complète');
        
        // Afficher détails
        await showDocumentDetails(finalDoc.id, userEmail);
        
        // Recharger liste documents
        const allDocs = await getUserDocuments(userEmail, sessionId);
        console.log('Documents:', allDocs);
        
    } catch (error) {
        console.error('❌ Erreur:', error);
    }
}
"""


# ============================================================================
# 5. CONFIGURATION PYTHON - UTILISATION DIRECTE
# ============================================================================

"""
# A. Ingestion manuelle (pour scripts/notebooks)
from ingestion.unified_ingester import UnifiedIngester
from pathlib import Path

ingester = UnifiedIngester(
    language="fr",      # fr ou en
    clean_text=True,    # Activer nettoyage auto
    extract_entities=True  # Extraire entités
)

# Ingérer fichier
result = ingester.ingest(
    file_path=Path("mon_document.pdf"),
    user_email="user@test.com",
    session_id="session_123"
)

if result:
    chunks, metadata = result
    
    print(f"Chunks: {len(chunks)}")
    print(f"Keywords: {metadata.keywords}")
    print(f"Entities: {metadata.extracted_entities}")
    print(f"Cleaning stats: {metadata.cleaning_stats}")


# B. Nettoyage texte uniquement
from ingestion.text_cleaner import TextCleaner, BatchCleaner

cleaner = TextCleaner("fr")

# Nettoyer un texte
text = "Bonjour! Visitez https://example.com ou email test@example.com"
cleaned = cleaner.clean_text(text)
print(cleaned)  # "Bonjour"

# Extraire entités
entities = cleaner.extract_entities(text)
print(entities)
# {
#   'emails': ['test@example.com'],
#   'urls': ['https://example.com'],
#   'numbers': [],
#   'phone_numbers': []
# }

# Extraire keywords
keywords = cleaner.extract_keywords("Long texte avec beaucoup de mots importants...")
print(keywords)  # Top 20 keywords

# Batch processing
batch = BatchCleaner("fr")
texts = ["Text 1", "Text 2", "Text 1"]  # Doublon

cleaned = batch.process_pipeline(
    texts,
    remove_stopwords=False,
    deduplicate=True
)
print(cleaned)  # Text 1, Text 2 (doublon supprimé)
"""


# ============================================================================
# 6. STRUCTURE BASE DE DONNÉES
# ============================================================================

"""
Table: user_documents

Colonnes Principales:
├─ id (SERIAL PRIMARY KEY)
├─ user_email (TEXT NOT NULL) - Email utilisateur
├─ session_id (TEXT) - ID session agent
├─ filename (TEXT NOT NULL) - Nom fichier
├─ file_type (TEXT) - Extension (.pdf, .mp4, etc)
├─ file_size (INTEGER) - Taille en bytes
├─ file_hash (TEXT UNIQUE) - SHA256 pour détection doublons
├─ source_type (TEXT) - Type extrait (pdf, video, transcription, etc)
├─ status (TEXT) - En attente | En cours | Ingéré | Erreur | Supprimé
├─ error_msg (TEXT) - Message erreur si status='Erreur'
├─ total_chunks (INTEGER) - Nombre chunks générés
├─ processing_time (FLOAT) - Temps traitement secondes
├─ language (TEXT) - Langue détectée
├─ keywords (TEXT/JSON) - Top 20 keywords
├─ extracted_entities (TEXT/JSON) - Emails, URLs, téléphones
├─ cleaning_stats (TEXT/JSON) - Stats nettoyage
├─ ingestion_timestamp (TIMESTAMP) - Quand ingestion complète
├─ created_at (TIMESTAMP) - Quand upload
└─ updated_at (TIMESTAMP) - Dernière modification

Indexes:
- idx_user_documents_email
- idx_user_documents_session
- idx_user_documents_status
"""


# ============================================================================
# 7. ÉTAPES DE TRAITEMENT DÉTAILLÉES
# ============================================================================

"""
Étape 1: DÉTECTION TYPE
├─ Détecte extension fichier
├─ Mappe à parser approprié
└─ Active transcription si audio/vidéo

Étape 2: EXTRACTION CONTENU
├─ PDF → PyMuPDF
├─ PowerPoint → python-pptx
├─ DOCX → python-docx
├─ TXT/MD → Lecture simple
└─ Audio/Vidéo → Whisper (transcription)

Étape 3: NETTOYAGE TEXTE
├─ Normalisation Unicode (NFKC)
├─ Suppression URLs & emails
├─ Suppression caractères spéciaux
├─ Fusion espaces multiples
└─ Suppression leading/trailing whitespace

Étape 4: DÉDUPLICATION
├─ Comparaison SequenceMatcher
├─ Seuil similarité: 95%
└─ Suppression textes similaires

Étape 5: EXTRACTION ENTITÉS
├─ Emails: regex \\S+@\\S+
├─ URLs: regex https?://\\S+ ou www\\.\\S+
├─ Téléphones: regex international
└─ Nombres: tous les chiffres

Étape 6: EXTRACTION KEYWORDS
├─ Tokenization
├─ Suppression stopwords (optionnel)
├─ Comptage fréquence
└─ Retour Top N (défaut: 20)

Étape 7: INDEXATION VECTEURS
├─ Embedding via agent.embeddings
├─ Ajout à FAISS
└─ Sauvegarde index

Étape 8: INDEXATION TEXTE
├─ Ajout chunks à BM25
└─ Sauvegarde index

Étape 9: STOCKAGE MÉTADONNÉES
├─ INSERT user_documents
├─ Stockage keywords JSON
├─ Stockage entities JSON
├─ Stockage cleaning_stats JSON
└─ UPDATE status='Ingéré'
"""


# ============================================================================
# 8. CONFIGURATION & TUNING
# ============================================================================

"""
Dans config/settings.py ou variables d'env:

INGESTION_SETTINGS = {
    # Nettoyage texte
    'CLEAN_TEXT': True,
    'EXTRACT_ENTITIES': True,
    'LANGUAGE': 'fr',  # ou 'en'
    
    # Déduplication
    'DEDUPLICATE': True,
    'SIMILARITY_THRESHOLD': 0.95,  # 0-1
    
    # Chunking
    'CHUNK_SIZE': 500,  # Caractères
    'CHUNK_OVERLAP': 100,  # Caractères
    
    # Keywords
    'TOP_KEYWORDS': 20,
    'MIN_KEYWORD_LENGTH': 3,
    
    # Embeddings
    'EMBEDDING_BATCH_SIZE': 32,
    'EMBEDDING_MODEL': 'distiluse-base-multilingual-v3-v2',
    
    # Stockage
    'KEEP_ORIGINAL_FILE': False,  # Supprimer après ingestion?
    'MAX_FILE_SIZE_MB': 500,
}
"""


# ============================================================================
# 9. DÉPANNAGE & ERREURS COMMUNES
# ============================================================================

"""
Problème 1: "Format non supporté"
└─ Vérifier extension fichier
└─ Extensions supportées: pdf, ppt, pptx, txt, md, docx, mp3, wav, m4a, mp4, avi, mov

Problème 2: "Erreur transcription Whisper"
└─ Vérifier: pip install openai-whisper
└─ Vérifier: modèle Whisper chargé
└─ Fichier audio/vidéo corrompu?

Problème 3: "Erreur extraction PDF"
└─ Vérifier: pip install pymupdf
└─ PDF protégé ou encodé?

Problème 4: "Chunk vide"
└─ Fichier texte vide?
└─ Vérifier encoding (UTF-8 vs Latin-1)

Problème 5: "Doublons non détectés"
└─ Augmenter SIMILARITY_THRESHOLD
└─ Vérifier texte vraiment similaire

Problème 6: "FAISS/BM25 indexing échoue"
└─ Chunks trop longs?
└─ Vérifier embedding dimensions
└─ Redémarrer agent?
"""


# ============================================================================
# 10. METRICS & MONITORING
# ============================================================================

"""
Suivi important par document:

1. Processing Time (secondes)
   └─ Total extraction + nettoyage
   
2. Chunks Générés
   └─ Plus élevé = plus long document
   
3. Keywords Extraits
   └─ Qualité du nettoyage
   
4. Entities Found
   └─ Données structurées identifiées
   
5. Cleaning Impact
   └─ original_length vs cleaned_length
   └─ Ratio de suppression bruit
   
6. Status Flow
   └─ En attente → En cours → Ingéré (✓)
   └─ En attente → En cours → Erreur (✗)

Query de monitoring:
SELECT 
    AVG(processing_time) as avg_time,
    COUNT(*) as total_docs,
    SUM(total_chunks) as total_chunks,
    COUNT(CASE WHEN status='Ingéré' THEN 1 END) as success_count,
    COUNT(CASE WHEN status='Erreur' THEN 1 END) as error_count
FROM user_documents
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY user_email;
"""


if __name__ == "__main__":
    print(__doc__)
