'''
Schema for Portfolio data in the Market Lens Dashboard.
'''

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, PlainSerializer

# Decimal internally (exact FIFO arithmetic), plain JSON number over the wire
# (Pydantic v2's default Decimal->JSON encoding is a *string*, which would
# silently hand the frontend "1500.00" instead of 1500.00 and break every
# money() call, comparison, and arithmetic op on that side). The conversion
# happens exactly once, at the API boundary, so it doesn't compound like the
# float storage this replaces.
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class StockPurchaseHistory(BaseModel):
    id: int
    sale: bool = False          # False = buy, True = sell
    ticker: str
    date: str
    shares: int
    bought_at: Money = Decimal(0)   # price per share on a buy; FIFO avg cost on sells
    sold_at: Money = Decimal(0)     # price per share on a sell; 0 on buys
    shares_remaining: int = 0  # unsold shares from this buy lot; always 0 for sells


class StockHolding(BaseModel):
    ticker: str
    market: str = "US"                   # "US" | "IN" — exchange the asset trades on
    currency: str = "USD"                # native currency of all monetary fields below
    company_name: str = ""               # display name; empty string if lookup failed
    shares: int                          # shares currently held
    sold_shares: int                     # total shares ever sold
    average_cost: Money                  # weighted avg cost of held shares
    # The next four are None when a live quote couldn't be fetched (yfinance
    # timeout, delisted ticker, etc.) — never a fabricated 0, since that would
    # be indistinguishable from "this stock is genuinely worthless" and would
    # silently render as a -100% loss. The frontend must treat None as
    # "price unavailable", not zero, and exclude it from aggregate totals.
    current_price: Money | None        # live price from yfinance
    stock_value: Money | None          # shares * current_price
    profit_loss: Money | None          # stock_value - total_invested
    profit_loss_percentage: Money | None  # (stock_value - total_invested) / total_invested * 100
    total_earned: Money                # proceeds from all sell transactions
    total_invested: Money              # total amount invested (bought_at * shares for all buy transactions)
    trade_history: list[StockPurchaseHistory]        # all buy + sell transactions, oldest first


class PositionAsOf(BaseModel):
    ticker: str
    date: str                  # the as-of date this position was computed for
    shares: int                # shares held as of this date (FIFO, log-derived)
    sold_shares: int           # cumulative shares sold on or before this date
    average_cost: Money        # weighted avg cost of held shares as of this date
    cost_basis: Money          # sum(shares_remaining * fifo_bought_at) as of this date
    realized_gains: Money      # proceeds - FIFO cost for sells on or before this date


class UndoResult(BaseModel):
    ticker: str    # ticker the undone action affected
    action: str    # "insert" | "delete" — the action that was reversed


class AuditEntrySummary(BaseModel):
    id: int
    ticker: str
    action: str        # "insert" | "delete"
    performed_at: str  # ISO-8601 UTC timestamp
    undone: bool


class PortfolioResponse(BaseModel):
    market: str | None = None   # market filter applied ("US"/"IN"), or None for all
    currency: str = "USD"       # native currency of the aggregate figures below
    # portfolio_value/total_return/return_percentage/net_profit_loss are computed
    # from holdings with a live price only — a holding whose quote is unavailable
    # (StockHolding.current_price is None) contributes to total_invested but is
    # excluded here, rather than being counted as worth $0.
    portfolio_value: Money    # current total value of priced holdings (sum of stock_value)
    realized_gains: Money     # proceeds from all sell transactions (sum of sold_shares * sold_at across all sell transactions)
    total_shares: int           # number of shares across all holdings
    total_invested: Money     # sum of (shares * average_cost) across all holdings
    total_return: Money       # portfolio_value - total_invested
    return_percentage: Money  # (portfolio_value - total_invested) / total_invested * 100
    net_profit_loss: Money    # total_return + realized_gains
    holdings: list[StockHolding] # list of all holdings with detailed info
