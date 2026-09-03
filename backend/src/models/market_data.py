from datetime import date as date_

from sqlalchemy import BigInteger, Float, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Date

from database import Base


class MarketData(Base):
    """One row per (symbol, trading day) of daily OHLCV data.

    This is a shared cache across all users — never scoped to user_id — kept
    up to date by services.price_fetcher via upsert. `source` distinguishes
    genuine Yahoo Finance daily bars from ones reconstructed from hourly data
    (see price_fetcher._patch_nan_daily_bars).
    """

    __tablename__ = "market_data"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[date_] = mapped_column(Date, primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String, default="yfinance")


class ArchiveRefresh(Base):
    """The last completed trading day we already tried to fetch for a symbol.

    Yahoo publishes a session's daily bar some time after the close, so
    between the close and the publish every request for that symbol finds a
    stale archive and asks again. This records the attempt so the next
    caller doesn't repeat it, and clears itself naturally: the marker is the
    trading day it was made for, so a newer completed session makes it
    obsolete without anything having to expire it.

    Persisted rather than held in a dict because the free-tier host restarts
    many times a day, and an in-memory marker means one wasted upstream call
    per tracked symbol on every one of those restarts.
    """

    __tablename__ = "archive_refresh"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    # The trading day the attempt was made *for*, not when it ran.
    attempted_for: Mapped[date_] = mapped_column(Date)
