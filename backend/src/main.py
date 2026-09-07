'''Main file for the dashboard backend. Sets up the FastAPI application and includes the necessary routers.'''

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import freshness
from auth import local_auth_enabled
from database import init_db
from routers import (
    account, ai, fx, health, indicators, logo, news, peers, performance, portfolio, portfolios,
    quote, stocks, watchlist,
)
from services.portfolio_service import repair_all_fifo, repair_stock_metadata
from services.stock_service import archive_refresh_loop
from services.yf_guard import restore as restore_yf_backoff


logger = logging.getLogger(__name__)

# Background tasks are held here because asyncio keeps only a weak
# reference to a bare task, and a garbage-collected one stops silently.
_background: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await repair_all_fifo()

    # Before any background job gets a chance to call Yahoo. A cooldown that
    # was still running when the last process died has to be back in force
    # first, or the restart itself becomes the retry that renews the throttle.
    await restore_yf_backoff()

    # Backfills any holding that lost its company name or its price-archive
    # coverage to a transient yfinance failure when it was first bought (see
    # repair_stock_metadata). Runs in the background, not awaited, since it
    # does real network I/O per affected ticker and shouldn't delay startup.
    _background.add(asyncio.create_task(repair_stock_metadata()))

    # Keeps the shared price archive moving without waiting for someone to
    # open each ticker. Without it the archive only advances for symbols
    # somebody happens to view, and everything else silently falls weeks
    # behind while still rendering as though it were current.
    _background.add(asyncio.create_task(archive_refresh_loop()))

    yield

    for task in _background:
        task.cancel()


app = FastAPI(
    title=os.getenv("APP_NAME", "Stakeout API"),
    openapi_url="/openapi",
    docs_url="/docs",
    lifespan=lifespan,
)

# Header names the frontend reads to render its "as of" badges. Listed once
# here because CORS has to be told to expose them: a cloud deployment serves
# the API from a different origin than the app, and a response header the
# browser can't read is a header that doesn't exist.
FRESHNESS_HEADERS = ["X-Data-Source", "X-Data-Fetched-At", "X-Data-Through", "X-Data-Age-Seconds"]


# CORS: the frontend is served from a different origin in cloud deployments
# (Vercel) than the API (Render). Comma-separated list, e.g.
#   CORS_ORIGINS=https://stakeout.vercel.app,http://localhost:5173
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=FRESHNESS_HEADERS,
    )

@app.middleware("http")
async def _stamp_freshness(request: Request, call_next):
    """Report where this response's data actually came from.

    Every layer that answers — a TTL cache hit, an archive read, a stale
    fallback — records a stamp; this reports the least fresh of them (see
    freshness.py). Wrapped so a provenance failure can never cost a response
    the app would otherwise have served successfully.
    """
    freshness.begin()
    response = await call_next(request)
    try:
        current = freshness.snapshot()
        if current is None:
            return response
        response.headers["X-Data-Source"] = current.source
        if current.fetched_at is not None:
            response.headers["X-Data-Fetched-At"] = current.fetched_at.isoformat()
            age = (datetime.now(timezone.utc) - current.fetched_at).total_seconds()
            response.headers["X-Data-Age-Seconds"] = str(int(max(0.0, age)))
        if current.data_through is not None:
            response.headers["X-Data-Through"] = current.data_through.isoformat()
    except Exception as e:  # noqa: BLE001 — never fail a good response over a header
        logger.debug("Could not attach freshness headers: %r", e)
    return response


app.include_router(stocks.router)
app.include_router(health.router)
app.include_router(portfolio.router)
app.include_router(portfolios.router)
app.include_router(performance.router)
app.include_router(indicators.router)
app.include_router(watchlist.router)
app.include_router(news.router)
app.include_router(peers.router)
app.include_router(logo.router)
app.include_router(quote.router)
app.include_router(fx.router)
app.include_router(ai.router)
app.include_router(account.router)

# Local email/password auth only exists when there's no Supabase project to
# verify tokens against — a real deployment never sees these routes at all.
if local_auth_enabled():
    from routers import local_auth
    app.include_router(local_auth.router)
