"""Tests for stock_service.search_tickers — the ticker/company autocomplete
backing the "add ticker" UI, and its /stocks/search route.

yf.Search is mocked throughout so tests are offline; the cache is cleared
between tests since it's a module-level singleton shared across the suite.
"""

import pytest
from unittest.mock import patch, MagicMock

from cache import search_cache
from services import stock_service


@pytest.fixture(autouse=True)
def _clear_search_cache():
    search_cache.clear()
    yield
    search_cache.clear()


def _mock_search(quotes):
    return MagicMock(quotes=quotes)


def _quote(symbol, name="Some Co", quote_type="EQUITY", exchange="", exch_disp=""):
    return {
        "symbol": symbol, "shortname": name, "quoteType": quote_type,
        "exchange": exchange, "exchDisp": exch_disp,
    }


# ── exchange scoping ──────────────────────────────────────────────────────────

async def test_us_exchange_returns_only_unsuffixed_symbols():
    quotes = [
        _quote("AAPL", "Apple Inc.", exchange="NMS", exch_disp="NASDAQ"),
        _quote("RELIANCE.NS", "Reliance Industries", exchange="NSI", exch_disp="NSE"),
    ]
    with patch("services.stock_service.yf.Search", return_value=_mock_search(quotes)):
        results = await stock_service.search_tickers("something", "US")

    assert len(results) == 1
    assert results[0]["symbol"] == "AAPL"
    assert results[0]["name"] == "Apple Inc."
    assert results[0]["exchange"] == "NASDAQ"


async def test_in_exchange_strips_ns_suffix_and_excludes_non_indian():
    quotes = [
        _quote("TCS.NS", "Tata Consultancy Services", exchange="NSI", exch_disp="NSE"),
        _quote("TCS.TO", "Tecsys Inc", exchange="TOR", exch_disp="Toronto"),
    ]
    with patch("services.stock_service.yf.Search", return_value=_mock_search(quotes)):
        results = await stock_service.search_tickers("tcs", "IN")

    assert len(results) == 1
    assert results[0]["symbol"] == "TCS"  # suffix stripped — resolution picks the exchange later


async def test_in_exchange_strips_bo_suffix_too():
    quotes = [
        _quote("TMCV.BO", "Tata Motors", exchange="BSE", exch_disp="Bombay"),
        _quote("AAPL", "Apple Inc.", exchange="NMS", exch_disp="NASDAQ"),
    ]
    with patch("services.stock_service.yf.Search", return_value=_mock_search(quotes)):
        results = await stock_service.search_tickers("tata motors", "IN")

    assert len(results) == 1
    assert results[0]["symbol"] == "TMCV"


async def test_in_exchange_includes_both_ns_and_bo_listings():
    """NSE and BSE aren't a separate choice — "IN" surfaces matches from
    either exchange, not just one."""
    quotes = [
        _quote("TCS.NS", "Tata Consultancy Services", exchange="NSI", exch_disp="NSE"),
        _quote("TMCV.BO", "Tata Motors", exchange="BSE", exch_disp="Bombay"),
    ]
    with patch("services.stock_service.yf.Search", return_value=_mock_search(quotes)):
        results = await stock_service.search_tickers("tata", "IN")

    symbols = {r["symbol"] for r in results}
    assert symbols == {"TCS", "TMCV"}


async def test_in_exchange_dedupes_ns_and_bo_listings_of_the_same_symbol():
    """A dual-listed company shouldn't show up twice just because it trades
    on both exchanges — only the combined "India" choice remains."""
    quotes = [
        _quote("RELIANCE.NS", "Reliance Industries", exchange="NSI", exch_disp="NSE"),
        _quote("RELIANCE.BO", "Reliance Industries", exchange="BSE", exch_disp="Bombay"),
    ]
    with patch("services.stock_service.yf.Search", return_value=_mock_search(quotes)):
        results = await stock_service.search_tickers("reliance", "IN")

    assert len(results) == 1
    assert results[0]["symbol"] == "RELIANCE"


async def test_defaults_to_us_when_exchange_omitted():
    quotes = [_quote("AAPL", exchange="NMS", exch_disp="NASDAQ")]
    with patch("services.stock_service.yf.Search", return_value=_mock_search(quotes)):
        results = await stock_service.search_tickers("apple")
    assert len(results) == 1


# ── quote-type filtering ──────────────────────────────────────────────────────

async def test_excludes_non_equity_non_etf_quote_types():
    quotes = [
        _quote("AAPL", exchange="NMS", exch_disp="NASDAQ", quote_type="EQUITY"),
        _quote("SPY", exchange="PCX", exch_disp="NYSEArca", quote_type="ETF"),
        _quote("TCSEX", exchange="NAS", exch_disp="NASDAQ", quote_type="MUTUALFUND"),
        _quote("BTC-USD", exchange="CCC", exch_disp="CCC", quote_type="CRYPTOCURRENCY"),
    ]
    with patch("services.stock_service.yf.Search", return_value=_mock_search(quotes)):
        results = await stock_service.search_tickers("x", "US")

    symbols = {r["symbol"] for r in results}
    assert symbols == {"AAPL", "SPY"}


# ── misc ──────────────────────────────────────────────────────────────────────

async def test_blank_query_returns_empty_without_calling_yfinance():
    with patch("services.stock_service.yf.Search") as mock_search:
        results = await stock_service.search_tickers("   ", "US")
    assert results == []
    mock_search.assert_not_called()


async def test_yfinance_failure_degrades_to_empty_list():
    with patch("services.stock_service.yf.Search", side_effect=Exception("Yahoo is down")):
        results = await stock_service.search_tickers("apple", "US")
    assert results == []


async def test_results_are_cached_per_exchange_and_query():
    quotes = [_quote("AAPL", exchange="NMS", exch_disp="NASDAQ")]
    with patch("services.stock_service.yf.Search", return_value=_mock_search(quotes)) as mock_search:
        await stock_service.search_tickers("apple", "US")
        await stock_service.search_tickers("apple", "US")
        assert mock_search.call_count == 1

        await stock_service.search_tickers("apple", "IN")  # different cache key
        assert mock_search.call_count == 2


async def test_deduplicates_by_stripped_symbol():
    quotes = [
        _quote("TCS.NS", "Tata Consultancy Services", exchange="NSI", exch_disp="NSE"),
        _quote("TCS.NS", "Tata Consultancy Services (dup)", exchange="NSI", exch_disp="NSE"),
    ]
    with patch("services.stock_service.yf.Search", return_value=_mock_search(quotes)):
        results = await stock_service.search_tickers("tcs", "IN")
    assert len(results) == 1


# ── HTTP contract ─────────────────────────────────────────────────────────────

async def test_search_endpoint_returns_query_and_results(client):
    from unittest.mock import AsyncMock
    with patch(
        "routers.stocks.stock_service.search_tickers",
        new_callable=AsyncMock,
        return_value=[{"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ"}],
    ):
        resp = await client.get("/stocks/search?q=apple&exchange=US")
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "apple"
    assert data["results"][0]["symbol"] == "AAPL"
