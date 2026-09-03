"""Tests for the shared in-memory TTL cache and the request coalescer.

stock_service used to carry its own near-identical (but unbounded) cache
class; these cover the shared cache.TTLCache that replaced it, plus
cache.single_flight, which is what actually keeps a burst of concurrent
callers from each spending an upstream request.
"""

import asyncio

import pytest
from unittest.mock import patch

from cache import TTLCache, single_flight
from services import stock_service


def test_get_missing_key_returns_none():
    cache = TTLCache(ttl_seconds=60)
    assert cache.get("nonexistent") is None


def test_set_then_get_returns_stored_value():
    cache = TTLCache(ttl_seconds=60)
    cache.set("key", {"data": 42})
    assert cache.get("key") == {"data": 42}


def test_overwrite_key_returns_latest_value():
    cache = TTLCache(ttl_seconds=60)
    cache.set("key", "v1")
    cache.set("key", "v2")
    assert cache.get("key") == "v2"


def test_invalidate_removes_entry():
    cache = TTLCache(ttl_seconds=60)
    cache.set("key", "value")
    cache.invalidate("key")
    assert cache.get("key") is None


def test_invalidate_missing_key_is_safe():
    cache = TTLCache(ttl_seconds=60)
    cache.invalidate("never_existed")  # must not raise


def test_invalidate_prefix_removes_only_matching_keys():
    cache = TTLCache(ttl_seconds=60)
    cache.set("AAPL:detailed", "aapl_details")
    cache.set("AAPL:eps", "aapl_eps")
    cache.set("MSFT:detailed", "msft_details")
    cache.invalidate_prefix("AAPL:")
    assert cache.get("AAPL:detailed") is None
    assert cache.get("AAPL:eps") is None
    assert cache.get("MSFT:detailed") == "msft_details"  # unaffected


def test_per_entry_ttl_overrides_the_default():
    cache = TTLCache(ttl_seconds=1000)
    fake_time = [0.0]
    with patch("cache.time.monotonic", side_effect=lambda: fake_time[0]):
        cache.set("short", "value", 10)
        fake_time[0] = 20.0
        assert cache.get("short") is None


def test_ttl_expiry():
    """Entry is valid before TTL and missing after."""
    cache = TTLCache(ttl_seconds=10)
    fake_time = [0.0]

    with patch("cache.time.monotonic", side_effect=lambda: fake_time[0]):
        fake_time[0] = 0.0
        cache.set("key", "value")

        fake_time[0] = 5.0
        assert cache.get("key") == "value"

        fake_time[0] = 10.1
        assert cache.get("key") is None


def test_ttl_expired_entry_removed_from_store():
    """After expiry, the internal store no longer holds the entry."""
    cache = TTLCache(ttl_seconds=10)
    fake_time = [0.0]

    with patch("cache.time.monotonic", side_effect=lambda: fake_time[0]):
        fake_time[0] = 0.0
        cache.set("key", "value")
        fake_time[0] = 20.0
        cache.get("key")  # triggers removal
        assert "key" not in cache._store


def test_store_stays_bounded_by_max_entries():
    """The size cap is the whole reason this replaced stock_service's own
    cache: entries hold full yfinance `.info` dicts, and an unbounded store
    grew until the process was killed."""
    cache = TTLCache(ttl_seconds=60, max_entries=16)
    for i in range(200):
        cache.set(f"k{i}", i)
    assert len(cache._store) <= 16


def test_stock_service_snapshot_cache_is_bounded():
    assert stock_service._snapshot_cache._max > 0


# ── single_flight ─────────────────────────────────────────────────────────

async def test_single_flight_runs_the_factory_once_for_concurrent_callers():
    calls = []

    async def factory():
        calls.append(1)
        await asyncio.sleep(0.01)
        return "result"

    results = await asyncio.gather(*(single_flight("k", factory) for _ in range(10)))

    assert results == ["result"] * 10
    assert len(calls) == 1


async def test_single_flight_runs_again_once_the_first_call_finished():
    calls = []

    async def factory():
        calls.append(1)
        return len(calls)

    assert await single_flight("k2", factory) == 1
    assert await single_flight("k2", factory) == 2


async def test_single_flight_propagates_the_error_to_every_waiter():
    async def factory():
        await asyncio.sleep(0.01)
        raise ValueError("upstream is down")

    results = await asyncio.gather(
        *(single_flight("k3", factory) for _ in range(5)), return_exceptions=True
    )
    assert all(isinstance(r, ValueError) for r in results)


async def test_single_flight_does_not_leak_keys():
    from cache import _inflight

    async def factory():
        return 1

    await single_flight("k4", factory)
    await asyncio.sleep(0)
    assert "k4" not in _inflight


async def test_single_flight_cancelled_waiter_does_not_break_the_others():
    """A client disconnecting mid-request cancels its own await; the shared
    task — and everyone else waiting on it — must survive."""
    async def factory():
        await asyncio.sleep(0.05)
        return "ok"

    survivor = asyncio.ensure_future(single_flight("k5", factory))
    await asyncio.sleep(0)
    quitter = asyncio.ensure_future(single_flight("k5", factory))
    await asyncio.sleep(0)
    quitter.cancel()

    with pytest.raises(asyncio.CancelledError):
        await quitter
    assert await survivor == "ok"
