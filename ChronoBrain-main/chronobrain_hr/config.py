from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HRConfig:
    # Data
    transcripts_dir: Path
    chroma_db_dir: Path
    collection_name: str = "chronobrain_hr"

    # Models
    llm_provider: str = "ollama"  # currently supported: "ollama"
    llm_model: str = "phi3"
    embed_model: str = "BAAI/bge-small-en-v1.5"

    # Retrieval
    top_k: int = 8
    min_score: float = 0.30
    fallback_top_k: int = 2

    # Prompt
    language: str = "fr"


def _default_transcripts_dir() -> Path:
    """
    Prefer data/transcribe (user wording), fall back to data/transcripts (existing repo).
    """
    root = Path(__file__).resolve().parents[1]
    candidate_a = root / "data" / "transcribe"
    candidate_b = root / "data" / "transcripts"
    if candidate_a.exists():
        return candidate_a
    return candidate_b


def default_config() -> HRConfig:
    root = Path(__file__).resolve().parents[1]
    transcripts_dir = Path(os.environ.get("CHRONOBRAIN_TRANSCRIPTS_DIR", str(_default_transcripts_dir())))
    chroma_db_dir = Path(os.environ.get("CHRONOBRAIN_CHROMA_DIR", str(root / "data" / "chroma_hr")))
    llm_model = os.environ.get("CHRONOBRAIN_LLM_MODEL", "phi3")
    embed_model = os.environ.get("CHRONOBRAIN_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
    return HRConfig(
        transcripts_dir=transcripts_dir,
        chroma_db_dir=chroma_db_dir,
        llm_model=llm_model,
        embed_model=embed_model,
    )

