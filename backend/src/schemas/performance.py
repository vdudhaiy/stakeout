"""Schemas for the Performance page.

Monetary *totals* are Money (Decimal), like every other portfolio schema.
The chart series are plain floats on purpose: each point is derived from the
archive's Float closes, so there is no exactness left to preserve, and a
thousand Decimals serialized per request would cost real bandwidth to
express precision the inputs never had.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from .portfolio import Money


class PerformancePoint(BaseModel):
    """One trading day on the performance chart."""

    date: str
    value: float             # portfolio market value at that day's close
    invested: float          # cumulative net contributions up to that day
    benchmark_value: float   # the same contributions, put into the index instead
    portfolio_index: float   # growth of 100, time-weighted (deposits removed)
    benchmark_index: float   # growth of 100 for the benchmark, same base date


class ReturnSummary(BaseModel):
    """The headline return measures for one series (portfolio or benchmark).

    `money_weighted` and `time_weighted` answer different questions and can
    differ a lot — see services/returns_math.py. None means "not answerable
    from this data", never zero.
    """

    money_weighted: float | None   # XIRR — includes the effect of when money went in
    time_weighted: float | None    # cumulative TWR over the window
    annualized: float | None       # TWR expressed per year (CAGR); None under a month
    max_drawdown: float            # largest peak-to-trough fall, as a negative fraction
    volatility: float | None       # annualized stdev of daily returns; None under 20 days


class PerformanceResponse(BaseModel):
    market: str                    # "US" | "IN"
    currency: str                  # native currency of every monetary field here
    portfolio_id: int | None       # None when the response covers every portfolio in the market
    portfolio_name: str | None

    benchmark_symbol: str          # Yahoo caret symbol, e.g. "^GSPC"
    benchmark_name: str            # e.g. "S&P 500"

    range: str                     # "1y" | "3y" | "5y" | "max"
    start_date: str | None
    end_date: str | None           # last completed session in the archive, not today
    days: int                      # calendar days spanned

    points: list[PerformancePoint]
    portfolio: ReturnSummary
    benchmark: ReturnSummary
    beta: float | None             # portfolio sensitivity to the benchmark's daily moves

    current_value: Money = Decimal(0)
    net_invested: Money = Decimal(0)       # contributions minus withdrawals
    total_dividends: Money = Decimal(0)
    realized_gains: Money = Decimal(0)
    unrealized_gains: Money = Decimal(0)

    # What the same money, on the same days, would be worth in the index —
    # the only apples-to-apples comparison when contributions are irregular.
    benchmark_final_value: Money = Decimal(0)
    value_added: Money = Decimal(0)        # current_value - benchmark_final_value

    # Holdings left out because the shared archive has no price history for
    # them. Surfaced rather than silently dropped: the totals on this page
    # would otherwise disagree with the Portfolio page for no visible reason.
    excluded_tickers: list[str] = []

    # True when there isn't enough history to say anything (no transactions,
    # or no overlapping archive data). The frontend shows an empty state
    # instead of a chart of one point.
    insufficient_data: bool = False
