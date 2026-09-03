"""Lower-level tests for stock_service functions.

Mocks market_data_service (the market_data table access layer), yfinance
(yf.Ticker), and pandas_market_calendars (mcal) at the call site instead of
at the router boundary so that the transformation / parsing logic inside
each function is actually executed and covered.
"""

import asyncio

import pytest
import pandas as pd
from datetime import date, datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from yfinance.exceptions import YFRateLimitError

from cache import info_cache
from services import stock_service, yf_guard
from services.stock_service import (
    _last_completed_trading_day,
    get_market_status,
    get_all_stocks,
    delete_stock,
    fetch_intraday,
    fetch,
    fetch_current,
    fetch_detailed,
    fetch_eps_history,
    fetch_revenue_history,
    fetch_stock_dashboard,
    get_industry_map,
    get_sector_map,
    _snapshot_cache,
    _update_attempted,
)
from schemas.stocks import (
    OHLCV,
    OHLCVResponse,
    EPSHistoryResponse,
    EPSHistoryRow,
    RevenueHistoryResponse,
    RevenueHistoryRow,
    StockDetailedResponse,
)


# ── shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_module_state():
    """Clear module-level singletons so tests are independent."""
    _snapshot_cache._store.clear()
    _update_attempted.clear()
    info_cache.clear()
    yield
    _snapshot_cache._store.clear()
    _update_attempted.clear()
    info_cache.clear()


def _make_ohlcv_df(datetimes: list[str], closes: list[float] | None = None) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame with a tz-naive DatetimeIndex."""
    idx = pd.DatetimeIndex([pd.Timestamp(dt) for dt in datetimes])
    n = len(datetimes)
    c = closes if closes is not None else [100.0 + i * 10 for i in range(n)]
    return pd.DataFrame(
        {
            "Open": c,
            "High": [v + 1 for v in c],
            "Low": [v - 1 for v in c],
            "Close": c,
            "Volume": [1000 * (i + 1) for i in range(n)],
        },
        index=idx,
    )


@pytest.fixture
def fake_to_thread():
    """Replace asyncio.to_thread with a synchronous caller so we can mock stock.history."""
    async def _call(fn, *args, **kwargs):
        return fn(*args, **kwargs)
    return _call


# ── get_all_stocks ────────────────────────────────────────────────────────────

async def test_get_all_stocks_reads_archive_and_builds_dict():
    mock_ticker = MagicMock()
    mock_ticker.ticker = "AAPL"
    mock_ticker.info = {"displayName": "Apple Inc."}

    with patch("services.stock_service.market_data_service.get_symbols",
               new_callable=AsyncMock, return_value=["AAPL"]):
        with patch("services.stock_service.yf.Ticker", return_value=mock_ticker):
            result = await get_all_stocks()

    assert "AAPL" in result
    assert result["AAPL"] == "Apple Inc."


async def test_get_all_stocks_cache_hit_skips_query():
    _snapshot_cache.set("all_stocks", {"AAPL": "Apple"})

    with patch("services.stock_service.market_data_service.get_symbols",
               new_callable=AsyncMock) as mock_symbols:
        result = await get_all_stocks()

    mock_symbols.assert_not_called()
    assert result == {"AAPL": "Apple"}


async def test_get_all_stocks_no_symbols_returns_empty_dict():
    with patch("services.stock_service.market_data_service.get_symbols",
               new_callable=AsyncMock, return_value=[]):
        result = await get_all_stocks()
    assert result == {}


async def test_get_all_stocks_falls_back_to_short_name():
    mock_ticker = MagicMock()
    mock_ticker.ticker = "AAPL"
    mock_ticker.info = {"displayName": None, "shortName": "Apple"}

    with patch("services.stock_service.market_data_service.get_symbols",
               new_callable=AsyncMock, return_value=["AAPL"]):
        with patch("services.stock_service.yf.Ticker", return_value=mock_ticker):
            result = await get_all_stocks()

    assert result["AAPL"] == "Apple"


# ── delete_stock ──────────────────────────────────────────────────────────────

async def test_delete_stock_removes_matching_rows():
    with patch("services.stock_service.market_data_service.delete_symbol",
               new_callable=AsyncMock, return_value=1) as mock_delete:
        result = await delete_stock("AAPL")

    assert "deleted successfully" in result["message"]
    mock_delete.assert_called_once_with("AAPL")


async def test_delete_stock_no_matching_rows_raises():
    with patch("services.stock_service.market_data_service.delete_symbol",
               new_callable=AsyncMock, return_value=0):
        with pytest.raises(ValueError, match="No data found"):
            await delete_stock("AAPL")


async def test_delete_stock_invalidates_cache():
    _snapshot_cache.set("AAPL:detailed", "cached_value")
    _snapshot_cache.set("all_stocks", {"AAPL": "Apple"})

    with patch("services.stock_service.market_data_service.delete_symbol",
               new_callable=AsyncMock, return_value=1):
        await delete_stock("AAPL")

    assert _snapshot_cache.get("AAPL:detailed") is None
    assert _snapshot_cache.get("all_stocks") is None


# ── fetch ─────────────────────────────────────────────────────────────────────

async def test_fetch_returns_ohlcv_response():
    records = [{
        "date": "2024-01-15", "open": 183.0, "high": 185.0,
        "low": 182.0, "close": 184.0, "volume": 5_000_000,
    }]

    with patch("services.stock_service.market_data_service.get_ohlcv",
               new_callable=AsyncMock, return_value=records):
        with patch(
            "services.stock_service._last_completed_trading_day",
            new_callable=AsyncMock,
            return_value=pd.Timestamp("2024-01-15"),
        ):
            result = await fetch("AAPL", days=30)

    assert result.ticker == "AAPL"
    assert len(result.data) == 1
    assert result.data[0].close == pytest.approx(184.0)


async def test_fetch_no_data_raises():
    with patch("services.stock_service.market_data_service.get_ohlcv",
               new_callable=AsyncMock, return_value=[]):
        with pytest.raises(ValueError, match="No data found"):
            await fetch("AAPL")


def _archive_state(last_archived, last_completed, attempted=None):
    """Patch the three reads ensure_archive_current makes its decision from."""
    return patch.multiple(
        "services.stock_service",
        _last_completed_trading_day=AsyncMock(return_value=pd.Timestamp(last_completed)),
        _last_update_attempt=AsyncMock(
            return_value=pd.Timestamp(attempted) if attempted else None
        ),
    ), patch(
        "services.stock_service.market_data_service.get_last_date",
        new_callable=AsyncMock,
        return_value=date.fromisoformat(last_archived) if last_archived else None,
    )


async def test_fetch_stale_data_triggers_append():
    stale_records = [{
        "date": "2024-01-10", "open": 183.0, "high": 185.0,
        "low": 182.0, "close": 184.0, "volume": 5_000_000,
    }]
    fresh_records = [{
        "date": "2024-01-15", "open": 186.0, "high": 188.0,
        "low": 185.0, "close": 187.0, "volume": 4_000_000,
    }]
    state, last_date = _archive_state("2024-01-10", "2024-01-15")

    with patch("services.stock_service.market_data_service.get_ohlcv",
               new_callable=AsyncMock, side_effect=[stale_records, fresh_records]):
        with state, last_date:
            with patch("services.price_fetcher.append_price_data",
                       new_callable=AsyncMock) as mock_append:
                result = await fetch("AAPL", days=1)

    mock_append.assert_called_once_with("AAPL")
    assert result.ticker == "AAPL"
    assert result.data[0].close == pytest.approx(187.0)


# ── ensure_archive_current ────────────────────────────────────────────────
# Extracted out of fetch() because the archive used to advance *only* for
# tickers someone opened on the Tracker. A portfolio-only user could hold a
# stock for weeks with its history frozen at the day it was added — which is
# exactly what left the Performance panel insisting there was no history.

async def test_ensure_archive_current_tops_up_a_stale_archive():
    state, last_date = _archive_state("2024-01-10", "2024-01-15")
    with state, last_date:
        with patch("services.price_fetcher.append_price_data",
                   new_callable=AsyncMock) as mock_append:
            updated = await stock_service.ensure_archive_current("AAPL")

    assert updated is True
    mock_append.assert_awaited_once_with("AAPL")


async def test_ensure_archive_current_is_a_no_op_when_already_current():
    state, last_date = _archive_state("2024-01-15", "2024-01-15")
    with state, last_date:
        with patch("services.price_fetcher.append_price_data",
                   new_callable=AsyncMock) as mock_append:
            updated = await stock_service.ensure_archive_current("AAPL")

    assert updated is False
    mock_append.assert_not_called()


async def test_ensure_archive_current_respects_the_attempt_marker():
    """Yahoo publishes a session's bar some time after the close; asking again
    within the same session is a wasted call, not a retry."""
    state, last_date = _archive_state("2024-01-10", "2024-01-15", attempted="2024-01-15")
    with state, last_date:
        with patch("services.price_fetcher.append_price_data",
                   new_callable=AsyncMock) as mock_append:
            updated = await stock_service.ensure_archive_current("AAPL")

    assert updated is False
    mock_append.assert_not_called()


async def test_ensure_archive_current_skips_a_ticker_with_no_archive_at_all():
    """Nothing to extend — that's add_stock's job, not a top-up's."""
    state, last_date = _archive_state(None, "2024-01-15")
    with state, last_date:
        with patch("services.price_fetcher.append_price_data",
                   new_callable=AsyncMock) as mock_append:
            updated = await stock_service.ensure_archive_current("AAPL")

    assert updated is False
    mock_append.assert_not_called()


