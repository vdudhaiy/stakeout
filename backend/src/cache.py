"""Shared in-memory TTL cache.

A single, dependency-free cache used across services (FX rates, news, stock
snapshots). Values live for a fixed TTL and are evicted lazily on read.

Design notes:
- In-memory is intentional: on Render's free tier there is no managed Redis,
  and every cached object here is cheap to re-derive (a quote, a news list,
  an FX rate). Losing the cache on restart costs one upstream request.
- If you later add Redis (e.g. Render Key Value), swap the implementation
  behind the same get/set interface — callers don't need to change.
- A TTL cache alone only dedupes *sequential* callers. `single_flight` below
  covers the concurrent case, which is the one that actually spends the
  upstream quota (a page load fires a dozen requests at once, and every one
  of them misses a cache that nobody has populated yet).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
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

    def invalidate_prefix(self, prefix: str) -> None:
        """Drop every entry whose key starts with `prefix`.

        Callers key related entries as "<ticker>:<aspect>", so this is how a
        ticker-level change (deleted, re-archived) clears all of its derived
        snapshots at once.
        """
        for k in [k for k in self._store if k.startswith(prefix)]:
            self._store.pop(k, None)

    def clear(self) -> None:
        self._store.clear()


# Shared instances (module-level singletons, one per concern)
fx_cache = TTLCache(ttl_seconds=60 * 60)        # FX rates: 1 hour
news_cache = TTLCache(ttl_seconds=15 * 60)      # News: 15 minutes
quote_cache = TTLCache(ttl_seconds=60)          # Live quotes: 60 seconds
index_cache = TTLCache(ttl_seconds=10 * 60)     # Major index quotes/sparklines: 10 minutes
info_cache = TTLCache(ttl_seconds=24 * 60 * 60) # Ticker sector/industry classification: 24 hours
ai_cache = TTLCache(ttl_seconds=60 * 60)        # AI stock insight summaries: 1 hour
dividend_sync_cache = TTLCache(ttl_seconds=24 * 60 * 60)  # Throttles yfinance dividend re-sync: 24 hours
search_cache = TTLCache(ttl_seconds=5 * 60)     # Ticker autocomplete results: 5 minutes
sec_ticker_cache = TTLCache(ttl_seconds=24 * 60 * 60)  # SEC ticker->company-name registry: one cached blob, refreshed daily
performance_cache = TTLCache(ttl_seconds=10 * 60, max_entries=512)  # Portfolio-vs-benchmark payloads: per (user, market, portfolio, range)


# ── Request coalescing ────────────────────────────────────────────────────

# key -> the in-flight task computing it. Safe without a lock: every caller
# runs on the same event loop, and the check-then-create below never awaits
# in between.
_inflight: dict[str, asyncio.Task] = {}


async def single_flight(key: str, factory: Callable[[], Awaitable[Any]]) -> Any:
    """Run `factory()` once for `key`, no matter how many callers ask at once.

    A TTL cache only helps the second caller if the first one has already
    finished. The traffic that actually burns an upstream quota looks
    nothing like that: a page load fans out a dozen concurrent requests, and
    two browser tabs reloading together double it — all of them missing the
    same empty key and all of them calling upstream. Joining them onto one
    task turns that burst back into a single request.

    Every waiter sees the same result, including the same exception; a
    failure is not cached here (that's the caller's TTL policy to decide),
    it just isn't multiplied.
    """
    existing = _inflight.get(key)
    if existing is not None:
        return await asyncio.shield(existing)

    task = asyncio.ensure_future(factory())
    _inflight[key] = task
    try:
        return await asyncio.shield(task)
    finally:
        # Only the owner clears the slot, and only once the task is actually
        # done — a cancelled *waiter* must not evict a task others still
        # await (hence the shield on both paths).
        if task.done():
            _inflight.pop(key, None)
        else:
            task.add_done_callback(lambda _t, k=key: _inflight.pop(k, None))
