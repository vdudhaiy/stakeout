'''
Schema for Portfolio data in the Market Lens Dashboard.
'''

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, PlainSerializer

# Decimal internally (exact FIFO arithmetic), plain JSON number over the wire
# (Pydantic v2's default Decimal->JSON encoding is a *string*, which would
# silently hand the frontend "1500.00" instead of 1500.00 and break every
# money() call, comparison, and arithmetic op on that side). The conversion
# happens exactly once, at the API boundary, so it doesn't compound like the
# float storage this replaces.
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class DividendEntry(BaseModel):
    id: int
    ticker: str
    date: str                  # ex-dividend date
    amount_per_share: Money
    shares_held: int            # shares held as of the ex-date when this was recorded
    total_amount: Money         # amount_per_share * shares_held, snapshotted at creation
    source: str                 # "auto" (yfinance) | "manual"


class BulkPurchaseLot(BaseModel):
    shares: int
    bought_at: Decimal
    date: str | None = None    # defaults to today, same as the single-purchase endpoint


class BulkSaleLot(BaseModel):
    shares: int
    sold_at: Decimal
    date: str | None = None    # defaults to today, same as the single-sale endpoint


class ImportPreviewRow(BaseModel):
    """One data row from an uploaded file, parsed and duplicate-checked but
    not yet applied. POST /portfolio/import/preview returns these; the
    frontend resolves any flagged duplicates with the user, then echoes
    valid rows back (as ImportApplyRow, with a per-row include/skip
    decision) to POST /portfolio/import/apply.
    """
    row: int                            # 1-indexed spreadsheet row (header is row 1)
    market: str                         # market cell as given in the file (e.g. "US", "IND")
    ticker: str                         # resolved ticker, exchange suffix applied (e.g. "RELIANCE.NS")
    date: str | None = None             # None if the date itself failed to parse
    action: Literal["buy", "sell", ""]  # "" only when the row failed before the action could be parsed
    shares: int
    price: Money
    valid: bool                         # False if the row failed to parse — see `error`
    error: str | None = None
    duplicate: bool = False             # True if this exactly matches another transaction
    duplicate_reason: str | None = None  # e.g. "Matches an existing transaction..." or "Duplicate of row 4 in this file"
    portfolio: str | None = None        # portfolio name as written in the file, if the column was present
    portfolio_id: int | None = None     # resolved portfolio; None if the name didn't resolve


class ImportBlockingError(BaseModel):
    """A problem that stops the whole import rather than skipping one row.

    Used for portfolio-column errors: a row naming a portfolio that doesn't
    exist can't be silently redirected somewhere else without misfiling the
    user's money, so the import refuses to run and the user fixes the file.
    """
    row: int         # 0 for a file-level problem that isn't tied to one row
    message: str


class ImportPreviewResult(BaseModel):
    total_rows: int                    # data rows found in the file (excludes the header)
    rows: list[ImportPreviewRow]        # one entry per data row, in file order
    # Non-empty means nothing may be imported until the file is corrected —
    # the frontend must not call /import/apply, and apply re-checks anyway.
    blocking_errors: list[ImportBlockingError] = []


class ImportApplyRow(BaseModel):
    """A previously-previewed row (must have been `valid` in the preview),
    echoed back with the user's include/skip decision."""
    row: int
    market: str
    ticker: str
    date: str
    action: Literal["buy", "sell"]
    shares: int
    price: Decimal
    include: bool = True                # False = user chose to skip this one (usually a duplicate)
    # Portfolio name from the file, re-resolved server-side on apply. The
    # client never sends an id: a forged one would write into whatever
    # portfolio it names, so apply resolves names against the caller's own
    # portfolios and rejects the request if any fail.
    portfolio: str | None = None


class ImportRowResult(BaseModel):
    row: int
    market: str
    ticker: str
    date: str
    action: Literal["buy", "sell"]
    shares: int
    price: Money
    status: Literal["imported", "failed", "skipped"]
    error: str | None = None            # reason, when status == "failed"


class PortfolioImportResult(BaseModel):
    total_rows: int             # rows included in the apply request
    imported_rows: int
    failed_rows: int
    skipped_rows: int           # user chose not to include these (see ImportApplyRow.include)
    rows: list[ImportRowResult]  # one entry per row, in file order


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
    portfolio_id: int = 0                # which portfolio holds it; 0 in guest mode
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
    total_dividends: Money = Decimal(0)   # cash dividend income received while holding shares
    trade_history: list[StockPurchaseHistory]        # all buy + sell transactions, oldest first
    dividends: list[DividendEntry] = []               # all dividend payments, oldest first


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


class PortfolioMeta(BaseModel):
    """A portfolio itself, without any position data — powers the tab bar."""

    id: int
    name: str
    market: str          # "US" | "IN"
    created_at: str      # ISO-8601 UTC timestamp


class PortfolioStats(BaseModel):
    """One portfolio's headline figures, in the same units as PortfolioResponse.

    Returned alongside the market-wide totals so the frontend can render both
    the per-portfolio stats row and the combined bar from a single fetch.
    """

    id: int
    name: str
    market: str = "US"
    currency: str = "USD"
    portfolio_value: Money
    realized_gains: Money
    total_shares: int
    total_invested: Money
    total_return: Money
    return_percentage: Money
    total_dividends: Money = Decimal(0)
    net_profit_loss: Money


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
    total_dividends: Money = Decimal(0)  # cash dividend income across all holdings
    net_profit_loss: Money    # total_return + realized_gains + total_dividends
    holdings: list[StockHolding] # list of all holdings with detailed info
    # Per-portfolio breakdown of the same figures, in tab order. The fields
    # above are the combined totals across every entry here, so a client that
    # predates multiple portfolios still reads exactly what it always did.
    # Holdings are not nested — each StockHolding above carries its
    # portfolio_id, so the frontend filters the flat list per tab.
    portfolios: list[PortfolioStats] = []
