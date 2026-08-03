import unittest

from orchestration.agent import UnifiedAgent


class TestConversationContext(unittest.TestCase):
    def setUp(self):
        from orchestration.agent import ConversationBuffer
        self.agent = UnifiedAgent.__new__(UnifiedAgent)
        self.agent.conversation_buffer = ConversationBuffer(max_turns=6)

    def test_format_conversation_history(self):
        history = [
            {"role": "user", "content": "Est-ce que l'anomalie est bloquante ?"},
            {"role": "assistant", "content": "Non, elle est non bloquante."},
        ]

        formatted = self.agent._format_conversation_history(history)

        self.assertIn("Utilisateur:", formatted)
        self.assertIn("Assistant:", formatted)
        self.assertIn("Est-ce que l'anomalie est bloquante ?", formatted)
        self.assertIn("Non, elle est non bloquante.", formatted)

    def test_build_follow_up_context_for_pronouns(self):
        history = [
            {"role": "user", "content": "Est-ce que l'anomalie est bloquante ?"},
            {"role": "assistant", "content": "Non, elle est non bloquante."},
        ]

        follow_up_context = self.agent._build_follow_up_context("Et quelle est sa priorité ?", history)

        self.assertIn("anomalie", follow_up_context.lower())
        self.assertIn("priorité", follow_up_context.lower())

    def test_get_previous_exchange_handles_duplicate_user_message(self):
        self.agent.conversation_buffer.add_user_message("donne moi les etapes")
        self.agent.conversation_buffer.add_assistant_message("Etape 1: Saisie")
        self.agent.conversation_buffer.add_user_message("non la premiere etape est Planification")
        self.agent.conversation_buffer.add_user_message("non la premiere etape est Planification")

        exchange = self.agent._get_previous_exchange()

        self.assertIsNotNone(exchange)
        self.assertEqual(exchange[0], "donne moi les etapes")
        self.assertEqual(exchange[1], "Etape 1: Saisie")

    def test_looks_like_correction(self):
        self.assertTrue(self.agent._looks_like_correction("non la premiere etape est Planification"))
        self.assertFalse(self.agent._looks_like_correction("peux-tu me donner plus de details ?"))


if __name__ == "__main__":
    unittest.main()
