"""Finnhub's company logo URL for one ticker, refreshed rarely.

Shared cache across all users, same spirit as models.peers.CompanyPeers — a
company's logo changes on the order of years (a rebrand), not days, so
services.logo_service's refresh interval is far longer than peers'.
`logo_url` is stored as "" (not NULL) for a ticker Finnhub confirmed has no
logo, distinguishing "we checked, there isn't one" from "never checked yet"
(no row at all) so that negative result stays cached too.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompanyLogo(Base):
    __tablename__ = "company_logos"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    logo_url: Mapped[str] = mapped_column(String)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
