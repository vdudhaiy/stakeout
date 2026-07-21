"""Lower-level tests for stock_service functions.

Mocks market_data_service (the market_data table access layer), yfinance
(yf.Ticker), and pandas_market_calendars (mcal) at the call site instead of
at the router boundary so that the transformation / parsing logic inside
each function is actually executed and covered.
"""

import pytest
import pandas as pd
from datetime import date, datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from market_lens_dashboard.services.stock_service import (
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
from market_lens_dashboard.schemas.stocks import (
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
    yield
    _snapshot_cache._store.clear()
    _update_attempted.clear()


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

    with patch("market_lens_dashboard.services.stock_service.market_data_service.get_symbols",
               new_callable=AsyncMock, return_value=["AAPL"]):
        with patch("market_lens_dashboard.services.stock_service.yf.Ticker", return_value=mock_ticker):
            result = await get_all_stocks()

    assert "AAPL" in result
    assert result["AAPL"] == "Apple Inc."


async def test_get_all_stocks_cache_hit_skips_query():
    _snapshot_cache.set("all_stocks", {"AAPL": "Apple"})

    with patch("market_lens_dashboard.services.stock_service.market_data_service.get_symbols",
               new_callable=AsyncMock) as mock_symbols:
        result = await get_all_stocks()

    mock_symbols.assert_not_called()
    assert result == {"AAPL": "Apple"}


async def test_get_all_stocks_no_symbols_returns_empty_dict():
    with patch("market_lens_dashboard.services.stock_service.market_data_service.get_symbols",
               new_callable=AsyncMock, return_value=[]):
        result = await get_all_stocks()
    assert result == {}


async def test_get_all_stocks_falls_back_to_short_name():
    mock_ticker = MagicMock()
    mock_ticker.ticker = "AAPL"
    mock_ticker.info = {"displayName": None, "shortName": "Apple"}

    with patch("market_lens_dashboard.services.stock_service.market_data_service.get_symbols",
               new_callable=AsyncMock, return_value=["AAPL"]):
        with patch("market_lens_dashboard.services.stock_service.yf.Ticker", return_value=mock_ticker):
            result = await get_all_stocks()

    assert result["AAPL"] == "Apple"


# ── delete_stock ──────────────────────────────────────────────────────────────

async def test_delete_stock_removes_matching_rows():
    with patch("market_lens_dashboard.services.stock_service.market_data_service.delete_symbol",
               new_callable=AsyncMock, return_value=1) as mock_delete:
        result = await delete_stock("AAPL")

    assert "deleted successfully" in result["message"]
    mock_delete.assert_called_once_with("AAPL")


async def test_delete_stock_no_matching_rows_raises():
    with patch("market_lens_dashboard.services.stock_service.market_data_service.delete_symbol",
               new_callable=AsyncMock, return_value=0):
        with pytest.raises(ValueError, match="No data found"):
            await delete_stock("AAPL")


async def test_delete_stock_invalidates_cache():
    _snapshot_cache.set("AAPL:detailed", "cached_value")
    _snapshot_cache.set("all_stocks", {"AAPL": "Apple"})

    with patch("market_lens_dashboard.services.stock_service.market_data_service.delete_symbol",
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

    with patch("market_lens_dashboard.services.stock_service.market_data_service.get_ohlcv",
               new_callable=AsyncMock, return_value=records):
        with patch(
            "market_lens_dashboard.services.stock_service._last_completed_trading_day",
            new_callable=AsyncMock,
            return_value=pd.Timestamp("2024-01-15"),
        ):
            result = await fetch("AAPL", days=30)

    assert result.ticker == "AAPL"
    assert len(result.data) == 1
    assert result.data[0].close == pytest.approx(184.0)


async def test_fetch_no_data_raises():
    with patch("market_lens_dashboard.services.stock_service.market_data_service.get_ohlcv",
               new_callable=AsyncMock, return_value=[]):
        with pytest.raises(ValueError, match="No data found"):
            await fetch("AAPL")


async def test_fetch_stale_data_triggers_append():
    stale_records = [{
        "date": "2024-01-10", "open": 183.0, "high": 185.0,
        "low": 182.0, "close": 184.0, "volume": 5_000_000,
    }]
    fresh_records = [{
        "date": "2024-01-15", "open": 186.0, "high": 188.0,
        "low": 185.0, "close": 187.0, "volume": 4_000_000,
    }]

    # last_completed is ahead of last_date → need_update=True
    with patch("market_lens_dashboard.services.stock_service.market_data_service.get_ohlcv",
               new_callable=AsyncMock, side_effect=[stale_records, fresh_records]):
        with patch(
            "market_lens_dashboard.services.stock_service._last_completed_trading_day",
            new_callable=AsyncMock,
            return_value=pd.Timestamp("2024-01-15"),
        ):
            with patch("market_lens_dashboard.services.price_fetcher.append_price_data",
                       new_callable=AsyncMock) as mock_append:
                result = await fetch("AAPL", days=1)

    mock_append.assert_called_once_with("AAPL")
    assert result.ticker == "AAPL"
    assert result.data[0].close == pytest.approx(187.0)


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

    with patch("market_lens_dashboard.services.stock_service.asyncio.to_thread",
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

    with patch("market_lens_dashboard.services.stock_service.asyncio.to_thread",
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

    with patch("market_lens_dashboard.services.stock_service.asyncio.to_thread",
               side_effect=fake_to_thread):
        with patch("market_lens_dashboard.services.stock_service.fetch",
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

    with patch("market_lens_dashboard.services.stock_service.asyncio.to_thread",
               side_effect=fake_to_thread):
        with patch("market_lens_dashboard.services.stock_service.fetch",
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

    with patch("market_lens_dashboard.services.stock_service.mcal.get_calendar",
               return_value=_mock_cal_with_schedule(schedule)):
        result = await get_market_status()

    assert result is True


async def test_get_market_status_returns_false_when_closed():
    now = datetime.now(timezone.utc)
    schedule = pd.DataFrame({
        "market_open": [pd.Timestamp(now - timedelta(hours=8))],
        "market_close": [pd.Timestamp(now - timedelta(hours=2))],
    })

    with patch("market_lens_dashboard.services.stock_service.mcal.get_calendar",
               return_value=_mock_cal_with_schedule(schedule)):
        result = await get_market_status()

    assert result is False


async def test_get_market_status_holiday_empty_schedule_returns_false():
    with patch("market_lens_dashboard.services.stock_service.mcal.get_calendar",
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

    with patch("market_lens_dashboard.services.stock_service.mcal.get_calendar",
               return_value=_mock_cal_with_schedule(schedule)):
        result = await _last_completed_trading_day()

    assert result is not None
    assert result.date() == yesterday.date()


async def test_last_completed_trading_day_empty_schedule_returns_none():
    with patch("market_lens_dashboard.services.stock_service.mcal.get_calendar",
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

    with patch("market_lens_dashboard.services.stock_service.mcal.get_calendar",
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

    with patch("market_lens_dashboard.services.stock_service.StockService") as MockSvc:
        MockSvc.return_value.get_stock_details.return_value = expected
        result = await fetch_detailed(mock_stock)

    assert result.ticker == "AAPL"
    assert _snapshot_cache.get("AAPL:detailed") is not None


async def test_fetch_detailed_cache_hit_skips_stock_service():
    cached = StockDetailedResponse(ticker="AAPL")
    _snapshot_cache.set("AAPL:detailed", cached)

    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"

    with patch("market_lens_dashboard.services.stock_service.StockService") as MockSvc:
        result = await fetch_detailed(mock_stock)

    MockSvc.assert_not_called()
    assert result == cached


# ── get_industry_map / get_sector_map ─────────────────────────────────────────

async def test_get_industry_map_groups_tickers():
    def _mock_yf(sym: str):
        m = MagicMock()
        m.info = {"industry": "Technology"}
        return m

    with patch("market_lens_dashboard.services.stock_service.get_all_stocks",
               new_callable=AsyncMock, return_value={"AAPL": "Apple", "MSFT": "Microsoft"}):
        with patch("market_lens_dashboard.services.stock_service.yf.Ticker", side_effect=_mock_yf):
            result = await get_industry_map()

    assert "Technology" in result
    assert set(result["Technology"]) == {"AAPL", "MSFT"}


async def test_get_sector_map_groups_tickers():
    def _mock_yf(sym: str):
        m = MagicMock()
        m.info = {"sector": "Technology" if sym == "AAPL" else "Financial Services"}
        return m

    with patch("market_lens_dashboard.services.stock_service.get_all_stocks",
               new_callable=AsyncMock, return_value={"AAPL": "Apple", "JPM": "JPMorgan"}):
        with patch("market_lens_dashboard.services.stock_service.yf.Ticker", side_effect=_mock_yf):
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

    with patch("market_lens_dashboard.services.stock_service.yf.Ticker"):
        with patch("market_lens_dashboard.services.stock_service.fetch",
                   new_callable=AsyncMock, return_value=ohlcv):
            with patch("market_lens_dashboard.services.stock_service.fetch_detailed",
                       new_callable=AsyncMock, return_value=detailed):
                with patch("market_lens_dashboard.services.stock_service.fetch_eps_history",
                           new_callable=AsyncMock, return_value=eps):
                    with patch("market_lens_dashboard.services.stock_service.fetch_revenue_history",
                               new_callable=AsyncMock, return_value=revenue):
                        result = await fetch_stock_dashboard("AAPL", days=1)

    assert result.ticker == "AAPL"
    assert result.earnings_history is not None
    assert result.revenue_history is not None


async def test_fetch_stock_dashboard_eps_and_revenue_errors_yield_none():
    ohlcv = OHLCVResponse(ticker="AAPL", data=[OHLCV(date="2024-01-15", close=184.0)])
    detailed = StockDetailedResponse(ticker="AAPL")

    with patch("market_lens_dashboard.services.stock_service.yf.Ticker"):
        with patch("market_lens_dashboard.services.stock_service.fetch",
                   new_callable=AsyncMock, return_value=ohlcv):
            with patch("market_lens_dashboard.services.stock_service.fetch_detailed",
                       new_callable=AsyncMock, return_value=detailed):
                with patch("market_lens_dashboard.services.stock_service.fetch_eps_history",
                           new_callable=AsyncMock, side_effect=ValueError("no eps")):
                    with patch("market_lens_dashboard.services.stock_service.fetch_revenue_history",
                               new_callable=AsyncMock, side_effect=ValueError("no revenue")):
                        result = await fetch_stock_dashboard("AAPL", days=1)

    assert result.ticker == "AAPL"
    assert result.earnings_history is None
    assert result.revenue_history is None
