"""Tests for rate_limit.py and its wiring onto the public routers.

The public data endpoints take no token at all, and each one can end in a
yfinance/Finnhub/GDELT call against a free-tier quota shared by every user.
The caches stop repeat work; nothing stopped a caller walking distinct
tickers or search terms, every one of which is a legitimate cache miss and
a fresh upstream request. These cover the limits that now bound that, and
the mechanics underneath them.

conftest's autouse fixture resets every limiter between tests.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import rate_limit
from rate_limit import RateLimiter, _client_ip


class _FakeRequest:
    def __init__(self, headers=None, host="1.2.3.4"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": host})() if host else None


# ── RateLimiter mechanics ─────────────────────────────────────────────────

def test_allows_up_to_the_limit_then_refuses():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        limiter.check("ip")
    with pytest.raises(HTTPException) as exc:
        limiter.check("ip")
    assert exc.value.status_code == 429


def test_refusal_carries_a_retry_after_header():
    """Without it the caller can only guess, and guessing means retrying
    straight back into the same wall."""
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.check("ip")
    with pytest.raises(HTTPException) as exc:
        limiter.check("ip")

    retry_after = int(exc.value.headers["Retry-After"])
    assert 0 < retry_after <= 60


def test_budgets_are_per_key():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.check("ip-a")
    limiter.check("ip-b")  # a different caller must not inherit the first's spend


def test_the_window_slides(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: clock[0])

    limiter = RateLimiter(max_requests=2, window_seconds=60)
    limiter.check("ip")
    limiter.check("ip")
    with pytest.raises(HTTPException):
        limiter.check("ip")

    clock[0] += 61
    limiter.check("ip")  # the old hits have aged out


def test_tracked_keys_stay_bounded(monkeypatch):
    """One key per client IP, so an attacker cycling source addresses would
    otherwise grow this without limit.

    Asserts the hard cap, not merely "fewer than we added". Dropping only
    *stale* keys doesn't bound a fast burst at all — every key in it is
    fresh — and on a platform with a coarse monotonic clock (Windows ticks
    at ~15 ms) they can even share a timestamp, so nothing ages out.
    """
    monkeypatch.setattr(rate_limit, "_MAX_TRACKED_KEYS", 64)
    limiter = RateLimiter(max_requests=10, window_seconds=60)
    for i in range(1000):
        limiter.check(f"ip-{i}")
    assert len(limiter._hits) <= 64


def test_the_cap_holds_even_when_every_key_is_fresh(monkeypatch):
    """The burst case, with a window long enough that nothing can age out."""
    monkeypatch.setattr(rate_limit, "_MAX_TRACKED_KEYS", 32)
    limiter = RateLimiter(max_requests=10, window_seconds=3600)
    for i in range(500):
        limiter.check(f"ip-{i}")
    assert len(limiter._hits) <= 32


def test_eviction_keeps_the_most_recently_seen_keys(monkeypatch):
    """Evicting the wrong end would reset the quota of whoever is actually
    hammering the endpoint."""
    monkeypatch.setattr(rate_limit, "_MAX_TRACKED_KEYS", 8)
    limiter = RateLimiter(max_requests=100, window_seconds=3600)
    for i in range(40):
        limiter.check(f"ip-{i}")
    survivors = set(limiter._hits)
    assert "ip-39" in survivors          # newest kept
    assert "ip-0" not in survivors       # oldest dropped


def test_reset_all_clears_every_limiter_including_new_ones():
    """Limiters self-register, so a new one can't be forgotten here."""
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.check("ip")
    rate_limit.reset_all()
    limiter.check("ip")  # must not raise


# ── client identification ─────────────────────────────────────────────────

def test_uses_the_leftmost_forwarded_for_entry():
    request = _FakeRequest({"x-forwarded-for": "9.9.9.9, 10.0.0.1"})
    assert _client_ip(request) == "9.9.9.9"


def test_falls_back_to_the_socket_address():
    assert _client_ip(_FakeRequest(host="5.6.7.8")) == "5.6.7.8"


