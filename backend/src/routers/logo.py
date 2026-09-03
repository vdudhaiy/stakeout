"""Company logo, backed by Finnhub's free /stock/profile2 endpoint (see
services.logo_service for the refresh/caching strategy)."""

from fastapi import APIRouter, HTTPException, Response

from rate_limit import public_read
from services import logo_service

router = APIRouter(prefix="/logo", tags=["Logo"], dependencies=public_read)

_CACHE_HEADER = "public, max-age=86400"  # logos barely ever change; let browsers hold a day


@router.get("/{ticker}")
async def get_logo(ticker: str, response: Response):
    try:
        logo_url = await logo_service.get_logo(ticker)
    except Exception as e:  # noqa: BLE001 — converted to a domain error below
        raise HTTPException(status_code=502, detail=f"Logo lookup unavailable: {e}")
    response.headers["Cache-Control"] = _CACHE_HEADER
    return {"ticker": ticker.upper(), "logo_url": logo_url}
