#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Text Cleaning and Preprocessing Module
Nettoyage automatique: normalisation, suppression bruit, extraction entités
"""

import re
import logging
from typing import List, Dict, Set, Any
from pathlib import Path
import unicodedata

logger = logging.getLogger(__name__)

# Stopwords français
FR_STOPWORDS = {
    'le', 'la', 'les', 'de', 'du', 'et', 'ou', 'à', 'au', 'avec', 'dans',
    'pour', 'par', 'que', 'qui', 'qu', 'ce', 'cette', 'ces', 'mon', 'ton',
    'son', 'notre', 'votre', 'leur', 'je', 'tu', 'il', 'elle', 'nous', 'vous',
    'ils', 'elles', 'un', 'une', 'des', 'en', 'est', 'sont', 'être', 'avoir',
    'a', 'été', 'étant', 'été', 'j', 'étaient', 'étais', 'était', 'étant',
    'me', 'te', 'se', 'lui', 'moi', 'toi', 'soi', 'mais', 'donc', 'car',
    'si', 'plus', 'moins', 'très', 'aussi', 'bien', 'mal', 'bon', 'mauvais',
}

EN_STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'by', 'is', 'are', 'was', 'were', 'be', 'being', 'been', 'have',
    'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
    'may', 'might', 'must', 'can', 'that', 'this', 'these', 'those', 'i',
    'you', 'he', 'she', 'it', 'we', 'they', 'him', 'her', 'us', 'them',
    'what', 'which', 'who', 'when', 'where', 'why', 'how', 'all', 'each',
    'every', 'both', 'few', 'more', 'most', 'some', 'such', 'no', 'nor',
    'not', 'only', 'own', 'so', 'than', 'too', 'very', 'just',
}


class TextCleaner:
    """Nettoyage et prétraitement de texte"""
    
    def __init__(self, language: str = "fr"):
        """
        Initialize le cleaner
        
        Args:
            language: "fr" ou "en"
        """
        self.language = language
        self.stopwords = FR_STOPWORDS if language == "fr" else EN_STOPWORDS
        self.cleaned_stats = {
            "original_length": 0,
            "cleaned_length": 0,
            "removed_chars": 0,
            "removed_duplicates": 0,
            "detected_entities": []
        }
    
    def clean_text(self, text: str, remove_stopwords: bool = False, 
                   remove_numbers: bool = False) -> str:
        """
        Nettoie un texte: normalisation, suppression bruit, etc
        
        Args:
            text: Texte à nettoyer
            remove_stopwords: Supprimer les stopwords
            remove_numbers: Supprimer les nombres
            
        Returns:
            Texte nettoyé
        """
        if not text:
            return ""
            
        original = text
        self.cleaned_stats["original_length"] = len(text)
        
        # 1. Normalisation Unicode
        text = self._normalize_unicode(text)
        
        # 2. Suppression des URLs
        text = re.sub(r'https?://\S+|www\.\S+', '', text)
        
        # 3. Suppression des emails
        text = re.sub(r'\S+@\S+', '', text)
        
        # 4. Suppression des caractères spéciaux (keep alphanum, accents, espaces)
        text = re.sub(r'[^\w\s\-\.éèêëàâäûüôöçæœñ]', '', text, flags=re.UNICODE)
        
        # 5. Suppression espaces multiples
        text = re.sub(r'\s+', ' ', text)
        
        # 6. Suppression nombres si demandé
        if remove_numbers:
            text = re.sub(r'\d+', '', text)
        
        # 7. Suppression stopwords si demandé
        if remove_stopwords:
            words = text.lower().split()
            words = [w for w in words if w.lower() not in self.stopwords]
            text = ' '.join(words)
        
        # 8. Conversion minuscules (optionnel - peut affecter proper nouns)
        # text = text.lower()  # À activer si besoin
        
        # 9. Suppression leading/trailing whitespace
        text = text.strip()
        
        # Stats
        self.cleaned_stats["cleaned_length"] = len(text)
        self.cleaned_stats["removed_chars"] = len(original) - len(text)
        
        return text
    
    def _normalize_unicode(self, text: str) -> str:
        """Normalise Unicode (NFD -> NFC)"""
        return unicodedata.normalize('NFKC', text)
    
    def remove_duplicates(self, texts: List[str], similarity_threshold: float = 0.95) -> List[str]:
        """
        Supprime les doublons et textes similaires
        
        Args:
            texts: Liste de textes
            similarity_threshold: Seuil de similarité (0-1)
            
        Returns:
            Liste sans doublons
        """
        from difflib import SequenceMatcher
        
        if not texts:
            return []
        
        unique_texts = []
        
        for text in texts:
            is_duplicate = False
            
            for unique_text in unique_texts:
                ratio = SequenceMatcher(None, text.lower(), unique_text.lower()).ratio()
                if ratio >= similarity_threshold:
                    is_duplicate = True
                    self.cleaned_stats["removed_duplicates"] += 1
                    break
            
            if not is_duplicate:
                unique_texts.append(text)
        
        return unique_texts
    
    def extract_entities(self, text: str) -> Dict[str, Any]:
        """
        Extrait les entités nommées du texte
        
        Returns:
            Dict avec emails, URLs, nombres, mots-clés
        """
        entities = {
            "emails": re.findall(r'\S+@\S+', text),
            "urls": re.findall(r'https?://\S+|www\.\S+', text),
            "numbers": re.findall(r'\d+(?:\.\d+)?', text),
            "phone_numbers": re.findall(r'\+?\d{1,3}[\s.-]?\d{1,4}[\s.-]?\d{1,4}[\s.-]?\d{1,9}', text),
        }
        
        self.cleaned_stats["detected_entities"] = entities
        return entities
    
    def extract_keywords(self, text: str, top_n: int = 20) -> List[str]:
        """
        Extrait les mots-clés principaux du texte
        
        Args:
            text: Texte source
            top_n: Nombre de mots-clés à retourner
            
        Returns:
            Liste des mots-clés
        """
        # Tokenize et remove stopwords
        words = text.lower().split()
        words = [w.strip('.,!?;:') for w in words if w and len(w) > 3]
        words = [w for w in words if w not in self.stopwords]
        
        # Count frequency
        from collections import Counter
        freq = Counter(words)
        
        # Get top N
        return [word for word, _ in freq.most_common(top_n)]
    
    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
        """
        Divise un texte en chunks chevauchants
        
        Args:
            text: Texte à diviser
            chunk_size: Taille d'un chunk
            overlap: Chevauchement entre chunks
            
        Returns:
            Liste de chunks
        """
        if not text or chunk_size <= 0:
            return [text] if text else []
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end].strip())
            start = end - overlap
        
        return [c for c in chunks if c]  # Remove empty chunks
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du nettoyage"""
        return self.cleaned_stats.copy()
    
    def reset_stats(self):
        """Réinitialise les statistiques"""
        self.cleaned_stats = {
            "original_length": 0,
            "cleaned_length": 0,
            "removed_chars": 0,
            "removed_duplicates": 0,
            "detected_entities": []
        }


