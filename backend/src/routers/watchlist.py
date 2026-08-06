"""Per-user watchlist.

The market_data table is a shared cache of OHLCV rows; this router is
the per-user view onto it. Adding a ticker fetches archive data if missing;
removing one only removes the user's row, never the shared archive.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_session
from markets import INDIAN_SUFFIXES, apply_exchange, market_of, normalize_market
from models.portfolio import WatchlistEntry
from services import stock_service

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])

DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA", "RELIANCE.NS", "TCS.NS"]


async def _entries(session: AsyncSession, user_id: str) -> list[WatchlistEntry]:
    result = await session.execute(
        select(WatchlistEntry).where(WatchlistEntry.user_id == user_id).order_by(WatchlistEntry.ticker)
    )
    return list(result.scalars().all())


def _serialize(entries: list[WatchlistEntry]) -> dict:
    return {
        "stocks": {
            e.ticker: {"name": e.company_name or e.ticker, "market": e.market}
            for e in entries
        }
    }


@router.get("/")
async def get_watchlist(
    market: str | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    entries = await _entries(session, user_id)

    if market is not None:
        m = normalize_market(market)
        entries = [e for e in entries if e.market == m]
    return _serialize(entries)


async def _resolve_ticker(session: AsyncSession, user_id: str, ticker: str, exchange: str | None) -> str:
    """Resolves a bare ticker + exchange choice to the canonical suffixed
    ticker, mirroring portfolio_service._resolve_ticker: "US" and an
    already-suffixed ticker pass through unchanged; a bare Indian ticker
    reuses whichever suffix the user already has on their watchlist, else
    probes NSE then BSE (via stock_service.add_stock, same existence check
    the plain-add path below uses) and keeps whichever exists.
    """
    ticker = ticker.upper().strip()
    if (exchange or "").upper() != "IN" or ticker.endswith((".NS", ".BO")):
        return apply_exchange(ticker, exchange)

    for suffix in INDIAN_SUFFIXES:
        existing = await session.execute(
            select(WatchlistEntry).where(
                WatchlistEntry.user_id == user_id, WatchlistEntry.ticker == f"{ticker}{suffix}"
            )
        )
        if existing.scalar_one_or_none():
            return f"{ticker}{suffix}"

    last_error: Exception | None = None
    for suffix in INDIAN_SUFFIXES:
        candidate = f"{ticker}{suffix}"
        try:
            archive = await stock_service.get_all_stocks()
            if candidate not in archive:
                await stock_service.add_stock(candidate)
            return candidate
        except ValueError as e:
            last_error = e

    raise ValueError(
        f"Ticker '{ticker}' could not be found on NSE or BSE. Please check the symbol and try again."
    ) from last_error


@router.post("/{ticker}")
async def add_to_watchlist(
    ticker: str,
    exchange: str | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    try:
        ticker = await _resolve_ticker(session, user_id, ticker, exchange)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    existing = await session.execute(
        select(WatchlistEntry).where(
            WatchlistEntry.user_id == user_id, WatchlistEntry.ticker == ticker
        )
    )
    if existing.scalar_one_or_none():
        entries = await _entries(session, user_id)
        return {"exist": True, "ticker": ticker, **_serialize(entries)}

    # Ensure the shared archive has data (validates the ticker as a side effect)
    try:
        archive = await stock_service.get_all_stocks()
        if ticker not in archive:
            await stock_service.add_stock(ticker)
            archive = await stock_service.get_all_stocks()
        name = archive.get(ticker, ticker)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session.add(WatchlistEntry(
        user_id=user_id, ticker=ticker, market=market_of(ticker), company_name=name,
    ))
    await session.commit()
    entries = await _entries(session, user_id)
    return {"exist": False, "ticker": ticker, **_serialize(entries)}


@router.delete("/{ticker}")
async def remove_from_watchlist(
    ticker: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    ticker = ticker.upper().strip()
    result = await session.execute(
        select(WatchlistEntry).where(
            WatchlistEntry.user_id == user_id, WatchlistEntry.ticker == ticker
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail=f"{ticker} is not on your watchlist")
    await session.delete(entry)
    await session.commit()
    entries = await _entries(session, user_id)
    return _serialize(entries)