def test_forwarded_for_can_be_distrusted(monkeypatch):
    """An instance exposed without a proxy in front of it must be able to
    ignore the header — otherwise a caller hands itself a fresh budget per
    request and every limit here is decorative."""
    monkeypatch.setenv("TRUST_FORWARDED_FOR", "false")
    request = _FakeRequest({"x-forwarded-for": "9.9.9.9"}, host="5.6.7.8")
    assert _client_ip(request) == "5.6.7.8"


def test_unknown_client_is_still_a_key():
    request = _FakeRequest(host=None)
    assert _client_ip(request) == "unknown"


# ── router wiring ─────────────────────────────────────────────────────────

async def test_public_read_tier_is_attached_to_the_stocks_router(client, monkeypatch):
    monkeypatch.setattr(rate_limit.public_read_limiter, "_max", 2)
    with patch("routers.stocks.stock_service.get_market_status",
               new_callable=AsyncMock, return_value=True):
        assert (await client.get("/stocks/market")).status_code == 200
        assert (await client.get("/stocks/market")).status_code == 200
        blocked = await client.get("/stocks/market")

    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


@pytest.mark.parametrize("path", [
    "/indicators/AAPL/rsi",
    "/peers/AAPL",
    "/logo/AAPL",
    "/quote/?tickers=AAPL",
    "/fx/USD/INR",
])
async def test_every_public_router_is_covered(client, monkeypatch, path):
    """Applied on the APIRouter rather than per route, so a new endpoint on
    a public prefix is covered by default."""
    monkeypatch.setattr(rate_limit.public_read_limiter, "_max", 0)
    assert (await client.get(path)).status_code == 429


async def test_search_has_its_own_tighter_budget(client, monkeypatch):
    """The cache key is the query string, so distinct queries are all
    legitimate misses — one caller can turn this into unbounded upstream
    Search traffic."""
    monkeypatch.setattr(rate_limit.search_limiter, "_max", 1)
    with patch("routers.stocks.stock_service.search_tickers",
               new_callable=AsyncMock, return_value=[]):
        assert (await client.get("/stocks/search?q=a")).status_code == 200
        assert (await client.get("/stocks/search?q=b")).status_code == 429

    # The looser read tier is untouched by the search burst.
    with patch("routers.stocks.stock_service.get_market_status",
               new_callable=AsyncMock, return_value=True):
        assert (await client.get("/stocks/market")).status_code == 200


async def test_archiving_a_new_ticker_is_the_strictest_tier(client, monkeypatch):
    """The only unauthenticated write to shared state, and it downloads
    years of daily history to serve it."""
    monkeypatch.setattr(rate_limit.add_stock_limiter, "_max", 1)
    with patch("routers.stocks.stock_service.is_tracked",
               new_callable=AsyncMock, return_value=True):
        assert (await client.post("/stocks/AAPL")).status_code == 200
        assert (await client.post("/stocks/MSFT")).status_code == 429


async def test_news_has_its_own_budget(client, monkeypatch):
    monkeypatch.setattr(rate_limit.news_limiter, "_max", 1)
    with patch("routers.news.news_service.get_market_news",
               new_callable=AsyncMock, return_value={"articles": []}):
        assert (await client.get("/news/market")).status_code == 200
        assert (await client.get("/news/market")).status_code == 429


async def test_ai_has_its_own_budget(client, monkeypatch):
    monkeypatch.setattr(rate_limit.ai_limiter, "_max", 0)
    assert (await client.get("/ai/stocks/AAPL/explain")).status_code == 429


async def test_health_is_never_rate_limited(client, monkeypatch):
    """The platform polls this; throttling it gets the instance replaced."""
    monkeypatch.setattr(rate_limit.public_read_limiter, "_max", 0)
    for _ in range(5):
        assert (await client.get("/health")).status_code == 200


async def test_authenticated_routes_are_not_on_the_public_budget(client, monkeypatch):
    """A signed-in user's own data shouldn't compete with anonymous reads
    for the same quota."""
    monkeypatch.setattr(rate_limit.public_read_limiter, "_max", 0)
    assert (await client.get("/watchlist/")).status_code == 200