async def test_ensure_archive_current_never_raises():
    """A stale archive is a degraded state, not an error — every caller has
    something older it can still show."""
    with patch("services.stock_service.market_data_service.get_last_date",
               new_callable=AsyncMock, side_effect=RuntimeError("db gone")):
        assert await stock_service.ensure_archive_current("AAPL") is False


async def test_archive_is_behind_reports_the_gap():
    state, last_date = _archive_state("2024-01-10", "2024-01-15")
    with state, last_date:
        assert await stock_service.archive_is_behind("AAPL") is True

    state, last_date = _archive_state("2024-01-15", "2024-01-15")
    with state, last_date:
        assert await stock_service.archive_is_behind("AAPL") is False


# ── fetch_intraday ────────────────────────────────────────────────────────────

async def test_fetch_intraday_filters_out_after_hours():
    today = date.today().isoformat()
    df = _make_ohlcv_df([
        f"{today} 09:30:00",
        f"{today} 12:00:00",
        f"{today} 15:59:00",
        f"{today} 16:30:00",  # after-hours — excluded by mask
    ])

    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"
    mock_stock.history.return_value = df

    result = await fetch_intraday(mock_stock)

    assert result.ticker == "AAPL"
    assert len(result.data) == 3
    assert all("16:30" not in row.date for row in result.data)


async def test_fetch_intraday_empty_df_raises():
    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"
    mock_stock.history.return_value = pd.DataFrame()

    with pytest.raises(ValueError, match="No intraday data"):
        await fetch_intraday(mock_stock)


