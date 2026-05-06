"""ChronoBrain HR assistant package.

This package provides:
- Transcript indexing (ChromaDB) from data/transcripts or data/transcribe
- A chat agent with retrieval-augmented answers + tool calling for leave/vacation math
"""

from .agent import build_hr_agent, build_hr_chatbot, ChronoBrainHR

__all__ = ["build_hr_agent", "build_hr_chatbot", "ChronoBrainHR"]

