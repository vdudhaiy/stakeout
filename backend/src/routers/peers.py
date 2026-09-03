"""Company peers, backed by Finnhub's free /stock/peers endpoint (see
services.peers_service for the refresh/caching strategy)."""

from fastapi import APIRouter, HTTPException, Response

from rate_limit import public_read
from services import peers_service

router = APIRouter(prefix="/peers", tags=["Peers"], dependencies=public_read)

_CACHE_HEADER = "public, max-age=1800"  # peer groups barely move; let browsers hold 30 min


@router.get("/{ticker}")
async def get_peers(ticker: str, response: Response):
    try:
        peers = await peers_service.get_peers(ticker)
    except Exception as e:  # noqa: BLE001 — converted to a domain error below
        raise HTTPException(status_code=502, detail=f"Peers lookup unavailable: {e}")
    response.headers["Cache-Control"] = _CACHE_HEADER
    return {"ticker": ticker.upper(), "peers": peers}