async def test_fetch_intraday_returns_most_recent_day_only():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    today = date.today().isoformat()
    df = _make_ohlcv_df([
        f"{yesterday} 09:30:00",
        f"{yesterday} 15:59:00",
        f"{today} 09:30:00",
        f"{today} 15:59:00",
    ])

    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"
    mock_stock.history.return_value = df

    result = await fetch_intraday(mock_stock)

    assert len(result.data) == 2
    assert today in result.data[0].date


# ── fetch_current ─────────────────────────────────────────────────────────────

async def test_fetch_current_market_open_aggregates_session(fake_to_thread):
    today = date.today().isoformat()
    df = _make_ohlcv_df(
        [f"{today} 09:30:00", f"{today} 12:00:00", f"{today} 15:59:00"],
        closes=[100.0, 110.0, 120.0],
    )

    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"
    mock_stock.history.return_value = df

    with patch("services.stock_service.asyncio.to_thread",
               side_effect=fake_to_thread):
        result = await fetch_current(mock_stock, is_market_open=True)

    assert result.ticker == "AAPL"
    assert len(result.data) == 1
    row = result.data[0]
    assert row.open == pytest.approx(100.0)   # first bar Open
    assert row.high == pytest.approx(121.0)   # max of [101, 111, 121]
    assert row.low == pytest.approx(99.0)     # min of [99, 109, 119]
    assert row.close == pytest.approx(120.0)  # last bar Close
    assert row.volume == 6000                  # 1000+2000+3000


async def test_fetch_current_market_open_no_rth_data_raises(fake_to_thread):
    today = date.today().isoformat()
    df = _make_ohlcv_df([f"{today} 17:00:00"])  # outside RTH

    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"
    mock_stock.history.return_value = df

    with patch("services.stock_service.asyncio.to_thread",
               side_effect=fake_to_thread):
        with pytest.raises(ValueError):
            await fetch_current(mock_stock, is_market_open=True)


async def test_fetch_current_market_closed_falls_back_to_archive(fake_to_thread):
    last_data = OHLCVResponse(ticker="AAPL", data=[OHLCV(date="2024-01-15", close=183.5)])
    today = date.today().isoformat()
    # Only RTH data today → after ~mask it's empty → fall back to last_data
    df = _make_ohlcv_df([f"{today} 10:00:00"])

    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"
    mock_stock.history.return_value = df

    with patch("services.stock_service.asyncio.to_thread",
               side_effect=fake_to_thread):
        with patch("services.stock_service.fetch",
                   new_callable=AsyncMock, return_value=last_data):
            result = await fetch_current(mock_stock, is_market_open=False)

    assert result == last_data


async def test_fetch_current_market_closed_returns_after_hours_price(fake_to_thread):
    last_data = OHLCVResponse(ticker="AAPL", data=[OHLCV(date="2024-01-15", close=183.5)])
    today = date.today().isoformat()
    # After-hours bar — survives both the date filter and ~mask
    df = _make_ohlcv_df([f"{today} 17:00:00"], closes=[187.5])

    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"
    mock_stock.history.return_value = df

    with patch("services.stock_service.asyncio.to_thread",
               side_effect=fake_to_thread):
        with patch("services.stock_service.fetch",
                   new_callable=AsyncMock, return_value=last_data):
            result = await fetch_current(mock_stock, is_market_open=False)

    assert result.data[0].close == pytest.approx(187.5)


# ── get_market_status ─────────────────────────────────────────────────────────

def _mock_cal_with_schedule(schedule: pd.DataFrame) -> MagicMock:
    cal = MagicMock()
    cal.schedule.return_value = schedule
    return cal


async def test_get_market_status_returns_true_when_open():
    now = datetime.now(timezone.utc)
    schedule = pd.DataFrame({
        "market_open": [pd.Timestamp(now - timedelta(hours=2))],
        "market_close": [pd.Timestamp(now + timedelta(hours=2))],
    })

    with patch("services.stock_service.mcal.get_calendar",
               return_value=_mock_cal_with_schedule(schedule)):
        result = await get_market_status()

    assert result is True


async def test_get_market_status_returns_false_when_closed():
    now = datetime.now(timezone.utc)
    schedule = pd.DataFrame({
        "market_open": [pd.Timestamp(now - timedelta(hours=8))],
        "market_close": [pd.Timestamp(now - timedelta(hours=2))],
    })

    with patch("services.stock_service.mcal.get_calendar",
               return_value=_mock_cal_with_schedule(schedule)):
        result = await get_market_status()

    assert result is False


async def test_get_market_status_holiday_empty_schedule_returns_false():
    with patch("services.stock_service.mcal.get_calendar",
               return_value=_mock_cal_with_schedule(pd.DataFrame())):
        result = await get_market_status()

    assert result is False


# ── _last_completed_trading_day ───────────────────────────────────────────────

async def test_last_completed_trading_day_returns_most_recent_closed():
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    schedule = pd.DataFrame(
        {
            "market_open": [pd.Timestamp(yesterday.replace(hour=14, minute=30))],
            "market_close": [pd.Timestamp(yesterday.replace(hour=21, minute=0))],
        },
        index=pd.DatetimeIndex([pd.Timestamp(yesterday.date())]),
    )

    with patch("services.stock_service.mcal.get_calendar",
               return_value=_mock_cal_with_schedule(schedule)):
        result = await _last_completed_trading_day()

    assert result is not None
    assert result.date() == yesterday.date()


async def test_last_completed_trading_day_empty_schedule_returns_none():
    with patch("services.stock_service.mcal.get_calendar",
               return_value=_mock_cal_with_schedule(pd.DataFrame())):
        result = await _last_completed_trading_day()

    assert result is None


