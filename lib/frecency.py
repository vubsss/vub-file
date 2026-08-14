"""Recency+frequency ("frecency") ranking on top of lib/store.py's raw counts.

The store keeps a monotonically increasing open-count and a last-used
timestamp per path. This module turns that into a single decayed score at
read time (exponential decay with a configurable half-life), rather than
decaying the stored value on write, so there's no background job needed to
keep old entries from staying artificially high forever.
"""

from __future__ import annotations

import math
import time

from lib.store import Store

HALF_LIFE_SECONDS = 7 * 24 * 3600  # 1 week

# The boost is capped well below the 1000-point gap matcher.py uses between
# ranking tiers, so frecency can only reorder candidates *within* a tier
# (e.g. break ties among several substring matches) and never make a
# frequently-opened weak match outrank a fresh exact/prefix match.
_MAX_BOOST = 500.0
_BOOST_SCALE = 50.0


class Frecency:
    def __init__(self, store: Store, half_life_seconds: float = HALF_LIFE_SECONDS):
        self._store = store
        self._half_life = half_life_seconds

    def record_open(self, path: str) -> None:
        self._store.bump_frecency(path)

    def _decayed_score(self, score: float, last_used: float, now: float) -> float:
        age = max(0.0, now - last_used)
        decay = 0.5 ** (age / self._half_life)
        return score * decay

    def boost(self, path: str) -> float:
        row = self._store.get_frecency(path)
        if row is None:
            return 0.0
        score, last_used = row
        decayed = self._decayed_score(score, last_used, time.time())
        return min(math.log1p(decayed) * _BOOST_SCALE, _MAX_BOOST)

    def top(self, limit: int = 8) -> list[str]:
        now = time.time()
        ranked = sorted(
            self._store.all_frecency(),
            key=lambda row: self._decayed_score(row[1], row[2], now),
            reverse=True,
        )
        return [path for path, _score, _last_used in ranked[:limit]]
