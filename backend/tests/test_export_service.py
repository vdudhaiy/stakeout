"""Tests for build_portfolio_xlsx — verifies the function produces a valid XLSX file."""

import pytest

from market_lens_dashboard.services.export_service import build_portfolio_xlsx
from market_lens_dashboard.schemas.portfolio import (
    PortfolioResponse, StockHolding, StockPurchaseHistory,
)


def _empty_portfolio():
    return PortfolioResponse(
        portfolio_value=0.0, realized_gains=0.0, total_shares=0,
        total_invested=0.0, total_return=0.0, return_percentage=0.0,
        net_profit_loss=0.0, holdings=[],
    )


def _sample_holding(ticker="AAPL", company_name="Apple Inc."):
    buy = StockPurchaseHistory(
        id=1, sale=False, ticker=ticker, date="2024-01-01",
        shares=100, bought_at=150.0, sold_at=0.0, shares_remaining=80,
    )
    sell = StockPurchaseHistory(
        id=2, sale=True, ticker=ticker, date="2024-06-01",
        shares=20, bought_at=150.0, sold_at=185.0, shares_remaining=0,
    )
    return StockHolding(
        ticker=ticker, company_name=company_name, shares=80, sold_shares=20,
        average_cost=150.0, current_price=175.0, stock_value=14000.0,
        total_invested=12000.0, total_earned=700.0,
        profit_loss=2000.0, profit_loss_percentage=16.67,
        trade_history=[buy, sell],
    )


def _portfolio_with_holdings(*holdings):
    total_value = sum(h.stock_value for h in holdings)
    total_invested = sum(h.total_invested for h in holdings)
    total_earned = sum(h.total_earned for h in holdings)
    total_shares = sum(h.shares for h in holdings)
    total_return = total_value - total_invested
    return_pct = (total_return / total_invested * 100) if total_invested else 0.0
    return PortfolioResponse(
        portfolio_value=total_value, realized_gains=total_earned,
        total_shares=total_shares, total_invested=total_invested,
        total_return=total_return, return_percentage=return_pct,
        net_profit_loss=total_return + total_earned,
        holdings=list(holdings),
    )


# ── output type ───────────────────────────────────────────────────────────────

def test_returns_bytes():
    assert isinstance(build_portfolio_xlsx(_empty_portfolio()), bytes)


def test_output_is_non_empty():
    assert len(build_portfolio_xlsx(_empty_portfolio())) > 0


# ── XLSX validity (ZIP magic bytes) ──────────────────────────────────────────

def test_empty_portfolio_is_valid_xlsx():
    result = build_portfolio_xlsx(_empty_portfolio())
    assert result[:2] == b"PK", "XLSX files are ZIP archives starting with PK magic bytes"


def test_portfolio_with_one_holding_is_valid_xlsx():
    p = _portfolio_with_holdings(_sample_holding())
    result = build_portfolio_xlsx(p)
    assert result[:2] == b"PK"
    assert len(result) > 2000   # should be a real file, not trivially small


def test_portfolio_with_multiple_holdings_is_valid_xlsx():
    msft = _sample_holding("MSFT", "Microsoft Corp.")
    p = _portfolio_with_holdings(_sample_holding(), msft)
    result = build_portfolio_xlsx(p)
    assert result[:2] == b"PK"


# ── edge cases ────────────────────────────────────────────────────────────────

def test_holding_with_no_transactions():
    holding = StockHolding(
        ticker="GOOGL", company_name="Alphabet", shares=10, sold_shares=0,
        average_cost=100.0, current_price=120.0, stock_value=1200.0,
        total_invested=1000.0, total_earned=0.0,
        profit_loss=200.0, profit_loss_percentage=20.0,
        trade_history=[],
    )
    p = _portfolio_with_holdings(holding)
    result = build_portfolio_xlsx(p)
    assert result[:2] == b"PK"


def test_negative_pnl_holding():
    buy = StockPurchaseHistory(
        id=1, sale=False, ticker="XYZ", date="2024-01-01",
        shares=100, bought_at=50.0, sold_at=0.0, shares_remaining=100,
    )
    losing = StockHolding(
        ticker="XYZ", company_name="XYZ Corp.", shares=100, sold_shares=0,
        average_cost=50.0, current_price=30.0, stock_value=3000.0,
        total_invested=5000.0, total_earned=0.0,
        profit_loss=-2000.0, profit_loss_percentage=-40.0,
        trade_history=[buy],
    )
    p = _portfolio_with_holdings(losing)
    result = build_portfolio_xlsx(p)
    assert result[:2] == b"PK"
