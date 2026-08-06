"""Tests for dividend tracking in portfolio_service.py.

Covers the auto-sync path (mocked yfinance dividend history), the manual
add/edit/delete CRUD path, and that totals roll up correctly into
StockHolding/PortfolioResponse.
"""

from decimal import Decimal

import pandas as pd
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock

from cache import dividend_sync_cache
from models.portfolio import Dividend, Holding, Transaction
from services import portfolio_service

USER_ID = "test-user"


def _dividend_series(pairs: dict[str, float]) -> pd.Series:
    return pd.Series({pd.Timestamp(date): amount for date, amount in pairs.items()})


@pytest_asyncio.fixture(autouse=True)
def _clear_dividend_sync_cache():
    dividend_sync_cache.clear()
    yield
    dividend_sync_cache.clear()


@pytest_asyncio.fixture
async def aapl_session(db_session, pid):
    """db_session pre-loaded with AAPL: 100 shares bought at $150 on 2024-01-01."""
    holding = Holding(
        user_id=USER_ID, portfolio_id=pid, ticker="AAPL", company_name="Apple Inc.",
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


# ── _sync_dividends ──────────────────────────────────────────────────────────

async def test_sync_inserts_dividends_after_earliest_buy(aapl_session, pid):
    series = _dividend_series({"2024-03-01": 0.24, "2024-06-01": 0.25})
    with patch("services.portfolio_service.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.dividends = series
        result = await portfolio_service.sync_dividends(aapl_session, USER_ID, pid, "AAPL")

    assert len(result) == 2
    assert result[0].date == "2024-03-01"
    assert float(result[0].amount_per_share) == pytest.approx(0.24)
    assert result[0].shares_held == 100
    assert float(result[0].total_amount) == pytest.approx(24.0)
    assert result[0].source == "auto"


async def test_sync_skips_ex_dates_before_earliest_buy(aapl_session, pid):
    series = _dividend_series({"2023-06-01": 0.20, "2024-03-01": 0.24})
    with patch("services.portfolio_service.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.dividends = series
        result = await portfolio_service.sync_dividends(aapl_session, USER_ID, pid, "AAPL")

    assert [d.date for d in result] == ["2024-03-01"]


async def test_sync_never_overwrites_existing_row(aapl_session, pid):
    """A manually-edited or auto-fetched row for a date is never clobbered by a later sync."""
    await portfolio_service.add_dividend(aapl_session, pid, "AAPL", "2024-03-01", Decimal("0.99"))

    series = _dividend_series({"2024-03-01": 0.24})  # yfinance disagrees with the manual value
    with patch("services.portfolio_service.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.dividends = series
        result = await portfolio_service.sync_dividends(aapl_session, USER_ID, pid, "AAPL")

    assert len(result) == 1
    assert float(result[0].amount_per_share) == pytest.approx(0.99)
    assert result[0].source == "manual"


async def test_sync_is_throttled_within_24h(aapl_session, pid):
    series = _dividend_series({"2024-03-01": 0.24})
    with patch("services.portfolio_service.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.dividends = series
        await portfolio_service.sync_dividends(aapl_session, USER_ID, pid, "AAPL")
        assert mock_ticker.call_count == 1

        # Second call within the TTL window must not hit yfinance again.
        await portfolio_service.sync_dividends(aapl_session, USER_ID, pid, "AAPL")
        assert mock_ticker.call_count == 1


async def test_sync_skips_dates_with_zero_shares_held(aapl_session, pid):
    """A dividend paid after every share was sold shouldn't be recorded."""
    with patch("services.portfolio_service._current_price",
               new_callable=AsyncMock, return_value=Decimal("200.0")):
        await portfolio_service.sell_stock_shares(
            aapl_session, USER_ID, pid, "AAPL", shares=100, sold_at=Decimal("200.0"), date="2024-02-01"
        )

    series = _dividend_series({"2024-03-01": 0.24})
    with patch("services.portfolio_service.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.dividends = series
        result = await portfolio_service.sync_dividends(aapl_session, USER_ID, pid, "AAPL")

    assert result == []


async def test_sync_unknown_ticker_raises(db_session, pid):
    with pytest.raises(ValueError, match="No holding"):
        await portfolio_service.sync_dividends(db_session, USER_ID, pid, "NOTEXIST")


# ── add_dividend / update_dividend / delete_dividend ─────────────────────────

async def test_add_dividend_defaults_shares_held_from_fifo_log(aapl_session, pid):
    entry = await portfolio_service.add_dividend(aapl_session, pid, "AAPL", "2024-03-01", Decimal("0.5"))
    assert entry.shares_held == 100
    assert float(entry.total_amount) == pytest.approx(50.0)
    assert entry.source == "manual"


async def test_add_dividend_explicit_shares_held_overrides_fifo(aapl_session, pid):
    entry = await portfolio_service.add_dividend(
        aapl_session, pid, "AAPL", "2024-03-01", Decimal("0.5"), shares_held=40,
    )
    assert entry.shares_held == 40
    assert float(entry.total_amount) == pytest.approx(20.0)


async def test_add_dividend_duplicate_date_raises(aapl_session, pid):
    await portfolio_service.add_dividend(aapl_session, pid, "AAPL", "2024-03-01", Decimal("0.5"))
    with pytest.raises(ValueError, match="already exists"):
        await portfolio_service.add_dividend(aapl_session, pid, "AAPL", "2024-03-01", Decimal("0.6"))


async def test_add_dividend_future_date_raises(aapl_session, pid):
    import datetime
    future = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
    with pytest.raises(ValueError, match="future"):
        await portfolio_service.add_dividend(aapl_session, pid, "AAPL", future, Decimal("0.5"))


async def test_add_dividend_before_earliest_buy_raises(aapl_session, pid):
    with pytest.raises(ValueError, match="before the earliest purchase"):
        await portfolio_service.add_dividend(aapl_session, pid, "AAPL", "2023-12-01", Decimal("0.5"))


async def test_add_dividend_with_no_shares_held_raises(aapl_session, pid):
    with pytest.raises(ValueError, match="No shares"):
        await portfolio_service.add_dividend(
            aapl_session, pid, "AAPL", "2024-03-01", Decimal("0.5"), shares_held=0,
        )


async def test_update_dividend_recomputes_total_and_marks_manual(aapl_session, pid):
    entry = await portfolio_service.add_dividend(aapl_session, pid, "AAPL", "2024-03-01", Decimal("0.5"))
    updated = await portfolio_service.update_dividend(
        aapl_session, pid, "AAPL", entry.id, amount_per_share=Decimal("1.0"),
    )
    assert float(updated.total_amount) == pytest.approx(100.0)
    assert updated.source == "manual"


async def test_update_dividend_not_found_raises(aapl_session, pid):
    with pytest.raises(ValueError, match="not found"):
        await portfolio_service.update_dividend(aapl_session, pid, "AAPL", 9999, amount_per_share=Decimal("1.0"))


async def test_delete_dividend_removes_it(aapl_session, pid):
    entry = await portfolio_service.add_dividend(aapl_session, pid, "AAPL", "2024-03-01", Decimal("0.5"))
    await portfolio_service.delete_dividend(aapl_session, pid, "AAPL", entry.id)
    assert await portfolio_service.get_dividends(aapl_session, pid, "AAPL") == []


async def test_delete_dividend_not_found_raises(aapl_session, pid):
    with pytest.raises(ValueError, match="not found"):
        await portfolio_service.delete_dividend(aapl_session, pid, "AAPL", 9999)


# ── roll-up into StockHolding / PortfolioResponse ─────────────────────────────

async def test_stock_holding_includes_total_dividends(aapl_session, pid):
    await portfolio_service.add_dividend(aapl_session, pid, "AAPL", "2024-03-01", Decimal("0.5"))
    holding = await portfolio_service.get_stock_holding(aapl_session, pid, "AAPL", price=Decimal("175.0"))
    assert float(holding.total_dividends) == pytest.approx(50.0)
    assert len(holding.dividends) == 1


async def test_portfolio_net_pl_includes_dividends(aapl_session, pid):
    await portfolio_service.add_dividend(aapl_session, pid, "AAPL", "2024-03-01", Decimal("0.5"))
    portfolio = await portfolio_service.get_portfolio(
        aapl_session, USER_ID, prices={"AAPL": Decimal("175.0")},
    )
    assert float(portfolio.total_dividends) == pytest.approx(50.0)
    expected_net = float(portfolio.total_return) + float(portfolio.realized_gains) + 50.0
    assert float(portfolio.net_profit_loss) == pytest.approx(expected_net)


# ── new-holding background sync doesn't break add_stock_purchase ─────────────

async def test_new_holding_purchase_schedules_dividend_sync(db_session, pid):
    """A brand-new holding should schedule a background dividend sync alongside
    the existing dashboard-registration task, without blocking the response."""
    with patch("services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value="Apple Inc."):
        with patch("services.portfolio_service._current_price",
                   new_callable=AsyncMock, return_value=Decimal("175.0")):
            with patch("services.portfolio_service.asyncio.create_task") as mock_create_task:
                await portfolio_service.add_stock_purchase(
                    db_session, USER_ID, pid, "AAPL", shares=100, bought_at=Decimal("150.0"), date="2024-01-01"
                )

    assert mock_create_task.call_count == 2
