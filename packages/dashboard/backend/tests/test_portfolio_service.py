"""Integration tests for portfolio_service — exercises the full service layer
with a real in-memory SQLite database via the db_session fixture.

External calls (yfinance, archive) are mocked so tests are offline.
"""

import asyncio
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from sqlalchemy import select

from market_lens_dashboard.models.portfolio import Holding, Transaction
from market_lens_dashboard.services import portfolio_service

USER_ID = "test-user"


# ── shared fixture: one AAPL holding with 100 shares @ $150 ──────────────────

@pytest_asyncio.fixture
async def aapl_session(db_session):
    """db_session pre-loaded with AAPL: 100 shares bought at $150 on 2024-01-01."""
    holding = Holding(
        user_id=USER_ID, ticker="AAPL", company_name="Apple Inc.",
        shares=0, sold_shares=0, average_cost=0.0,
    )
    db_session.add(holding)
    await db_session.flush()

    txn = Transaction(
        holding_id=holding.id, sale=False, date="2024-01-01",
        shares=100, bought_at=150.0, shares_remaining=100,
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
                   new_callable=AsyncMock, return_value=175.0):
            with patch("market_lens_dashboard.services.portfolio_service.asyncio.create_task"):
                result = await portfolio_service.add_stock_purchase(
                    db_session, USER_ID, "AAPL", shares=100, bought_at=150.0, date="2024-01-01"
                )

    assert result.ticker == "AAPL"
    assert result.company_name == "Apple Inc."
    assert result.shares == 100
    assert result.average_cost == pytest.approx(150.0)
    assert result.current_price == pytest.approx(175.0)


async def test_add_purchase_to_existing_holding(aapl_session):
    with patch("market_lens_dashboard.services.portfolio_service._current_price",
               new_callable=AsyncMock, return_value=175.0):
        result = await portfolio_service.add_stock_purchase(
            aapl_session, USER_ID, "AAPL", shares=50, bought_at=160.0, date="2024-02-01"
        )

    assert result.shares == 150
    expected_avg = (100 * 150.0 + 50 * 160.0) / 150
    assert result.average_cost == pytest.approx(expected_avg, rel=1e-3)


async def test_add_purchase_future_date_raises(db_session):
    import datetime
    future = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
    with pytest.raises(ValueError, match="future"):
        await portfolio_service.add_stock_purchase(db_session, USER_ID, "AAPL", 10, 100.0, date=future)


# ── sell_stock_shares ─────────────────────────────────────────────────────────

async def test_sell_reduces_shares(aapl_session):
    with patch("market_lens_dashboard.services.portfolio_service._current_price",
               new_callable=AsyncMock, return_value=200.0):
        result = await portfolio_service.sell_stock_shares(
            aapl_session, USER_ID, "AAPL", shares=40, sold_at=200.0, date="2024-02-01"
        )

    assert result.shares == 60
    assert result.sold_shares == 40


async def test_sell_exceeds_available_raises(aapl_session):
    with pytest.raises(ValueError, match="cannot sell"):
        await portfolio_service.sell_stock_shares(
            aapl_session, USER_ID, "AAPL", shares=999, sold_at=200.0, date="2024-02-01"
        )


async def test_sell_before_earliest_buy_raises(aapl_session):
    with pytest.raises(ValueError, match="before the earliest purchase"):
        await portfolio_service.sell_stock_shares(
            aapl_session, USER_ID, "AAPL", shares=10, sold_at=200.0, date="2023-12-31"
        )


async def test_sell_unknown_ticker_raises(db_session):
    with pytest.raises(ValueError, match="No holding"):
        await portfolio_service.sell_stock_shares(
            db_session, USER_ID, "NOTEXIST", shares=10, sold_at=100.0
        )


# ── get_stock_holding ─────────────────────────────────────────────────────────

async def test_get_holding_returns_correct_data(aapl_session):
    result = await portfolio_service.get_stock_holding(aapl_session, USER_ID, "AAPL", price=175.0)
    assert result.ticker == "AAPL"
    assert result.shares == 100
    assert result.current_price == 175.0
    assert result.stock_value == pytest.approx(17500.0)


async def test_get_holding_not_found_raises(db_session):
    with pytest.raises(ValueError, match="No holding"):
        await portfolio_service.get_stock_holding(db_session, USER_ID, "NOTEXIST", price=100.0)


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
    holding = Holding(user_id=USER_ID, ticker="TSLA", company_name="Tesla", shares=0, sold_shares=0, average_cost=0.0)
    db_session.add(holding)
    await db_session.flush()

    b1 = Transaction(holding_id=holding.id, sale=False, date="2024-01-01",
                     shares=50, bought_at=200.0, shares_remaining=50)
    b2 = Transaction(holding_id=holding.id, sale=False, date="2024-02-01",
                     shares=50, bought_at=250.0, shares_remaining=50)
    db_session.add(b1)
    db_session.add(b2)
    portfolio_service._replay_fifo(holding, [b1, b2])
    await db_session.commit()

    # Refresh to get IDs
    await db_session.refresh(b1)

    with patch("market_lens_dashboard.services.portfolio_service._current_price",
               new_callable=AsyncMock, return_value=300.0):
        result = await portfolio_service.delete_transaction(db_session, USER_ID, "TSLA", b1.id)

    # Only b2 remains: 50 shares @ $250
    assert result.shares == 50
    assert result.average_cost == pytest.approx(250.0)


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

    assert result.portfolio_value == 0.0
    assert result.holdings == []
    assert result.total_shares == 0


async def test_get_portfolio_with_prices_dict(aapl_session):
    """When prices dict is supplied, no network calls are made."""
    result = await portfolio_service.get_portfolio(aapl_session, USER_ID, prices={"AAPL": 175.0})

    assert len(result.holdings) == 1
    assert result.holdings[0].ticker == "AAPL"
    assert result.portfolio_value == pytest.approx(175.0 * 100)
    assert result.total_invested == pytest.approx(100 * 150.0)
    assert result.total_return == pytest.approx(175.0 * 100 - 100 * 150.0)
