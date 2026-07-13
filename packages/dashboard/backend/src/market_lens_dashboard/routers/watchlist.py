"""Per-user watchlist.

The on-disk price archive is a shared cache of OHLCV CSVs; this router is
the per-user view onto it. Adding a ticker fetches archive data if missing;
removing one only removes the user's row, never the shared archive.

In local mode (auth disabled) the first GET seeds the watchlist from
whatever is already in the archive so existing single-user installs keep
their tracked stocks after upgrading.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import LOCAL_USER_ID, get_current_user
from ..database import get_session
from ..markets import market_of, normalize_market
from ..models.portfolio import WatchlistEntry
from ..services import stock_service

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

    # Migration convenience: seed local single-user installs from the archive
    if not entries and user_id == LOCAL_USER_ID:
        try:
            archive = await stock_service.get_all_stocks()
        except Exception:
            archive = {}
        for ticker, name in archive.items():
            session.add(WatchlistEntry(
                user_id=user_id, ticker=ticker, market=market_of(ticker), company_name=name,
            ))
        if archive:
            await session.commit()
            entries = await _entries(session, user_id)

    if market is not None:
        m = normalize_market(market)
        entries = [e for e in entries if e.market == m]
    return _serialize(entries)


@router.post("/{ticker}")
async def add_to_watchlist(
    ticker: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    ticker = ticker.upper().strip()
    existing = await session.execute(
        select(WatchlistEntry).where(
            WatchlistEntry.user_id == user_id, WatchlistEntry.ticker == ticker
        )
    )
    if existing.scalar_one_or_none():
        entries = await _entries(session, user_id)
        return {"exist": True, **_serialize(entries)}

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
    return {"exist": False, **_serialize(entries)}


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
