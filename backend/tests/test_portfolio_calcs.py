"""Tests for _realized_gains and _build_stock_holding — pure computation helpers."""

import pytest
from types import SimpleNamespace

from market_lens_dashboard.services.portfolio_service import _realized_gains, _build_stock_holding


def _txn(id=1, sale=False, ticker="AAPL", date="2024-01-01",
         shares=100, bought_at=10.0, sold_at=0.0, shares_remaining=100):
    return SimpleNamespace(
        id=id, sale=sale, ticker=ticker, date=date,
        shares=shares, bought_at=bought_at, sold_at=sold_at,
        shares_remaining=shares_remaining,
    )


def _holding(ticker="AAPL", company_name="Apple Inc.",
             shares=100, sold_shares=0, average_cost=10.0, market=None):
    return SimpleNamespace(
        ticker=ticker, company_name=company_name, market=market,
        shares=shares, sold_shares=sold_shares, average_cost=average_cost,
    )


# ── _realized_gains ───────────────────────────────────────────────────────────

def test_realized_gains_empty_list():
    assert _realized_gains([]) == 0.0


def test_realized_gains_only_buys():
    assert _realized_gains([_txn(sale=False, bought_at=10.0)]) == 0.0


def test_realized_gains_single_sell():
    t = _txn(sale=True, shares=10, bought_at=10.0, sold_at=15.0)
    assert _realized_gains([t]) == pytest.approx(50.0)


def test_realized_gains_loss():
    t = _txn(sale=True, shares=10, bought_at=20.0, sold_at=15.0)
    assert _realized_gains([t]) == pytest.approx(-50.0)


def test_realized_gains_multiple_sells_summed():
    sells = [
        _txn(id=1, sale=True, shares=10, bought_at=10.0, sold_at=15.0),  # +50
        _txn(id=2, sale=True, shares=5,  bought_at=12.0, sold_at=20.0),  # +40
    ]
    assert _realized_gains(sells) == pytest.approx(90.0)


def test_realized_gains_ignores_buy_rows():
    mixed = [
        _txn(id=1, sale=False, shares=100, bought_at=10.0),
        _txn(id=2, sale=True,  shares=50,  bought_at=10.0, sold_at=20.0),
    ]
    assert _realized_gains(mixed) == pytest.approx(500.0)


# ── _build_stock_holding ──────────────────────────────────────────────────────

def test_build_holding_basic_metrics():
    h = _holding(shares=100, sold_shares=0, average_cost=10.0)
    buy = _txn(sale=False, shares=100, bought_at=10.0, shares_remaining=100)
    result = _build_stock_holding(h, [buy], price=15.0)

    assert result.ticker == "AAPL"
    assert result.company_name == "Apple Inc."
    assert result.shares == 100
    assert result.current_price == 15.0
    assert result.stock_value == pytest.approx(1500.0)
    assert result.total_invested == pytest.approx(1000.0)   # 100 * 10.0 (shares_remaining * bought_at)
    assert result.profit_loss == pytest.approx(500.0)
    assert result.profit_loss_percentage == pytest.approx(50.0)


def test_build_holding_zero_cost_basis_gives_zero_pct():
    h = _holding(shares=0, sold_shares=0, average_cost=0.0)
    result = _build_stock_holding(h, [], price=10.0)
    assert result.profit_loss_percentage == 0.0


def test_build_holding_negative_profit_loss():
    h = _holding(shares=100, sold_shares=0, average_cost=20.0)
    buy = _txn(sale=False, shares=100, bought_at=20.0, shares_remaining=100)
    result = _build_stock_holding(h, [buy], price=15.0)
    assert result.profit_loss == pytest.approx(-500.0)
    assert result.profit_loss_percentage < 0


def test_build_holding_with_partial_sell_adjusts_cost_basis():
    """Cost basis uses shares_remaining * bought_at, not all shares * average_cost."""
    h = _holding(shares=60, sold_shares=40, average_cost=10.0)
    buy = _txn(sale=False, id=1, shares=100, bought_at=10.0, shares_remaining=60)
    sell = _txn(sale=True, id=2, shares=40, bought_at=10.0, sold_at=15.0, shares_remaining=0)
    result = _build_stock_holding(h, [buy, sell], price=12.0)

    assert result.total_invested == pytest.approx(600.0)       # 60 * 10.0
    assert result.total_earned == pytest.approx(200.0)         # 40 * (15 - 10)
    assert result.stock_value == pytest.approx(720.0)          # 60 * 12.0
    assert result.profit_loss == pytest.approx(120.0)          # 720 - 600


def test_build_holding_trade_history_preserves_order():
    h = _holding()
    t1 = _txn(id=1, sale=False, date="2024-01-01", shares=100, bought_at=10.0, shares_remaining=100)
    t2 = _txn(id=2, sale=True,  date="2024-02-01", shares=50,  bought_at=10.0, sold_at=20.0, shares_remaining=0)
    result = _build_stock_holding(h, [t1, t2], price=15.0)

    assert len(result.trade_history) == 2
    assert result.trade_history[0].id == 1
    assert result.trade_history[0].sale is False
    assert result.trade_history[1].id == 2
    assert result.trade_history[1].sale is True


# ── _build_stock_holding: price unavailable (price=None) ──────────────────────
#
# A holding whose live quote couldn't be fetched must never be treated as
# worth $0 — that's indistinguishable from a real quote and silently reports
# a fabricated -100% loss. price=None must propagate to every price-derived
# field instead.

def test_build_holding_none_price_gives_none_current_price():
    h = _holding(shares=100, sold_shares=0, average_cost=10.0)
    buy = _txn(sale=False, shares=100, bought_at=10.0, shares_remaining=100)
    result = _build_stock_holding(h, [buy], price=None)
    assert result.current_price is None


def test_build_holding_none_price_gives_none_stock_value():
    h = _holding(shares=100, sold_shares=0, average_cost=10.0)
    buy = _txn(sale=False, shares=100, bought_at=10.0, shares_remaining=100)
    result = _build_stock_holding(h, [buy], price=None)
    assert result.stock_value is None


def test_build_holding_none_price_gives_none_profit_loss():
    h = _holding(shares=100, sold_shares=0, average_cost=10.0)
    buy = _txn(sale=False, shares=100, bought_at=10.0, shares_remaining=100)
    result = _build_stock_holding(h, [buy], price=None)
    assert result.profit_loss is None
    assert result.profit_loss_percentage is None


def test_build_holding_none_price_still_reports_cost_basis_and_realized_gains():
    """Fields derived purely from the transaction log (not the live price) stay populated."""
    h = _holding(shares=60, sold_shares=40, average_cost=10.0)
    buy = _txn(sale=False, id=1, shares=100, bought_at=10.0, shares_remaining=60)
    sell = _txn(sale=True, id=2, shares=40, bought_at=10.0, sold_at=15.0, shares_remaining=0)
    result = _build_stock_holding(h, [buy, sell], price=None)

    assert result.total_invested == pytest.approx(600.0)   # 60 * 10.0 — unaffected by missing price
    assert result.total_earned == pytest.approx(200.0)     # 40 * (15 - 10) — from the sell, not the quote
    assert result.current_price is None
    assert result.stock_value is None
