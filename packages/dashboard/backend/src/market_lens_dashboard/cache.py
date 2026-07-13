"""Shared in-memory TTL cache.

A single, dependency-free cache used across services (FX rates, news, stock
snapshots). Values live for a fixed TTL and are evicted lazily on read.

Design notes:
- In-memory is intentional: on Render's free tier there is no managed Redis,
  and every cached object here is cheap to re-derive (a quote, a news list,
  an FX rate). Losing the cache on restart costs one upstream request.
- If you later add Redis (e.g. Render Key Value), swap the implementation
  behind the same get/set interface — callers don't need to change.
"""

from __future__ import annotations

import time
from typing import Any


class TTLCache:
    def __init__(self, ttl_seconds: float, max_entries: int = 2048):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        # Crude size cap: drop the oldest-expiring entries when full.
        if len(self._store) >= self._max:
            for k in sorted(self._store, key=lambda k: self._store[k][1])[: self._max // 8]:
                self._store.pop(k, None)
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl
        self._store[key] = (value, time.monotonic() + ttl)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()


# Shared instances (module-level singletons, one per concern)
fx_cache = TTLCache(ttl_seconds=60 * 60)        # FX rates: 1 hour
news_cache = TTLCache(ttl_seconds=15 * 60)      # News: 15 minutes
quote_cache = TTLCache(ttl_seconds=60)          # Live quotes: 60 seconds
