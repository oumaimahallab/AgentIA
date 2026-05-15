#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Détecteur d'Intent - Reconnaît le type de question
Classification: Définition, Procédure, Énumération, Explication, Calcul HR
"""

import logging
import re
from typing import Tuple, Dict, List, Optional
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Types de questions"""
    DEFINITION = "definition"         # c'est quoi?
    PROCEDURE = "procedure"          # comment faire?
    ENUMERATION = "enumeration"      # quels/quelles?
    EXPLANATION = "explanation"      # pourquoi/expliquer?
    HR_CALCULATION = "hr_calculation"  # calculs de congés/heures
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    """Résultat de la détection d'intent"""
    intent: QueryIntent
    confidence: float  # 0.0 à 1.0
    matching_patterns: List[str]
    original_query: str
    
    def __repr__(self) -> str:
        return (
            f"Intent: {self.intent.value} "
            f"(Confidence: {self.confidence:.0%}) "
            f"Patterns: {', '.join(self.matching_patterns[:2])}"
        )


class IntentDetector:
    """Détecteur d'intent de questions"""
    
    # Patterns pour chaque type
    DEFINITION_PATTERNS = [
        r"^c['\s]*est quoi",
        r"qu['\s]*est-?ce qu",
        r"signifie",
        r"définition",
        r"qu['\s]*est-?ce",
        r"quel est",
        r"quelle est",
        r"explique le terme",
        r"qu['\s]*entend-?on",
        r"définir",
        r"comprendre",
    ]
    
    PROCEDURE_PATTERNS = [
        r"comment (?:faire|(?:crée|créer|approuver|valider|fixer))",
        r"comment\s+(?:on|tu)",
        r"a quoi ca sert",
        r"comment ca marche",
        r"étapes",
        r"démarche",
        r"procédure",
        r"procedure",
        r"instructions",
        r"guide",
        r"méthode",
        r"methode",
        r"processus",
        r"comment\s+(?:faire|(?:on|tu))",
    ]
    
    ENUMERATION_PATTERNS = [
        r"quels?(?:\s+sont)?(?:\s+les)?",
        r"quelles?(?:\s+sont)?(?:\s+les)?",
        r"(?:^|\s)types?(?:\s+de)?",
        r"liste",
        r"énumér",
        r"enumér",
        r"lesquels",
        r"combien\s+(?:de|d['\s])",
        r"tous?\s+les",
        r"tous?\s+(?:les|les\s+types)",
    ]
    
    HR_CALCULATION_PATTERNS = [
        r"congé|congés",
        r"vacance|vacances",
        r"jours?\s+(?:de|d['\s])?(?:congé|vacance)",
        r"solde\s+(?:de|d['\s])?congé",
        r"reste|restant",
        r"combien.*(?:jour|congé|vacance)",
        r"heures\s+(?:supplémentaire|extra)",
        r"heure\s+(?:supplémentaire|extra)",
        r"astreinte",
        r"permission",
        r"absence",
        r"congé parental",
        r"maladie",
        r"formation",
        r"déplacement",
    ]
    
    def __init__(self, custom_patterns: Optional[Dict[str, List[str]]] = None):
        """
        Initialize le détecteur
        
        Args:
            custom_patterns: Patterns personnalisés (optionnel)
        """
        self.patterns = {
            QueryIntent.DEFINITION: self.DEFINITION_PATTERNS,
            QueryIntent.PROCEDURE: self.PROCEDURE_PATTERNS,
            QueryIntent.ENUMERATION: self.ENUMERATION_PATTERNS,
            QueryIntent.HR_CALCULATION: self.HR_CALCULATION_PATTERNS,
        }
        
        if custom_patterns:
            for intent, patterns in custom_patterns.items():
                if intent in self.patterns:
                    self.patterns[intent].extend(patterns)
        
        # Compile tous les patterns
        self.compiled_patterns = {}
        for intent, patterns in self.patterns.items():
            self.compiled_patterns[intent] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
    
    def detect(self, query: str) -> IntentResult:
        """
        Détecte le type de question
        
        Args:
            query: Question de l'utilisateur
            
        Returns:
            IntentResult avec le type détecté et la confiance
        """
        
        # Normalise la query
        query_normalized = self._normalize(query)
        
        # Compte les matches par intent
        matches_by_intent = {}
        
        for intent, compiled_patterns in self.compiled_patterns.items():
            matches = []
            for pattern in compiled_patterns:
                if pattern.search(query_normalized):
                    matches.append(pattern.pattern)
            
            if matches:
                matches_by_intent[intent] = matches
        
        # Si pas de match, retourne UNKNOWN
        if not matches_by_intent:
            return IntentResult(
                intent=QueryIntent.UNKNOWN,
                confidence=0.0,
                matching_patterns=[],
                original_query=query,
            )
        
        # Sélectionne l'intent avec le plus de matches
        best_intent = max(
            matches_by_intent.items(),
            key=lambda x: len(x[1]),
        )[0]
        
        matching_patterns = matches_by_intent[best_intent]
        
        # Calcule la confiance (nombre de patterns matchés)
        # Moins il y a de patterns, plus la confiance est faible
        confidence = min(1.0, len(matching_patterns) / 3.0)
        
        logger.debug(
            f"Intent detected: {best_intent.value} "
            f"(confidence: {confidence:.0%}) "
            f"Patterns matched: {len(matching_patterns)}"
        )
        
        return IntentResult(
            intent=best_intent,
            confidence=confidence,
            matching_patterns=matching_patterns,
            original_query=query,
        )
    
    def detect_multiple(
        self,
        query: str,
        top_k: int = 3,
    ) -> List[IntentResult]:
        """
        Retourne les top-k intents possibles
        
        Args:
            query: Question de l'utilisateur
            top_k: Nombre de résultats à retourner
            
        Returns:
            Liste d'IntentResult triée par confiance décroissante
        """
        
        query_normalized = self._normalize(query)
        results = []
        
        for intent, compiled_patterns in self.compiled_patterns.items():
            matches = []
            for pattern in compiled_patterns:
                if pattern.search(query_normalized):
                    matches.append(pattern.pattern)
            
            if matches:
                confidence = min(1.0, len(matches) / 3.0)
                results.append(IntentResult(
                    intent=intent,
                    confidence=confidence,
                    matching_patterns=matches,
                    original_query=query,
                ))
        
        # Trie par confiance décroissante
        results = sorted(results, key=lambda x: x.confidence, reverse=True)
        
        return results[:top_k]
    
    def _normalize(self, text: str) -> str:
        """Normalise le texte pour comparaison"""
        # Minuscule
        text = text.lower()
        
        # Supprime les accents (approximatif)
        replacements = {
            'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
            'à': 'a', 'â': 'a',
            'î': 'i', 'ï': 'i',
            'ô': 'o', 'ö': 'o',
            'ù': 'u', 'û': 'u', 'ü': 'u',
            'ç': 'c',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text
    
    @staticmethod
    def get_system_prompt(intent: QueryIntent) -> str:
        """Retourne le system prompt adapté à l'intent"""
        
        # --- PERSONA PROFESSIONNEL (Entrée Vocale / Sortie Texte) ---
        global_instruction = (
            "Tu es l'Assistant Intelligent Unifié d'Inetum, un expert de haut niveau en solutions RH et Chronotime. "
            "Ton objectif est de fournir des réponses d'une précision chirurgicale, avec un ton professionnel, élégant et rassurant. "
            "\n\nDIRECTIVES DE QUALITÉ CRITIQUES :\n"
            "1. GROUNDING ABSOLU : Ne réponds QU'EN UTILISANT les informations du contexte fourni. Si une information n'est pas présente, indique-le avec courtoisie.\n"
            "2. STRUCTURE PREMIUM : Utilise une mise en forme Markdown riche (Gras, Listes à puces) pour une lecture instantanée.\n"
            "3. CONCISION : Va droit au but. Évite les phrases d'introduction inutiles comme 'D'après les documents...'.\n"
            "4. FIDÉLITÉ : Ta réponse doit être factuellement irréprochable par rapport aux documents. Ne fais aucune supposition.\n"
            "5. RÉFÉRENCES : Ne cite pas tes sources manuellement à la fin, l'interface s'en occupe."
        )

        prompts = {
            QueryIntent.DEFINITION: (
                f"Tu es un expert Chronotime. {global_instruction}\n"
                "Fournis une DÉFINITION PRÉCISE et FACTUELLE basée uniquement sur les documents."
            ),
            QueryIntent.PROCEDURE: (
                f"Tu es un expert technique. {global_instruction}\n"
                "Fournis une RÉPONSE ÉTAPE PAR ÉTAPE claire et numérotée basée sur les guides."
            ),
            QueryIntent.ENUMERATION: (
                f"Tu es un expert en listes. {global_instruction}\n"
                "ÉNUMÈRE LES ÉLÉMENTS de manière structurée selon les documents fournis."
            ),
            QueryIntent.EXPLANATION: (
                f"Tu es un assistant pédagogique. {global_instruction}\n"
                "EXPLIQUE LE CONCEPT de manière claire en te basant sur le contexte."
            ),
            QueryIntent.HR_CALCULATION: (
                f"Tu es un expert RH. {global_instruction}\n"
                "Utilise les outils de calcul et cite les règles issues du contexte."
            ),
            QueryIntent.UNKNOWN: (
                f"Tu es un assistant précis. {global_instruction}\n"
                "Réponds en utilisant strictement les contextes fournis."
            ),
        }
        
        return prompts.get(intent, prompts[QueryIntent.UNKNOWN])


# Tests
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    detector = IntentDetector()
    
    test_queries = [
        "c'est quoi une habilitation?",
        "comment créer un profil utilisateur?",
        "quels sont les types d'heures?",
        "pourquoi faut-il approuver les congés?",
        "combien de jours de congés restants?",
    ]
    
    print("=" * 60)
    print("INTENT DETECTION TESTS")
    print("=" * 60)
    
    for query in test_queries:
        result = detector.detect(query)
        print(f"\n❓ Query: {query}")
        print(f"✓ {result}")
        print(f"  System Prompt: {detector.get_system_prompt(result.intent)[:80]}...")
