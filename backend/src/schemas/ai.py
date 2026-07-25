'''
Pydantic schemas for the AI Explanation Layer (per-stock insight + chat).
'''

from typing import Literal, Optional

from pydantic import BaseModel


# ── Stock insight ────────────────────────────────────────────────────────────

class RSIRecoveryStats(BaseModel):
    occurrences: int
    horizon_days: int
    recovered_pct: float
    avg_return_pct: float


class StockFacts(BaseModel):
    ticker: str
    as_of: str
    history_days: int
    close: float
    change_pct: Optional[float]
    rsi: Optional[float]
    rsi_zone: Optional[str]
    bollinger_position: Optional[str]
    macd_signal: Optional[str]
    sma_trend: Optional[str]
    volume_vs_avg_pct: Optional[float]
    rsi_recovery: Optional[RSIRecoveryStats]
    headlines: list[str]
    confidence: Literal["low", "medium", "high"]


class StockExplanationResponse(BaseModel):
    ticker: str
    summary: str
    facts: StockFacts
    confidence: Literal["low", "medium", "high"]
    generated_at: str
    model: str


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatContext(BaseModel):
    kind: Literal["stock", "portfolio", "general"]
    ticker: Optional[str] = None
    # Frontend-supplied precomputed numbers — used as-is for "portfolio"
    # context, since guest portfolios never touch the backend database.
    facts: Optional[dict] = None


class ChatRequest(BaseModel):
    message: str
    context: Optional[ChatContext] = None
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
