"""Tests for the in-memory TTL cache used by stock_service."""

from unittest.mock import patch

from market_lens_dashboard.services.stock_service import _SnapshotCache


def test_get_missing_key_returns_none():
    cache = _SnapshotCache(ttl_seconds=60)
    assert cache.get("nonexistent") is None


def test_set_then_get_returns_stored_value():
    cache = _SnapshotCache(ttl_seconds=60)
    cache.set("key", {"data": 42})
    assert cache.get("key") == {"data": 42}


def test_overwrite_key_returns_latest_value():
    cache = _SnapshotCache(ttl_seconds=60)
    cache.set("key", "v1")
    cache.set("key", "v2")
    assert cache.get("key") == "v2"


def test_invalidate_removes_entry():
    cache = _SnapshotCache(ttl_seconds=60)
    cache.set("key", "value")
    cache.invalidate("key")
    assert cache.get("key") is None


def test_invalidate_missing_key_is_safe():
    cache = _SnapshotCache(ttl_seconds=60)
    cache.invalidate("never_existed")  # must not raise


def test_invalidate_ticker_removes_only_matching_keys():
    cache = _SnapshotCache(ttl_seconds=60)
    cache.set("AAPL:detailed", "aapl_details")
    cache.set("AAPL:eps", "aapl_eps")
    cache.set("MSFT:detailed", "msft_details")
    cache.invalidate_ticker("AAPL")
    assert cache.get("AAPL:detailed") is None
    assert cache.get("AAPL:eps") is None
    assert cache.get("MSFT:detailed") == "msft_details"  # unaffected


def test_invalidate_all_stocks_key():
    cache = _SnapshotCache(ttl_seconds=60)
    cache.set("all_stocks", {"AAPL": "Apple"})
    cache.invalidate("all_stocks")
    assert cache.get("all_stocks") is None


def test_ttl_expiry():
    """Entry is valid before TTL and missing after."""
    cache = _SnapshotCache(ttl_seconds=10)
    fake_time = [0.0]

    with patch(
        "market_lens_dashboard.services.stock_service._time.monotonic",
        side_effect=lambda: fake_time[0],
    ):
        # t=0: write entry (expires at t=10)
        fake_time[0] = 0.0
        cache.set("key", "value")

        # t=5: still valid
        fake_time[0] = 5.0
        assert cache.get("key") == "value"

        # t=10.1: expired
        fake_time[0] = 10.1
        assert cache.get("key") is None


def test_ttl_expired_entry_removed_from_store():
    """After expiry, the internal store no longer holds the entry."""
    cache = _SnapshotCache(ttl_seconds=10)
    fake_time = [0.0]

    with patch(
        "market_lens_dashboard.services.stock_service._time.monotonic",
        side_effect=lambda: fake_time[0],
    ):
        fake_time[0] = 0.0
        cache.set("key", "value")
        fake_time[0] = 20.0
        cache.get("key")  # triggers removal
        assert "key" not in cache._store
