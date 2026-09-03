"""Portfolio performance against a benchmark index.

Authenticated and user-scoped, like /portfolio — the whole payload is
derived from the caller's own transaction history. Read-only: nothing here
mutates a position, and nothing here calls yfinance for the portfolio side
(see services/performance_service.py for why that matters).
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_session
from schemas.performance import PerformanceResponse
from services import performance_service, portfolio_admin_service

router = APIRouter(prefix="/performance", tags=["Performance"])

# Matches performance_service's own TTL. The payload only changes when a
# session closes or the user trades, and a trade invalidates the server-side
# entry anyway — so a reload inside the window costs nothing at all.
_CACHE_HEADER = "private, max-age=600"


@router.get("/", response_model=PerformanceResponse)
async def get_performance(
    response: Response,
    market: str | None = None,
    portfolio_id: int | None = None,
    range: str = performance_service.DEFAULT_RANGE,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """Value, benchmark comparison and return statistics for `market`.

    Without `portfolio_id`, covers every portfolio in the market combined —
    the same scoping rule as GET /portfolio. `range` is one of 1y, 3y, 5y,
    max; anything else falls back to max rather than erroring, since it only
    narrows a view.

    `private` on the cache header, not `public`: this is one user's holdings,
    and a shared cache must never hand it to anyone else.
    """
    name: str | None = None
    if portfolio_id is not None:
        try:
            portfolio = await portfolio_admin_service.resolve(session, user_id, portfolio_id, None)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        portfolio_id, name, market = portfolio.id, portfolio.name, portfolio.market

    data = await performance_service.get_performance(
        session, user_id, market, portfolio_id=portfolio_id, portfolio_name=name, range_key=range,
    )
    response.headers["Cache-Control"] = _CACHE_HEADER
    return data


@router.get("/ranges")
async def list_ranges(response: Response):
    """The window presets the chart offers, so the frontend doesn't hardcode
    a list that can drift from the one the server actually accepts."""
    response.headers["Cache-Control"] = "public, max-age=86400"
    return {"ranges": list(performance_service.RANGES)}
