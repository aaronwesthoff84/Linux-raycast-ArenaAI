"""Fuzzy subsequence matching with Raycast-like scoring.

The matcher is intentionally small and fast: it looks for the query as a
subsequence of the text and rewards word starts, consecutive runs and exact
case, while penalising gaps.
"""
from __future__ import annotations

import re

_WORD_BOUNDARY = re.compile(r"^[\s._/\-+[\]{}()':\",;@#&|=<>~`$%*!0-9]$")


def fuzzy_score(query: str, text: str) -> int | None:
    """Score ``text`` against ``query``.

    Returns ``None`` when the query is not a subsequence of the text.
    Higher scores are better; callers should sort descending.
    """
    if not query:
        return 0
    if not text:
        return None

    q = query.lower()
    t = text.lower()

    score = 0
    ti = 0
    prev = -1
    for ci, ch in enumerate(q):
        found = t.find(ch, ti)
        if found == -1:
            return None
        if prev >= 0:
            gap = found - prev - 1
            score -= min(gap, 24) * 2
        if found == 0 or _WORD_BOUNDARY.match(t[found - 1]):
            score += 12
        # Exact-case bonus: only meaningful when the user typed uppercase.
        if query[ci].isupper() and text[found] == query[ci]:
            score += 8
        if found == prev + 1:
            score += 6  # consecutive run bonus
        score += 3
        prev = found
        ti = found + 1

    if t.startswith(q):
        score += 20
    # Slightly prefer shorter labels for the same match quality.
    score -= max(0, len(t) - len(q)) // 8
    return score


def fuzzy_rank(query: str, texts: list[str]) -> list[int]:
    """Return indices of ``texts`` matching ``query``, best score first.

    Entries that do not match are omitted.
    """
    scored = []
    for i, text in enumerate(texts):
        s = fuzzy_score(query, text)
        if s is not None:
            scored.append((s, -i, i))  # -i keeps stable order
    scored.sort(reverse=True)
    return [i for _, _, i in scored]