async def test_last_completed_trading_day_no_closed_sessions_returns_none():
    now = datetime.now(timezone.utc)
    # Only future sessions — none have closed yet
    schedule = pd.DataFrame(
        {
            "market_open": [pd.Timestamp(now + timedelta(hours=1))],
            "market_close": [pd.Timestamp(now + timedelta(hours=7))],
        },
        index=pd.DatetimeIndex([pd.Timestamp(now.date())]),
    )

    with patch("services.stock_service.mcal.get_calendar",
               return_value=_mock_cal_with_schedule(schedule)):
        result = await _last_completed_trading_day()

    assert result is None


# ── fetch_eps_history ─────────────────────────────────────────────────────────

def _make_earnings_df() -> pd.DataFrame:
    """Five quarters of earnings — function should return last four."""
    idx = pd.DatetimeIndex([
        pd.Timestamp("2023-01-01"),
        pd.Timestamp("2023-04-01"),
        pd.Timestamp("2023-07-01"),
        pd.Timestamp("2023-10-01"),
        pd.Timestamp("2024-01-01"),
    ])
    return pd.DataFrame(
        {
            "Reported EPS": [1.0, 1.1, 1.2, 1.3, 1.5],
            "EPS Estimate": [0.9, 1.0, 1.1, 1.2, 1.4],
            "Surprise(%)": [10.0, 10.0, 9.1, 8.3, 7.1],
        },
        index=idx,
    )


async def test_fetch_eps_history_returns_last_four_quarters():
    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"
    mock_stock.get_earnings_dates.return_value = _make_earnings_df()

    result = await fetch_eps_history(mock_stock)

    assert result.ticker == "AAPL"
    assert len(result.earnings_history) == 4
    assert isinstance(result.earnings_history[0], EPSHistoryRow)


async def test_fetch_eps_history_none_earnings_raises():
    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"
    mock_stock.get_earnings_dates.return_value = None

    with pytest.raises(ValueError):
        await fetch_eps_history(mock_stock)


async def test_fetch_eps_history_empty_earnings_raises():
    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"
    mock_stock.get_earnings_dates.return_value = pd.DataFrame()

    with pytest.raises(ValueError):
        await fetch_eps_history(mock_stock)


async def test_fetch_eps_history_cache_hit_skips_yfinance():
    cached = EPSHistoryResponse(ticker="AAPL", earnings_history=[])
    _snapshot_cache.set("AAPL:eps", cached)

    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"

    result = await fetch_eps_history(mock_stock)

    assert result == cached
    mock_stock.get_earnings_dates.assert_not_called()


async def test_fetch_eps_history_filters_out_future_rows():
    """Rows where Reported EPS is NaN (future dates) must be dropped."""
    idx = pd.DatetimeIndex([
        pd.Timestamp("2023-10-01"),
        pd.Timestamp("2024-01-01"),
        pd.Timestamp("2024-04-01"),  # future — NaN reported EPS
    ])
    df = pd.DataFrame(
        {
            "Reported EPS": [1.2, 1.3, float("nan")],
            "EPS Estimate": [1.1, 1.2, 1.4],
            "Surprise(%)": [9.1, 8.3, float("nan")],
        },
        index=idx,
    )

    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"
    mock_stock.get_earnings_dates.return_value = df

    result = await fetch_eps_history(mock_stock)

    assert len(result.earnings_history) == 2  # future row removed


# ── fetch_revenue_history ─────────────────────────────────────────────────────

def _make_income_stmt() -> pd.DataFrame:
    """Quarterly income statement: rows = metrics, columns = dates."""
    dates = pd.DatetimeIndex([
        pd.Timestamp("2023-01-01"),
        pd.Timestamp("2023-04-01"),
        pd.Timestamp("2023-07-01"),
        pd.Timestamp("2023-10-01"),
        pd.Timestamp("2024-01-01"),
    ])
    return pd.DataFrame(
        [[100e9, 110e9, 120e9, 130e9, 140e9]],
        index=["Total Revenue"],
        columns=dates,
    )


async def test_fetch_revenue_history_returns_last_four_quarters():
    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"
    mock_stock.quarterly_income_stmt = _make_income_stmt()

    result = await fetch_revenue_history(mock_stock)

    assert result.ticker == "AAPL"
    assert len(result.revenue_history) == 4
    assert isinstance(result.revenue_history[0], RevenueHistoryRow)


async def test_fetch_revenue_history_none_income_stmt_raises():
    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"
    mock_stock.quarterly_income_stmt = None

    with pytest.raises(ValueError):
        await fetch_revenue_history(mock_stock)


async def test_fetch_revenue_history_cache_hit_skips_yfinance():
    cached = RevenueHistoryResponse(ticker="AAPL", revenue_history=[])
    _snapshot_cache.set("AAPL:revenue", cached)

    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"

    result = await fetch_revenue_history(mock_stock)

    assert result == cached


async def test_fetch_revenue_history_computes_percent_change():
    dates = pd.DatetimeIndex([
        pd.Timestamp("2023-01-01"),
        pd.Timestamp("2023-04-01"),
    ])
    income_stmt = pd.DataFrame(
        [[100e9, 200e9]],
        index=["Total Revenue"],
        columns=dates,
    )

    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"
    mock_stock.quarterly_income_stmt = income_stmt

    result = await fetch_revenue_history(mock_stock)

    assert len(result.revenue_history) == 2
    assert result.revenue_history[1].percent_change == pytest.approx(100.0)


# ── fetch_detailed ────────────────────────────────────────────────────────────

async def test_fetch_detailed_cache_miss_calls_stock_service():
    expected = StockDetailedResponse(ticker="AAPL")

    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"

    with patch("services.stock_service.StockService") as MockSvc:
        MockSvc.return_value.get_stock_details.return_value = expected
        result = await fetch_detailed(mock_stock)

    assert result.ticker == "AAPL"
    assert _snapshot_cache.get("AAPL:detailed") is not None


