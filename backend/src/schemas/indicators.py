'''
Pydantic schemas for technical indicator responses.
'''

from pydantic import BaseModel
from typing import List, Optional


# ── SMA ───────────────────────────────────────────────────────────────────────
class SMAPoint(BaseModel):
    date: str
    value: Optional[float]


class SMAResponse(BaseModel):
    ticker: str
    period: int
    values: List[SMAPoint]


# ── EMA ───────────────────────────────────────────────────────────────────────
class EMAPoint(BaseModel):
    date: str
    value: Optional[float]


class EMAResponse(BaseModel):
    ticker: str
    period: int
    values: List[EMAPoint]


# ── RSI ───────────────────────────────────────────────────────────────────────
class RSIPoint(BaseModel):
    date: str
    value: Optional[float]


class RSIResponse(BaseModel):
    ticker: str
    period: int
    values: List[RSIPoint]


# ── MACD ──────────────────────────────────────────────────────────────────────
class MACDPoint(BaseModel):
    date: str
    macd: Optional[float]
    signal: Optional[float]
    histogram: Optional[float]


class MACDResponse(BaseModel):
    ticker: str
    fast: int
    slow: int
    signal_period: int
    values: List[MACDPoint]


# ── Bollinger Bands ───────────────────────────────────────────────────────────
class BollingerPoint(BaseModel):
    date: str
    upper: Optional[float]
    middle: Optional[float]
    lower: Optional[float]


class BollingerResponse(BaseModel):
    ticker: str
    period: int
    std_dev: float
    values: List[BollingerPoint]


# ── Composite ─────────────────────────────────────────────────────────────────
class IndicatorsResponse(BaseModel):
    ticker:    str
    days:      int
    sma:       List[SMAResponse]
    ema:       List[EMAResponse]
    rsi:       Optional[RSIResponse]
    macd:      Optional[MACDResponse]
    bollinger: Optional[BollingerResponse]

