#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM Orchestrator - Gère Groq + Ollama avec Fallback
Garantit une réponse (Groq ou Ollama)
"""

import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class LLMOrchestrator:
    """Orchestrates primary (Groq) et fallback (Ollama) LLMs"""
    
    def __init__(
        self,
        groq_config: Optional[Dict] = None,
        ollama_config: Optional[Dict] = None,
    ):
        """
        Initialize LLM Orchestrator
        
        Args:
            groq_config: Configuration Groq
            ollama_config: Configuration Ollama
        """
        self.groq = None
        self.ollama = None
        
        # Initialize Groq (primary)
        if groq_config is not False:  # Allow explicit disable
            try:
                from llm.groq_client import GroqClient
                
                config = groq_config or {}
                self.groq = GroqClient(**config)
                logger.info("✓ Groq initialized as primary LLM")
            except Exception as e:
                logger.warning(f"Groq initialization failed: {e}")
        
        # Initialize Ollama (fallback)
        if ollama_config is not False:  # Allow explicit disable
            try:
                from llm.ollama_client import OllamaClient
                
                config = ollama_config or {}
                self.ollama = OllamaClient(**config)
                logger.info("✓ Ollama initialized as fallback LLM")
            except Exception as e:
                logger.warning(f"Ollama initialization failed: {e}")
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        force_primary: bool = False,
    ) -> Dict[str, str]:
        """
        Génère une réponse (Groq ou Ollama)
        
        Args:
            prompt: Texte de la prompt
            system_prompt: System prompt
            force_primary: Force Groq même si échoue
            
        Returns:
            Dict avec {text, source, error}
        """
        
        # Try Groq first
        if self.groq:
            try:
                text = self.groq.generate(prompt, system_prompt)
                return {
                    "text": text,
                    "source": "groq",
                    "error": None,
                }
            except Exception as e:
                logger.warning(f"Groq generation failed: {e}")
                if force_primary:
                    return {
                        "text": "",
                        "source": "groq",
                        "error": str(e),
                    }
        
        # Fallback to Ollama
        if self.ollama:
            try:
                text = self.ollama.generate(prompt, system_prompt)
                return {
                    "text": text,
                    "source": "ollama",
                    "error": None,
                }
            except Exception as e:
                logger.error(f"Ollama generation failed: {e}")
                return {
                    "text": "",
                    "source": "ollama",
                    "error": str(e),
                }
        
        # No LLM available
        logger.error("No LLM available!")
        return {
            "text": "",
            "source": "none",
            "error": "No LLM available",
        }
    
    def generate_batch(
        self,
        prompts: List[str],
        system_prompt: Optional[str] = None,
        force_primary: bool = False,
    ) -> List[Dict[str, str]]:
        """
        Génère batch de réponses
        
        Args:
            prompts: Liste de prompts
            system_prompt: System prompt
            force_primary: Force Groq
            
        Returns:
            Liste de resultats
        """
        
        results = []
        for prompt in prompts:
            result = self.generate(prompt, system_prompt, force_primary)
            results.append(result)
        
        return results
    
    def get_status(self) -> Dict[str, bool]:
        """Retourne le statut des LLMs"""
        
        groq_available = False
        if self.groq:
            try:
                groq_available = self.groq.is_available()
            except:
                pass
        
        ollama_available = False
        if self.ollama:
            try:
                ollama_available = self.ollama.is_available()
            except:
                pass
        
        return {
            "groq": groq_available,
            "ollama": ollama_available,
            "has_primary": self.groq is not None,
            "has_fallback": self.ollama is not None,
        }


# Test simple
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    orchestrator = LLMOrchestrator()
    
    print("📊 LLM Status:")
    status = orchestrator.get_status()
    for llm, available in status.items():
        print(f"  {llm}: {'✓' if available else '✗'}")
    
    # Try generation
    result = orchestrator.generate(
        "Bonjour! C'est quoi une habilitation?",
        system_prompt="Réponds en français très court"
    )
    
    print(f"\n✓ Generated ({result['source']}):")
    print(result['text'][:200] if result['text'] else "No response")