class BatchCleaner:
    """Nettoyage par batch pour plusieurs textes"""
    
    def __init__(self, language: str = "fr"):
        self.cleaner = TextCleaner(language)
    
    def clean_batch(self, texts: List[str], **kwargs) -> List[str]:
        """Nettoie un batch de textes"""
        return [self.cleaner.clean_text(text, **kwargs) for text in texts]
    
    def deduplicate_batch(self, texts: List[str], **kwargs) -> List[str]:
        """Supprime les doublons dans un batch"""
        return self.cleaner.remove_duplicates(texts, **kwargs)
    
    def process_pipeline(self, texts: List[str], 
                        remove_stopwords: bool = False,
                        deduplicate: bool = True,
                        progress_callback=None) -> List[str]:
        """
        Pipeline complet: nettoyage + déduplication
        
        Args:
            texts: Liste de textes
            remove_stopwords: Supprimer les stopwords
            deduplicate: Supprimer les doublons
            
        Returns:
            Textes traités
        """
        # Clean each chunk with optional progress callback
        cleaned = []
        total = len(texts)
        for index, text in enumerate(texts, start=1):
            cleaned_text = self.cleaner.clean_text(text, remove_stopwords=remove_stopwords)
            cleaned.append(cleaned_text)
            if progress_callback and total:
                pct = 45 + int((index / total) * 10)
                try:
                    progress_callback(f"Nettoyage chunk {index}/{total}", min(54, pct))
                except Exception:
                    pass
        
        # Deduplicate if needed
        if deduplicate:
            if progress_callback:
                try:
                    progress_callback("Déduplication des chunks", 55)
                except Exception:
                    pass
            cleaned = self.deduplicate_batch(cleaned)
        
        # Filter empty
        cleaned = [t for t in cleaned if t and len(t) > 10]
        
        return cleaned


if __name__ == "__main__":
    # Test
    cleaner = TextCleaner("fr")
    
    test_text = """
    Bonjour! Voici un test de nettoyage.
    Email: test@example.com   URL: https://example.com
    Il y a trop d'espaces    et des caractères spéciaux!!!
    """
    
    cleaned = cleaner.clean_text(test_text)
    print(f"Original: {test_text}")
    print(f"Cleaned: {cleaned}")
    print(f"Stats: {cleaner.get_stats()}")
    
    # Extract entities
    entities = cleaner.extract_entities(test_text)
    print(f"Entities: {entities}")
    
    # Keywords
    keywords = cleaner.extract_keywords(test_text)
    print(f"Keywords: {keywords}")
