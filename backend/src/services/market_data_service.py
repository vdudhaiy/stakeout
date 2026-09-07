'''
Async CRUD access to the market_data table — the shared daily OHLCV price
archive. Every function opens and closes its own short-lived session: this
table is a cross-cutting, eventually-consistent cache (never scoped to a
single user or request), not part of any request's transactional unit of
work.
'''

import logging
from datetime import date, datetime, timezone

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.dialects import postgresql, sqlite

from database import SessionLocal, _IS_SQLITE
from models.market_data import ArchiveRefresh, MarketData

logger = logging.getLogger(__name__)

_UPSERT_COLUMNS = ("open", "high", "low", "close", "volume", "source", "fetched_at")


def _upsert_statement(rows: list[dict]):
    insert = sqlite.insert if _IS_SQLITE else postgresql.insert
    stmt = insert(MarketData).values(rows)
    return stmt.on_conflict_do_update(
        index_elements=["symbol", "date"],
        set_={col: getattr(stmt.excluded, col) for col in _UPSERT_COLUMNS},
    )


async def upsert_ohlcv(
    symbol: str,
    df: pd.DataFrame,
    source: str = "yfinance",
    synthetic_dates: set | None = None,
) -> None:
    '''
    Upsert a DataFrame of OHLCV rows (DatetimeIndex, Open/High/Low/Close/Volume
    columns) for `symbol`. Rows whose date falls in `synthetic_dates` are
    tagged with a distinct source, since they were reconstructed from hourly
    data rather than reported directly by Yahoo Finance.
    '''
    synthetic_dates = synthetic_dates or set()
    # One timestamp for the whole batch: these rows all came out of a single
    # upstream response, so stamping them individually would imply a precision
    # the fetch never had.
    fetched_at = datetime.now(timezone.utc)
    rows = [
        {
            "symbol": symbol,
            "date": pd.Timestamp(ts).date(),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
            "source": "yfinance_synthetic" if pd.Timestamp(ts).date() in synthetic_dates else source,
            "fetched_at": fetched_at,
        }
        for ts, row in df.iterrows()
    ]
    if not rows:
        return
    async with SessionLocal() as session:
        await session.execute(_upsert_statement(rows))
        await session.commit()


async def has_data(symbol: str) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(
            select(MarketData.symbol).where(MarketData.symbol == symbol).limit(1)
        )
        return result.scalar_one_or_none() is not None


