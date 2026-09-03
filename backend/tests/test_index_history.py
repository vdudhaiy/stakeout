"""Tests for index_service.get_history — the persisted benchmark series.

The whole point of this code path is that a decade of settled index closes
is downloaded once and then read from the database forever, including across
the restarts the free-tier host does many times a day. So what these pin is
the *fetch decision*: whether Yahoo is called at all, and if so from which
date. The DB helpers are mocked at the call site, same as test_peers does
for peers_service.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from yfinance.exceptions import YFRateLimitError

from services import index_service, yf_guard

TODAY = date.today()


@pytest.fixture
def store():
    """Stand-in for the index_history tables.

    `stored` is the (first, last) date range of rows held; `marker` is the
    (covered_from, covered_to) window already requested from Yahoo.
    """
    state = {"stored": (None, None), "marker": None, "rows": {}}

    async def _stored_range(_symbol):
        return state["stored"]

    async def _read_marker(_symbol):
        return state["marker"]

    async def _save_history(_symbol, rows, covered_from, covered_to):
        state["saved"] = (rows, covered_from, covered_to)

    async def _read_history(_symbol, start):
        return {d: c for d, c in state["rows"].items() if d >= start}

    with patch.multiple(
        index_service,
        _stored_range=AsyncMock(side_effect=_stored_range),
        _read_marker=AsyncMock(side_effect=_read_marker),
        _save_history=AsyncMock(side_effect=_save_history),
        _read_history=AsyncMock(side_effect=_read_history),
    ):
        yield state


def _rows(symbol, days):
    return [{"symbol": symbol, "date": d, "close": 100.0} for d in days]


async def test_an_empty_table_fetches_from_the_requested_start(store):
    start = TODAY - timedelta(days=400)
    with patch.object(index_service, "_download_history",
                      return_value=_rows("^GSPC", [start])) as download:
        await index_service.get_history("^GSPC", start)

    _symbol, fetch_from, _end = download.call_args.args
    assert fetch_from == start


async def test_a_covered_symbol_makes_no_outbound_call_at_all(store):
    """The case that matters: everything needed is already stored and the
    marker says it's current, so redrawing the chart costs one query."""
    start = TODAY - timedelta(days=400)
    store["stored"] = (start, TODAY)
    store["marker"] = (start, TODAY)

    with patch.object(index_service, "_download_history") as download:
        await index_service.get_history("^GSPC", start)

    download.assert_not_called()


async def test_a_stale_marker_only_fetches_the_recent_tail(store):
    """Settled history is never re-requested — only the days since the newest
    stored bar, plus a short overlap for restatements."""
    start = TODAY - timedelta(days=3000)
    last = TODAY - timedelta(days=3)
    store["stored"] = (start, last)
    store["marker"] = (start, TODAY - timedelta(days=3))

    with patch.object(index_service, "_download_history",
                      return_value=_rows("^GSPC", [TODAY])) as download:
        await index_service.get_history("^GSPC", start)

    _symbol, fetch_from, _end = download.call_args.args
    assert fetch_from == last - timedelta(days=index_service._REFRESH_OVERLAP_DAYS)


async def test_a_request_for_earlier_history_than_stored_backfills(store):
    """A portfolio older than anything cached has to extend the range
    backwards, not just forwards."""
    stored_first = TODAY - timedelta(days=365)
    store["stored"] = (stored_first, TODAY)
    store["marker"] = (stored_first, TODAY)
    start = TODAY - timedelta(days=1500)

    with patch.object(index_service, "_download_history",
                      return_value=_rows("^GSPC", [start])) as download:
        await index_service.get_history("^GSPC", start)

    _symbol, fetch_from, _end = download.call_args.args
    assert fetch_from == start


async def test_asking_from_a_non_trading_day_does_not_refetch_forever(store):
    """The bug this marker shape exists to prevent.

    A request starting on a Sunday gets a first bar dated Monday. Comparing
    the request against the *oldest stored row* then decides history is still
    missing and re-downloads the entire series — on every single request, for
    the ~2/7 of window starts that land on a weekend. Comparing against the
    window already *asked for* is what makes it fetch once.
    """
    sunday = TODAY - timedelta(days=TODAY.weekday() + 1 + 364)
    monday = sunday + timedelta(days=1)
    store["stored"] = (monday, TODAY)          # Yahoo had nothing for the Sunday
    store["marker"] = (sunday, TODAY)          # but we did ask from it

    with patch.object(index_service, "_download_history") as download:
        await index_service.get_history("^GSPC", sunday)

    download.assert_not_called()


