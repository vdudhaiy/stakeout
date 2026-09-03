"""Tests for services.quote_service and the /quote router.

Purely in-process cached (never persisted — see the module docstring), so
unlike test_peers.py / test_logo.py there's no DB-row layer to mock: only
finnhub_client.get needs mocking.
"""

from unittest.mock import AsyncMock, patch

import pytest

from services import quote_service


@pytest.fixture(autouse=True)
def reset_module_state():
    quote_service._quote_cache.clear()
    yield
    quote_service._quote_cache.clear()


# ── _fetch_one ────────────────────────────────────────────────────────────────

async def test_fetch_one_returns_quote_dict():
    payload = {"o": 100.0, "h": 105.0, "l": 98.0, "c": 103.0, "pc": 99.0, "d": 4.0, "dp": 4.04}
    with patch("services.quote_service.finnhub_client.get", new_callable=AsyncMock, return_value=payload):
        result = await quote_service._fetch_one("AAPL")

    assert result == {
        "open": 100.0, "high": 105.0, "low": 98.0, "close": 103.0,
        "prev_close": 99.0, "change": 4.0, "change_percent": 4.04,
    }


async def test_fetch_one_zero_price_treated_as_no_quote():
    """Finnhub answers an unknown symbol with an all-zero payload, not an
    error — that's a definite "no quote", not a failed call."""
    payload = {"o": 0, "h": 0, "l": 0, "c": 0, "pc": 0, "d": 0, "dp": 0}
    with patch("services.quote_service.finnhub_client.get", new_callable=AsyncMock, return_value=payload):
        result = await quote_service._fetch_one("BOGUS")

    assert result is None


async def test_fetch_one_none_response_returns_none():
    with patch("services.quote_service.finnhub_client.get", new_callable=AsyncMock, return_value=None):
        result = await quote_service._fetch_one("AAPL")

    assert result is None


async def test_fetch_one_caches_negative_result():
    with patch("services.quote_service.finnhub_client.get",
               new_callable=AsyncMock, return_value=None) as mock_get:
        await quote_service._fetch_one("AAPL")
        result = await quote_service._fetch_one("AAPL")

    mock_get.assert_awaited_once()  # second call served from cache
    assert result is None


async def test_fetch_one_cache_hit_skips_finnhub():
    payload = {"o": 1, "h": 2, "l": 0.5, "c": 1.5, "pc": 1.0, "d": 0.5, "dp": 50.0}
    with patch("services.quote_service.finnhub_client.get",
               new_callable=AsyncMock, return_value=payload) as mock_get:
        first = await quote_service._fetch_one("AAPL")
        second = await quote_service._fetch_one("AAPL")

    assert first == second
    mock_get.assert_awaited_once()


# ── get_quotes ──────────────────────────────────────────────────────────────

async def test_get_quotes_dedupes_and_uppercases():
    with patch("services.quote_service._fetch_one", new_callable=AsyncMock, return_value=None) as mock_fetch:
        result = await quote_service.get_quotes(["aapl", "AAPL", " msft "])

    assert set(result.keys()) == {"AAPL", "MSFT"}
    assert mock_fetch.await_count == 2


async def test_get_quotes_maps_each_ticker_to_its_result():
    async def fake_fetch(symbol: str):
        return {"close": 1.0} if symbol == "AAPL" else None

    with patch("services.quote_service._fetch_one", side_effect=fake_fetch):
        result = await quote_service.get_quotes(["AAPL", "MSFT"])

    assert result == {"AAPL": {"close": 1.0}, "MSFT": None}


async def test_get_quotes_empty_input_returns_empty_dict():
    result = await quote_service.get_quotes([])
    assert result == {}


# ── router ────────────────────────────────────────────────────────────────────

async def test_quote_router_returns_batch(client):
    with patch("routers.quote.quote_service.get_quotes",
               new_callable=AsyncMock, return_value={"AAPL": {"close": 1.0}, "MSFT": None}):
        resp = await client.get("/quote/?tickers=AAPL,MSFT")

    assert resp.status_code == 200
    assert resp.json() == {"quotes": {"AAPL": {"close": 1.0}, "MSFT": None}}


async def test_quote_router_no_tickers_400s(client):
    resp = await client.get("/quote/?tickers=")
    assert resp.status_code == 400


async def test_quote_router_too_many_tickers_400s(client):
    tickers = ",".join(f"T{i}" for i in range(51))
    resp = await client.get(f"/quote/?tickers={tickers}")
    assert resp.status_code == 400
