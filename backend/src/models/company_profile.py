"""Slow-moving descriptive facts about one ticker: display name, sector,
industry.

Shared cache across all users (never scoped to user_id), same spirit as
models.peers.CompanyPeers and models.company_logo.CompanyLogo. Persisted
rather than only held in an in-memory TTLCache because none of these fields
move on any timescale the app cares about — a company changes sector about
as often as it rebrands — while the process they were cached in restarts
whenever the free-tier host spins down, which is many times a day. Keeping
them in the database is what makes "fetched once" actually mean once.

All three columns come from a single yfinance `.info` call, which is the
most rate-limit-prone thing the app does; storing them together is also
what lets one fetch answer both the name lookup and the sector/industry
lookup. See services.company_profile_service for the refresh logic.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompanyProfile(Base):
    __tablename__ = "company_profile"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    # "" means "asked, and yfinance had nothing" — distinct from a row that
    # doesn't exist yet, which means "never asked".
    name: Mapped[str] = mapped_column(String, default="")
    sector: Mapped[str] = mapped_column(String, default="")
    industry: Mapped[str] = mapped_column(String, default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
