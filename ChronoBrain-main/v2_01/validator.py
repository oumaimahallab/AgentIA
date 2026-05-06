"""
validator.py — Input validation for ChronoBrain
Blocks garbage queries before they reach the retriever or LLM.
"""

import re
from config import MIN_QUERY_WORDS, MIN_ALPHA_RATIO


def is_valid_query(text: str) -> tuple[bool, str]:
    """
    Validate a user query.
    Returns (is_valid, reason_if_invalid).

    Blocks:
      - Empty strings
      - Single-word inputs
      - Mostly non-alphabetic strings  (e.g. "???", "12345")
      - Repeated-character runs        (e.g. "rrrrrr", "aaaaa")
      - Pure punctuation
    """
    if not text or not text.strip():
        return False, "La question est vide."

    text = text.strip()

    # Must have minimum word count
    words = text.split()
    if len(words) < MIN_QUERY_WORDS:
        return False, "Veuillez poser une question complète (au moins 2 mots)."

    # Must be mostly alphabetic
    total_chars = len(text.replace(" ", ""))
    alpha_chars = sum(c.isalpha() for c in text)
    if total_chars == 0 or alpha_chars / total_chars < MIN_ALPHA_RATIO:
        return False, "La question doit contenir des mots réels."

    # Block repeated-character runs: 'aaaa', 'rrrrrr', 'hmmmmm'
    if re.match(r'^(.)\1{3,}$', text.replace(" ", "")):
        return False, "Entrée non reconnue. Veuillez poser une vraie question."

    # Block pure punctuation / symbol noise
    if re.match(r'^[\W\d]+$', text):
        return False, "Veuillez poser une question en français."

    return True, ""
