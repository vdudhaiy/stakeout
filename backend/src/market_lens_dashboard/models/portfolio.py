from decimal import Decimal

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

# 20 total digits / 8 after the decimal point — enough headroom for both
# per-share prices and post-split share counts without ever routing money
# through a binary float (see Holding.average_cost / Transaction.bought_at).
Money = Numeric(20, 8)


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
    average_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))  # weighted avg cost of held shares

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
    bought_at: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))   # price per share on a buy; 0 on sells
    sold_at: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))     # price per share on a sell; 0 on buys
    # Decremented as FIFO sells consume this lot. Starts equal to `shares` for buys; always 0 for sells.
    shares_remaining: Mapped[int] = mapped_column(Integer, default=0)

    holding: Mapped["Holding"] = relationship(back_populates="transactions")


class AuditEntry(Base):
    """Append-only log of transaction/holding mutations, enabling undo.

    `payload` shape depends on `action`:
      - "insert": {"transaction_id": int} — the transaction to remove on undo.
      - "delete": {"holding": {"company_name": str, "market": str} | None,
                   "transactions": [{"sale", "date", "shares", "bought_at",
                                      "sold_at", "shares_remaining"}, ...]}
        `holding` is set only when the holding itself was deleted (either
        directly, or because this removed its last remaining transaction) —
        undo needs its metadata to recreate the row.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    ticker: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String)  # "insert" | "delete"
    payload: Mapped[dict] = mapped_column(JSON)
    performed_at: Mapped[str] = mapped_column(String)  # ISO-8601 UTC timestamp
    undone: Mapped[bool] = mapped_column(Boolean, default=False)


class WatchlistEntry(Base):
    """A ticker the user tracks on the dashboard.

    The market_data table is a *shared cache*; this table is the per-user
    view onto it. Removing an entry never deletes archive data (another
    user may still track the same ticker).
    """

    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="uq_watchlist_user_ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String, default="local", index=True)
    ticker: Mapped[str] = mapped_column(String, index=True)
    market: Mapped[str] = mapped_column(String, default="US", index=True)
    company_name: Mapped[str] = mapped_column(String, default="")
