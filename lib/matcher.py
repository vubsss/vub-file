"""Ranks FileIndex entries against a query string.

Matching is deliberately restricted to a contiguous-substring pre-filter
(cheap: a plain `in` check against each entry's precomputed lowercase name)
rather than true fzf-style non-contiguous subsequence matching — at
home-directory scale (tens to hundreds of thousands of entries) a plain
substring scan of short strings stays in the low single-digit milliseconds
in pure Python, which is what makes per-keystroke queries free of the
subprocess/disk-walk cost the existing extensions pay. Within that
substring-filtered candidate set, results are still ranked by *where* the
match falls: exact name match, then prefix, then right after a path/word
separator, then anywhere else — which gets most of the practical benefit of
fuzzy ranking without the more expensive matching pass.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable, Iterable

from lib.index import Entry

_BOUNDARY_CHARS = frozenset("_-. /")

_TIER_EXACT = 3
_TIER_PREFIX = 2
_TIER_BOUNDARY = 1
_TIER_SUBSTRING = 0


def _tier(name_lower: str, query_lower: str, match_index: int) -> int:
    if name_lower == query_lower:
        return _TIER_EXACT
    if name_lower.startswith(query_lower):
        return _TIER_PREFIX
    if match_index == 0 or name_lower[match_index - 1] in _BOUNDARY_CHARS:
        return _TIER_BOUNDARY
    return _TIER_SUBSTRING


def score(entry: Entry, query_lower: str) -> float | None:
    match_index = entry.name_lower.find(query_lower)
    if match_index == -1:
        return None
    tier = _tier(entry.name_lower, query_lower, match_index)
    length_bonus = 1.0 / (1 + len(entry.path))
    return tier * 1000 + length_bonus


def search(
    entries: Iterable[Entry],
    query: str,
    limit: int = 8,
    boost: Callable[[str], float] | None = None,
) -> list[Entry]:
    query_lower = query.lower()
    if not query_lower:
        return []

    candidates: list[tuple[float, Entry]] = []
    for entry in entries:
        if query_lower not in entry.name_lower:
            continue
        entry_score = score(entry, query_lower)
        if entry_score is None:
            continue
        if boost is not None:
            entry_score += boost(entry.path)
        candidates.append((entry_score, entry))

    top = heapq.nlargest(limit, candidates, key=lambda pair: pair[0])
    return [entry for _, entry in top]
