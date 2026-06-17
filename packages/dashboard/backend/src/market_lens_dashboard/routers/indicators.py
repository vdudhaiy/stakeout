'''
Router for technical indicator endpoints.
'''

from fastapi import APIRouter, HTTPException, Query
from typing import List
from ..schemas.indicators import (
    SMAResponse,
    EMAResponse,
    RSIResponse,
    MACDResponse,
    BollingerResponse,
    IndicatorsResponse,
)
from ..services import indicators_service


router = APIRouter(prefix="/indicators", tags=["Indicators"])


# ── SMA ───────────────────────────────────────────────────────────────────────

@router.get("/{ticker}/sma", response_model=SMAResponse)
async def get_sma(ticker: str, days: int = 90, period: int = 20):
    '''
    Return a Simple Moving Average series for the given ticker.

    Steps:
    1. Call indicators_service._load_ticker_df(ticker, days + period) to get
       enough history for warm-up, then compute_sma on the result.
    2. Trim to the last `days` entries.
    3. Wrap in SMAResponse and return.
    4. Catch ValueError from the service layer (ticker not found) and raise
       HTTPException 404 — follow the same pattern as the stocks router.
    '''
    try:
        df = indicators_service._load_ticker_df(ticker, days + period)
        points = indicators_service.compute_sma(df, period)
        return SMAResponse(ticker=ticker, period=period, values=points[-days:])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── EMA ───────────────────────────────────────────────────────────────────────

@router.get("/{ticker}/ema", response_model=EMAResponse)
async def get_ema(ticker: str, days: int = 90, period: int = 20):
    '''
    Return an Exponential Moving Average series for the given ticker.

    Same structure as get_sma — load with warm-up buffer, compute, trim, return.
    '''
    try:
        df = indicators_service._load_ticker_df(ticker, days + period)
        points = indicators_service.compute_ema(df, period)
        return EMAResponse(ticker=ticker, period=period, values=points[-days:])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── RSI ───────────────────────────────────────────────────────────────────────

@router.get("/{ticker}/rsi", response_model=RSIResponse)
async def get_rsi(ticker: str, days: int = 90, period: int = 14):
    '''
    Return an RSI series for the given ticker.

    RSI needs at least `period + 1` rows before producing its first valid value.
    Load days + period + 1 rows as the warm-up buffer so the first visible
    candle already has an RSI value.
    '''
    try:
        df = indicators_service._load_ticker_df(ticker, days + period + 1)
        points = indicators_service.compute_rsi(df, period)
        return RSIResponse(ticker=ticker, period=period, values=points[-days:])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── MACD ──────────────────────────────────────────────────────────────────────

@router.get("/{ticker}/macd", response_model=MACDResponse)
async def get_macd(
    ticker: str,
    days: int = 90,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
):
    '''
    Return MACD line, signal line, and histogram series for the given ticker.

    MACD is the greediest indicator: meaningful values only appear after roughly
    (slow + signal) periods.  Load days + slow + signal rows as the warm-up
    buffer.  After computing, trim to the last `days` entries.
    '''
    try:
        df = indicators_service._load_ticker_df(ticker, days + slow + signal)
        points = indicators_service.compute_macd(df, fast, slow, signal)
        return MACDResponse(ticker=ticker, fast=fast, slow=slow, signal_period=signal, values=points[-days:])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Bollinger Bands ───────────────────────────────────────────────────────────

@router.get("/{ticker}/bollinger", response_model=BollingerResponse)
async def get_bollinger(
    ticker: str,
    days: int = 90,
    period: int = 20,
    std_dev: float = 2.0,
):
    '''
    Return Bollinger Bands (upper, middle, lower) for the given ticker.

    Load days + period rows for warm-up, compute, trim to `days`, return.
    Note: `std_dev` is a float — validate that it is positive and raise a 422
    if not (FastAPI will do this automatically if you add a Query constraint).
    '''
    if std_dev <= 0:
        raise HTTPException(status_code=422, detail="std_dev must be a positive number")

    try:
        df = indicators_service._load_ticker_df(ticker, days + period)
        points = indicators_service.compute_bollinger(df, period, std_dev)
        return BollingerResponse(ticker=ticker, period=period, std_dev=std_dev, values=points[-days:])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Composite ─────────────────────────────────────────────────────────────────

@router.get("/{ticker}", response_model=IndicatorsResponse)
async def get_indicators(
    ticker: str,
    days: int = 90,
    sma_periods: List[int] = Query(default=[10, 20, 50, 100, 200]),
    ema_periods: List[int] = Query(default=[9, 12, 20, 26, 50, 200]),
    rsi_period: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    bb_period: int = 20,
    bb_std: float = 2.0,
):
    '''
    Return all indicators for a ticker in a single request.

    sma_periods / ema_periods accept repeated query params, e.g.:
      ?sma_periods=20&sma_periods=50&sma_periods=200
    Defaults cover the full standard set so the frontend gets everything
    in one round-trip and can toggle display without re-fetching.
    '''
    try:
        return await indicators_service.fetch_indicators(
            ticker=ticker,
            days=days,
            sma_periods=sma_periods,
            ema_periods=ema_periods,
            rsi_period=rsi_period,
            macd_fast=macd_fast,
            macd_slow=macd_slow,
            macd_signal=macd_signal,
            bb_period=bb_period,
            bb_std=bb_std,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
