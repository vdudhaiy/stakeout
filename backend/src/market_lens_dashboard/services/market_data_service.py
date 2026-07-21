'''
Async CRUD access to the market_data table — the shared daily OHLCV price
archive. Every function opens and closes its own short-lived session: this
table is a cross-cutting, eventually-consistent cache (never scoped to a
single user or request), not part of any request's transactional unit of
work.
'''

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.dialects import postgresql, sqlite

from ..database import SessionLocal, _IS_SQLITE
from ..models.market_data import MarketData

_UPSERT_COLUMNS = ("open", "high", "low", "close", "volume", "source")


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


async def get_symbols() -> list[str]:
    '''All distinct tracked symbols, sorted ascending.'''
    async with SessionLocal() as session:
        result = await session.execute(
            select(MarketData.symbol).distinct().order_by(MarketData.symbol)
        )
        return list(result.scalars().all())


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


async def delete_symbol(symbol: str) -> int:
    '''Delete all rows for `symbol`. Returns the number of rows deleted.'''
    async with SessionLocal() as session:
        result = await session.execute(delete(MarketData).where(MarketData.symbol == symbol))
        await session.commit()
        return result.rowcount