async def test_fetch_detailed_cache_hit_skips_stock_service():
    cached = StockDetailedResponse(ticker="AAPL")
    _snapshot_cache.set("AAPL:detailed", cached)

    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"

    with patch("services.stock_service.StockService") as MockSvc:
        result = await fetch_detailed(mock_stock)

    MockSvc.assert_not_called()
    assert result == cached


# ── get_industry_map / get_sector_map ─────────────────────────────────────────

async def test_get_industry_map_groups_tickers():
    def _mock_yf(sym: str):
        m = MagicMock()
        m.info = {"industry": "Technology"}
        return m

    with patch("services.market_data_service.get_symbols",
               new_callable=AsyncMock, return_value=["AAPL", "MSFT"]):
        with patch("services.stock_service.yf.Ticker", side_effect=_mock_yf):
            result = await get_industry_map()

    assert "Technology" in result
    assert set(result["Technology"]) == {"AAPL", "MSFT"}


async def test_get_sector_map_groups_tickers():
    def _mock_yf(sym: str):
        m = MagicMock()
        m.info = {"sector": "Technology" if sym == "AAPL" else "Financial Services"}
        return m

    with patch("services.market_data_service.get_symbols",
               new_callable=AsyncMock, return_value=["AAPL", "JPM"]):
        with patch("services.stock_service.yf.Ticker", side_effect=_mock_yf):
            result = await get_sector_map()

    assert "Technology" in result
    assert "Financial Services" in result
    assert result["Technology"] == ["AAPL"]


# ── fetch_stock_dashboard ─────────────────────────────────────────────────────

async def test_fetch_stock_dashboard_returns_combined_response():
    ohlcv = OHLCVResponse(ticker="AAPL", data=[OHLCV(date="2024-01-15", close=184.0)])
    detailed = StockDetailedResponse(ticker="AAPL")
    eps = EPSHistoryResponse(ticker="AAPL", earnings_history=[])
    revenue = RevenueHistoryResponse(ticker="AAPL", revenue_history=[])

    with patch("services.stock_service.yf.Ticker"):
        with patch("services.stock_service.fetch",
                   new_callable=AsyncMock, return_value=ohlcv):
            with patch("services.stock_service.fetch_detailed",
                       new_callable=AsyncMock, return_value=detailed):
                with patch("services.stock_service.fetch_eps_history",
                           new_callable=AsyncMock, return_value=eps):
                    with patch("services.stock_service.fetch_revenue_history",
                               new_callable=AsyncMock, return_value=revenue):
                        result = await fetch_stock_dashboard("AAPL", days=1)

    assert result.ticker == "AAPL"
    assert result.earnings_history is not None
    assert result.revenue_history is not None


async def test_fetch_stock_dashboard_eps_and_revenue_errors_yield_none():
    ohlcv = OHLCVResponse(ticker="AAPL", data=[OHLCV(date="2024-01-15", close=184.0)])
    detailed = StockDetailedResponse(ticker="AAPL")

    with patch("services.stock_service.yf.Ticker"):
        with patch("services.stock_service.fetch",
                   new_callable=AsyncMock, return_value=ohlcv):
            with patch("services.stock_service.fetch_detailed",
                       new_callable=AsyncMock, return_value=detailed):
                with patch("services.stock_service.fetch_eps_history",
                           new_callable=AsyncMock, side_effect=ValueError("no eps")):
                    with patch("services.stock_service.fetch_revenue_history",
                               new_callable=AsyncMock, side_effect=ValueError("no revenue")):
                        result = await fetch_stock_dashboard("AAPL", days=1)

    assert result.ticker == "AAPL"
    assert result.earnings_history is None
    assert result.revenue_history is None


# ── quote caching / coalescing ────────────────────────────────────────────────
# fetch_current is the hottest upstream call in the app (ticker tape on every
# mount, tracker poll, portfolio valuation) and was the one quote path with no
# cache at all, so a couple of page reloads spent a couple of dozen fresh
# yfinance requests. These pin the caching, the coalescing, and the "serve the
# archive rather than fail" behaviour during a backoff.

def _one_minute_bar_stock(ticker="AAPL"):
    today = date.today().isoformat()
    stock = MagicMock()
    stock.ticker = ticker
    stock.history.return_value = _make_ohlcv_df(
        [f"{today} 09:30:00", f"{today} 15:59:00"], closes=[100.0, 120.0]
    )
    return stock


async def test_fetch_current_second_call_is_served_from_cache(fake_to_thread):
    stock = _one_minute_bar_stock()
    with patch("services.stock_service.asyncio.to_thread", side_effect=fake_to_thread):
        first = await fetch_current(stock, is_market_open=True)
        second = await fetch_current(stock, is_market_open=True)

    assert stock.history.call_count == 1
    assert second.data[0].close == first.data[0].close


async def test_fetch_current_concurrent_callers_share_one_upstream_call(fake_to_thread):
    """The ticker tape fires a dozen of these at once on mount; a TTL cache
    alone doesn't help the ones that start before the first has finished."""
    stock = _one_minute_bar_stock()
    with patch("services.stock_service.asyncio.to_thread", side_effect=fake_to_thread):
        results = await asyncio.gather(
            *(fetch_current(stock, is_market_open=True) for _ in range(10))
        )

    assert stock.history.call_count == 1
    assert len({r.data[0].close for r in results}) == 1


