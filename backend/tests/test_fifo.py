"""Tests for the core FIFO cost-basis algorithm (_replay_fifo).

Uses SimpleNamespace so tests stay pure and don't touch the database.
_replay_fifo only reads/writes plain attributes on its arguments.
"""

import pytest
from types import SimpleNamespace

from market_lens_dashboard.services.portfolio_service import _replay_fifo, _position_as_of


def _holding(**kw):
    return SimpleNamespace(shares=0, sold_shares=0, average_cost=0.0, **kw)


def _buy(date, shares, bought_at, shares_remaining=None):
    return SimpleNamespace(
        sale=False, date=date, shares=shares, bought_at=bought_at,
        sold_at=0.0,
        shares_remaining=shares if shares_remaining is None else shares_remaining,
    )


def _sell(date, shares, sold_at):
    return SimpleNamespace(
        sale=True, date=date, shares=shares, bought_at=0.0,
        sold_at=sold_at, shares_remaining=0,
    )


# ── single buy ────────────────────────────────────────────────────────────────

def test_single_buy_no_sell():
    h = _holding()
    b = _buy("2024-01-01", 100, 10.0)
    _replay_fifo(h, [b])
    assert h.shares == 100
    assert h.sold_shares == 0
    assert h.average_cost == pytest.approx(10.0)
    assert b.shares_remaining == 100


def test_two_buys_no_sell_weighted_average_cost():
    h = _holding()
    b1 = _buy("2024-01-01", 100, 10.0)
    b2 = _buy("2024-02-01", 100, 20.0)
    _replay_fifo(h, [b1, b2])
    assert h.shares == 200
    assert h.average_cost == pytest.approx(15.0)


# ── full and partial sells ────────────────────────────────────────────────────

def test_full_sell_exhausts_lot():
    h = _holding()
    b = _buy("2024-01-01", 100, 10.0)
    s = _sell("2024-02-01", 100, 15.0)
    _replay_fifo(h, [b, s])
    assert h.shares == 0
    assert h.sold_shares == 100
    assert b.shares_remaining == 0


def test_partial_sell_leaves_remainder():
    h = _holding()
    b = _buy("2024-01-01", 100, 10.0)
    s = _sell("2024-02-01", 40, 15.0)
    _replay_fifo(h, [b, s])
    assert h.shares == 60
    assert h.sold_shares == 40
    assert b.shares_remaining == 60


# ── FIFO ordering ─────────────────────────────────────────────────────────────

def test_fifo_consumes_oldest_lot_first():
    h = _holding()
    lot1 = _buy("2024-01-01", 50, 10.0)
    lot2 = _buy("2024-02-01", 50, 20.0)
    s = _sell("2024-03-01", 50, 25.0)
    _replay_fifo(h, [lot1, lot2, s])
    assert lot1.shares_remaining == 0
    assert lot2.shares_remaining == 50


def test_fifo_cost_basis_is_oldest_lot_price():
    h = _holding()
    lot1 = _buy("2024-01-01", 100, 10.0)
    lot2 = _buy("2024-02-01", 100, 20.0)
    s = _sell("2024-03-01", 100, 30.0)
    _replay_fifo(h, [lot1, lot2, s])
    assert s.bought_at == pytest.approx(10.0)


def test_fifo_cost_basis_spans_multiple_lots():
    h = _holding()
    lot1 = _buy("2024-01-01", 60, 10.0)
    lot2 = _buy("2024-02-01", 60, 20.0)
    s = _sell("2024-03-01", 80, 30.0)
    _replay_fifo(h, [lot1, lot2, s])
    # 60 shares @ $10 + 20 shares @ $20 = $1000 for 80 shares → avg = $12.50
    expected = (60 * 10.0 + 20 * 20.0) / 80
    assert s.bought_at == pytest.approx(expected)
    assert lot1.shares_remaining == 0
    assert lot2.shares_remaining == 40
    assert h.shares == 40


# ── error cases ───────────────────────────────────────────────────────────────

def test_sell_exceeds_available_raises():
    h = _holding()
    b = _buy("2024-01-01", 10, 10.0)
    s = _sell("2024-02-01", 20, 15.0)
    with pytest.raises(ValueError, match="cannot sell"):
        _replay_fifo(h, [b, s])


