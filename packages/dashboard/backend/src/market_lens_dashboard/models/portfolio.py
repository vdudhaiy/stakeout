from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Holding(Base):
    """One row per ticker the user has ever bought. Deleted only via explicit DELETE endpoint."""

    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String, unique=True, index=True)
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
