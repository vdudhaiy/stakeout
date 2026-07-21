from datetime import date as date_

from sqlalchemy import BigInteger, Float, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Date

from ..database import Base


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
