"""Batched quote snapshots, backed by Finnhub's free /quote endpoint (see
services.quote_service). No {ticker} path param on this router on purpose —
mirrors /stocks/classification's comma-separated batch style, since a
single-ticker route here would hit the same route-ordering trap as
routers/stocks.py if a second path were ever added later."""

from fastapi import APIRouter, HTTPException, Query

from rate_limit import public_read
from services import quote_service

router = APIRouter(prefix="/quote", tags=["Quote"], dependencies=public_read)


@router.get("/")
async def get_quotes(tickers: str = Query(...)):
    symbols = [t for t in (s.strip() for s in tickers.split(",")) if t]
    if not symbols:
        raise HTTPException(status_code=400, detail="No tickers provided")
    if len(symbols) > 50:
        raise HTTPException(status_code=400, detail="At most 50 tickers per request")
    data = await quote_service.get_quotes(symbols)
    return {"quotes": data}
