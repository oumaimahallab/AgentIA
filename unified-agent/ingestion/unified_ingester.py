#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ingestion Unifiée - Traite Documents ET Transcriptions
Support pour: PDF, PPT, Images, Audio, Vidéo, Texte
Avec nettoyage automatique et extraction d'entités
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass
import hashlib
from datetime import datetime

# Import text cleaner
try:
    from ingestion.text_cleaner import TextCleaner, BatchCleaner
except ImportError:
    from text_cleaner import TextCleaner, BatchCleaner

# Import whisper at module level
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("⚠ Module 'whisper' non trouvé. Installation: pip install openai-whisper")

logger = logging.getLogger(__name__)


class SourceType(Enum):
    """Type de source"""
    PDF = "pdf"
    POWERPOINT = "powerpoint"
    IMAGE = "image"
    TEXT = "text"
    AUDIO = "audio"
    VIDEO = "video"
    TRANSCRIPTION = "transcription"


@dataclass
class DocumentMetadata:
    """Métadonnées enrichies d'un document"""
    file_path: Path
    source_type: SourceType
    file_name: str
    file_size: int
    file_hash: str
    created_at: str
    modified_at: str
    language: str = "fr"
    encoding: str = "utf-8"
    
    # Metadata document
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    keywords: Optional[List[str]] = None
    
    # Traitement
    total_pages: int = 0
    total_chunks: int = 0
    processing_time: float = 0.0
    
    # Nettoyage
    cleaning_stats: Optional[Dict[str, Any]] = None
    extracted_entities: Optional[Dict[str, Any]] = None
    
    # Infos agent/session
    user_email: Optional[str] = None
    session_id: Optional[str] = None
    agent_version: Optional[str] = None
    ingestion_timestamp: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": str(self.file_path),
            "source_type": self.source_type.value,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "file_hash": self.file_hash,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "language": self.language,
            "encoding": self.encoding,
            "title": self.title,
            "author": self.author,
            "subject": self.subject,
            "keywords": self.keywords,
            "total_pages": self.total_pages,
            "total_chunks": self.total_chunks,
            "processing_time": self.processing_time,
            "cleaning_stats": self.cleaning_stats,
            "extracted_entities": self.extracted_entities,
            "user_email": self.user_email,
            "session_id": self.session_id,
            "agent_version": self.agent_version,
            "ingestion_timestamp": self.ingestion_timestamp,
        }


class DocumentParser:
    """Parser document base class"""
    
    @staticmethod
    def parse(file_path: Path) -> Tuple[List[str], DocumentMetadata]:
        """Parse un document et retourne chunks + metadata"""
        raise NotImplementedError


