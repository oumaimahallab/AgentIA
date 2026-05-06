"""
postprocess.py — Answer post-processing for ChronoBrain

Two jobs:
  1. strip_hallucinations()  — remove sentences with speculation/uncertainty markers
  2. faithfulness_check()    — keyword overlap between answer and context
"""

import re
from typing import Optional
from config import MIN_OVERLAP_RATIO

# ── Hallucination / hedging markers ──────────────────────────────────────────
# Sentences containing these are stripped from the answer.
HALLUCINATION_MARKERS = [
    r"il pourrait",
    r"il se pourrait",
    r"cela pourrait",
    r"bien que cela",
    r"bien qu'il",
    r"bien qu'elle",
    r"cela dépend",
    r"ça dépend",
    r"je suppose",
    r"probablement",
    r"à titre indicatif",
    r"il est possible que",
    r"selon les cas",
    r"cette information.*n'est pas",
    r"n'est pas mentionné",
    r"n'est pas précisé",
    r"n'a pas été précisé",
    r"n'est pas disponible",
    r"ces informations.*ne sont pas",
    r"pas précisé",
    r"je ne suis pas sûr",
    r"je ne suis pas certain",
    r"il faudrait vérifier",
]

_MARKER_RE = re.compile(
    "|".join(HALLUCINATION_MARKERS),
    re.IGNORECASE,
)

FALLBACK_INDICATORS = [
    "je n'ai pas trouvé",
    "je ne sais pas",
    "je n'ai pas cette information",
    "je ne peux pas répondre",
    "aucune information",
]


def strip_hallucinations(answer: str) -> str:
    """
    Remove sentences that contain hedging / speculation markers.
    Also trims truncated incomplete sentences at the end.
    Returns the cleaned answer, or FALLBACK_MSG if nothing remains.
    """
    if not answer:
        return answer

    # Split on French sentence boundaries
    sentences = re.split(r'(?<=[.!?»])\s+', answer.strip())
    cleaned   = []

    for sentence in sentences:
        if _MARKER_RE.search(sentence):
            continue
        cleaned.append(sentence)

    result = " ".join(cleaned).strip()

    # Truncation guard: if answer ends mid-sentence, trim to last full stop
    if result and result[-1] not in ".!?»":
        last_punct = max(result.rfind("."), result.rfind("!"), result.rfind("?"))
        if last_punct > len(result) // 2:
            result = result[: last_punct + 1].strip()

    return result if result else (
        "Je n'ai pas trouvé cette information dans les données de formation."
    )


def faithfulness_check(question: str, context: str, answer: str) -> dict:
    """
    Lightweight keyword-overlap faithfulness check.
    No second LLM call — runs in < 1ms.

    Returns dict with keys: faithful (bool), overlap (float), method (str).
    """
    answer_lower  = answer.lower()
    context_lower = context.lower()

    # Explicit fallback → always faithful
    if any(p in answer_lower for p in FALLBACK_INDICATORS):
        return {"faithful": True, "overlap": 1.0, "method": "explicit-fallback"}

    # Extract meaningful words (>3 chars) from answer and context
    answer_words  = set(re.findall(r'\b\w{4,}\b', answer_lower))
    context_words = set(re.findall(r'\b\w{4,}\b', context_lower))
    question_words = set(re.findall(r'\b\w{4,}\b', question.lower()))

    if not answer_words:
        return {"faithful": False, "overlap": 0.0, "method": "empty-answer"}

    # Overlap with context (primary signal)
    ctx_overlap = (
        len(answer_words & context_words) / len(answer_words)
        if answer_words else 0.0
    )

    # Overlap with question (secondary signal — ensures relevance)
    q_overlap = (
        len(answer_words & question_words) / max(1, len(question_words))
    )

    combined = 0.7 * ctx_overlap + 0.3 * q_overlap
    faithful = combined >= MIN_OVERLAP_RATIO

    return {
        "faithful": faithful,
        "overlap":  round(combined, 3),
        "method":   f"keyword-overlap(ctx={ctx_overlap:.2f},q={q_overlap:.2f})",
    }
