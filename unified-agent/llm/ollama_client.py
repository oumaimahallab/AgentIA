#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ollama LLM Client - Wrapper pour Ollama Local LLM
Fallback LLM (local, aucune limite)
"""

import logging
import os
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class OllamaClient:
    """Client pour Ollama Local LLM"""
    
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2:3b",
        temperature: float = 0.3,
        max_tokens: int = 1024,
        timeout: int = 60,
    ):
        """
        Initialize Ollama Client
        
        Args:
            base_url: URL du serveur Ollama
            model: Nom du modèle
            temperature: Generation temperature
            max_tokens: Max tokens
            timeout: Request timeout
        """
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        
        self._init_client()
    
    def _init_client(self):
        """Initialize le client Ollama"""
        try:
            import requests
            
            self.requests = requests
            logger.info(f"✓ Ollama client initialized (model: {self.model}, url: {self.base_url})")
        except ImportError:
            logger.error("requests library not installed. Install with: pip install requests")
            raise
    
    def is_available(self) -> bool:
        """Check si Ollama est disponible"""
        try:
            response = self.requests.get(
                f"{self.base_url}/api/tags",
                timeout=5,
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
            return False
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Génère une réponse
        
        Args:
            prompt: Texte de la prompt
            system_prompt: System prompt
            
        Returns:
            Texte généré
        """
        
        try:
            # Combine prompts
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"
            
            # Call Ollama
            response = self.requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": self.max_tokens,
                    },
                },
                timeout=self.timeout,
            )
            
            if response.status_code != 200:
                raise Exception(f"Ollama error: {response.text}")
            
            result = response.json()
            text = result.get("response", "").strip()
            
            logger.debug(f"Generated {len(text)} chars")
            
            return text
        
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            raise
    
    def generate_batch(
        self,
        prompts: List[str],
        system_prompt: Optional[str] = None,
    ) -> List[str]:
        """
        Génère batch de réponses
        
        Args:
            prompts: Liste de prompts
            system_prompt: System prompt
            
        Returns:
            Liste de réponses
        """
        
        results = []
        for prompt in prompts:
            try:
                result = self.generate(prompt, system_prompt)
                results.append(result)
            except Exception as e:
                logger.error(f"Batch generation error: {e}")
                results.append(f"Error: {str(e)}")
        
        return results


# Test simple
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    client = OllamaClient()
    
    if client.is_available():
        print("✓ Ollama is available!")
        
        result = client.generate(
            "Explique en une phrase ce qu'est une habilitation",
            system_prompt="Réponds en français",
        )
        print(f"Response: {result}")
    else:
        print("⚠️ Ollama not available")
        print("Make sure Ollama is running: ollama serve")
        print("And you have a model: ollama pull llama2")
