"""
llm.py — LLM interface for ChronoBrain

Handles:
  - Prompt construction (structured, grounded, French)
  - Safe Ollama call with retry + timeout guard
  - Conversation history management
"""

import time
import logging
from typing import Optional

import httpx
import ollama

from config import (
    LLM_MODEL, LLM_TIMEOUT, LLM_RETRIES,
    MAX_CONTEXT_TOKENS, HISTORY_TURNS, COMPANY_NAME,
)
from hybrid_retriever import RetrievedChunk

log = logging.getLogger("chronobrain.llm")


# ── Prompt builder ────────────────────────────────────────────────────────────

def build_prompt(
    context:       str,
    chunks:        list[RetrievedChunk],
    history:       list[tuple[str, str]],
    question:      str,
    low_confidence: bool = False,
) -> str:
    """
    Build the full LLM prompt.
    - Structured context with source + timestamp per chunk
    - Conversation history
    - Strict grounding rules
    - French, detailed, structured output required
    """
    # Build per-chunk context block with timestamps
    context_blocks = []
    for i, chunk in enumerate(chunks, 1):
        asr_note = " [⚠ transcription incertaine]" if chunk.has_asr_warning else ""
        context_blocks.append(
            f"[Extrait {i} | {chunk.source} | {chunk.start_time} → {chunk.end_time}{asr_note}]\n"
            f"{chunk.text}"
        )
    context_str = "\n\n".join(context_blocks)

    # Trim to token budget
    char_budget = MAX_CONTEXT_TOKENS * 4
    if len(context_str) > char_budget:
        context_str = context_str[:char_budget] + "…"

    # History
    history_str = ""
    if history:
        history_str = (
            "## Historique récent\n"
            + "\n".join(f"Q: {q}\nR: {a}" for q, a in history[-HISTORY_TURNS:])
            + "\n\n"
        )

    # Low-confidence warning
    confidence_note = (
        "\n⚠ ATTENTION: Les extraits ci-dessous sont de faible pertinence. "
        "Si tu n'es pas certain, réponds: "
        "\"Je n'ai pas trouvé cette information dans les données de formation.\"\n"
        if low_confidence else ""
    )

    return (
        f"Tu es ChronoBrain, l'assistant expert de {COMPANY_NAME}.\n"
        "Tu réponds UNIQUEMENT en te basant sur les extraits de formation fournis ci-dessous.\n"
        "Tu n'utilises JAMAIS tes connaissances générales ou extérieures.\n\n"
        "## Règles absolues\n"
        "1. Réponds exclusivement en français.\n"
        "2. Réponds de manière DÉTAILLÉE et STRUCTURÉE (points numérotés ou titres).\n"
        "3. Cite les timestamps sous la forme [Source: fichier | HH:MM → HH:MM] pour chaque élément.\n"
        "4. N'invente AUCUN fait, chiffre, règle ou définition absent des extraits.\n"
        "5. N'utilise PAS ces formulations: 'cela dépend', 'il pourrait', 'pas précisé', "
        "'probablement', 'je suppose'.\n"
        "6. Si l'information n'est pas dans les extraits, réponds EXACTEMENT:\n"
        "   \"Je n'ai pas trouvé cette information dans les données de formation.\"\n\n"
        f"{confidence_note}"
        "## Extraits de formation\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{context_str}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{history_str}"
        f"## Question\n{question}\n\n"
        "## Réponse détaillée (basée uniquement sur les extraits ci-dessus)\n"
    )


# ── Safe LLM call ─────────────────────────────────────────────────────────────

def safe_complete(prompt: str) -> Optional[str]:
    """
    Call Ollama with retry on timeout.
    Returns the response string, or None if all attempts fail.
    Never raises or crashes the caller.
    """
    for attempt in range(LLM_RETRIES + 1):
        try:
            response = ollama.generate(
                model=LLM_MODEL,
                prompt=prompt,
                options={"num_predict": 1024, "temperature": 0.1},
            )
            return response["response"].strip()

        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            if attempt < LLM_RETRIES:
                log.warning("Ollama timeout (attempt %d/%d), retry in 2s…",
                            attempt + 1, LLM_RETRIES + 1)
                time.sleep(2)
            else:
                log.warning("Ollama failed after %d attempts.", LLM_RETRIES + 1)
                return None

        except Exception as e:
            log.warning("Ollama error: %s", e)
            return None

    return None


# ── History manager ───────────────────────────────────────────────────────────

class ConversationHistory:
    def __init__(self, max_turns: int = HISTORY_TURNS):
        self._turns:     list[tuple[str, str]] = []
        self._max_turns = max_turns

    def add(self, question: str, answer: str) -> None:
        self._turns.append((question, answer))
        if len(self._turns) > self._max_turns:
            self._turns.pop(0)

    def get(self) -> list[tuple[str, str]]:
        return list(self._turns)

    def clear(self) -> None:
        self._turns.clear()