async def test_fetch_current_open_and_closed_answers_do_not_share_a_cache_entry(fake_to_thread):
    """The two branches answer different questions — a cached open-session
    aggregate must not be served once the session has closed."""
    stock = _one_minute_bar_stock()
    with patch("services.stock_service.asyncio.to_thread", side_effect=fake_to_thread):
        await fetch_current(stock, is_market_open=True)
        with patch("services.stock_service.fetch", new_callable=AsyncMock,
                   return_value=OHLCVResponse(ticker="AAPL", data=[OHLCV(date="2024-01-15", close=183.5)])):
            closed = await fetch_current(stock, is_market_open=False)

    assert closed.data[0].close == pytest.approx(183.5)


async def test_fetch_current_failure_is_cached_briefly_rather_than_retried(fake_to_thread):
    stock = MagicMock()
    stock.ticker = "AAPL"
    stock.history.return_value = pd.DataFrame()

    with patch("services.stock_service.asyncio.to_thread", side_effect=fake_to_thread):
        for _ in range(3):
            with pytest.raises(ValueError):
                await fetch_current(stock, is_market_open=True)

    assert stock.history.call_count == 1


async def test_fetch_current_serves_the_archive_during_a_yfinance_backoff():
    """A rate limit must not turn into a 404 when the archive already holds
    a perfectly good last close."""
    yf_guard.note(YFRateLimitError())
    stock = MagicMock()
    stock.ticker = "AAPL"

    with patch("services.stock_service.market_data_service.get_ohlcv",
               new_callable=AsyncMock,
               return_value=[{"date": "2024-01-15", "open": 180.0, "high": 184.0,
                              "low": 179.0, "close": 183.5, "volume": 1000}]):
        result = await fetch_current(stock, is_market_open=True)

    stock.history.assert_not_called()
    assert result.data[0].close == pytest.approx(183.5)


async def test_fetch_intraday_second_call_is_served_from_cache():
    today = date.today().isoformat()
    stock = MagicMock()
    stock.ticker = "AAPL"
    stock.history.return_value = _make_ohlcv_df([f"{today} 09:30:00", f"{today} 12:00:00"])

    await fetch_intraday(stock)
    await fetch_intraday(stock)

    assert stock.history.call_count == 1


# ── archive top-up ────────────────────────────────────────────────────────────

async def test_update_attempted_map_stays_bounded():
    """market_data holds every symbol any user ever archived, so this map
    grows with the whole archive if nothing sheds from it."""
    with patch("services.stock_service.market_data_service.set_refresh_marker",
               new_callable=AsyncMock):
        for i in range(stock_service._UPDATE_ATTEMPTED_MAX + 500):
            await stock_service._note_update_attempt(
                f"T{i}", pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
            )

    assert len(_update_attempted) <= stock_service._UPDATE_ATTEMPTED_MAX


async def test_update_attempt_is_persisted_so_a_restart_does_not_repeat_it():
    """The marker used to live only in the dict above, so every restart of
    the free-tier host re-spent one upstream call per tracked symbol
    re-learning that Yahoo hadn't published yet."""
    with patch("services.stock_service.market_data_service.set_refresh_marker",
               new_callable=AsyncMock) as save:
        await stock_service._note_update_attempt("AAPL", pd.Timestamp("2026-03-10"))

    save.assert_awaited_once_with("AAPL", date(2026, 3, 10))


async def test_update_attempt_is_read_back_from_the_database_after_a_restart():
    _update_attempted.clear()  # a fresh process
    with patch("services.stock_service.market_data_service.get_refresh_marker",
               new_callable=AsyncMock, return_value=date(2026, 3, 10)) as read:
        first = await stock_service._last_update_attempt("AAPL")
        second = await stock_service._last_update_attempt("AAPL")

    assert first == pd.Timestamp("2026-03-10")
    assert second == first
    read.assert_awaited_once()  # memoized in-process after the first read


async def test_a_persisted_marker_suppresses_a_redundant_refetch():
    """End to end: a stale archive plus a marker for the same trading day
    means no upstream call."""
    records = [{"date": "2026-03-06", "open": 1.0, "high": 1.0, "low": 1.0,
                "close": 1.0, "volume": 1}]
    with patch("services.stock_service.market_data_service.get_ohlcv",
               new_callable=AsyncMock, return_value=records):
        with patch("services.stock_service._last_completed_trading_day",
                   new_callable=AsyncMock, return_value=pd.Timestamp("2026-03-10")):
            with patch("services.stock_service.market_data_service.get_refresh_marker",
                       new_callable=AsyncMock, return_value=date(2026, 3, 10)):
                with patch("services.price_fetcher.append_price_data",
                           new_callable=AsyncMock) as append:
                    await fetch("AAPL")

    append.assert_not_called()


# ── dashboard degradation ─────────────────────────────────────────────────
# The reported bug: reloading the Tracker during a yfinance rate limit showed
# "Error fetching dashboard data for AMD: Too Many Requests" and rendered
# nothing — even though the chart comes from the archive and needed no
# network at all. Only a missing archive may fail this endpoint now.

def _ohlcv(ticker="AMD"):
    return OHLCVResponse(ticker=ticker, data=[OHLCV(date="2024-01-15", close=457.06)])


async def test_dashboard_survives_a_rate_limited_details_fetch():
    with patch("services.stock_service.fetch", new_callable=AsyncMock, return_value=_ohlcv()):
        with patch("services.stock_service.fetch_detailed",
                   new_callable=AsyncMock, side_effect=YFRateLimitError()):
            with patch("services.stock_service.fetch_eps_history",
                       new_callable=AsyncMock, side_effect=YFRateLimitError()):
                with patch("services.stock_service.fetch_revenue_history",
                           new_callable=AsyncMock, side_effect=YFRateLimitError()):
                    result = await fetch_stock_dashboard("AMD")

    # The chart is what the page is for, and it survived.
    assert result.ticker == "AMD"
    assert len(result.ohlcv) == 1
    assert result.ohlcv[0].close == pytest.approx(457.06)
    # Supplementary panels degrade to empty rather than taking the page down.
    assert result.info is None
    assert result.earnings_history is None
    assert result.revenue_history is None


