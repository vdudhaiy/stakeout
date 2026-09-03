"""Finnhub's company-peers list for one ticker, refreshed periodically.

Shared cache across all users (never scoped to user_id), same spirit as
models.market_data.MarketData — GICS-based peer groups change rarely, so
this is persisted rather than only held in an in-memory TTLCache: it
survives restarts and avoids re-spending Finnhub's free-tier quota every
time the process comes back up. See services.peers_service for the
refresh/fallback logic that reads and writes this table.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompanyPeers(Base):
    __tablename__ = "company_peers"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    peers: Mapped[list[str]] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
