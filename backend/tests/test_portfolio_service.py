"""Integration tests for portfolio_service — exercises the full service layer
with a real in-memory SQLite database via the db_session fixture.

External calls (yfinance, archive) are mocked so tests are offline.

Money fields (Holding.average_cost, Transaction.bought_at/sold_at) are
Numeric/Decimal columns — service functions that accept a price or per-share
cost expect Decimal, matching what the Decimal-typed FastAPI query params
actually deliver. Mixing a plain float with a Decimal read back from the DB
raises TypeError, so every money literal below is Decimal, and assertions
against pytest.approx() convert the actual value to float first.
"""

import asyncio
from decimal import Decimal

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from sqlalchemy import select

from market_lens_dashboard.models.portfolio import Holding, Transaction
from market_lens_dashboard.services import portfolio_service

USER_ID = "test-user"


# ── _current_price ────────────────────────────────────────────────────────────
# Never falls back to a fabricated $0 — see portfolio_service._current_price
# docstring. These exercise the real function directly (unmocked), only
# stubbing its two external dependencies (fetch_current, yf.Ticker.history).

async def test_current_price_uses_live_quote():
    from market_lens_dashboard.schemas.stocks import OHLCV, OHLCVResponse
    response = OHLCVResponse(ticker="AAPL", data=[OHLCV(date="2024-01-15", close=184.0)])
    with patch("market_lens_dashboard.services.portfolio_service.fetch_current",
               new_callable=AsyncMock, return_value=response):
        price = await portfolio_service._current_price("AAPL")
    assert price == Decimal("184.0")