async def test_dashboard_still_fails_when_there_is_no_price_history():
    """The one failure with no fallback — without price rows there is no
    chart and nothing worth rendering."""
    with patch("services.stock_service.fetch",
               new_callable=AsyncMock, side_effect=ValueError("No data found for ticker: ZZZZ")):
        with pytest.raises(ValueError, match="Error fetching dashboard data"):
            await fetch_stock_dashboard("ZZZZ")


async def test_dashboard_keeps_the_details_it_can_still_get():
    """A partial failure must not discard the parts that worked."""
    details = StockDetailedResponse(ticker="AMD", info={"shortName": "AMD"})
    with patch("services.stock_service.fetch", new_callable=AsyncMock, return_value=_ohlcv()):
        with patch("services.stock_service.fetch_detailed",
                   new_callable=AsyncMock, return_value=details):
            with patch("services.stock_service.fetch_eps_history",
                       new_callable=AsyncMock, side_effect=YFRateLimitError()):
                with patch("services.stock_service.fetch_revenue_history",
                           new_callable=AsyncMock, side_effect=YFRateLimitError()):
                    result = await fetch_stock_dashboard("AMD")

    assert result.info == {"shortName": "AMD"}


# ── stale snapshot tier ───────────────────────────────────────────────────

async def test_a_snapshot_falls_back_to_a_stale_copy_when_the_fetch_fails():
    """Analyst targets from this morning beat a blank panel."""
    good = StockDetailedResponse(ticker="AMD", info={"shortName": "AMD"})
    mock_stock = MagicMock()
    mock_stock.ticker = "AMD"

    with patch("services.stock_service.StockService.get_stock_details", return_value=good):
        first = await fetch_detailed(mock_stock)
    assert first.info == {"shortName": "AMD"}

    # The live entry expires but the week-long stale copy remains.
    _snapshot_cache.invalidate("AMD:detailed")

    with patch("services.stock_service.StockService.get_stock_details",
               side_effect=YFRateLimitError()):
        served = await fetch_detailed(mock_stock)

    assert served.info == {"shortName": "AMD"}


async def test_a_snapshot_with_no_stale_copy_still_raises():
    """Nothing to fall back on means the caller has to hear about it."""
    mock_stock = MagicMock()
    mock_stock.ticker = "NEVERSEEN"

    with patch("services.stock_service.StockService.get_stock_details",
               side_effect=YFRateLimitError()):
        with pytest.raises(YFRateLimitError):
            await fetch_detailed(mock_stock)


async def test_a_fresh_fetch_refreshes_the_stale_copy_too():
    mock_stock = MagicMock()
    mock_stock.ticker = "AMD"

    for name in ("first", "second"):
        _snapshot_cache.invalidate("AMD:detailed")
        with patch("services.stock_service.StockService.get_stock_details",
                   return_value=StockDetailedResponse(ticker="AMD", info={"shortName": name})):
            await fetch_detailed(mock_stock)

    _snapshot_cache.invalidate("AMD:detailed")
    with patch("services.stock_service.StockService.get_stock_details",
               side_effect=YFRateLimitError()):
        served = await fetch_detailed(mock_stock)

    assert served.info == {"shortName": "second"}


# ── add_stock degrades on the details scrape ──────────────────────────────

async def test_add_stock_keeps_the_archive_when_the_details_scrape_fails():
    """Archiving prices is what add_stock is for. It used to scrape `.info`
    afterwards and let a failure there raise, discarding a price archive that
    had already been written — which is why the Performance panel's "Fetch
    now" reported failure on tickers it had just archived."""
    with patch("services.price_fetcher.fetch_historical_price_data",
               new_callable=AsyncMock) as mock_archive:
        with patch("services.stock_service.fetch",
                   new_callable=AsyncMock, return_value=_ohlcv("AAPL")):
            with patch("services.stock_service.fetch_detailed",
                       new_callable=AsyncMock, side_effect=YFRateLimitError()):
                result = await stock_service.add_stock("AAPL")

    mock_archive.assert_awaited_once_with("AAPL")
    assert result.exist is False
    assert result.ohlcv.ticker == "AAPL"
    assert result.details.info is None      # degraded, not fatal


async def test_add_stock_still_fails_when_the_archive_cannot_be_written():
    with patch("services.price_fetcher.fetch_historical_price_data",
               new_callable=AsyncMock, side_effect=ValueError("no data for ticker")):
        with pytest.raises(ValueError, match="Error creating stock data"):
            await stock_service.add_stock("ZZZZ")


# ── the attempt marker records answers, not attempts ──────────────────────

async def test_a_failed_top_up_leaves_the_ticker_retryable():
    """The bug that froze archives for weeks: a rate-limited request marked
    the session as asked, so nothing retried until the next trading day."""
    state, last_date = _archive_state("2024-01-10", "2024-01-15")
    with state, last_date:
        with patch("services.price_fetcher.append_price_data",
                   new_callable=AsyncMock, return_value=False):
            with patch("services.stock_service._note_update_attempt",
                       new_callable=AsyncMock) as mock_note:
                await stock_service.ensure_archive_current("AAPL")

    mock_note.assert_not_called()


async def test_a_successful_top_up_records_the_attempt():
    state, last_date = _archive_state("2024-01-10", "2024-01-15")
    with state, last_date:
        with patch("services.price_fetcher.append_price_data",
                   new_callable=AsyncMock, return_value=True):
            with patch("services.stock_service._note_update_attempt",
                       new_callable=AsyncMock) as mock_note:
                await stock_service.ensure_archive_current("AAPL")

    mock_note.assert_awaited_once()


