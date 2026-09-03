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

from services import price_fetcher


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
