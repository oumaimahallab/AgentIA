#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Groq LLM Client - Wrapper pour Groq API
Primary LLM pour l'agent
"""

import logging
import os
from typing import Dict, Optional, Any, List

logger = logging.getLogger(__name__)


class GroqClient:
    """Client pour Groq LLM API"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "llama-3.1-8b-instant",
        temperature: float = 0.3,
        max_tokens: int = 1024,
        timeout: int = 30,
    ):
        """
        Initialize Groq Client
        
        Args:
            api_key: Groq API key (from .env if None)
            model: Model name
            temperature: Generation temperature
            max_tokens: Max tokens to generate
            timeout: Request timeout en secondes
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found in env or parameters")
        
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        
        self._init_client()
    
    def _init_client(self):
        """Initialize le client Groq"""
        try:
            from groq import Groq
            
            self.client = Groq(
                api_key=self.api_key,
                timeout=self.timeout,
            )
            logger.info(f"✓ Groq client initialized (model: {self.model})")
        except ImportError:
            logger.error("groq library not installed. Install with: pip install groq")
            raise
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Génère une réponse
        
        Args:
            prompt: Texte de la prompt
            system_prompt: System prompt (optionnel)
            
        Returns:
            Texte généré
        """
        
        import time
        import groq
        
        max_retries = 5
        for attempt in range(max_retries):
            try:
                messages = []
                
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                
                messages.append({"role": "user", "content": prompt})
                
                # Call Groq
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                
                text = response.choices[0].message.content.strip()
                logger.debug(f"Generated {len(text)} chars")
                return text
            
            except groq.RateLimitError as e:
                wait_time = (attempt + 1) * 5
                logger.warning(f"⚠️ Groq Rate Limit (429). Retry in {wait_time}s... ({e})")
                time.sleep(wait_time)
                if attempt == max_retries - 1:
                    raise
                    
            except Exception as e:
                if "429" in str(e):
                    wait_time = (attempt + 1) * 5
                    logger.warning(f"⚠️ Groq Rate Limit (detected in string). Retry in {wait_time}s...")
                    time.sleep(wait_time)
                    if attempt == max_retries - 1:
                        raise
                    continue
                    
                logger.error(f"Groq generation error: {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2)
        
        return ""
    
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
                logger.error(f"Batch generation error for prompt: {e}")
                results.append(f"Error: {str(e)}")
        
        return results
    
    def is_available(self) -> bool:
        """Check si le service est disponible"""
        try:
            # Simple ping
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=10,
            )
            return response.choices[0].message.content is not None
        except Exception as e:
            logger.warning(f"Groq not available: {e}")
            return False


# Test simple
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    try:
        client = GroqClient()
        
        if client.is_available():
            result = client.generate(
                "Explique en une phrase ce qu'est une habilitation",
                system_prompt="Réponds en français",
            )
            print(f"✓ Response: {result}")
        else:
            print("⚠️ Groq not available")
    
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print("Set GROQ_API_KEY in .env or pass as parameter")
