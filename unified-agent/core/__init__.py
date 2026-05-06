# Core module
from .deduplication import DeduplicationEngine, SourceType, MergedChunk, ChunkMetadata
from .intent_detector import IntentDetector, QueryIntent, IntentResult

__all__ = [
    "DeduplicationEngine",
    "SourceType",
    "MergedChunk",
    "ChunkMetadata",
    "IntentDetector",
    "QueryIntent",
    "IntentResult",
]
