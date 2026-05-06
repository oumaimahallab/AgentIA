from __future__ import annotations

import re


def is_valid_query(text: str, *, min_words: int = 2, min_alpha_ratio: float = 0.6) -> bool:
    """
    Basic anti-gibberish filter (ported from your ChronoBrain v6/v7 loop).

    Examples rejected:
    - "iiiiiiii"
    - "eee"
    - "??!!"
    """
    t = (text or "").strip()
    if not t:
        return False

    words = t.split()
    if len(words) < min_words:
        return False

    alpha = sum(c.isalpha() for c in t)
    total = len(t.replace(" ", ""))
    if total == 0 or alpha / total < min_alpha_ratio:
        return False

    # repeated single character like "iiiiiiii" or "aaaa"
    if re.match(r"^(.)\1{3,}$", t.replace(" ", "")):
        return False

    return True

