from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Holding(Base):
    """One row per (user, ticker) the user has ever bought.

    ``market`` is derived from the ticker suffix at creation time (``.NS`` /
    ``.BO`` -> IN, otherwise US) and is what the portfolio market switcher
    filters on. Monetary columns are stored in the asset's *native* currency
    (USD for US stocks, INR for Indian stocks); display conversion happens
    client-side against the /fx rate.
    """

    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="uq_holdings_user_ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String, default="local", index=True)
    ticker: Mapped[str] = mapped_column(String, index=True)
    market: Mapped[str] = mapped_column(String, default="US", index=True)  # "US" | "IN"
    company_name: Mapped[str] = mapped_column(String, default="")    # display name fetched once on first buy
    shares: Mapped[int] = mapped_column(Integer, default=0)          # shares currently held
    sold_shares: Mapped[int] = mapped_column(Integer, default=0)     # total shares ever sold
    average_cost: Mapped[float] = mapped_column(Float, default=0.0)  # weighted avg cost of held shares

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="holding",
        cascade="all, delete-orphan",
        order_by="Transaction.date",
    )


class Transaction(Base):
    """One row per buy or sell event. Buys carry shares_remaining for FIFO cost-basis tracking."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    holding_id: Mapped[int] = mapped_column(ForeignKey("holdings.id"))
    sale: Mapped[bool] = mapped_column(Boolean, default=False)  # False = buy, True = sell
    date: Mapped[str] = mapped_column(String)                   # ISO-8601 date string, e.g. "2024-03-15"
    shares: Mapped[int] = mapped_column(Integer)
    bought_at: Mapped[float] = mapped_column(Float, default=0.0)   # price per share on a buy; 0 on sells
    sold_at: Mapped[float] = mapped_column(Float, default=0.0)     # price per share on a sell; 0 on buys
    # Decremented as FIFO sells consume this lot. Starts equal to `shares` for buys; always 0 for sells.
    shares_remaining: Mapped[int] = mapped_column(Integer, default=0)

    holding: Mapped["Holding"] = relationship(back_populates="transactions")


class WatchlistEntry(Base):
    """A ticker the user tracks on the dashboard.

    The price archive on disk is a *shared cache*; this table is the
    per-user view onto it. Removing an entry never deletes archive data
    (another user may still track the same ticker).
    """

    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="uq_watchlist_user_ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String, default="local", index=True)
    ticker: Mapped[str] = mapped_column(String, index=True)
    market: Mapped[str] = mapped_column(String, default="US", index=True)
    company_name: Mapped[str] = mapped_column(String, default="")
