"""HTTP contract tests for all three routers: health, portfolio, stocks.

Service functions are mocked so tests are offline and DB-independent beyond
what the client fixture already provides.
"""

import pytest
from unittest.mock import patch, AsyncMock

from market_lens_dashboard.schemas.portfolio import (
    PortfolioResponse, StockHolding, StockPurchaseHistory,
)
from market_lens_dashboard.schemas.stocks import (
    OHLCV, OHLCVResponse, StockDetailedResponse,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _empty_portfolio():
    return PortfolioResponse(
        portfolio_value=0.0, realized_gains=0.0, total_shares=0,
        total_invested=0.0, total_return=0.0, return_percentage=0.0,
        net_profit_loss=0.0, holdings=[],
    )


def _sample_holding():
    return StockHolding(
        ticker="AAPL", company_name="Apple Inc.", shares=100, sold_shares=0,
        average_cost=150.0, current_price=175.0, stock_value=17500.0,
        total_invested=15000.0, total_earned=0.0,
        profit_loss=2500.0, profit_loss_percentage=16.67,
        trade_history=[],
    )


def _sample_ohlcv():
    return OHLCVResponse(
        ticker="AAPL",
        data=[OHLCV(date="2024-01-15", open=183.0, high=185.0, low=182.0, close=184.0, volume=5_000_000)],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_version_endpoint_returns_latest_release_tag(client):
    with patch("market_lens_dashboard.main.get_latest_release_tag",
               new_callable=AsyncMock, return_value="v1.2.3"):
        resp = await client.get("/version")
    assert resp.status_code == 200
    assert resp.json() == {"version": "v1.2.3"}


async def test_version_endpoint_falls_back_when_github_unavailable(client):
    with patch("market_lens_dashboard.main.get_latest_release_tag",
               new_callable=AsyncMock, return_value=None):
        resp = await client.get("/version")
    assert resp.status_code == 200
    assert resp.json() == {"version": "0.1.0"}


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio — GET
# ─────────────────────────────────────────────────────────────────────────────

async def test_get_portfolio_empty(client):
    with patch(
        "market_lens_dashboard.routers.portfolio.portfolio_service.get_portfolio",
        new_callable=AsyncMock, return_value=_empty_portfolio(),
    ):
        resp = await client.get("/portfolio/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["portfolio_value"] == 0.0
    assert data["holdings"] == []


async def test_get_portfolio_with_holding(client):
    portfolio = _empty_portfolio()
    portfolio.holdings = [_sample_holding()]
    portfolio.portfolio_value = 17500.0
    with patch(
        "market_lens_dashboard.routers.portfolio.portfolio_service.get_portfolio",
        new_callable=AsyncMock, return_value=portfolio,
    ):
        resp = await client.get("/portfolio/")
    assert resp.status_code == 200
    assert len(resp.json()["holdings"]) == 1
    assert resp.json()["holdings"][0]["ticker"] == "AAPL"


async def test_get_stock_holding_success(client):
    with patch(
        "market_lens_dashboard.routers.portfolio.portfolio_service.get_stock_holding",
        new_callable=AsyncMock, return_value=_sample_holding(),
    ):
        resp = await client.get("/portfolio/AAPL")
    assert resp.status_code == 200
    assert resp.json()["ticker"] == "AAPL"
    assert resp.json()["shares"] == 100


async def test_get_stock_holding_not_found(client):
    with patch(
        "market_lens_dashboard.routers.portfolio.portfolio_service.get_stock_holding",
        new_callable=AsyncMock, side_effect=ValueError("No holding found for ticker: XYZ"),
    ):
        resp = await client.get("/portfolio/XYZ")
    assert resp.status_code == 404
    assert "No holding" in resp.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio — POST (buy / sell)
# ─────────────────────────────────────────────────────────────────────────────

async def test_buy_stock_success(client):
    with patch(
        "market_lens_dashboard.routers.portfolio.portfolio_service.add_stock_purchase",
        new_callable=AsyncMock, return_value=_sample_holding(),
    ):
        resp = await client.post("/portfolio/AAPL/buy?shares=100&bought_at=150.0")
    assert resp.status_code == 200
    assert resp.json()["ticker"] == "AAPL"


async def test_buy_stock_invalid_ticker_returns_400(client):
    with patch(
        "market_lens_dashboard.routers.portfolio.portfolio_service.add_stock_purchase",
        new_callable=AsyncMock,
        side_effect=ValueError("Ticker 'XYZ' could not be found"),
    ):
        resp = await client.post("/portfolio/XYZ/buy?shares=10&bought_at=100.0")
    assert resp.status_code == 400


async def test_sell_stock_success(client):
    with patch(
        "market_lens_dashboard.routers.portfolio.portfolio_service.sell_stock_shares",
        new_callable=AsyncMock, return_value=_sample_holding(),
    ):
        resp = await client.post("/portfolio/AAPL/sell?shares=50&sold_at=180.0")
    assert resp.status_code == 200


async def test_sell_stock_insufficient_shares_returns_400(client):
    with patch(
        "market_lens_dashboard.routers.portfolio.portfolio_service.sell_stock_shares",
        new_callable=AsyncMock,
        side_effect=ValueError("Only 100 share(s) were available — cannot sell 999."),
    ):
        resp = await client.post("/portfolio/AAPL/sell?shares=999&sold_at=180.0")
    assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio — DELETE
# ─────────────────────────────────────────────────────────────────────────────

async def test_delete_holding_success(client):
    with patch(
        "market_lens_dashboard.routers.portfolio.portfolio_service.delete_stock_holding",
        new_callable=AsyncMock,
        return_value={"message": "Holding for AAPL deleted successfully."},
    ):
        resp = await client.delete("/portfolio/AAPL")
    assert resp.status_code == 200
    assert "deleted" in resp.json()["message"].lower()


async def test_delete_holding_not_found_returns_404(client):
    with patch(
        "market_lens_dashboard.routers.portfolio.portfolio_service.delete_stock_holding",
        new_callable=AsyncMock, side_effect=ValueError("No holding found"),
    ):
        resp = await client.delete("/portfolio/NOTEXIST")
    assert resp.status_code == 404


async def test_delete_transaction_success(client):
    with patch(
        "market_lens_dashboard.routers.portfolio.portfolio_service.delete_transaction",
        new_callable=AsyncMock, return_value=_sample_holding(),
    ):
        resp = await client.delete("/portfolio/AAPL/transactions/1")
    assert resp.status_code == 200


async def test_delete_last_transaction_returns_empty_object(client):
    """When the holding is also deleted, the router returns {}."""
    with patch(
        "market_lens_dashboard.routers.portfolio.portfolio_service.delete_transaction",
        new_callable=AsyncMock, return_value=None,
    ):
        resp = await client.delete("/portfolio/AAPL/transactions/1")
    assert resp.status_code == 200
    assert resp.json() == {}


# ─────────────────────────────────────────────────────────────────────────────
# Stocks — GET
# ─────────────────────────────────────────────────────────────────────────────

async def test_get_all_stocks(client):
    with patch(
        "market_lens_dashboard.routers.stocks.stock_service.get_all_stocks",
        new_callable=AsyncMock, return_value={"AAPL": "Apple Inc.", "MSFT": "Microsoft"},
    ):
        resp = await client.get("/stocks/")
    assert resp.status_code == 200
    assert "stocks" in resp.json()
    assert "AAPL" in resp.json()["stocks"]


async def test_get_market_status_closed(client):
    with patch(
        "market_lens_dashboard.routers.stocks.stock_service.get_market_status",
        new_callable=AsyncMock, return_value=False,
    ):
        resp = await client.get("/stocks/market")
    assert resp.status_code == 200
    assert resp.json()["status"] is False


async def test_get_market_status_open(client):
    with patch(
        "market_lens_dashboard.routers.stocks.stock_service.get_market_status",
        new_callable=AsyncMock, return_value=True,
    ):
        resp = await client.get("/stocks/market")
    assert resp.json()["status"] is True


async def test_get_industries(client):
    with patch(
        "market_lens_dashboard.routers.stocks.stock_service.get_industry_map",
        new_callable=AsyncMock, return_value={"Technology": ["AAPL", "MSFT"]},
    ):
        resp = await client.get("/stocks/industries")
    assert resp.status_code == 200
    assert resp.json()["industries"]["Technology"] == ["AAPL", "MSFT"]


async def test_get_sectors(client):
    with patch(
        "market_lens_dashboard.routers.stocks.stock_service.get_sector_map",
        new_callable=AsyncMock, return_value={"Technology": ["AAPL"]},
    ):
        resp = await client.get("/stocks/sectors")
    assert resp.status_code == 200
    assert "Technology" in resp.json()["sectors"]


async def test_get_stock_ohlcv(client):
    with patch(
        "market_lens_dashboard.routers.stocks.stock_service.fetch",
        new_callable=AsyncMock, return_value=_sample_ohlcv(),
    ):
        resp = await client.get("/stocks/AAPL")
    assert resp.status_code == 200
    assert resp.json()["ticker"] == "AAPL"
    assert len(resp.json()["data"]) == 1
    assert resp.json()["data"][0]["close"] == 184.0


async def test_get_stock_not_in_archive_returns_404(client):
    with patch(
        "market_lens_dashboard.routers.stocks.stock_service.fetch",
        new_callable=AsyncMock, side_effect=ValueError("No CSV data found for ticker: NOTEXIST"),
    ):
        resp = await client.get("/stocks/NOTEXIST")
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Stocks — POST / DELETE
# ─────────────────────────────────────────────────────────────────────────────

async def test_add_stock_when_already_exists(client):
    with patch(
        "market_lens_dashboard.routers.stocks.stock_service.get_all_stocks",
        new_callable=AsyncMock, return_value={"AAPL": "Apple Inc."},
    ):
        resp = await client.post("/stocks/AAPL")
    assert resp.status_code == 200
    assert resp.json()["exist"] is True


async def test_delete_stock_success(client):
    with patch(
        "market_lens_dashboard.routers.stocks.stock_service.delete_stock",
        new_callable=AsyncMock, return_value={"message": "deleted"},
    ):
        resp = await client.delete("/stocks/AAPL")
    assert resp.status_code == 200


async def test_delete_stock_not_found_returns_404(client):
    with patch(
        "market_lens_dashboard.routers.stocks.stock_service.delete_stock",
        new_callable=AsyncMock, side_effect=ValueError("No CSV data found for ticker: NOTEXIST"),
    ):
        resp = await client.delete("/stocks/NOTEXIST")
    assert resp.status_code == 404