class PDFParser(DocumentParser):
    """Parser pour fichiers PDF"""
    
    @staticmethod
    def parse(file_path: Path, progress_callback=None) -> Tuple[List[str], DocumentMetadata]:
        """Parse un PDF avec fallback robuste si PyMuPDF n'est pas disponible."""
        chunks = []
        num_pages = 0
        extracted_text = []
        parser_used = "none"

        try:
            import pymupdf
            parser_used = "pymupdf"
            doc = pymupdf.open(file_path)
            num_pages = len(doc)
            for page_idx, page in enumerate(doc, start=1):
                text = page.get_text()
                if text and text.strip():
                    extracted_text.append(text)
                if progress_callback and num_pages:
                    pct = 20 + int((page_idx / num_pages) * 20)
                    try:
                        progress_callback(f"Parsing PDF ({page_idx}/{num_pages})", min(40, pct))
                    except Exception:
                        pass
            doc.close()
        except Exception as e:
            logger.warning(f"PyMuPDF indisponible ou échec: {e}")
            try:
                from PyPDF2 import PdfReader
                parser_used = "pypdf2"
                reader = PdfReader(str(file_path))
                num_pages = len(reader.pages)
                for page_idx, page in enumerate(reader.pages, start=1):
                    text = page.extract_text() or ""
                    if text and text.strip():
                        extracted_text.append(text)
                    if progress_callback and num_pages:
                        pct = 20 + int((page_idx / num_pages) * 20)
                        try:
                            progress_callback(f"Parsing PDF ({page_idx}/{num_pages})", min(40, pct))
                        except Exception:
                            pass
            except Exception as pdf_error:
                logger.warning(f"Fallback PyPDF2 échoué: {pdf_error}")
                extracted_text = []

        if extracted_text:
            chunks = extracted_text
        else:
            # Fallback final: conserver un message explicite pour éviter l'ingestion vide
            chunks = [
                "[Contenu PDF non extrait automatiquement] Le document a été téléchargé mais son contenu texte n'a pas pu être lu. "
                "Le système peut nécessiter un PDF textuel ou un scan avec OCR."
            ]
            logger.warning(f"PDF vide ou non lisible: {file_path.name}")

        metadata = DocumentMetadata(
            file_path=file_path,
            source_type=SourceType.PDF,
            file_name=file_path.name,
            file_size=file_path.stat().st_size,
            file_hash=PDFParser._compute_hash(file_path),
            created_at=str(file_path.stat().st_ctime),
            modified_at=str(file_path.stat().st_mtime),
            total_pages=num_pages,
        )
        
        logger.info(f"✓ PDF parsé: {file_path.name} ({num_pages} pages, parser={parser_used})")
        
        return chunks, metadata
    
    @staticmethod
    def _compute_hash(file_path: Path) -> str:
        """Compute SHA256 hash du fichier"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()


class PowerPointParser(DocumentParser):
    """Parser pour fichiers PowerPoint"""
    
    @staticmethod
    def parse(file_path: Path) -> Tuple[List[str], DocumentMetadata]:
        """Parse un PowerPoint"""
        from pptx import Presentation
        
        chunks = []
        prs = Presentation(file_path)
        
        for slide_idx, slide in enumerate(prs.slides):
            slide_text = f"--- Slide {slide_idx + 1} ---\n"
            
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text = shape.text.strip()
                    if text:
                        slide_text += text + "\n"
            
            if slide_text.strip():
                chunks.append(slide_text)
        
        metadata = DocumentMetadata(
            file_path=file_path,
            source_type=SourceType.POWERPOINT,
            file_name=file_path.name,
            file_size=file_path.stat().st_size,
            file_hash=PowerPointParser._compute_hash(file_path),
            created_at=str(file_path.stat().st_ctime),
            modified_at=str(file_path.stat().st_mtime),
            total_pages=len(prs.slides),
        )
        
        logger.info(f"✓ PowerPoint parsé: {file_path.name} ({len(prs.slides)} slides)")
        
        return chunks, metadata
    
    @staticmethod
    def _compute_hash(file_path: Path) -> str:
        """Compute SHA256 hash du fichier"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()


