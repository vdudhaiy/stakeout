"""Tests for services.price_fetcher's archive refresh.

The point of interest is how much history a refresh asks yfinance for.
append_price_data used to re-download everything from ARCHIVE_START_DATE on
every staleness check, so learning one new daily bar cost a multi-year
download — per ticker, for every ticker on a watchlist, the first time
anyone opened the app after a session closed. These pin it to the gap.
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from unittest.mock import patch as _patch  # noqa: F401
from yfinance.exceptions import YFRateLimitError

from services import price_fetcher, yf_guard


def _df(dates: list[str]) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])
    n = len(dates)
    return pd.DataFrame(
        {
            "Open": [100.0] * n, "High": [101.0] * n, "Low": [99.0] * n,
            "Close": [100.5] * n, "Volume": [1000] * n,
        },
        index=idx,
    )


@pytest.fixture
def refresh_harness():
    """Patches out everything append_price_data touches, and hands back the
    _download mock so a test can assert on the date range it was given."""
    def _make(last_archived: date | None, end_date: str = "2026-03-10"):
        return (
            patch("services.price_fetcher.market_data_service.get_last_date",
                  new_callable=AsyncMock, return_value=last_archived),
            patch("services.price_fetcher.market_data_service.upsert_ohlcv",
                  new_callable=AsyncMock),
            patch("services.price_fetcher._archive_end_date", return_value=end_date),
            patch("services.price_fetcher._download",
                  return_value=(_df(["2026-03-09"]), set())),
        )
    return _make


async def test_refresh_asks_only_for_the_gap_since_the_last_archived_bar(refresh_harness):
    last, upsert, end, download = refresh_harness(date(2026, 3, 6))
    with last, upsert, end, download as mock_download:
        await price_fetcher.append_price_data("AAPL")

    _ticker, start_date, end_date = mock_download.call_args.args
    # 2026-03-06 minus the overlap window, not ARCHIVE_START_DATE.
    assert start_date == "2026-02-27"
    assert end_date == "2026-03-10"


async def test_refresh_overlaps_a_few_days_so_restated_bars_are_re_upserted(refresh_harness):
    last, upsert, end, download = refresh_harness(date(2026, 3, 6))
    with last, upsert, end, download as mock_download:
        await price_fetcher.append_price_data("AAPL")

    _ticker, start_date, _end = mock_download.call_args.args
    gap = date(2026, 3, 6) - date.fromisoformat(start_date)
    assert gap.days == price_fetcher._REFRESH_OVERLAP_DAYS


async def test_empty_archive_still_does_a_full_fetch(refresh_harness, monkeypatch):
    monkeypatch.setenv("ARCHIVE_START_DATE", "2023-01-01")
    last, upsert, end, download = refresh_harness(None)
    with last, upsert, end, download as mock_download:
        await price_fetcher.append_price_data("AAPL")

    _ticker, start_date, _end = mock_download.call_args.args
    assert start_date == "2023-01-01"


async def test_refresh_never_starts_before_archive_start_date(refresh_harness, monkeypatch):
    """A ticker archived from its first day has nothing before ARCHIVE_START_DATE
    to overlap into."""
    monkeypatch.setenv("ARCHIVE_START_DATE", "2026-03-05")
    last, upsert, end, download = refresh_harness(date(2026, 3, 6))
    with last, upsert, end, download as mock_download:
        await price_fetcher.append_price_data("AAPL")

    _ticker, start_date, _end = mock_download.call_args.args
    assert start_date == "2026-03-05"


async def test_refresh_is_a_no_op_when_nothing_has_closed_since_the_last_bar(refresh_harness):
    """The caller's staleness check can race the session boundary; asking
    anyway returns an empty frame that looks like a failure."""
    last, upsert, end, download = refresh_harness(date(2026, 3, 20), end_date="2026-03-10")
    with last, upsert, end, download as mock_download:
        await price_fetcher.append_price_data("AAPL")

    mock_download.assert_not_called()


async def test_a_failed_refresh_leaves_the_existing_archive_alone(refresh_harness):
    last, upsert, end, _download = refresh_harness(date(2026, 3, 6))
    with last, upsert as mock_upsert, end, patch(
        "services.price_fetcher._download", side_effect=RuntimeError("yahoo is down")
    ):
        await price_fetcher.append_price_data("AAPL")

    mock_upsert.assert_not_called()


async def test_an_empty_result_is_not_upserted(refresh_harness):
    last, upsert, end, _download = refresh_harness(date(2026, 3, 6))
    with last, upsert as mock_upsert, end, patch(
        "services.price_fetcher._download", return_value=(pd.DataFrame(), set())
    ):
        await price_fetcher.append_price_data("AAPL")

    mock_upsert.assert_not_called()


# ── a failed top-up must stay retryable ───────────────────────────────────
# The marker means "Yahoo has already been asked about this session". Writing
# it for a request that never got an answer is what let a rate-limited
# archive sit weeks behind: one failure a day, and the next page load
# politely declined to retry.

async def test_a_failed_download_is_not_reported_as_answered(refresh_harness):
    last, upsert, end, _download = refresh_harness(date(2026, 3, 6))
    with last, upsert, end, patch(
        "services.price_fetcher._download", side_effect=RuntimeError("Too Many Requests")
    ):
        answered = await price_fetcher.append_price_data("AAPL")

    assert answered is False


async def test_an_empty_response_is_a_definitive_answer(refresh_harness):
    """Yahoo replied and had nothing — usually the bar isn't published yet.
    Worth remembering, unlike a request that failed."""
    last, upsert, end, _download = refresh_harness(date(2026, 3, 6))
    with last, upsert as mock_upsert, end, patch(
        "services.price_fetcher._download", return_value=(pd.DataFrame(), set())
    ):
        answered = await price_fetcher.append_price_data("AAPL")

    assert answered is True
    mock_upsert.assert_not_called()


async def test_a_successful_download_is_answered(refresh_harness):
    last, upsert, end, download = refresh_harness(date(2026, 3, 6))
    with last, upsert, end, download:
        assert await price_fetcher.append_price_data("AAPL") is True


async def test_nothing_to_fetch_counts_as_answered(refresh_harness):
    last, upsert, end, download = refresh_harness(date(2026, 3, 20), end_date="2026-03-10")
    with last, upsert, end, download:
        assert await price_fetcher.append_price_data("AAPL") is True


async def test_the_bulk_download_runs_behind_the_backoff(refresh_harness):
    """The heaviest yfinance call the app makes was the one outside the
    cooldown — it neither tripped it nor respected it."""
    yf_guard.note(YFRateLimitError())
    last, upsert, end, download = refresh_harness(date(2026, 3, 6))
    with last, upsert, end, download as mock_download:
        answered = await price_fetcher.append_price_data("AAPL")

    mock_download.assert_not_called()
    assert answered is False


# ── _archive_end_date follows the ticker's own market ────────────────────────
#
# The staleness check (stock_service.ensure_archive_current) uses the ticker's
# own trading calendar; this used to use NYSE's for everything. In the ~10
# hours between the NSE close and the NYSE close the two disagreed, so an
# Indian ticker was judged stale for today, asked for a window ending
# yesterday, and got the empty frame that counts as a definitive "nothing new"
# — burning its one attempt for the day and leaving NSE history a session
# behind indefinitely.

def test_archive_end_date_uses_the_indian_calendar_for_indian_tickers():
    us_close = pd.Timestamp("2026-03-10")
    in_close = pd.Timestamp("2026-03-11")

    def _by_market(market):
        return in_close if market == "IN" else us_close

    with patch("services.price_fetcher.last_completed_trading_day", side_effect=_by_market):
        assert price_fetcher._archive_end_date("AAPL") == "2026-03-11"
        assert price_fetcher._archive_end_date("RELIANCE.NS") == "2026-03-12"


def test_archive_end_date_falls_back_to_today_without_a_calendar():
    with patch("services.price_fetcher.last_completed_trading_day", return_value=None):
        assert price_fetcher._archive_end_date("AAPL") == \
            pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")


async def test_append_passes_the_tickers_own_market_end_date(refresh_harness):
    """The end date the download actually receives is derived from the ticker,
    not from a hardcoded NYSE calendar."""
    last, upsert, _end, download = refresh_harness(date(2026, 3, 6))
    with last, upsert, download as mock_download, \
         patch("services.price_fetcher.last_completed_trading_day",
               side_effect=lambda m: pd.Timestamp("2026-03-11") if m == "IN"
               else pd.Timestamp("2026-03-10")):
        await price_fetcher.append_price_data("RELIANCE.NS")

    _ticker, _start, end_date = mock_download.call_args.args
    assert end_date == "2026-03-12"
