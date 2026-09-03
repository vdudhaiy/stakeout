"""Tests for services.logo_service and the /logo router.

Same rationale as test_peers.py: logo_service reads/writes company_logos
through the module-level SessionLocal, so DB-access helpers are mocked at
the call site, and the Finnhub HTTP call is mocked via finnhub_client.get
(see test_finnhub_client.py for the shared budget/transport behavior).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from models.company_logo import CompanyLogo
from services import logo_service


@pytest.fixture(autouse=True)
def reset_module_state():
    logo_service._logo_cache.clear()
    yield
    logo_service._logo_cache.clear()


def _row(logo_url: str, age: timedelta = timedelta(days=1)) -> CompanyLogo:
    return CompanyLogo(symbol="AAPL", logo_url=logo_url, fetched_at=datetime.now(timezone.utc) - age)


# ── _fetch_from_finnhub ───────────────────────────────────────────────────────

async def test_fetch_from_finnhub_returns_logo_url():
    with patch("services.logo_service.finnhub_client.get",
               new_callable=AsyncMock, return_value={"logo": "https://static2.finnhub.io/AAPL.png"}):
        result = await logo_service._fetch_from_finnhub("AAPL")

    assert result == "https://static2.finnhub.io/AAPL.png"


async def test_fetch_from_finnhub_missing_logo_field_returns_empty_string():
    """A successful profile with no `logo` key is a definite "no logo" —
    cacheable, distinct from a failed call."""
    with patch("services.logo_service.finnhub_client.get",
               new_callable=AsyncMock, return_value={"name": "Some Co"}):
        result = await logo_service._fetch_from_finnhub("AAPL")

    assert result == ""


async def test_fetch_from_finnhub_none_response_returns_none():
    with patch("services.logo_service.finnhub_client.get", new_callable=AsyncMock, return_value=None):
        result = await logo_service._fetch_from_finnhub("AAPL")

    assert result is None


async def test_fetch_from_finnhub_non_dict_response_returns_none():
    with patch("services.logo_service.finnhub_client.get", new_callable=AsyncMock, return_value=["oops"]):
        result = await logo_service._fetch_from_finnhub("AAPL")

    assert result is None


# ── get_logo orchestration ────────────────────────────────────────────────────

async def test_get_logo_in_process_cache_hit_skips_everything():
    logo_service._logo_cache.set("AAPL", "https://example.com/aapl.png")

    with patch("services.logo_service._read_row", new_callable=AsyncMock) as mock_read:
        result = await logo_service.get_logo("aapl")

    assert result == "https://example.com/aapl.png"
    mock_read.assert_not_called()


async def test_get_logo_cached_empty_string_returns_none():
    """A cached negative result ("" — checked, no logo) surfaces as None to
    callers, not as an empty-string URL."""
    logo_service._logo_cache.set("AAPL", "")

    result = await logo_service.get_logo("AAPL")

    assert result is None


async def test_get_logo_fresh_db_row_skips_finnhub():
    fresh = _row("https://example.com/aapl.png", age=timedelta(days=1))

    with patch("services.logo_service._read_row", new_callable=AsyncMock, return_value=fresh):
        with patch("services.logo_service._fetch_from_finnhub", new_callable=AsyncMock) as mock_fetch:
            result = await logo_service.get_logo("AAPL")

    assert result == "https://example.com/aapl.png"
    mock_fetch.assert_not_called()


async def test_get_logo_stale_row_refreshes_and_saves():
    stale = _row("https://old.example.com/aapl.png", age=timedelta(days=200))

    with patch("services.logo_service._read_row", new_callable=AsyncMock, return_value=stale):
        with patch("services.logo_service._fetch_from_finnhub",
                   new_callable=AsyncMock, return_value="https://new.example.com/aapl.png"):
            with patch("services.logo_service._save", new_callable=AsyncMock) as mock_save:
                result = await logo_service.get_logo("AAPL")

    assert result == "https://new.example.com/aapl.png"
    mock_save.assert_awaited_once_with("AAPL", "https://new.example.com/aapl.png")


async def test_get_logo_finnhub_fails_falls_back_to_stale_row():
    stale = _row("https://old.example.com/aapl.png", age=timedelta(days=200))

    with patch("services.logo_service._read_row", new_callable=AsyncMock, return_value=stale):
        with patch("services.logo_service._fetch_from_finnhub", new_callable=AsyncMock, return_value=None):
            result = await logo_service.get_logo("AAPL")

    assert result == "https://old.example.com/aapl.png"


async def test_get_logo_no_row_and_finnhub_fails_returns_none():
    with patch("services.logo_service._read_row", new_callable=AsyncMock, return_value=None):
        with patch("services.logo_service._fetch_from_finnhub", new_callable=AsyncMock, return_value=None):
            result = await logo_service.get_logo("AAPL")

    assert result is None


async def test_get_logo_no_row_finnhub_returns_no_logo_saves_empty_string():
    with patch("services.logo_service._read_row", new_callable=AsyncMock, return_value=None):
        with patch("services.logo_service._fetch_from_finnhub", new_callable=AsyncMock, return_value=""):
            with patch("services.logo_service._save", new_callable=AsyncMock) as mock_save:
                result = await logo_service.get_logo("AAPL")

    assert result is None
    mock_save.assert_awaited_once_with("AAPL", "")


# ── router ────────────────────────────────────────────────────────────────────

async def test_logo_router_returns_ticker_and_logo_url(client):
    with patch("routers.logo.logo_service.get_logo",
               new_callable=AsyncMock, return_value="https://example.com/aapl.png"):
        resp = await client.get("/logo/aapl")

    assert resp.status_code == 200
    data = resp.json()
    assert data == {"ticker": "AAPL", "logo_url": "https://example.com/aapl.png"}
    assert resp.headers["cache-control"] == "public, max-age=86400"


async def test_logo_router_no_logo_returns_null(client):
    with patch("routers.logo.logo_service.get_logo", new_callable=AsyncMock, return_value=None):
        resp = await client.get("/logo/AAPL")

    assert resp.status_code == 200
    assert resp.json() == {"ticker": "AAPL", "logo_url": None}


async def test_logo_router_service_failure_returns_502(client):
    with patch("routers.logo.logo_service.get_logo",
               new_callable=AsyncMock, side_effect=RuntimeError("boom")):
        resp = await client.get("/logo/AAPL")

    assert resp.status_code == 502
