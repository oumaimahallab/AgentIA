#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for LLM modules (Phase 3)
"""

import unittest
import logging
from unittest.mock import Mock, patch, MagicMock

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestGroqClient(unittest.TestCase):
    """Tests pour GroqClient"""
    
    def setUp(self):
        """Setup test fixtures"""
        from llm.groq_client import GroqClient
        
        self.client = GroqClient()
    
    def test_initialization(self):
        """Test client initialization"""
        self.assertIsNotNone(self.client)
        self.assertIsNotNone(self.client.client)
    
    @patch('llm.groq_client.Groq')
    def test_generate_success(self, mock_groq):
        """Test successful generation"""
        from llm.groq_client import GroqClient
        
        # Mock the Groq API response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Réponse test"))]
        
        mock_instance = Mock()
        mock_instance.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_instance
        
        client = GroqClient()
        result = client.generate(
            prompt="Question de test?",
            system_prompt="Tu es un assistant"
        )
        
        self.assertIn("text", result)
        self.assertEqual(result["source"], "groq")
    
    def test_format_messages(self):
        """Test message formatting"""
        from llm.groq_client import GroqClient
        
        messages = GroqClient._format_messages(
            prompt="Test prompt",
            system_prompt="Test system"
        )
        
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")


class TestOllamaClient(unittest.TestCase):
    """Tests pour OllamaClient"""
    
    def setUp(self):
        """Setup test fixtures"""
        from llm.ollama_client import OllamaClient
        
        self.client = OllamaClient(endpoint="http://localhost:11434")
    
    def test_initialization(self):
        """Test client initialization"""
        self.assertIsNotNone(self.client)
        self.assertEqual(self.client.endpoint, "http://localhost:11434")
        self.assertEqual(self.client.model, "llama2")
    
    @patch('requests.post')
    def test_generate_success(self, mock_post):
        """Test successful generation"""
        from llm.ollama_client import OllamaClient
        
        # Mock the response
        mock_response = Mock()
        mock_response.json.return_value = {
            "response": "Réponse test"
        }
        mock_post.return_value = mock_response
        
        client = OllamaClient()
        result = client.generate(prompt="Question?")
        
        self.assertIn("text", result)
        self.assertEqual(result["source"], "ollama")
    
    @patch('requests.post')
    def test_model_list(self, mock_post):
        """Test listing models"""
        from llm.ollama_client import OllamaClient
        
        mock_response = Mock()
        mock_response.json.return_value = {
            "models": [
                {"name": "llama2"},
                {"name": "mistral"},
            ]
        }
        mock_post.return_value = mock_response
        
        client = OllamaClient()
        models = client.list_models()
        
        self.assertGreater(len(models), 0)


class TestLLMOrchestrator(unittest.TestCase):
    """Tests pour LLMOrchestrator"""
    
    def setUp(self):
        """Setup test fixtures"""
        from llm.llm_orchestrator import LLMOrchestrator
        
        self.orchestrator = LLMOrchestrator()
    
    def test_initialization(self):
        """Test orchestrator initialization"""
        self.assertIsNotNone(self.orchestrator)
        self.assertIsNotNone(self.orchestrator.groq_client)
        self.assertIsNotNone(self.orchestrator.ollama_client)
    
    @patch('llm.groq_client.Groq')
    def test_generate_with_groq(self, mock_groq):
        """Test generation with Groq"""
        from llm.llm_orchestrator import LLMOrchestrator
        
        # Mock successful Groq response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Réponse Groq"))]
        
        mock_instance = Mock()
        mock_instance.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_instance
        
        orchestrator = LLMOrchestrator()
        result = orchestrator.generate(
            prompt="Test?",
            system_prompt="System"
        )
        
        self.assertIn("text", result)
        self.assertEqual(result["source"], "groq")
    
    @patch('llm.groq_client.Groq')
    @patch('requests.post')
    def test_fallback_to_ollama(self, mock_post, mock_groq):
        """Test fallback to Ollama when Groq fails"""
        from llm.llm_orchestrator import LLMOrchestrator
        
        # Mock Groq failure
        mock_groq.side_effect = Exception("Groq API Error")
        
        # Mock Ollama success
        mock_response = Mock()
        mock_response.json.return_value = {
            "response": "Réponse Ollama"
        }
        mock_post.return_value = mock_response
        
        orchestrator = LLMOrchestrator()
        result = orchestrator.generate(
            prompt="Test?",
            system_prompt="System"
        )
        
        # Should succeed via Ollama
        self.assertIn("text", result)
        self.assertEqual(result["source"], "ollama")


class TestResponseValidation(unittest.TestCase):
    """Tests pour validation des réponses LLM"""
    
    def test_response_quality_check(self):
        """Test response quality validation"""
        from llm.llm_orchestrator import LLMOrchestrator
        
        # Test good response
        good_response = "Ceci est une réponse de bonne qualité avec du contenu."
        quality = LLMOrchestrator._validate_response(good_response)
        self.assertTrue(quality > 0.5)
        
        # Test bad response
        bad_response = ""
        quality = LLMOrchestrator._validate_response(bad_response)
        self.assertEqual(quality, 0)
        
        # Test minimal response
        minimal_response = "Ok"
        quality = LLMOrchestrator._validate_response(minimal_response)
        self.assertGreater(quality, 0)


class TestHRTools(unittest.TestCase):
    """Tests pour HR Tools"""
    
    def setUp(self):
        """Setup test fixtures"""
        from tools.hr_tools import HRTools
        
        self.hr_tools = HRTools()
    
    def test_leave_calculation(self):
        """Test leave balance calculation"""
        # Example: 30 days total, 10 used, should return 20
        balance = self.hr_tools.calculate_leave_balance(
            total_days=30,
            used_days=10
        )
        
        self.assertEqual(balance, 20)
    
    def test_working_days(self):
        """Test working days calculation"""
        from datetime import date
        
        # Between two dates should exclude weekends
        start = date(2024, 1, 1)  # Monday
        end = date(2024, 1, 5)    # Friday
        
        days = self.hr_tools.working_days_between(start, end)
        
        # Should be 5 days (Mon-Fri)
        self.assertEqual(days, 5)
    
    def test_tool_selection(self):
        """Test HR tool selection based on intent"""
        from core.intent_detector import QueryIntent
        
        # Should select HR tool for calculations
        should_use = self.hr_tools.should_use_hr_tool(
            query="Combien de jours de congés me reste-t-il?",
            intent=QueryIntent.HR_CALCULATION
        )
        
        self.assertTrue(should_use)


class TestIntegration(unittest.TestCase):
    """Integration tests"""
    
    @patch('llm.groq_client.Groq')
    def test_end_to_end_flow(self, mock_groq):
        """Test complete flow from question to answer"""
        from orchestration.dispatcher import Dispatcher, DispatcherMode
        
        # Mock Groq response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Réponse complète"))]
        
        mock_instance = Mock()
        mock_instance.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_instance
        
        dispatcher = Dispatcher()
        result = dispatcher.dispatch(
            "Qu'est-ce qu'une habilitation?",
            DispatcherMode.SINGLE
        )
        
        self.assertTrue(result.get("success", False))
        self.assertIn("answer", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
