#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ingestion Unifiée - Traite Documents ET Transcriptions
Support pour: PDF, PPT, Images, Audio, Vidéo, Texte
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from enum import Enum
from dataclasses import dataclass
import hashlib

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
    """Métadonnées d'un document"""
    file_path: Path
    source_type: SourceType
    file_name: str
    file_size: int
    file_hash: str
    created_at: str
    modified_at: str
    language: str = "fr"
    encoding: str = "utf-8"
    
    # Metadata additionnel
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    keywords: Optional[List[str]] = None
    
    # Traitement
    total_pages: int = 0
    total_chunks: int = 0
    processing_time: float = 0.0
    
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
    def parse(file_path: Path) -> Tuple[List[str], DocumentMetadata]:
        """Parse un PDF"""
        import PyPDF2
        import pdfplumber
        
        chunks = []
        num_pages = 0
        
        # Essaie pdfplumber d'abord (meilleur pour text extraction)
        try:
            with pdfplumber.open(file_path) as pdf:
                num_pages = len(pdf.pages)
                for page in pdf.pages:
                    text = page.extract_text()
                    if text and text.strip():
                        chunks.append(text)
        except Exception as e:
            logger.warning(f"Erreur pdfplumber: {e}, basculant sur PyPDF2")
            
            # Fallback sur PyPDF2
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                num_pages = len(reader.pages)
                
                for page in reader.pages:
                    text = page.extract_text()
                    if text and text.strip():
                        chunks.append(text)
        
        # Crée metadata
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
        
        logger.info(f"✓ PDF parsé: {file_path.name} ({num_pages} pages)")
        
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


class AudioTranscriber:
    """Transcripteur audio/vidéo (Whisper)"""
    
    @staticmethod
    def transcribe(file_path: Path, model: str = "small") -> Tuple[str, DocumentMetadata]:
        """Transcribe un fichier audio/vidéo"""
        import whisper
        
        logger.info(f"🎤 Transcription en cours: {file_path.name} (modèle: {model})")
        
        # Charge le modèle
        model_obj = whisper.load_model(model)
        
        # Transcribe
        result = model_obj.transcribe(str(file_path))
        
        # Extrait le texte
        transcription = result["text"].strip()
        
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
        
        logger.info(f"✓ Transcription complète: {file_path.name} ({detected_language})")
        
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
    """Ingestion unifiée pour tous les types de documents"""
    
    # Mapping d'extension à parser
    PARSERS = {
        ".pdf": PDFParser,
        ".ppt": PowerPointParser,
        ".pptx": PowerPointParser,
        ".txt": TextParser,
        ".md": TextParser,
    }
    
    # Audio/Vidéo extensions
    AUDIO_VIDEO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".avi", ".mov"}
    
    def __init__(self):
        self.processed_files = []
        self.failed_files = []
    
    def ingest(self, file_path: Path) -> Optional[Tuple[List[str], DocumentMetadata]]:
        """Ingère un fichier"""
        
        # Vérifie extension
        suffix = file_path.suffix.lower()
        
        # Audio/Vidéo → Transcription
        if suffix in self.AUDIO_VIDEO_EXTENSIONS:
            try:
                text, metadata = AudioTranscriber.transcribe(file_path)
                metadata.source_type = SourceType.TRANSCRIPTION
                self.processed_files.append(metadata)
                return [text], metadata
            except Exception as e:
                logger.error(f"✗ Erreur transcription {file_path.name}: {e}")
                self.failed_files.append((file_path, str(e)))
                return None
        
        # Documents → Parse
        elif suffix in self.PARSERS:
            try:
                parser_class = self.PARSERS[suffix]
                chunks, metadata = parser_class.parse(file_path)
                self.processed_files.append(metadata)
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