async def get_last_date(symbol: str) -> date | None:
    '''
    The most recent archived date for `symbol`, or None if it has no rows.
    Lets callers fetch only the gap since that date instead of re-downloading
    a multi-year history to learn one new bar (see price_fetcher).
    '''
    async with SessionLocal() as session:
        result = await session.execute(
            select(MarketData.date)
            .where(MarketData.symbol == symbol)
            .order_by(MarketData.date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def get_symbols() -> list[str]:
    '''All distinct tracked symbols, sorted ascending.'''
    async with SessionLocal() as session:
        result = await session.execute(
            select(MarketData.symbol).distinct().order_by(MarketData.symbol)
        )
        return list(result.scalars().all())


async def get_provenance(symbol: str) -> tuple[datetime | None, date | None]:
    '''
    (when `symbol`'s newest bar was pulled, what trading day it covers).

    Two different questions, and the UI needs both: an archive read a minute
    ago whose newest bar is from last Tuesday is fresh and four days behind,
    and reporting only one of those numbers hides whichever one is the
    problem. Either element is None when the archive has nothing to say —
    rows predating the fetched_at column report an unknown fetch time rather
    than a fabricated one.
    '''
    async with SessionLocal() as session:
        result = await session.execute(
            select(MarketData.fetched_at, MarketData.date)
            .where(MarketData.symbol == symbol)
            .order_by(MarketData.date.desc())
            .limit(1)
        )
        row = result.first()
    if row is None:
        return None, None
    fetched_at, through = row
    if fetched_at is not None and fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return fetched_at, through


async def get_ohlcv(symbol: str, days: int = 0) -> list[dict]:
    '''
    Rows for `symbol` ascending by date. `days <= 0` returns full history;
    otherwise the most recent `days` rows (via an indexed range query on the
    composite primary key, not a full-table scan).
    '''
    async with SessionLocal() as session:
        query = select(MarketData).where(MarketData.symbol == symbol).order_by(MarketData.date.desc())
        if days > 0:
            query = query.limit(days)
        result = await session.execute(query)
        rows = list(result.scalars().all())
    rows.reverse()
    return [
        {
            "date": r.date.isoformat(),
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
        }
        for r in rows
    ]


async def get_closes(symbols: list[str], start: date | None = None) -> dict[str, dict[date, float]]:
    '''
    Closing prices for several symbols at once, as {symbol: {date: close}}.

    One query for the whole set rather than a round trip per symbol: the
    portfolio value series needs every held ticker's full history on the same
    date axis, and a portfolio of twenty names would otherwise mean twenty
    sequential queries to draw one chart. Symbols with no rows are simply
    absent from the result.
    '''
    if not symbols:
        return {}
    query = select(MarketData.symbol, MarketData.date, MarketData.close).where(
        MarketData.symbol.in_(symbols)
    )
    if start is not None:
        query = query.where(MarketData.date >= start)
    async with SessionLocal() as session:
        result = await session.execute(query.order_by(MarketData.symbol, MarketData.date))
        rows = result.all()

    closes: dict[str, dict[date, float]] = {}
    for symbol, day, close in rows:
        closes.setdefault(symbol, {})[day] = close
    return closes


async def get_first_date(symbol: str) -> date | None:
    '''The oldest archived date for `symbol`, or None if it has no rows.'''
    async with SessionLocal() as session:
        result = await session.execute(
            select(MarketData.date)
            .where(MarketData.symbol == symbol)
            .order_by(MarketData.date)
            .limit(1)
        )
        return result.scalar_one_or_none()


async def get_refresh_marker(symbol: str) -> date | None:
    '''
    The last completed trading day `symbol` was already asked about, or None.

    See models.market_data.ArchiveRefresh: this is what stops every request
    in the gap between a session's close and Yahoo publishing its bar from
    re-asking for data that isn't there yet.

    Fail-soft, both here and in set_refresh_marker: the marker is an
    optimization, not a fact anything depends on. Losing it costs one extra
    upstream call; raising from it would fail a price request that could
    have been answered.
    '''
    try:
        async with SessionLocal() as session:
            row = await session.get(ArchiveRefresh, symbol)
            return row.attempted_for if row is not None else None
    except Exception as e:  # noqa: BLE001 — degrades to "no marker recorded"
        logger.warning("Refresh marker read failed for %s: %r", symbol, e)
        return None


async def set_refresh_marker(symbol: str, attempted_for: date) -> None:
    '''Record that `symbol` was asked about for `attempted_for`.'''
    insert = sqlite.insert if _IS_SQLITE else postgresql.insert
    stmt = insert(ArchiveRefresh).values(symbol=symbol, attempted_for=attempted_for)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol"], set_={"attempted_for": stmt.excluded.attempted_for}
    )
    try:
        async with SessionLocal() as session:
            await session.execute(stmt)
            await session.commit()
    except Exception as e:  # noqa: BLE001 — the in-process memo still holds
        logger.warning("Refresh marker write failed for %s: %r", symbol, e)


async def delete_symbol(symbol: str) -> int:
    '''Delete all rows for `symbol`. Returns the number of rows deleted.'''
    async with SessionLocal() as session:
        result = await session.execute(delete(MarketData).where(MarketData.symbol == symbol))
        # The refresh marker describes an archive that no longer exists; left
        # behind, it would suppress the first re-fetch after a re-add.
        await session.execute(delete(ArchiveRefresh).where(ArchiveRefresh.symbol == symbol))
        await session.commit()
        return result.rowcount
