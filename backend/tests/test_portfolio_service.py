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
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.portfolio import Holding, Transaction, WatchlistEntry
from schemas.portfolio import BulkPurchaseLot, BulkSaleLot
from services import portfolio_service

USER_ID = "test-user"


# ── _current_price ────────────────────────────────────────────────────────────
# Never falls back to a fabricated $0 — see portfolio_service._current_price
# docstring. These exercise the real function directly (unmocked), only
# stubbing its two external dependencies (fetch_current, yf.Ticker.history).

async def test_current_price_uses_live_quote():
    from schemas.stocks import OHLCV, OHLCVResponse
    response = OHLCVResponse(ticker="AAPL", data=[OHLCV(date="2024-01-15", close=184.0)])
    with patch("services.portfolio_service.fetch_current",
               new_callable=AsyncMock, return_value=response):
        price = await portfolio_service._current_price("AAPL")
    assert price == Decimal("184.0")


async def test_current_price_returns_none_when_both_sources_fail():
    with patch("services.portfolio_service.fetch_current",
               new_callable=AsyncMock, side_effect=Exception("network error")):
        with patch("services.portfolio_service.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.side_effect = Exception("also fails")
            price = await portfolio_service._current_price("AAPL")
    assert price is None


async def test_current_price_falls_back_to_direct_history_when_live_fetch_fails():
    import pandas as pd
    with patch("services.portfolio_service.fetch_current",
               new_callable=AsyncMock, side_effect=Exception("archive missing")):
        with patch("services.portfolio_service.yf.Ticker") as mock_ticker:
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
    with patch("services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value="Apple Inc."):
        with patch("services.portfolio_service._current_price",
                   new_callable=AsyncMock, return_value=Decimal("175.0")):
            with patch("services.portfolio_service.asyncio.create_task"):
                result = await portfolio_service.add_stock_purchase(
                    db_session, USER_ID, "AAPL", shares=100, bought_at=Decimal("150.0"), date="2024-01-01"
                )

    assert result.ticker == "AAPL"
    assert result.company_name == "Apple Inc."
    assert result.shares == 100
    assert float(result.average_cost) == pytest.approx(150.0)
    assert float(result.current_price) == pytest.approx(175.0)


async def test_add_purchase_to_existing_holding(aapl_session):
    with patch("services.portfolio_service._current_price",
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


# ── add_stock_purchases_bulk ──────────────────────────────────────────────────

async def test_bulk_purchase_creates_new_holding_with_multiple_lots(db_session):
    lots = [
        BulkPurchaseLot(shares=100, bought_at=Decimal("150.0"), date="2024-01-01"),
        BulkPurchaseLot(shares=50, bought_at=Decimal("160.0"), date="2024-02-01"),
    ]
    with patch("services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value="Apple Inc."):
        with patch("services.portfolio_service._current_price",
                   new_callable=AsyncMock, return_value=Decimal("175.0")):
            with patch("services.portfolio_service.asyncio.create_task"):
                result = await portfolio_service.add_stock_purchases_bulk(
                    db_session, USER_ID, "AAPL", lots,
                )

    assert result.ticker == "AAPL"
    assert result.shares == 150
    assert len(result.trade_history) == 2
    expected_avg = (100 * 150.0 + 50 * 160.0) / 150
    assert float(result.average_cost) == pytest.approx(expected_avg, rel=1e-3)


async def test_bulk_purchase_to_existing_holding(aapl_session):
    lots = [
        BulkPurchaseLot(shares=25, bought_at=Decimal("140.0"), date="2023-12-01"),
        BulkPurchaseLot(shares=25, bought_at=Decimal("160.0"), date="2024-02-01"),
    ]
    with patch("services.portfolio_service._current_price",
               new_callable=AsyncMock, return_value=Decimal("175.0")):
        result = await portfolio_service.add_stock_purchases_bulk(
            aapl_session, USER_ID, "AAPL", lots,
        )

    assert result.shares == 150
    assert len(result.trade_history) == 3


async def test_bulk_purchase_empty_list_raises(db_session):
    with pytest.raises(ValueError, match="At least one purchase"):
        await portfolio_service.add_stock_purchases_bulk(db_session, USER_ID, "AAPL", [])


async def test_bulk_purchase_bad_date_rolls_back_entire_batch(db_session):
    import datetime
    future = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
    lots = [
        BulkPurchaseLot(shares=100, bought_at=Decimal("150.0"), date="2024-01-01"),
        BulkPurchaseLot(shares=50, bought_at=Decimal("160.0"), date=future),
    ]
    with patch("services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value="Apple Inc."):
        with pytest.raises(ValueError, match="future"):
            await portfolio_service.add_stock_purchases_bulk(db_session, USER_ID, "AAPL", lots)

    # Nothing from the batch should have been committed — not even the first,
    # valid-looking lot, and not the holding itself.
    result = await db_session.execute(select(Holding).where(Holding.ticker == "AAPL"))
    assert result.scalar_one_or_none() is None


async def test_bulk_purchase_logs_one_audit_entry_per_lot(db_session):
    from models.portfolio import AuditEntry
    lots = [
        BulkPurchaseLot(shares=10, bought_at=Decimal("100.0"), date="2024-01-01"),
        BulkPurchaseLot(shares=10, bought_at=Decimal("110.0"), date="2024-01-02"),
        BulkPurchaseLot(shares=10, bought_at=Decimal("120.0"), date="2024-01-03"),
    ]
    with patch("services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value="Apple Inc."):
        with patch("services.portfolio_service._current_price",
                   new_callable=AsyncMock, return_value=Decimal("175.0")):
            with patch("services.portfolio_service.asyncio.create_task"):
                await portfolio_service.add_stock_purchases_bulk(db_session, USER_ID, "AAPL", lots)

    result = await db_session.execute(select(AuditEntry).where(AuditEntry.user_id == USER_ID))
    assert len(result.scalars().all()) == 3


# ── sell_stock_shares ─────────────────────────────────────────────────────────

async def test_sell_reduces_shares(aapl_session):
    with patch("services.portfolio_service._current_price",
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


# ── sell_stock_shares_bulk ────────────────────────────────────────────────────

async def test_bulk_sell_reduces_shares_across_multiple_lots(aapl_session):
    lots = [
        BulkSaleLot(shares=20, sold_at=Decimal("200.0"), date="2024-02-01"),
        BulkSaleLot(shares=10, sold_at=Decimal("210.0"), date="2024-03-01"),
    ]
    with patch("services.portfolio_service._current_price",
               new_callable=AsyncMock, return_value=Decimal("220.0")):
        result = await portfolio_service.sell_stock_shares_bulk(aapl_session, USER_ID, "AAPL", lots)

    assert result.shares == 70
    assert result.sold_shares == 30


async def test_bulk_sell_exceeds_available_raises(aapl_session):
    lots = [
        BulkSaleLot(shares=60, sold_at=Decimal("200.0"), date="2024-02-01"),
        BulkSaleLot(shares=60, sold_at=Decimal("200.0"), date="2024-03-01"),
    ]
    with pytest.raises(ValueError, match="cannot sell"):
        await portfolio_service.sell_stock_shares_bulk(aapl_session, USER_ID, "AAPL", lots)


async def test_bulk_sell_before_earliest_buy_rolls_back_entire_batch(aapl_session):
    lots = [
        BulkSaleLot(shares=10, sold_at=Decimal("200.0"), date="2024-02-01"),
        BulkSaleLot(shares=10, sold_at=Decimal("200.0"), date="2023-12-31"),
    ]
    with pytest.raises(ValueError, match="before the earliest purchase"):
        await portfolio_service.sell_stock_shares_bulk(aapl_session, USER_ID, "AAPL", lots)

    # Nothing from the batch should have landed — not even the first, valid-looking lot.
    holding = (await aapl_session.execute(
        select(Holding).where(Holding.ticker == "AAPL")
    )).scalar_one()
    txns = await portfolio_service._fetch_transactions(aapl_session, holding.id)
    assert len(txns) == 1  # only the original aapl_session buy


async def test_bulk_sell_unknown_ticker_raises(db_session):
    with pytest.raises(ValueError, match="No holding"):
        await portfolio_service.sell_stock_shares_bulk(
            db_session, USER_ID, "NOTEXIST", [BulkSaleLot(shares=10, sold_at=Decimal("100.0"))]
        )


async def test_bulk_sell_empty_list_raises(aapl_session):
    with pytest.raises(ValueError, match="At least one sale"):
        await portfolio_service.sell_stock_shares_bulk(aapl_session, USER_ID, "AAPL", [])


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

    with patch("services.portfolio_service._current_price",
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
    with patch("services.portfolio_service.get_market_status",
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
    with patch("services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value="Apple Inc."):
        with patch("services.portfolio_service._current_price",
                   new_callable=AsyncMock, return_value=Decimal("175.0")):
            with patch("services.portfolio_service.asyncio.create_task"):
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
    with patch("services.portfolio_service._current_price",
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
    with patch("services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value="Apple Inc."):
        with patch("services.portfolio_service._current_price",
                   new_callable=AsyncMock, return_value=Decimal("175.0")):
            with patch("services.portfolio_service.asyncio.create_task"):
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
    with patch("services.portfolio_service._current_price",
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
    with patch("services.portfolio_service._current_price",
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
    with patch("services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value=""):
        with patch("services.portfolio_service._current_price",
                   new_callable=AsyncMock, return_value=Decimal("100.0")):
            with patch("services.portfolio_service.asyncio.create_task"):
                await portfolio_service.add_stock_purchase(
                    db_session, USER_ID, "AAPL", shares=10, bought_at=Decimal("100.0"), date="2024-01-01"
                )
                await portfolio_service.add_stock_purchase(
                    db_session, USER_ID, "MSFT", shares=5, bought_at=Decimal("200.0"), date="2024-01-02"
                )

    entries = await portfolio_service.list_audit_log(db_session, USER_ID)
    assert [e.ticker for e in entries] == ["MSFT", "AAPL"]


# ── repair_stock_metadata ───────────────────────────────────────────────────
#
# Like repair_all_fifo, this opens its own sessions via `from database import
# SessionLocal` rather than taking one as a parameter — so tests patch
# database.SessionLocal to the per-test engine (db_engine) instead of using
# the db_session fixture directly.

@pytest_asyncio.fixture
async def repaired_db(db_engine):
    """Runs portfolio_service.repair_stock_metadata() against the per-test
    engine and hands back a session on it afterward for assertions."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _run():
        with patch("database.SessionLocal", factory):
            await portfolio_service.repair_stock_metadata()

    async with factory() as session:
        yield session, _run


async def test_repair_backfills_missing_company_name(repaired_db):
    session, run = repaired_db
    session.add(Holding(
        user_id=USER_ID, ticker="AAPL", company_name="", market="US",
        shares=10, sold_shares=0, average_cost=Decimal("150.0"),
    ))
    session.add(Holding(
        user_id=USER_ID, ticker="MSFT", company_name="Microsoft Corp", market="US",
        shares=5, sold_shares=0, average_cost=Decimal("300.0"),
    ))
    await session.commit()

    with patch("services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value="Apple Inc."):
        with patch("services.portfolio_service.get_all_stocks",
                   new_callable=AsyncMock, return_value={"AAPL": "Apple Inc.", "MSFT": "Microsoft Corp"}):
            await run()

    result = await session.execute(select(Holding).order_by(Holding.ticker))
    holdings = {h.ticker: h.company_name for h in result.scalars().all()}
    assert holdings["AAPL"] == "Apple Inc."
    assert holdings["MSFT"] == "Microsoft Corp"  # untouched — wasn't broken


async def test_repair_backfills_watchlist_entry_that_fell_back_to_ticker(repaired_db):
    session, run = repaired_db
    session.add(Holding(
        user_id=USER_ID, ticker="AAPL", company_name="", market="US",
        shares=10, sold_shares=0, average_cost=Decimal("150.0"),
    ))
    session.add(WatchlistEntry(user_id=USER_ID, ticker="AAPL", market="US", company_name="AAPL"))
    await session.commit()

    with patch("services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value="Apple Inc."):
        with patch("services.portfolio_service.get_all_stocks",
                   new_callable=AsyncMock, return_value={"AAPL": "Apple Inc."}):
            await run()

    entry = (await session.execute(
        select(WatchlistEntry).where(WatchlistEntry.ticker == "AAPL")
    )).scalar_one()
    assert entry.company_name == "Apple Inc."


async def test_repair_backfills_missing_archive_entry(repaired_db):
    session, run = repaired_db
    session.add(Holding(
        user_id=USER_ID, ticker="TSLA", company_name="Tesla, Inc.", market="US",
        shares=3, sold_shares=0, average_cost=Decimal("200.0"),
    ))
    await session.commit()

    with patch("services.portfolio_service.get_all_stocks",
               new_callable=AsyncMock, return_value={}):  # TSLA missing from the archive
        with patch("services.portfolio_service.add_stock", new_callable=AsyncMock) as mock_add_stock:
            await run()

    mock_add_stock.assert_awaited_once_with("TSLA")


async def test_repair_skips_ticker_that_no_longer_resolves(repaired_db):
    session, run = repaired_db
    session.add(Holding(
        user_id=USER_ID, ticker="DELISTED", company_name="", market="US",
        shares=1, sold_shares=0, average_cost=Decimal("1.0"),
    ))
    await session.commit()

    with patch("services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, side_effect=ValueError("not found")):
        with patch("services.portfolio_service.get_all_stocks",
                   new_callable=AsyncMock, return_value={"DELISTED": "x"}):
            await run()  # should not raise

    holding = (await session.execute(
        select(Holding).where(Holding.ticker == "DELISTED")
    )).scalar_one()
    assert holding.company_name == ""


async def test_repair_no_holdings_is_a_noop(repaired_db):
    _session, run = repaired_db
    with patch("services.portfolio_service.get_all_stocks", new_callable=AsyncMock) as mock_get_all:
        await run()
    mock_get_all.assert_not_awaited()
