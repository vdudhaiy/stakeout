"""News endpoints backed by GDELT with Yahoo Finance fallback (see news_service)."""

from fastapi import APIRouter, HTTPException, Query, Response

from ..services import news_service

router = APIRouter(prefix="/news", tags=["News"])

_CACHE_HEADER = "public, max-age=300"  # let browsers/CDN hold results for 5 min


@router.get("/market")
async def market_news(
    response: Response,
    region: str = Query("all", pattern="^(all|us|in)$"),
    limit: int = Query(12, ge=1, le=30),
):
    try:
        data = await news_service.get_market_news(region=region, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"News sources unavailable: {e}")
    response.headers["Cache-Control"] = _CACHE_HEADER
    return data


@router.get("/stock/{ticker}")
async def stock_news(
    ticker: str,
    response: Response,
    limit: int = Query(12, ge=1, le=30),
):
    try:
        data = await news_service.get_stock_news(ticker, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"News sources unavailable: {e}")
    response.headers["Cache-Control"] = _CACHE_HEADER
    return data