# ── background archive sweep ──────────────────────────────────────────────
# On-demand top-up only advances tickers somebody opens, so anything not
# viewed drifts indefinitely — which is how a deployment served a chart weeks
# out of date with nothing looking broken. These cover the sweep that makes
# staleness self-correcting.

async def test_the_sweep_visits_every_archived_symbol():
    with patch("services.stock_service.market_data_service.get_symbols",
               new_callable=AsyncMock, return_value=["AAPL", "MSFT", "TCS.NS"]):
        with patch("services.stock_service.ensure_archive_current",
                   new_callable=AsyncMock, return_value=True) as mock_ensure:
            with patch("services.stock_service.config.ARCHIVE_SWEEP_SPACING_SECONDS", 0):
                attempted = await stock_service.refresh_all_archives()

    assert attempted == 3
    assert [c.args[0] for c in mock_ensure.await_args_list] == ["AAPL", "MSFT", "TCS.NS"]


async def test_the_sweep_is_free_when_everything_is_current():
    """ensure_archive_current short-circuits on two indexed reads, so a
    steady-state pass must report no work rather than re-downloading."""
    with patch("services.stock_service.market_data_service.get_symbols",
               new_callable=AsyncMock, return_value=["AAPL", "MSFT"]):
        with patch("services.stock_service.ensure_archive_current",
                   new_callable=AsyncMock, return_value=False):
            with patch("services.stock_service.config.ARCHIVE_SWEEP_SPACING_SECONDS", 0):
                assert await stock_service.refresh_all_archives() == 0


async def test_the_sweep_spaces_its_tickers_out():
    """A burst of history downloads is exactly the shape yfinance rate-limits,
    and nothing is waiting on this job."""
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    with patch("services.stock_service.market_data_service.get_symbols",
               new_callable=AsyncMock, return_value=["A", "B", "C"]):
        with patch("services.stock_service.ensure_archive_current",
                   new_callable=AsyncMock, return_value=False):
            with patch("services.stock_service.config.ARCHIVE_SWEEP_SPACING_SECONDS", 4):
                with patch("services.stock_service.asyncio.sleep", fake_sleep):
                    await stock_service.refresh_all_archives()

    # One gap between each pair, none before the first.
    assert slept == [4, 4]


async def test_one_bad_symbol_does_not_abandon_the_sweep():
    async def flaky(ticker):
        if ticker == "MSFT":
            raise RuntimeError("boom")
        return True

    with patch("services.stock_service.market_data_service.get_symbols",
               new_callable=AsyncMock, return_value=["AAPL", "MSFT", "NVDA"]):
        # ensure_archive_current swallows its own failures; assert the real
        # one does so rather than mocking that guarantee away.
        with patch("services.stock_service._last_completed_trading_day",
                   new_callable=AsyncMock, side_effect=flaky):
            with patch("services.stock_service.config.ARCHIVE_SWEEP_SPACING_SECONDS", 0):
                attempted = await stock_service.refresh_all_archives()

    assert attempted == 0   # nothing advanced, but it visited all three


async def test_the_sweep_survives_an_unreadable_symbol_list():
    with patch("services.stock_service.market_data_service.get_symbols",
               new_callable=AsyncMock, side_effect=RuntimeError("db gone")):
        assert await stock_service.refresh_all_archives() == 0


async def test_the_loop_can_be_switched_off():
    """A deployment that doesn't want the background upstream spend needs a
    way to say so."""
    with patch("services.stock_service.config.ARCHIVE_SWEEP_INTERVAL_MINUTES", 0):
        with patch("services.stock_service.refresh_all_archives",
                   new_callable=AsyncMock) as mock_sweep:
            await stock_service.archive_refresh_loop()   # returns immediately

    mock_sweep.assert_not_called()


async def test_the_loop_waits_before_its_first_pass():
    """The process has just woken; the user's own page load gets the budget
    first."""
    import asyncio as _asyncio

    calls = []

    async def fake_sleep(seconds):
        calls.append(seconds)
        if len(calls) > 1:          # let the first pass run, then stop
            raise _asyncio.CancelledError

    with patch("services.stock_service.config.ARCHIVE_SWEEP_INTERVAL_MINUTES", 60):
        with patch("services.stock_service.config.ARCHIVE_SWEEP_START_DELAY_SECONDS", 45):
            with patch("services.stock_service.refresh_all_archives",
                       new_callable=AsyncMock) as mock_sweep:
                with patch("services.stock_service.asyncio.sleep", fake_sleep):
                    with pytest.raises(_asyncio.CancelledError):
                        await stock_service.archive_refresh_loop()

    assert calls[0] == 45           # startup delay came first
    mock_sweep.assert_awaited_once()
    assert calls[1] == 60 * 60      # then the interval


async def test_a_failing_sweep_does_not_kill_the_loop():
    import asyncio as _asyncio

    calls = []

    async def fake_sleep(seconds):
        calls.append(seconds)
        if len(calls) > 2:
            raise _asyncio.CancelledError

    with patch("services.stock_service.config.ARCHIVE_SWEEP_INTERVAL_MINUTES", 60):
        with patch("services.stock_service.config.ARCHIVE_SWEEP_START_DELAY_SECONDS", 0):
            with patch("services.stock_service.refresh_all_archives",
                       new_callable=AsyncMock, side_effect=RuntimeError("upstream down")) as mock_sweep:
                with patch("services.stock_service.asyncio.sleep", fake_sleep):
                    with pytest.raises(_asyncio.CancelledError):
                        await stock_service.archive_refresh_loop()

    assert mock_sweep.await_count >= 2   # kept going after the first failure