class TextParser(DocumentParser):
    """Parser pour fichiers texte"""
    
    @staticmethod
    def parse(file_path: Path, encoding: str = "utf-8") -> Tuple[List[str], DocumentMetadata]:
        """Parse un fichier texte"""
        
        try:
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()
        except UnicodeDecodeError:
            # Essaie autre encoding
            with open(file_path, "r", encoding="latin-1") as f:
                content = f.read()
            encoding = "latin-1"
        
        chunks = [content] if content.strip() else []
        
        metadata = DocumentMetadata(
            file_path=file_path,
            source_type=SourceType.TEXT,
            file_name=file_path.name,
            file_size=file_path.stat().st_size,
            file_hash=TextParser._compute_hash(file_path),
            created_at=str(file_path.stat().st_ctime),
            modified_at=str(file_path.stat().st_mtime),
            encoding=encoding,
            total_pages=1,
        )
        
        logger.info(f"✓ Texte parsé: {file_path.name}")
        
        return chunks, metadata
    
    @staticmethod
    def _compute_hash(file_path: Path) -> str:
        """Compute SHA256 hash du fichier"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()


class DocxParser(DocumentParser):
    """Parser pour fichiers Word (.docx)"""
    
    @staticmethod
    def parse(file_path: Path, progress_callback=None) -> Tuple[List[str], DocumentMetadata]:
        import docx
        
        chunks = []
        
        doc = docx.Document(file_path)
        total_paragraphs = len(doc.paragraphs)
        for para_idx, para in enumerate(doc.paragraphs, start=1):
            text = para.text.strip()
            if text:
                chunks.append(text)
            if progress_callback and total_paragraphs:
                pct = 20 + int((para_idx / total_paragraphs) * 20)
                try:
                    progress_callback(f"Parsing DOCX ({para_idx}/{total_paragraphs})", min(40, pct))
                except Exception:
                    pass
                
        metadata = DocumentMetadata(
            file_path=file_path,
            source_type=SourceType.TEXT,
            file_name=file_path.name,
            file_size=file_path.stat().st_size,
            file_hash=DocxParser._compute_hash(file_path),
            created_at=str(file_path.stat().st_ctime),
            modified_at=str(file_path.stat().st_mtime),
            total_pages=1,
        )
        
        logger.info(f"✓ DOCX parsé: {file_path.name}")
        
        return chunks, metadata
        
    @staticmethod
    def _compute_hash(file_path: Path) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()


class AudioTranscriber:
    """Transcripteur audio/vidéo (Whisper)"""
    
    @staticmethod
    def transcribe(file_path: Path, model: str = "tiny") -> Tuple[str, DocumentMetadata]:
        """Transcribe un fichier audio/vidéo"""
        # Vérifier que whisper est disponible
        if not WHISPER_AVAILABLE:
            logger.error(f"✗ Erreur transcription [{file_path.name}]: Module whisper non disponible")
            logger.error("  → Installer: pip install openai-whisper")
            raise RuntimeError(
                f"Module 'whisper' non trouvé. "
                f"Installez-le avec: pip install openai-whisper"
            )
        
        logger.info(f"🎤 Transcription en cours: {file_path.name} (modèle: {model}, taille: {file_path.stat().st_size / 1024 / 1024:.1f}MB)")
        
        # Charge le modèle
        try:
            logger.info(f"  📥 Chargement modèle Whisper '{model}'...")
            model_obj = whisper.load_model(model)
            logger.info(f"  ✓ Modèle chargé")
        except Exception as e:
            logger.error(f"✗ Erreur chargement modèle Whisper [{model}]: {str(e)}")
            raise RuntimeError(f"Impossible de charger le modèle Whisper: {e}") from e
        
        # Transcribe
        try:
            logger.info(f"  🎙️ Transcription du fichier...")
            result = model_obj.transcribe(str(file_path), language="fr", verbose=False)
            logger.info(f"  ✓ Transcription réussie")
        except Exception as e:
            logger.error(f"✗ Erreur transcription Whisper: {str(e)}")
            raise RuntimeError(f"Erreur lors de la transcription: {e}") from e
        
        # Extrait le texte
        transcription = result.get("text", "").strip()
        if not transcription:
            logger.warning(f"⚠ Transcription vide pour {file_path.name}")
            transcription = "[Pas de contenu audio détecté]"
        
        # Détecte la langue
        detected_language = result.get("language", "fr")
        
        metadata = DocumentMetadata(
            file_path=file_path,
            source_type=SourceType.AUDIO if file_path.suffix.lower() in [".mp3", ".wav", ".m4a"] else SourceType.VIDEO,
            file_name=file_path.name,
            file_size=file_path.stat().st_size,
            file_hash=AudioTranscriber._compute_hash(file_path),
            created_at=str(file_path.stat().st_ctime),
            modified_at=str(file_path.stat().st_mtime),
            language=detected_language,
            total_pages=1,
        )
        
        logger.info(f"✓ Transcription complète: {file_path.name} ({detected_language}, {len(transcription)} chars)")
        
        return transcription, metadata
    
    @staticmethod
    def _compute_hash(file_path: Path) -> str:
        """Compute SHA256 hash du fichier"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()


