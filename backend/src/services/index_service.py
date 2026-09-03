"""Market indices: the home page strip, and benchmark history.

Two jobs, both about the same handful of Yahoo caret symbols (^GSPC, ^NSEI, …):

1. `get_major_indices` — the headline levels and ~3-month sparklines for the
   public home page. Short-lived, in-memory, stale-while-revalidate: these
   are *quotes*, and a ten-minute-old level is fine but a month-old one is
   not.
2. `get_history` — multi-year daily closes, used by performance_service to
   plot a portfolio against its benchmark. These are *settled history*: a
   2019 close will never change, so re-downloading a decade of it to redraw
   the same chart is pure waste. Stored in the index_history table and
   extended only by the gap since the newest stored bar, exactly like
   price_fetcher.append_price_data does for tradeable symbols.

Indices are not tradeable tickers and never appear in watchlists or
portfolios, so both paths stay out of the market_data archive — see
models.index_history for why that separation matters.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite

from cache import index_cache, single_flight
from database import SessionLocal, _IS_SQLITE
from models.index_history import IndexHistory, IndexHistoryRefresh
from . import yf_guard

logger = logging.getLogger(__name__)

# (symbol, display name, region). Order here is the display order.
MAJOR_INDICES: list[tuple[str, str, str]] = [
    ("^GSPC", "S&P 500", "US"),
    ("^DJI", "Dow Jones", "US"),
    ("^IXIC", "NASDAQ Composite", "US"),
    ("^NSEI", "NIFTY 50", "IN"),
    ("^BSESN", "BSE SENSEX", "IN"),
    ("^NSEBANK", "NIFTY Bank", "IN"),
]

# The index each market's portfolio is benchmarked against on the
# Performance page. Both are already in MAJOR_INDICES above — this only
# picks the one headline index per market, since a comparison against three
# at once is noise, not insight.
BENCHMARKS: dict[str, tuple[str, str]] = {
    "US": ("^GSPC", "S&P 500"),
    "IN": ("^NSEI", "NIFTY 50"),
}

_CACHE_KEY = "indices:v1"

# The same payload under a much longer TTL, used only while a refresh is in
# flight. See get_major_indices for why this exists.
_STALE_KEY = "indices:v1:stale"
_STALE_TTL = 24 * 60 * 60

# Background refreshes, kept referenced so the event loop's only reference
# isn't a weak one (asyncio does not keep bare tasks alive).
_refresh_tasks: set[asyncio.Task] = set()


def _fetch_one(symbol: str, name: str, region: str) -> dict | None:
    """Blocking yfinance fetch for a single index. Runs in a worker thread."""
    import yfinance as yf

    try:
        yf_guard.check()
        hist = yf.Ticker(symbol).history(period="3mo", interval="1d")
    except Exception as e:  # noqa: BLE001
        yf_guard.note(e)
        logger.warning("Index fetch failed for %s: %r", symbol, e)
        return None
    if hist is None or hist.empty or "Close" not in hist:
        return None

    closes = hist["Close"].dropna()
    if closes.empty:
        return None

    points = [
        {"date": idx.strftime("%Y-%m-%d"), "close": round(float(val), 2)}
        for idx, val in closes.items()
    ]
    last = points[-1]["close"]
    prev = points[-2]["close"] if len(points) > 1 else None
    change = round(last - prev, 2) if prev is not None else None
    change_pct = round((last - prev) / prev * 100, 2) if prev else None

    return {
        "symbol": symbol,
        "name": name,
        "region": region,
        "last": last,
        "change": change,
        "change_pct": change_pct,
        "points": points,
    }


async def get_major_indices() -> dict:
    """All major indices, fetched concurrently and cached for 10 minutes.

    Serves a stale copy while refreshing in the background once the fresh
    entry expires, so only the very first request of a process's life ever
    waits on Yahoo. Indices whose fetch fails are simply omitted rather than
    failing the whole response — a partially rendered strip beats an error
    banner.
    """
    cached = index_cache.get(_CACHE_KEY)
    if cached is not None:
        return cached

    stale = index_cache.get(_STALE_KEY)
    if stale is not None:
        # Stale-while-revalidate. This is the public home page's first paint,
        # and six sequential-ish yfinance history calls is a visible stall to
        # wear every ten minutes for numbers that barely moved. Hand back the
        # previous levels now and refresh behind the request; the next caller
        # gets the fresh ones. single_flight means the refresh runs once no
        # matter how many callers arrive during it.
        task = asyncio.ensure_future(single_flight(_CACHE_KEY, _refresh))
        _refresh_tasks.add(task)
        task.add_done_callback(_refresh_tasks.discard)
        return stale

    # Nothing to serve at all (cold process, first ever request): the caller
    # has to wait, but only one of them does.
    return await single_flight(_CACHE_KEY, _refresh)


async def _refresh() -> dict:
    """Fetch every index concurrently and repopulate both cache entries."""
    results = await asyncio.gather(
        *(asyncio.to_thread(_fetch_one, sym, name, region) for sym, name, region in MAJOR_INDICES)
    )
    indices = [r for r in results if r is not None]

    result = {"indices": indices}
    # Don't cache a fully empty result — a transient Yahoo outage would
    # otherwise blank the home page strip, and leaving the stale entry in
    # place means the next caller still gets real numbers.
    if indices:
        index_cache.set(_CACHE_KEY, result)
        index_cache.set(_STALE_KEY, result, _STALE_TTL)
    return result


# ── Benchmark history (persisted) ─────────────────────────────────────────

# How far back a benchmark is ever fetched. Portfolios older than this get a
# comparison starting from here rather than an unbounded download.
_MAX_HISTORY_YEARS = 15

# Days of overlap re-requested on an incremental top-up, so a bar Yahoo
# restates after first publishing it still gets corrected. The upsert
# absorbs the duplicates.
_REFRESH_OVERLAP_DAYS = 5


def _upsert_history_statement(rows: list[dict]):
    insert = sqlite.insert if _IS_SQLITE else postgresql.insert
    stmt = insert(IndexHistory).values(rows)
    return stmt.on_conflict_do_update(
        index_elements=["symbol", "date"], set_={"close": stmt.excluded.close}
    )


def _upsert_marker_statement(symbol: str, covered_from: date, covered_to: date):
    insert = sqlite.insert if _IS_SQLITE else postgresql.insert
    stmt = insert(IndexHistoryRefresh).values(
        symbol=symbol, covered_from=covered_from, covered_to=covered_to
    )
    return stmt.on_conflict_do_update(
        index_elements=["symbol"],
        set_={"covered_from": stmt.excluded.covered_from, "covered_to": stmt.excluded.covered_to},
    )


def _download_history(symbol: str, start: date, end: date) -> list[dict]:
    """Blocking yfinance fetch of daily closes. Runs in a worker thread."""
    import yfinance as yf

    hist = yf.Ticker(symbol).history(
        start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(), interval="1d"
    )
    if hist is None or hist.empty or "Close" not in hist:
        return []
    closes = hist["Close"].dropna()
    return [
        {"symbol": symbol, "date": idx.date(), "close": round(float(val), 4)}
        for idx, val in closes.items()
    ]


async def _stored_range(symbol: str) -> tuple[date | None, date | None]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(IndexHistory.date).where(IndexHistory.symbol == symbol).order_by(IndexHistory.date)
        )
        dates = list(result.scalars().all())
    return (dates[0], dates[-1]) if dates else (None, None)


async def _read_marker(symbol: str) -> tuple[date, date] | None:
    """(covered_from, covered_to) already fetched for `symbol`, or None."""
    async with SessionLocal() as session:
        row = await session.get(IndexHistoryRefresh, symbol)
        return (row.covered_from, row.covered_to) if row else None


async def _save_history(symbol: str, rows: list[dict], covered_from: date, covered_to: date) -> None:
    async with SessionLocal() as session:
        if rows:
            await session.execute(_upsert_history_statement(rows))
        await session.execute(_upsert_marker_statement(symbol, covered_from, covered_to))
        await session.commit()


async def _read_history(symbol: str, start: date) -> dict[date, float]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(IndexHistory.date, IndexHistory.close)
            .where(IndexHistory.symbol == symbol, IndexHistory.date >= start)
            .order_by(IndexHistory.date)
        )
        return {d: c for d, c in result.all()}


async def get_history(symbol: str, start: date) -> dict[date, float]:
    """Daily closes for `symbol` from `start` to the latest available day.

    Reads the stored history and asks Yahoo only for what's missing: the gap
    forward since the newest stored bar, and/or a backfill if the caller
    needs to start earlier than anything stored. A portfolio opened years ago
    therefore pays one download once, and every later page load — including
    after a restart, which is the case an in-memory cache never survives —
    is a database read.

    Never raises: if Yahoo can't be reached the stored rows are returned as
    they are, and the caller decides whether that's enough to draw.
    """
    start = max(start, date.today() - timedelta(days=365 * _MAX_HISTORY_YEARS))
    return await single_flight(f"index-history:{symbol}:{start}", lambda: _load_history(symbol, start))


async def _load_history(symbol: str, start: date) -> dict[date, float]:
    today = date.today()
    _stored_first, stored_last = await _stored_range(symbol)
    marker = await _read_marker(symbol)

    fetch_from: date | None = None
    if stored_last is None or marker is None:
        fetch_from = start                       # nothing stored, or nothing recorded
    elif start < marker[0]:
        fetch_from = start                       # caller needs earlier history than we've asked for
    elif marker[1] < today:
        # Settled history is already stored; only the tail can be new.
        fetch_from = stored_last - timedelta(days=_REFRESH_OVERLAP_DAYS)

    if fetch_from is not None:
        try:
            with yf_guard.guard():
                rows = await asyncio.to_thread(_download_history, symbol, fetch_from, today)
        except Exception as e:  # noqa: BLE001 — degrades to whatever is already stored
            logger.warning("Index history fetch failed for %s: %r", symbol, e)
            rows = []
        if rows:
            # Only advanced on a fetch that actually returned something, so a
            # failed call retries next time instead of being recorded as
            # covered. `covered_from` keeps the earliest window ever asked
            # for — never narrowing it on a later, shorter request.
            covered_from = min(fetch_from, marker[0]) if marker else fetch_from
            await _save_history(symbol, rows, covered_from, today)

    return await _read_history(symbol, start)
