'''Main file for the dashboard backend. Sets up the FastAPI application and includes the necessary routers.'''

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .routers import fx, health, indicators, news, portfolio, stocks, watchlist
from .services.portfolio_service import repair_all_fifo


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await repair_all_fifo()
    yield


app = FastAPI(
    title=os.getenv("APP_NAME", "Stakeout API"),
    openapi_url="/openapi",
    docs_url="/docs",
    lifespan=lifespan,
)

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
    )

app.include_router(stocks.router)
app.include_router(health.router)
app.include_router(portfolio.router)
app.include_router(indicators.router)
app.include_router(watchlist.router)
app.include_router(news.router)
app.include_router(fx.router)


@app.get("/version", include_in_schema=False)
async def get_version():
    return {"version": "0.1.0"}


def _frontend_dist() -> Path | None:
    # PyInstaller bundles the built frontend under frontend-dist/ inside _MEIPASS.
    if hasattr(sys, "_MEIPASS"):
        p = Path(sys._MEIPASS) / "frontend-dist"
        if p.is_dir():
            return p
    return None


_dist = _frontend_dist()
if _dist is not None:
    _assets = _dist / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets), name="static-assets")

    @app.get("/", include_in_schema=False)
    async def serve_root():
        return FileResponse(_dist / "index.html")