async def test_a_later_shorter_request_does_not_narrow_the_covered_window(store):
    """Switching the chart to a 1y range must not throw away the fact that a
    decade was already fetched, or the next "max" view re-downloads it."""
    old_start = TODAY - timedelta(days=3000)
    store["stored"] = (old_start, TODAY - timedelta(days=3))
    store["marker"] = (old_start, TODAY - timedelta(days=3))
    recent = TODAY - timedelta(days=365)

    with patch.object(index_service, "_download_history",
                      return_value=_rows("^GSPC", [TODAY])):
        await index_service.get_history("^GSPC", recent)

    _rows_saved, covered_from, _covered_to = store["saved"]
    assert covered_from == old_start


async def test_history_requests_are_clamped_to_a_maximum_lookback(store):
    """An unbounded start would ask Yahoo for the entire history of the index."""
    with patch.object(index_service, "_download_history", return_value=[]) as download:
        await index_service.get_history("^GSPC", date(1900, 1, 1))

    _symbol, fetch_from, _end = download.call_args.args
    assert fetch_from >= TODAY - timedelta(days=365 * index_service._MAX_HISTORY_YEARS + 1)


async def test_a_failed_fetch_returns_what_is_stored_rather_than_raising(store):
    start = TODAY - timedelta(days=10)
    store["rows"] = {start: 4000.0}

    with patch.object(index_service, "_download_history", side_effect=RuntimeError("yahoo down")):
        result = await index_service.get_history("^GSPC", start)

    assert result == {start: 4000.0}


async def test_a_failed_fetch_does_not_advance_the_marker(store):
    """Recording a failed call as "covered" would suppress the retry and
    leave the benchmark permanently short of the last few days."""
    start = TODAY - timedelta(days=10)

    with patch.object(index_service, "_download_history", side_effect=RuntimeError("yahoo down")):
        await index_service.get_history("^GSPC", start)

    assert "saved" not in store


async def test_an_empty_response_does_not_advance_the_marker_either(store):
    start = TODAY - timedelta(days=10)

    with patch.object(index_service, "_download_history", return_value=[]):
        await index_service.get_history("^GSPC", start)

    assert "saved" not in store


async def test_a_successful_fetch_is_persisted_with_a_marker(store):
    start = TODAY - timedelta(days=10)

    with patch.object(index_service, "_download_history", return_value=_rows("^GSPC", [start])):
        await index_service.get_history("^GSPC", start)

    rows, covered_from, covered_to = store["saved"]
    assert rows and covered_from == start and covered_to == TODAY


async def test_a_backoff_skips_the_call_and_serves_what_is_stored(store):
    """Benchmark history shares the same yfinance budget as everything else,
    so it has to respect the cooldown."""
    yf_guard.note(YFRateLimitError())
    start = TODAY - timedelta(days=10)
    store["rows"] = {start: 4000.0}

    with patch.object(index_service, "_download_history") as download:
        result = await index_service.get_history("^GSPC", start)

    download.assert_not_called()
    assert result == {start: 4000.0}


async def test_concurrent_callers_share_one_fetch(store):
    """Two browser tabs opening the Performance page at once must not each
    download the same decade."""
    import asyncio

    start = TODAY - timedelta(days=10)
    with patch.object(index_service, "_download_history",
                      return_value=_rows("^GSPC", [start])) as download:
        await asyncio.gather(*(index_service.get_history("^GSPC", start) for _ in range(5)))

    assert download.call_count == 1


def test_every_market_has_a_benchmark():
    from markets import MARKET_META

    for market in MARKET_META:
        assert market in index_service.BENCHMARKS


def test_benchmarks_are_symbols_the_home_page_strip_already_fetches():
    """Reusing MAJOR_INDICES' symbols means the two paths warm the same rows
    rather than each maintaining their own."""
    known = {symbol for symbol, _name, _region in index_service.MAJOR_INDICES}
    for symbol, _name in index_service.BENCHMARKS.values():
        assert symbol in known