class UnifiedIngester:
    """Ingestion unifiée pour tous les types de documents
    Avec nettoyage auto, extraction d'entités et enrichissement métadonnées
    """
    
    # Mapping d'extension à parser
    PARSERS = {
        ".pdf": PDFParser,
        ".ppt": PowerPointParser,
        ".pptx": PowerPointParser,
        ".txt": TextParser,
        ".md": TextParser,
        ".docx": DocxParser,
    }
    
    # Audio/Vidéo extensions
    AUDIO_VIDEO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".avi", ".mov"}
    
    def __init__(self, language: str = "fr", clean_text: bool = True, 
                 extract_entities: bool = True, save_chunks_to_db: bool = False):
        """
        Initialize l'ingester
        
        Args:
            language: Langue pour nettoyage (fr/en)
            clean_text: Activer le nettoyage automatique
            extract_entities: Activer l'extraction d'entités
            save_chunks_to_db: Sauvegarder les chunks en PostgreSQL
        """
        self.processed_files = []
        self.failed_files = []
        self.language = language
        self.clean_text_enabled = clean_text
        self.extract_entities_enabled = extract_entities
        self.save_chunks_to_db = save_chunks_to_db
        self.text_cleaner = TextCleaner(language) if clean_text else None
        self.batch_cleaner = BatchCleaner(language) if clean_text else None
        
        # Initialiser le ChunkManager si nécessaire
        if save_chunks_to_db:
            try:
                from ingestion.chunk_manager import ChunkManager
                self.chunk_manager = ChunkManager()
            except ImportError:
                logger.warning("ChunkManager non disponible, chunks ne seront pas sauvegardés")
                self.chunk_manager = None
        else:
            self.chunk_manager = None
    
    def ingest(self, file_path: Path, user_email: Optional[str] = None, 
               session_id: Optional[str] = None, progress_callback=None) -> Optional[Tuple[List[str], DocumentMetadata]]:
        """
        Ingère un fichier avec nettoyage et enrichissement
        
        Args:
            file_path: Chemin du fichier
            user_email: Email de l'utilisateur
            session_id: ID de la session
        """
        import time
        start_time = time.time()
        
        # Vérifie extension
        suffix = file_path.suffix.lower()
        
        # Audio/Vidéo → Transcription
        if suffix in self.AUDIO_VIDEO_EXTENSIONS:
            try:
                if progress_callback:
                    try:
                        progress_callback("Transcription audio/vidéo", 35)
                    except Exception:
                        pass
                text, metadata = AudioTranscriber.transcribe(file_path)
                metadata.source_type = SourceType.TRANSCRIPTION
                
                # Nettoyage
                if self.clean_text_enabled:
                    text = self.text_cleaner.clean_text(text)
                    metadata.cleaning_stats = self.text_cleaner.get_stats()
                
                # Extraction entités
                if self.extract_entities_enabled:
                    metadata.extracted_entities = self.text_cleaner.extract_entities(text)
                
                # Enrichissement metadata
                metadata.user_email = user_email
                metadata.session_id = session_id
                metadata.ingestion_timestamp = datetime.now().isoformat()
                metadata.processing_time = time.time() - start_time
                
                # Sauvegarder les chunks en BD si demandé et que document_id est disponible
                if self.chunk_manager and hasattr(metadata, 'document_id'):
                    try:
                        self.chunk_manager.save_chunks(metadata.document_id, [text])
                        logger.info(f"✓ Transcription sauvegardée pour doc {metadata.document_id}")
                    except Exception as e:
                        logger.warning(f"⚠ Impossible de sauvegarder les chunks: {e}")
                
                self.processed_files.append(metadata)
                logger.info(f"✓ Transcription ingérée: {file_path.name} ({len(text)} chars, nettoyé)")
                return [text], metadata
                
            except Exception as e:
                logger.error(f"✗ Erreur transcription {file_path.name}: {e}")
                self.failed_files.append((file_path, str(e)))
                return None
        
        # Documents → Parse
        elif suffix in self.PARSERS:
            try:
                parser_class = self.PARSERS[suffix]
                if progress_callback:
                    try:
                        progress_callback(f"Parsing {suffix.upper().lstrip('.')}", 25)
                    except Exception:
                        pass
                chunks, metadata = parser_class.parse(file_path, progress_callback=progress_callback)
                
                # Nettoyage des chunks
                if self.clean_text_enabled and chunks:
                    chunks = self.batch_cleaner.process_pipeline(
                        chunks,
                        remove_stopwords=False,  # Garder les stopwords pour contexte
                        deduplicate=True,
                        progress_callback=progress_callback
                    )
                    metadata.cleaning_stats = self.text_cleaner.get_stats()
                
                # Extraction entités du premier chunk
                if self.extract_entities_enabled and chunks:
                    metadata.extracted_entities = self.text_cleaner.extract_entities(chunks[0])
                
                # Keywords
                if chunks:
                    all_text = " ".join(chunks)
                    metadata.keywords = self.text_cleaner.extract_keywords(all_text, top_n=20)
                
                # Enrichissement metadata
                metadata.user_email = user_email
                metadata.session_id = session_id
                metadata.ingestion_timestamp = datetime.now().isoformat()
                metadata.processing_time = time.time() - start_time
                metadata.total_chunks = len(chunks)

                if progress_callback:
                    try:
                        progress_callback("Préparation indexation", 55)
                    except Exception:
                        pass
                
                # Sauvegarder les chunks en BD si demandé et que document_id est disponible
                if self.chunk_manager and hasattr(metadata, 'document_id'):
                    try:
                        self.chunk_manager.save_chunks(metadata.document_id, chunks)
                        logger.info(f"✓ {len(chunks)} chunks sauvegardés pour doc {metadata.document_id}")
                    except Exception as e:
                        logger.warning(f"⚠ Impossible de sauvegarder les chunks: {e}")
                
                self.processed_files.append(metadata)
                logger.info(f"✓ Document ingéré: {file_path.name} ({len(chunks)} chunks, nettoyé)")
                return chunks, metadata
                
            except Exception as e:
                logger.error(f"✗ Erreur parsing {file_path.name}: {e}")
                self.failed_files.append((file_path, str(e)))
                return None
        
        else:
            logger.warning(f"⚠ Format non supporté: {file_path.name}")
            return None
    
    def ingest_directory(self, directory: Path) -> Dict[str, Any]:
        """Ingère tous les fichiers d'un répertoire"""
        
        results = {
            "total_files": 0,
            "successful": 0,
            "failed": 0,
            "documents": [],
        }
        
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                results["total_files"] += 1
                
                result = self.ingest(file_path)
                if result:
                    chunks, metadata = result
                    results["successful"] += 1
                    results["documents"].append({
                        "metadata": metadata.to_dict(),
                        "chunks_count": len(chunks),
                    })
                else:
                    results["failed"] += 1
        
        logger.info(
            f"📊 Ingestion complète: {results['successful']}/{results['total_files']} "
            f"réussis, {results['failed']} échoués"
        )
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques d'ingestion"""
        
        documents_by_type = {}
        for metadata in self.processed_files:
            key = metadata.source_type.value
            documents_by_type[key] = documents_by_type.get(key, 0) + 1
        
        return {
            "total_processed": len(self.processed_files),
            "total_failed": len(self.failed_files),
            "documents_by_type": documents_by_type,
            "failed_files": [(str(f[0]), f[1]) for f in self.failed_files],
        }


# Tests simples
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test ingestion fichier texte
    ingester = UnifiedIngester()
    
    # Crée fichier test
    test_file = Path("/tmp/test.txt")
    test_file.write_text("Ceci est un test de contenu texte.")
    
    result = ingester.ingest(test_file)
    if result:
        chunks, metadata = result
        print(f"✓ Chunks: {len(chunks)}")
        print(f"✓ Metadata: {metadata.file_name}")
    
    print("\n📊 Stats:", ingester.get_stats())