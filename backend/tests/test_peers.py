"""Tests for services.peers_service and the /peers router.

peers_service reads/writes company_peers through the module-level SessionLocal
(same pattern as market_data_service), not the per-test get_session override,
so — mirroring test_stock_service.py's treatment of market_data_service — the
DB-access helpers (_read_row / _save) are mocked at the call site rather than
exercised against a real database. The actual Finnhub HTTP call now lives in
services.finnhub_client (see test_finnhub_client.py for the budget/transport
tests) — here _fetch_from_finnhub is tested against a mocked
finnhub_client.get to cover just the peers-specific response shaping.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from models.peers import CompanyPeers
from services import peers_service


@pytest.fixture(autouse=True)
def reset_module_state():
    peers_service._peers_cache.clear()
    yield
    peers_service._peers_cache.clear()


def _row(peers: list[str], age: timedelta = timedelta(hours=1)) -> CompanyPeers:
    return CompanyPeers(symbol="AAPL", peers=peers, fetched_at=datetime.now(timezone.utc) - age)


# ── _fetch_from_finnhub ───────────────────────────────────────────────────────

async def test_fetch_from_finnhub_excludes_self():
    with patch("services.peers_service.finnhub_client.get",
               new_callable=AsyncMock, return_value=["AAPL", "MSFT", "GOOGL"]):
        result = await peers_service._fetch_from_finnhub("AAPL")

    assert result == ["MSFT", "GOOGL"]


async def test_fetch_from_finnhub_none_response_returns_none():
    with patch("services.peers_service.finnhub_client.get", new_callable=AsyncMock, return_value=None):
        result = await peers_service._fetch_from_finnhub("AAPL")

    assert result is None


async def test_fetch_from_finnhub_non_list_response_returns_none():
    with patch("services.peers_service.finnhub_client.get",
               new_callable=AsyncMock, return_value={"error": "not found"}):
        result = await peers_service._fetch_from_finnhub("AAPL")

    assert result is None


# ── get_peers orchestration ───────────────────────────────────────────────────

async def test_get_peers_in_process_cache_hit_skips_everything():
    peers_service._peers_cache.set("AAPL", ["MSFT"])

    with patch("services.peers_service._read_row", new_callable=AsyncMock) as mock_read:
        result = await peers_service.get_peers("aapl")

    assert result == ["MSFT"]
    mock_read.assert_not_called()


async def test_get_peers_fresh_db_row_skips_finnhub():
    fresh = _row(["MSFT", "GOOGL"], age=timedelta(hours=1))

    with patch("services.peers_service._read_row", new_callable=AsyncMock, return_value=fresh):
        with patch("services.peers_service._fetch_from_finnhub", new_callable=AsyncMock) as mock_fetch:
            result = await peers_service.get_peers("AAPL")

    assert result == ["MSFT", "GOOGL"]
    mock_fetch.assert_not_called()


async def test_get_peers_stale_row_refreshes_and_saves():
    stale = _row(["OLD"], age=timedelta(days=30))

    with patch("services.peers_service._read_row", new_callable=AsyncMock, return_value=stale):
        with patch("services.peers_service._fetch_from_finnhub",
                   new_callable=AsyncMock, return_value=["MSFT", "GOOGL"]):
            with patch("services.peers_service._save", new_callable=AsyncMock) as mock_save:
                result = await peers_service.get_peers("AAPL")

    assert result == ["MSFT", "GOOGL"]
    mock_save.assert_awaited_once_with("AAPL", ["MSFT", "GOOGL"])


async def test_get_peers_finnhub_fails_falls_back_to_stale_row():
    stale = _row(["OLD"], age=timedelta(days=30))

    with patch("services.peers_service._read_row", new_callable=AsyncMock, return_value=stale):
        with patch("services.peers_service._fetch_from_finnhub", new_callable=AsyncMock, return_value=None):
            result = await peers_service.get_peers("AAPL")

    assert result == ["OLD"]


async def test_get_peers_no_row_and_finnhub_fails_returns_empty_list():
    with patch("services.peers_service._read_row", new_callable=AsyncMock, return_value=None):
        with patch("services.peers_service._fetch_from_finnhub", new_callable=AsyncMock, return_value=None):
            result = await peers_service.get_peers("AAPL")

    assert result == []


async def test_get_peers_no_row_finnhub_succeeds_saves_and_caches():
    with patch("services.peers_service._read_row", new_callable=AsyncMock, return_value=None):
        with patch("services.peers_service._fetch_from_finnhub",
                   new_callable=AsyncMock, return_value=["MSFT"]):
            with patch("services.peers_service._save", new_callable=AsyncMock) as mock_save:
                result = await peers_service.get_peers("AAPL")

    assert result == ["MSFT"]
    mock_save.assert_awaited_once_with("AAPL", ["MSFT"])
    assert peers_service._peers_cache.get("AAPL") == ["MSFT"]


# ── router ────────────────────────────────────────────────────────────────────

async def test_peers_router_returns_ticker_and_peers(client):
    with patch("routers.peers.peers_service.get_peers",
               new_callable=AsyncMock, return_value=["MSFT", "GOOGL"]):
        resp = await client.get("/peers/aapl")

    assert resp.status_code == 200
    data = resp.json()
    assert data == {"ticker": "AAPL", "peers": ["MSFT", "GOOGL"]}
    assert resp.headers["cache-control"] == "public, max-age=1800"


async def test_peers_router_service_failure_returns_502(client):
    with patch("routers.peers.peers_service.get_peers",
               new_callable=AsyncMock, side_effect=RuntimeError("boom")):
        resp = await client.get("/peers/AAPL")

    assert resp.status_code == 502