async def test_current_price_returns_none_when_both_sources_fail():
    with patch("market_lens_dashboard.services.portfolio_service.fetch_current",
               new_callable=AsyncMock, side_effect=Exception("network error")):
        with patch("market_lens_dashboard.services.portfolio_service.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.side_effect = Exception("also fails")
            price = await portfolio_service._current_price("AAPL")
    assert price is None


async def test_current_price_falls_back_to_direct_history_when_live_fetch_fails():
    import pandas as pd
    with patch("market_lens_dashboard.services.portfolio_service.fetch_current",
               new_callable=AsyncMock, side_effect=Exception("archive missing")):
        with patch("market_lens_dashboard.services.portfolio_service.yf.Ticker") as mock_ticker:
            hist = pd.DataFrame({"Close": [123.45]})
            mock_ticker.return_value.history.return_value = hist
            price = await portfolio_service._current_price("AAPL")
    assert price == Decimal("123.45")


# ── shared fixture: one AAPL holding with 100 shares @ $150 ──────────────────

@pytest_asyncio.fixture
async def aapl_session(db_session):
    """db_session pre-loaded with AAPL: 100 shares bought at $150 on 2024-01-01."""
    holding = Holding(
        user_id=USER_ID, ticker="AAPL", company_name="Apple Inc.",
        shares=0, sold_shares=0, average_cost=Decimal(0),
    )
    db_session.add(holding)
    await db_session.flush()

    txn = Transaction(
        holding_id=holding.id, sale=False, date="2024-01-01",
        shares=100, bought_at=Decimal("150.0"), shares_remaining=100,
    )
    db_session.add(txn)
    portfolio_service._replay_fifo(holding, [txn])
    await db_session.commit()
    return db_session


# ── add_stock_purchase ────────────────────────────────────────────────────────

async def test_add_purchase_creates_new_holding(db_session):
    with patch("market_lens_dashboard.services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value="Apple Inc."):
        with patch("market_lens_dashboard.services.portfolio_service._current_price",
                   new_callable=AsyncMock, return_value=Decimal("175.0")):
            with patch("market_lens_dashboard.services.portfolio_service.asyncio.create_task"):
                result = await portfolio_service.add_stock_purchase(
                    db_session, USER_ID, "AAPL", shares=100, bought_at=Decimal("150.0"), date="2024-01-01"
                )

    assert result.ticker == "AAPL"
    assert result.company_name == "Apple Inc."
    assert result.shares == 100
    assert float(result.average_cost) == pytest.approx(150.0)
    assert float(result.current_price) == pytest.approx(175.0)


async def test_add_purchase_to_existing_holding(aapl_session):
    with patch("market_lens_dashboard.services.portfolio_service._current_price",
               new_callable=AsyncMock, return_value=Decimal("175.0")):
        result = await portfolio_service.add_stock_purchase(
            aapl_session, USER_ID, "AAPL", shares=50, bought_at=Decimal("160.0"), date="2024-02-01"
        )

    assert result.shares == 150
    expected_avg = (100 * 150.0 + 50 * 160.0) / 150
    assert float(result.average_cost) == pytest.approx(expected_avg, rel=1e-3)


async def test_add_purchase_future_date_raises(db_session):
    import datetime
    future = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
    with pytest.raises(ValueError, match="future"):
        await portfolio_service.add_stock_purchase(db_session, USER_ID, "AAPL", 10, Decimal("100.0"), date=future)


# ── sell_stock_shares ─────────────────────────────────────────────────────────

async def test_sell_reduces_shares(aapl_session):
    with patch("market_lens_dashboard.services.portfolio_service._current_price",
               new_callable=AsyncMock, return_value=Decimal("200.0")):
        result = await portfolio_service.sell_stock_shares(
            aapl_session, USER_ID, "AAPL", shares=40, sold_at=Decimal("200.0"), date="2024-02-01"
        )

    assert result.shares == 60
    assert result.sold_shares == 40


async def test_sell_exceeds_available_raises(aapl_session):
    with pytest.raises(ValueError, match="cannot sell"):
        await portfolio_service.sell_stock_shares(
            aapl_session, USER_ID, "AAPL", shares=999, sold_at=Decimal("200.0"), date="2024-02-01"
        )


async def test_sell_before_earliest_buy_raises(aapl_session):
    with pytest.raises(ValueError, match="before the earliest purchase"):
        await portfolio_service.sell_stock_shares(
            aapl_session, USER_ID, "AAPL", shares=10, sold_at=Decimal("200.0"), date="2023-12-31"
        )


async def test_sell_unknown_ticker_raises(db_session):
    with pytest.raises(ValueError, match="No holding"):
        await portfolio_service.sell_stock_shares(
            db_session, USER_ID, "NOTEXIST", shares=10, sold_at=Decimal("100.0")
        )


# ── get_stock_holding ─────────────────────────────────────────────────────────

async def test_get_holding_returns_correct_data(aapl_session):
    result = await portfolio_service.get_stock_holding(aapl_session, USER_ID, "AAPL", price=Decimal("175.0"))
    assert result.ticker == "AAPL"
    assert result.shares == 100
    assert float(result.current_price) == 175.0
    assert float(result.stock_value) == pytest.approx(17500.0)


async def test_get_holding_not_found_raises(db_session):
    with pytest.raises(ValueError, match="No holding"):
        await portfolio_service.get_stock_holding(db_session, USER_ID, "NOTEXIST", price=Decimal("100.0"))


# ── delete_transaction ────────────────────────────────────────────────────────

async def test_delete_last_transaction_removes_holding(aapl_session):
    result_row = await aapl_session.execute(
        select(Transaction).where(Transaction.sale == False)  # noqa: E712
    )
    txn = result_row.scalar_one()

    ret = await portfolio_service.delete_transaction(aapl_session, USER_ID, "AAPL", txn.id)

    assert ret is None  # holding was also deleted


async def test_delete_one_of_two_transactions_rereplays_fifo(db_session):
    """After deleting a buy transaction, FIFO is re-replayed on remaining transactions."""
    holding = Holding(user_id=USER_ID, ticker="TSLA", company_name="Tesla", shares=0, sold_shares=0, average_cost=Decimal(0))
    db_session.add(holding)
    await db_session.flush()

    b1 = Transaction(holding_id=holding.id, sale=False, date="2024-01-01",
                     shares=50, bought_at=Decimal("200.0"), shares_remaining=50)
    b2 = Transaction(holding_id=holding.id, sale=False, date="2024-02-01",
                     shares=50, bought_at=Decimal("250.0"), shares_remaining=50)
    db_session.add(b1)
    db_session.add(b2)
    portfolio_service._replay_fifo(holding, [b1, b2])
    await db_session.commit()

    # Refresh to get IDs
    await db_session.refresh(b1)

    with patch("market_lens_dashboard.services.portfolio_service._current_price",
               new_callable=AsyncMock, return_value=Decimal("300.0")):
        result = await portfolio_service.delete_transaction(db_session, USER_ID, "TSLA", b1.id)

    # Only b2 remains: 50 shares @ $250
    assert result.shares == 50
    assert float(result.average_cost) == pytest.approx(250.0)


async def test_delete_nonexistent_transaction_raises(aapl_session):
    with pytest.raises(ValueError, match="not found"):
        await portfolio_service.delete_transaction(aapl_session, USER_ID, "AAPL", 999999)


# ── delete_stock_holding ──────────────────────────────────────────────────────

async def test_delete_holding_removes_it(aapl_session):
    result = await portfolio_service.delete_stock_holding(aapl_session, USER_ID, "AAPL")
    assert "deleted" in result["message"].lower()


async def test_delete_holding_not_found_raises(db_session):
    with pytest.raises(ValueError, match="No holding"):
        await portfolio_service.delete_stock_holding(db_session, USER_ID, "NOTEXIST")


# ── get_portfolio ─────────────────────────────────────────────────────────────

async def test_get_portfolio_empty_db(db_session):
    with patch("market_lens_dashboard.services.portfolio_service.get_market_status",
               new_callable=AsyncMock, return_value=False):
        result = await portfolio_service.get_portfolio(db_session, USER_ID)

    assert result.portfolio_value == 0
    assert result.holdings == []
    assert result.total_shares == 0


async def test_get_portfolio_with_prices_dict(aapl_session):
    """When prices dict is supplied, no network calls are made."""
    result = await portfolio_service.get_portfolio(aapl_session, USER_ID, prices={"AAPL": Decimal("175.0")})

    assert len(result.holdings) == 1
    assert result.holdings[0].ticker == "AAPL"
    assert float(result.portfolio_value) == pytest.approx(175.0 * 100)
    assert float(result.total_invested) == pytest.approx(100 * 150.0)
    assert float(result.total_return) == pytest.approx(175.0 * 100 - 100 * 150.0)


async def test_get_portfolio_excludes_holding_with_unavailable_price(aapl_session):
    """A holding whose quote is None is excluded from portfolio_value, not counted as $0."""
    result = await portfolio_service.get_portfolio(aapl_session, USER_ID, prices={"AAPL": None})

    assert len(result.holdings) == 1
    holding = result.holdings[0]
    assert holding.current_price is None
    assert holding.stock_value is None
    assert holding.profit_loss is None
    assert holding.profit_loss_percentage is None
    # total_invested (cost basis) is still known even without a live price —
    # only the price-derived aggregate (portfolio_value) is affected.
    assert float(result.total_invested) == pytest.approx(100 * 150.0)
    assert result.portfolio_value == 0


# ── get_position_as_of / get_portfolio_as_of ──────────────────────────────────

async def test_get_position_as_of_before_purchase_is_empty(aapl_session):
    pos = await portfolio_service.get_position_as_of(aapl_session, USER_ID, "AAPL", "2023-12-31")
    assert pos.shares == 0
    assert pos.sold_shares == 0


async def test_get_position_as_of_after_purchase_reflects_holding(aapl_session):
    pos = await portfolio_service.get_position_as_of(aapl_session, USER_ID, "AAPL", "2024-01-01")
    assert pos.shares == 100
    assert float(pos.average_cost) == pytest.approx(150.0)
    assert float(pos.cost_basis) == pytest.approx(100 * 150.0)


async def test_get_position_as_of_unknown_ticker_raises(db_session):
    with pytest.raises(ValueError):
        await portfolio_service.get_position_as_of(db_session, USER_ID, "MSFT", "2024-01-01")


async def test_get_portfolio_as_of_omits_holdings_not_yet_bought(aapl_session):
    positions = await portfolio_service.get_portfolio_as_of(aapl_session, USER_ID, "2023-12-31")
    assert positions == []


async def test_get_portfolio_as_of_includes_current_holdings(aapl_session):
    positions = await portfolio_service.get_portfolio_as_of(aapl_session, USER_ID, "2024-06-01")
    assert len(positions) == 1
    assert positions[0].ticker == "AAPL"
    assert positions[0].shares == 100


async def test_get_portfolio_as_of_does_not_persist_changes(aapl_session):
    """Read-only: computing a past snapshot must not alter the live holding row."""
    await portfolio_service.get_portfolio_as_of(aapl_session, USER_ID, "2024-01-01")
    result = await aapl_session.execute(select(Holding).where(Holding.user_id == USER_ID))
    holding = result.scalar_one()
    assert holding.shares == 100
    assert float(holding.average_cost) == pytest.approx(150.0)


# ── audit log / undo ──────────────────────────────────────────────────────────

async def test_buy_logs_an_insert_audit_entry(db_session):
    with patch("market_lens_dashboard.services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value="Apple Inc."):
        with patch("market_lens_dashboard.services.portfolio_service._current_price",
                   new_callable=AsyncMock, return_value=Decimal("175.0")):
            with patch("market_lens_dashboard.services.portfolio_service.asyncio.create_task"):
                await portfolio_service.add_stock_purchase(
                    db_session, USER_ID, "AAPL", shares=100, bought_at=Decimal("150.0"), date="2024-01-01"
                )

    entries = await portfolio_service.list_audit_log(db_session, USER_ID)
    assert len(entries) == 1
    assert entries[0].action == "insert"
    assert entries[0].ticker == "AAPL"
    assert entries[0].undone is False


async def test_undo_last_buy_reverts_to_prior_state(aapl_session):
    """aapl_session already has 100 shares seeded outside the audit log; buying
    more and undoing it should land exactly back on that pre-existing state."""
    with patch("market_lens_dashboard.services.portfolio_service._current_price",
               new_callable=AsyncMock, return_value=Decimal("200.0")):
        await portfolio_service.add_stock_purchase(
            aapl_session, USER_ID, "AAPL", shares=50, bought_at=Decimal("160.0"), date="2024-02-01"
        )

    result = await portfolio_service.undo_last_action(aapl_session, USER_ID)
    assert result.ticker == "AAPL"
    assert result.action == "insert"

    holding = await portfolio_service.get_stock_holding(aapl_session, USER_ID, "AAPL", price=Decimal("200.0"))
    assert holding.shares == 100
    assert float(holding.average_cost) == pytest.approx(150.0)


async def test_undo_last_buy_that_created_the_holding_removes_it(db_session):
    with patch("market_lens_dashboard.services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value="Apple Inc."):
        with patch("market_lens_dashboard.services.portfolio_service._current_price",
                   new_callable=AsyncMock, return_value=Decimal("175.0")):
            with patch("market_lens_dashboard.services.portfolio_service.asyncio.create_task"):
                await portfolio_service.add_stock_purchase(
                    db_session, USER_ID, "AAPL", shares=100, bought_at=Decimal("150.0"), date="2024-01-01"
                )

    await portfolio_service.undo_last_action(db_session, USER_ID)

    with pytest.raises(ValueError, match="No holding"):
        await portfolio_service.get_stock_holding(db_session, USER_ID, "AAPL", price=Decimal("175.0"))


async def test_undo_delete_of_last_transaction_restores_holding(aapl_session):
    result_row = await aapl_session.execute(select(Transaction).where(Transaction.sale == False))  # noqa: E712
    txn = result_row.scalar_one()
    await portfolio_service.delete_transaction(aapl_session, USER_ID, "AAPL", txn.id)

    result = await portfolio_service.undo_last_action(aapl_session, USER_ID)
    assert result.action == "delete"

    holding = await portfolio_service.get_stock_holding(aapl_session, USER_ID, "AAPL", price=Decimal("175.0"))
    assert holding.shares == 100
    assert float(holding.average_cost) == pytest.approx(150.0)
    assert holding.company_name == "Apple Inc."


async def test_undo_delete_holding_restores_holding_and_transactions(aapl_session):
    with patch("market_lens_dashboard.services.portfolio_service._current_price",
               new_callable=AsyncMock, return_value=Decimal("200.0")):
        await portfolio_service.sell_stock_shares(
            aapl_session, USER_ID, "AAPL", shares=40, sold_at=Decimal("200.0"), date="2024-02-01"
        )

    await portfolio_service.delete_stock_holding(aapl_session, USER_ID, "AAPL")
    await portfolio_service.undo_last_action(aapl_session, USER_ID)

    holding = await portfolio_service.get_stock_holding(aapl_session, USER_ID, "AAPL", price=Decimal("200.0"))
    assert holding.shares == 60
    assert holding.sold_shares == 40
    assert holding.company_name == "Apple Inc."


async def test_undo_with_nothing_to_undo_raises(db_session):
    with pytest.raises(ValueError, match="Nothing to undo"):
        await portfolio_service.undo_last_action(db_session, USER_ID)


async def test_undo_is_lifo_and_marks_entries_undone(aapl_session):
    """A second undo call reverses the next-most-recent action, not the same one again."""
    with patch("market_lens_dashboard.services.portfolio_service._current_price",
               new_callable=AsyncMock, return_value=Decimal("200.0")):
        await portfolio_service.add_stock_purchase(
            aapl_session, USER_ID, "AAPL", shares=10, bought_at=Decimal("160.0"), date="2024-02-01"
        )
        await portfolio_service.sell_stock_shares(
            aapl_session, USER_ID, "AAPL", shares=5, sold_at=Decimal("200.0"), date="2024-03-01"
        )

    first = await portfolio_service.undo_last_action(aapl_session, USER_ID)  # reverses the sell
    second = await portfolio_service.undo_last_action(aapl_session, USER_ID)  # reverses the buy
    assert first.action == "insert"
    assert second.action == "insert"

    entries = await portfolio_service.list_audit_log(aapl_session, USER_ID)
    assert all(e.undone for e in entries)

    with pytest.raises(ValueError, match="Nothing to undo"):
        await portfolio_service.undo_last_action(aapl_session, USER_ID)

    holding = await portfolio_service.get_stock_holding(aapl_session, USER_ID, "AAPL", price=Decimal("200.0"))
    assert holding.shares == 100
    assert float(holding.average_cost) == pytest.approx(150.0)


async def test_list_audit_log_returns_newest_first(db_session):
    with patch("market_lens_dashboard.services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value=""):
        with patch("market_lens_dashboard.services.portfolio_service._current_price",
                   new_callable=AsyncMock, return_value=Decimal("100.0")):
            with patch("market_lens_dashboard.services.portfolio_service.asyncio.create_task"):
                await portfolio_service.add_stock_purchase(
                    db_session, USER_ID, "AAPL", shares=10, bought_at=Decimal("100.0"), date="2024-01-01"
                )
                await portfolio_service.add_stock_purchase(
                    db_session, USER_ID, "MSFT", shares=5, bought_at=Decimal("200.0"), date="2024-01-02"
                )

    entries = await portfolio_service.list_audit_log(db_session, USER_ID)
    assert [e.ticker for e in entries] == ["MSFT", "AAPL"]