def test_sell_before_all_buys_raises():
    """Sell date precedes every buy lot → no shares available → ValueError."""
    h = _holding()
    b = _buy("2024-01-01", 10, 10.0)
    s = _sell("2023-12-31", 10, 15.0)
    # _replay_fifo splits by sale flag; buy_txns=[b], sell_txns=[s].
    # For sell on 2023-12-31: lot b.date "2024-01-01" > sell.date → skipped.
    with pytest.raises(ValueError):
        _replay_fifo(h, [s, b])


# ── multiple sells ────────────────────────────────────────────────────────────

def test_multiple_sequential_sells():
    h = _holding()
    lot = _buy("2024-01-01", 100, 10.0)
    s1 = _sell("2024-02-01", 30, 15.0)
    s2 = _sell("2024-03-01", 30, 20.0)
    _replay_fifo(h, [lot, s1, s2])
    assert lot.shares_remaining == 40
    assert h.shares == 40
    assert h.sold_shares == 60


# ── idempotency ───────────────────────────────────────────────────────────────

def test_replay_resets_stale_shares_remaining():
    """shares_remaining is always reset before replay, so calling twice gives the same result."""
    h = _holding()
    b = _buy("2024-01-01", 100, 10.0, shares_remaining=42)  # stale / wrong value
    _replay_fifo(h, [b])
    assert b.shares_remaining == 100


# ── backdated buy ─────────────────────────────────────────────────────────────

def test_backdated_buy_is_consumed_before_later_lot():
    """Inserting an earlier (cheaper) buy before a sell means that lot is consumed first."""
    h = _holding()
    b_backdated = _buy("2024-01-01", 100, 5.0)   # older, cheaper lot
    b_later = _buy("2024-01-02", 100, 20.0)        # newer, pricier lot
    s = _sell("2024-01-03", 100, 30.0)
    _replay_fifo(h, [b_backdated, b_later, s])
    assert b_backdated.shares_remaining == 0        # consumed first by FIFO
    assert b_later.shares_remaining == 100
    assert s.bought_at == pytest.approx(5.0)        # cost basis from the backdated lot


# ── point-in-time replay (_position_as_of) ────────────────────────────────────

def test_position_as_of_excludes_transactions_after_the_date():
    lot1 = _buy("2024-01-01", 100, 10.0)
    lot2 = _buy("2024-06-01", 50, 20.0)  # after the as-of date
    pos = _position_as_of("AAPL", [lot1, lot2], "2024-03-01")
    assert pos.shares == 100
    assert pos.average_cost == pytest.approx(10.0)


def test_position_as_of_includes_sells_up_to_and_on_the_date():
    lot = _buy("2024-01-01", 100, 10.0)
    early_sell = _sell("2024-02-01", 40, 15.0)
    late_sell = _sell("2024-05-01", 20, 20.0)  # after the as-of date
    pos = _position_as_of("AAPL", [lot, early_sell, late_sell], "2024-03-01")
    assert pos.shares == 60
    assert pos.sold_shares == 40
    assert pos.realized_gains == pytest.approx((15.0 - 10.0) * 40)


def test_position_as_of_matches_final_state_when_date_is_latest():
    lot1 = _buy("2024-01-01", 60, 10.0)
    lot2 = _buy("2024-02-01", 60, 20.0)
    s = _sell("2024-03-01", 80, 30.0)
    h = _holding()
    _replay_fifo(h, [lot1, lot2, s])

    pos = _position_as_of("AAPL", [lot1, lot2, s], "2024-03-01")
    assert pos.shares == h.shares
    assert pos.sold_shares == h.sold_shares
    assert pos.average_cost == pytest.approx(h.average_cost)


def test_position_as_of_does_not_mutate_inputs():
    """_position_as_of is read-only — unlike _replay_fifo it must never write back."""
    lot = _buy("2024-01-01", 100, 10.0, shares_remaining=999)
    s = _sell("2024-02-01", 40, 15.0)
    _position_as_of("AAPL", [lot, s], "2024-02-01")
    assert lot.shares_remaining == 999  # untouched
    assert s.bought_at == 0.0           # untouched


def test_position_as_of_before_any_transaction_is_empty():
    lot = _buy("2024-01-01", 100, 10.0)
    pos = _position_as_of("AAPL", [lot], "2023-12-31")
    assert pos.shares == 0
    assert pos.sold_shares == 0
    assert pos.average_cost == pytest.approx(0.0)
    assert pos.realized_gains == pytest.approx(0.0)
