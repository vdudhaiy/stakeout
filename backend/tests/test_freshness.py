"""Tests for server-side data provenance (freshness.py) and its headers.

The claim being pinned: a user can tell, from the response alone, whether
what they're looking at was pulled just now, served from a cache, read out of
the archive, or is a stale copy standing in for a fetch that failed. All four
render identically in the UI, so if the backend doesn't say, nobody can.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

import freshness
from cache import TTLCache


@pytest.fixture(autouse=True)
def _collecting():
    """Stamps are dropped outside a request; open a collection window."""
    freshness.begin()
    yield


# ── the ranking ──────────────────────────────────────────────────────────────

def test_snapshot_reports_the_least_fresh_contributor():
    """An aggregate endpoint blends tiers. Calling the whole thing "live"
    because one component was is the misreport this module exists to stop."""
    freshness.stamp(freshness.LIVE)
    freshness.stamp(freshness.CACHED)
    freshness.stamp(freshness.ARCHIVE)

    assert freshness.snapshot().source == freshness.ARCHIVE


def test_stale_outranks_everything():
    freshness.stamp(freshness.LIVE)
    freshness.stamp(freshness.STALE)

    assert freshness.snapshot().source == freshness.STALE


def test_snapshot_reports_the_oldest_fetch_time_across_tiers():
    old = datetime.now(timezone.utc) - timedelta(hours=5)
    freshness.stamp(freshness.LIVE)
    freshness.stamp(freshness.CACHED, fetched_at=old)

    assert freshness.snapshot().fetched_at == old


def test_unstamped_response_reports_nothing():
    assert freshness.snapshot() is None


def test_an_unknown_fetch_time_is_not_reported_as_now():
    """Archive rows written before market_data tracked fetch times have no
    honest timestamp. Defaulting them to now would date every historical bar
    to the moment it was read."""
    freshness.stamp(freshness.ARCHIVE, fetched_at=None, data_through=date(2026, 3, 9))

    current = freshness.snapshot()
    assert current.fetched_at is None
    assert current.data_through == date(2026, 3, 9)


def test_data_through_is_tracked_separately_from_fetch_time():
    """Fresh and behind are different problems: a chart pulled a minute ago
    whose newest bar is from Friday is both."""
    just_now = datetime.now(timezone.utc)
    freshness.stamp(freshness.ARCHIVE, fetched_at=just_now, data_through="2026-03-06")

    current = freshness.snapshot()
    assert (datetime.now(timezone.utc) - current.fetched_at).total_seconds() < 5
    assert current.data_through == date(2026, 3, 6)


def test_stamping_never_raises_on_bad_input():
    freshness.stamp(freshness.CACHED, data_through="not-a-date")
    assert freshness.snapshot().data_through is None


# ── cache provenance ─────────────────────────────────────────────────────────

def test_a_cache_hit_reports_when_the_value_was_fetched_not_when_it_was_read():
    """The whole point: a 6-hour-old cached snapshot must not claim to be
    current just because this request touched it."""
    cache = TTLCache(ttl_seconds=3600)
    two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    cache.set("k", "value", stored_at=two_hours_ago.timestamp())

    assert cache.get_stamped("k") == "value"

    current = freshness.snapshot()
    assert current.source == freshness.CACHED
    assert abs((current.fetched_at - two_hours_ago).total_seconds()) < 2


def test_a_cache_miss_stamps_nothing():
    cache = TTLCache(ttl_seconds=3600)
    assert cache.get_stamped("absent") is None
    assert freshness.snapshot() is None


def test_an_expired_entry_stamps_nothing():
    cache = TTLCache(ttl_seconds=3600)
    cache.set("k", "value", ttl_seconds=-1)

    assert cache.get_stamped("k") is None
    assert freshness.snapshot() is None


def test_re_shelving_a_db_row_preserves_its_original_fetch_time():
    """peers/logo/profile promote a DB row into the memo. Without carrying
    stored_at across, the next cache hit would report when this process
    re-shelved the value rather than when upstream was actually called."""
    cache = TTLCache(ttl_seconds=3600)
    fetched = (datetime.now(timezone.utc) - timedelta(days=3)).timestamp()
    cache.set("k", "value", stored_at=fetched)

    assert abs(cache.stored_at("k") - fetched) < 1


# ── the headers ──────────────────────────────────────────────────────────────

_ROWS = [{"date": "2026-09-04", "open": 1.0, "high": 2.0,
          "low": 0.5, "close": 1.5, "volume": 10}]


async def test_archive_response_carries_source_fetch_time_and_data_through(client):
    pulled = datetime(2026, 9, 5, 20, 3, tzinfo=timezone.utc)
    with patch("services.stock_service.market_data_service.get_ohlcv",
               new_callable=AsyncMock, return_value=_ROWS), \
         patch("services.stock_service.market_data_service.get_provenance",
               new_callable=AsyncMock, return_value=(pulled, date(2026, 9, 4))), \
         patch("services.stock_service.ensure_archive_current",
               new_callable=AsyncMock, return_value=False):
        response = await client.get("/stocks/AAPL?days=5")

    assert response.status_code == 200
    assert response.headers["X-Data-Source"] == "archive"
    assert response.headers["X-Data-Fetched-At"].startswith("2026-09-05T20:03")
    assert response.headers["X-Data-Through"] == "2026-09-04"
    assert int(response.headers["X-Data-Age-Seconds"]) > 0


async def test_an_archive_with_no_recorded_fetch_time_omits_the_header(client):
    """Rows predating the fetched_at column report an unknown fetch time
    rather than a fabricated one — the source and the data date still go out."""
    with patch("services.stock_service.market_data_service.get_ohlcv",
               new_callable=AsyncMock, return_value=_ROWS), \
         patch("services.stock_service.market_data_service.get_provenance",
               new_callable=AsyncMock, return_value=(None, date(2026, 9, 4))), \
         patch("services.stock_service.ensure_archive_current",
               new_callable=AsyncMock, return_value=False):
        response = await client.get("/stocks/AAPL?days=5")

    assert response.headers["X-Data-Source"] == "archive"
    assert response.headers["X-Data-Through"] == "2026-09-04"
    assert "X-Data-Fetched-At" not in response.headers


async def test_a_failing_response_is_not_given_a_freshness_claim(client):
    """No data, no provenance — an error must not carry a header implying
    something was served."""
    with patch("services.stock_service.market_data_service.get_ohlcv",
               new_callable=AsyncMock, return_value=[]), \
         patch("services.stock_service.ensure_archive_current",
               new_callable=AsyncMock, return_value=False):
        response = await client.get("/stocks/NOPE?days=5")

    assert response.status_code == 404
    assert "X-Data-Source" not in response.headers


async def test_health_is_unstamped(client):
    """Nothing upstream backs it, so there is nothing to date."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert "X-Data-Source" not in response.headers
