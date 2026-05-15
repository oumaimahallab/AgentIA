#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evaluator - LLM-as-a-Judge pour scorer les réponses
Mesure la fidélité au contexte et la pertinence par rapport à la question
"""

import logging
import json
import requests
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ResponseEvaluator:
    """Évaluateur automatique des réponses"""
    
    def __init__(self, config=None):
        if config is None:
            from config import get_config
            config = get_config()
        self.config = config
        
    def evaluate(self, context: str, question: str, answer: str) -> Dict[str, float]:
        """
        Évalue une réponse par rapport au contexte et à la question
        
        Returns:
            Dict: {"faithfulness": score, "relevance": score}
        """
        eval_prompt = (
            "Tu es un juge impartial chargé d'évaluer la qualité d'une réponse générée par une IA.\n"
            "Analyse la réponse basée uniquement sur le contexte fourni.\n\n"
            "CRITÈRES:\n"
            "1. Fidélité (Faithfulness): La réponse est-elle factuellement exacte par rapport au contexte ? (0.0 à 1.0)\n"
            "2. Pertinence (Relevance): La réponse répond-elle directement à la question ? (0.0 à 1.0)\n\n"
            "RENVOIE UNIQUEMENT UN OBJET JSON avec ce format exact: "
            '{"faithfulness": score, "relevance": score}\n\n'
            f"CONTEXTE:\n{context[:3000]}\n\n"
            f"QUESTION: {question}\n"
            f"RÉPONSE: {answer}"
        )
        
        try:
            # On utilise Groq pour l'évaluation (rapide et précis)
            api_key = self.config.llm.GROQ_API_KEY
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": eval_prompt}],
                "temperature": 0.0,
                "response_format": {"type": "json_object"}
            }
            
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                scores = json.loads(content)
                logger.info(f"✓ Evaluation: Faithfulness={scores.get('faithfulness')}, Relevance={scores.get('relevance')}")
                return scores
            else:
                logger.error(f"Erreur API Groq (Evaluator): {response.text}")
        except Exception as e:
            logger.error(f"Erreur lors de l'évaluation: {str(e)}")
            
        return {"faithfulness": 0.0, "relevance": 0.0}
