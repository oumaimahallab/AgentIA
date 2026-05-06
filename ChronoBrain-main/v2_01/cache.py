"""
cache.py — LRU response cache for ChronoBrain
Skips LLM entirely for repeated questions.
"""

import hashlib
from collections import deque
from typing import Optional
from config import CACHE_SIZE


class ResponseCache:
    def __init__(self, maxsize: int = CACHE_SIZE):
        self._cache: dict[str, str] = {}
        self._keys  = deque(maxlen=maxsize)

    def _key(self, text: str) -> str:
        return hashlib.md5(text.lower().strip().encode()).hexdigest()

    def get(self, question: str) -> Optional[str]:
        return self._cache.get(self._key(question))

    def set(self, question: str, answer: str) -> None:
        k = self._key(question)
        if k not in self._cache:
            if len(self._keys) == self._keys.maxlen:
                evicted = self._keys[0]
                self._cache.pop(evicted, None)
            self._keys.append(k)
        self._cache[k] = answer

    def invalidate(self, question: str) -> None:
        k = self._key(question)
        self._cache.pop(k, None)

    def clear(self) -> None:
        self._cache.clear()
        self._keys.clear()

    def __len__(self) -> int:
        return len(self._cache)
