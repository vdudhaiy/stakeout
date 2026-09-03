"""Portfolio performance against a benchmark index.

Authenticated and user-scoped, like /portfolio — the whole payload is
derived from the caller's own transaction history. Read-only: nothing here
mutates a position, and nothing here calls yfinance for the portfolio side
(see services/performance_service.py for why that matters).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_session
from rate_limit import performance_backfill_limiter
from schemas.performance import PerformanceResponse
from services import performance_service, portfolio_admin_service

router = APIRouter(prefix="/performance", tags=["Performance"])

# Revalidate every time. The obvious choice here is a max-age matching
# performance_service's own TTL, and it was — until a trade proved that
# invalidating the server-side entry cannot reach a copy already sitting in
# the browser: the panel kept insisting there was no history for ten minutes
# after the user added positions. The server cache still absorbs the compute,
# so revalidating costs a round trip, not a recomputation.
#
# `private`, never `public`: this is one user's holdings.
_CACHE_HEADER = "private, no-cache"


@router.get("/", response_model=PerformanceResponse)
async def get_performance(
    response: Response,
    market: str | None = None,
    portfolio_id: int | None = None,
    range: str = performance_service.DEFAULT_RANGE,
    refresh: bool = Query(False),
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

    Pass `refresh=true` (the panel's reload control) to drop the cached
    answer and archive any holding that has no price history yet — the one
    thing a plain reload cannot fix, since a ticker with an empty archive has
    nothing to top up. Rate-limited per user: each miss is a multi-year
    download.
    """
    if refresh:
        performance_backfill_limiter.check(user_id)

    name: str | None = None
    if portfolio_id is not None:
        try:
            portfolio = await portfolio_admin_service.resolve(session, user_id, portfolio_id, None)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        portfolio_id, name, market = portfolio.id, portfolio.name, portfolio.market

    if refresh:
        performance_service.invalidate(user_id)
        await performance_service.backfill_missing_archives(
            session, user_id, market, portfolio_id,
        )

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
