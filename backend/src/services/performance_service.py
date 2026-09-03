"""Portfolio performance against a benchmark.

Answers the question the Portfolio page can't: not "what am I holding and
what is it worth", but "was any of this worth doing". Three things make that
answer honest, and all three are the reason this is its own service rather
than another field on PortfolioResponse:

1. **The comparison is against the same money, not the same period.**
   Reporting "you're up 14%, the S&P is up 11%" is close to meaningless when
   the contributions were irregular — most of the money may have arrived
   last month. So the benchmark series here is a simulation: every cash flow
   the user actually made, on the day they made it, bought units of the
   index instead. `value_added` is the difference in what those two paths
   are worth today.

2. **Both return measures are reported.** Money-weighted (XIRR) includes the
   effect of timing and is what the investor actually earned; time-weighted
   strips deposits out and is the only thing comparable to an index. They
   diverge exactly when timing mattered, which is worth seeing.

3. **Nothing here calls yfinance for the portfolio side.** The whole value
   series is built from the market_data archive the app already maintains,
   and the benchmark comes from the persisted index_history table. Drawing a
   ten-year chart costs a couple of database reads, not a decade of
   downloads — which is the only way a page like this can exist inside the
   free-tier budget.

The series ends at the last completed session in the archive, not at a live
quote. That keeps every point on the chart derived from the same source, so
the line can't kink at the right-hand edge because its last point came from
somewhere else; the Portfolio page remains the place for a live figure.
"""

from __future__ import annotations

import logging
import asyncio
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cache import performance_cache, single_flight
from markets import currency_of, normalize_market
from models.portfolio import Dividend, Holding, Transaction
from schemas.performance import PerformancePoint, PerformanceResponse, ReturnSummary
from . import index_service, market_data_service, returns_math, stock_service

logger = logging.getLogger(__name__)

# Window presets. "max" means "since the first transaction".
RANGES: dict[str, int | None] = {
    "1y": 365,
    "3y": 365 * 3,
    "5y": 365 * 5,
    "max": None,
}

DEFAULT_RANGE = "max"

# Recomputing is cheap (no network) but not free — a portfolio of twenty
# names over ten years is a few thousand rows to walk. The page polls
# nothing, so this only needs to cover a reload and a range toggle.
_CACHE_TTL = 10 * 60


def _cache_key(user_id: str, market: str, portfolio_id: int | None, range_key: str) -> str:
    return f"perf:{user_id}:{market}:{portfolio_id or 'all'}:{range_key}"


def invalidate(user_id: str) -> None:
    """Drop every cached response for `user_id`.

    Called after any mutation to their positions — a chart that still shows
    yesterday's holdings after a buy reads as a bug, not as a cache.
    """
    performance_cache.invalidate_prefix(f"perf:{user_id}:")


# ── Data loading ──────────────────────────────────────────────────────────

async def _load_positions(
    session: AsyncSession, user_id: str, market: str, portfolio_id: int | None,
) -> list[tuple[Holding, list[Transaction], list[Dividend]]]:
    query = select(Holding).where(Holding.user_id == user_id, Holding.market == market)
    if portfolio_id is not None:
        query = query.where(Holding.portfolio_id == portfolio_id)
    holdings = list((await session.execute(query)).scalars().all())

    positions = []
    for holding in holdings:
        transactions = list((await session.execute(
            select(Transaction).where(Transaction.holding_id == holding.id).order_by(Transaction.date)
        )).scalars().all())
        dividends = list((await session.execute(
            select(Dividend).where(Dividend.holding_id == holding.id).order_by(Dividend.date)
        )).scalars().all())
        if transactions:
            positions.append((holding, transactions, dividends))
    return positions


def _parse(day: str) -> date:
    return date.fromisoformat(day[:10])


# ── Series construction ───────────────────────────────────────────────────

def _forward_fill(closes: dict[date, float], axis: list[date]) -> list[float | None]:
    """Project a symbol's sparse closes onto the shared date axis.

    A holding whose exchange was shut that day, or whose bar Yahoo simply
    never published, must keep its last known price rather than dropping to
    zero — an unpriced day is not a worthless day, and letting it read as one
    would put a spike in the chart for every missing bar.
    """
    known = sorted(closes)
    result: list[float | None] = []
    last: float | None = None
    i = 0
    for day in axis:
        while i < len(known) and known[i] <= day:
            last = closes[known[i]]
            i += 1
        result.append(last)
    return result


def _shares_on(transactions: list[Transaction], axis: list[date]) -> list[int]:
    """Share count held at the close of each day on the axis.

    Plain cumulative buys minus sells — no FIFO replay. Which lot a sale
    consumed changes the cost basis, and nothing about how many shares are
    left, which is all a valuation needs.
    """
    events = sorted(
        ((_parse(t.date), -t.shares if t.sale else t.shares) for t in transactions),
        key=lambda e: e[0],
    )
    result: list[int] = []
    running = 0
    i = 0
    for day in axis:
        while i < len(events) and events[i][0] <= day:
            running += events[i][1]
            i += 1
        result.append(running)
    return result


def _cash_flows(
    positions: list[tuple[Holding, list[Transaction], list[Dividend]]],
) -> dict[date, Decimal]:
    """Net external money into the portfolio per day, positive for a buy.

    Dividends are deliberately *not* here. They are money the portfolio
    produced, not money the investor put in, so counting them as a
    contribution would make income look like a deposit and depress every
    return figure on the page. They enter the XIRR flow list separately, as
    the inflows to the investor that they are.
    """
    flows: dict[date, Decimal] = {}
    for _holding, transactions, _dividends in positions:
        for t in transactions:
            day = _parse(t.date)
            amount = (-t.sold_at * t.shares) if t.sale else (t.bought_at * t.shares)
            flows[day] = flows.get(day, Decimal(0)) + amount
    return flows


def _build_axis(
    closes_by_symbol: dict[str, dict[date, float]], start: date, end: date,
) -> list[date]:
    """Sorted trading days that any held symbol has a price for, within range."""
    days: set[date] = set()
    for closes in closes_by_symbol.values():
        days.update(d for d in closes if start <= d <= end)
    return sorted(days)


def _summarize(
    returns: list[float], flows: list[tuple[date, float]], span_days: int,
) -> ReturnSummary:
    index = returns_math.growth_index(returns)
    drawdown, _peak, _trough = returns_math.max_drawdown(index)
    twr = returns_math.total_return(returns)
    # XIRR is an annual rate by construction, so it needs the same floor as
    # CAGR. Without it a two-day-old portfolio up 0.6% reported "+8796.1% per
    # year" — arithmetically correct, and the least trustworthy thing on the
    # page. The cumulative time-weighted return is still shown, because that
    # one is honest over any span.
    money_weighted = (
        returns_math.xirr(flows) if span_days >= returns_math.MIN_ANNUALIZATION_DAYS else None
    )
    return ReturnSummary(
        money_weighted=money_weighted,
        time_weighted=twr,
        annualized=returns_math.annualized(twr, span_days),
        max_drawdown=drawdown,
        volatility=returns_math.volatility(returns),
    )


async def _archive_is_behind(tickers: list[str]) -> bool:
    """Whether any held ticker's archive stops short of the last completed
    session. Only consulted when there's nothing to chart, to say which of
    the two very different reasons applies."""
    behind = await asyncio.gather(*(stock_service.archive_is_behind(t) for t in tickers))
    return any(behind)


def _empty(
    market: str, portfolio_id: int | None, portfolio_name: str | None, range_key: str,
    excluded: list[str] | None = None, stale_archive: bool = False,
) -> PerformanceResponse:
    symbol, name = index_service.BENCHMARKS.get(market, index_service.BENCHMARKS["US"])
    blank = ReturnSummary(
        money_weighted=None, time_weighted=None, annualized=None,
        max_drawdown=0.0, volatility=None,
    )
    return PerformanceResponse(
        market=market,
        currency="INR" if market == "IN" else "USD",
        portfolio_id=portfolio_id,
        portfolio_name=portfolio_name,
        benchmark_symbol=symbol,
        benchmark_name=name,
        benchmark_available=False,
        range=range_key,
        start_date=None,
        end_date=None,
        days=0,
        points=[],
        portfolio=blank,
        benchmark=blank,
        beta=None,
        excluded_tickers=excluded or [],
        stale_archive=stale_archive,
        insufficient_data=True,
    )


async def backfill_missing_archives(
    session: AsyncSession, user_id: str, market: str | None = None,
    portfolio_id: int | None = None,
) -> list[str]:
    """Archive price history for held tickers that have none yet.

    `ensure_archive_current` deliberately does nothing for a ticker with an
    empty archive — extending nothing is not a top-up. But that is exactly
    the state a holding lands in when its first-buy backfill lost a race with
    a rate limit, and nothing afterwards ever retried it: the position simply
    sat in the "not included" list forever. This is the retry, triggered by
    the user rather than on a timer, because it is expensive (a full history
    download per ticker) and pointless to repeat unprompted.

    Returns the tickers it managed to archive. Never raises — a ticker that
    still fails stays in `excluded_tickers`, which is where the UI reports it.
    """
    market = normalize_market(market)
    positions = await _load_positions(session, user_id, market, portfolio_id)
    tickers = [h.ticker for h, _t, _d in positions]
    if not tickers:
        return []

    present = await market_data_service.get_closes(tickers)
    missing = [t for t in tickers if t not in present]

    archived: list[str] = []
    for ticker in missing:
        try:
            # Sequential on purpose: each is a multi-year download, and
            # firing them together is the shape yfinance rate-limits.
            await stock_service.add_stock(ticker)
            archived.append(ticker)
        except Exception as e:  # noqa: BLE001 — a miss stays reported as excluded
            logger.warning("Backfill failed for %s: %r", ticker, e)

    if archived:
        invalidate(user_id)
    return archived


# ── Orchestrator ──────────────────────────────────────────────────────────

async def get_performance(
    session: AsyncSession,
    user_id: str,
    market: str | None = None,
    portfolio_id: int | None = None,
    portfolio_name: str | None = None,
    range_key: str = DEFAULT_RANGE,
) -> PerformanceResponse:
    """Full performance payload for one market (optionally one portfolio).

    Cached per (user, market, portfolio, range) and coalesced, so a reload
    or a range toggle costs nothing. The caller resolves and ownership-checks
    `portfolio_id` before getting here — same contract as get_portfolio.
    """
    market = normalize_market(market)
    range_key = range_key if range_key in RANGES else DEFAULT_RANGE
    key = _cache_key(user_id, market, portfolio_id, range_key)

    cached = performance_cache.get(key)
    if cached is not None:
        return cached

    async def _load() -> PerformanceResponse:
        result = await _compute(session, user_id, market, portfolio_id, portfolio_name, range_key)
        performance_cache.set(key, result, _CACHE_TTL)
        return result

    return await single_flight(key, _load)


async def _compute(
    session: AsyncSession,
    user_id: str,
    market: str,
    portfolio_id: int | None,
    portfolio_name: str | None,
    range_key: str,
) -> PerformanceResponse:
    positions = await _load_positions(session, user_id, market, portfolio_id)
    if not positions:
        return _empty(market, portfolio_id, portfolio_name, range_key)

    first_transaction = min(_parse(t.date) for _h, txns, _d in positions for t in txns)
    window = RANGES[range_key]
    today = date.today()
    start = first_transaction if window is None else max(first_transaction, today - timedelta(days=window))

    tickers = [h.ticker for h, _t, _d in positions]

    # Bring the archive up to date before reading it. The Portfolio page
    # prices from live quotes and never touches the archive, so without this
    # a portfolio-only user's history stops at the day each ticker was added
    # — and a portfolio opened over a weekend has no archived bar anywhere
    # inside its own window, which reads as "no history" when it is really
    # "not fetched yet". Gap-only, marker-guarded and coalesced (see
    # stock_service.ensure_archive_current), so this is normally a no-op.
    await asyncio.gather(*(stock_service.ensure_archive_current(t) for t in tickers))
    # One query for every held symbol, and from the window start rather than
    # all of history — a "1y" view must not drag a decade of rows out of the
    # archive to throw them away.
    closes_by_symbol = await market_data_service.get_closes(tickers, start - timedelta(days=10))
    excluded = sorted({t for t in tickers if t not in closes_by_symbol})

    priced = [(h, txns, divs) for h, txns, divs in positions if h.ticker in closes_by_symbol]
    if not priced:
        return _empty(
            market, portfolio_id, portfolio_name, range_key, excluded,
            stale_archive=await _archive_is_behind(tickers),
        )

    axis = _build_axis(closes_by_symbol, start, today)
    if len(axis) < 2:
        # Distinguish "you have barely any history" from "the archive hasn't
        # caught up yet" — they look identical here but mean opposite things
        # to the user, and only one of them is their problem.
        return _empty(
            market, portfolio_id, portfolio_name, range_key, excluded,
            stale_archive=await _archive_is_behind(tickers),
        )

    # ── Portfolio value and contribution series ──
    # `opening_value` is what the positions held *before* this window were
    # worth on its first day. It is deliberately market value, not the cost
    # basis of those shares: a windowed comparison has to start the portfolio
    # and the benchmark from the same amount of money, and what the investor
    # actually had that morning is the market value. Seeding with cost basis
    # instead understates the capital already at risk, which inflates the
    # windowed return and makes the benchmark look worse than it was.
    # For the "max" window nothing was held beforehand, so this is 0.
    values = [0.0] * len(axis)
    opening_value = 0.0
    day_before = axis[0] - timedelta(days=1)
    for holding, transactions, _divs in priced:
        prices = _forward_fill(closes_by_symbol[holding.ticker], axis)
        shares = _shares_on(transactions, axis)
        prior_shares = _shares_on(transactions, [day_before])[0]
        if prices[0] is not None and prior_shares > 0:
            opening_value += prices[0] * prior_shares
        for i, (price, count) in enumerate(zip(prices, shares)):
            if price is not None and count:
                values[i] += price * count

    daily_flow = _cash_flows(priced)
    flows_on_axis = [float(daily_flow.get(day, Decimal(0))) for day in axis]

    # Capital at the window's open, plus everything added since. Flows from
    # before the window are not added again — they are already expressed in
    # `opening_value`.
    invested: list[float] = []
    running = opening_value
    for flow in flows_on_axis:
        running += flow
        invested.append(running)

    # ── Benchmark ──
    benchmark_symbol, benchmark_name = index_service.BENCHMARKS.get(
        market, index_service.BENCHMARKS["US"]
    )
    index_closes = await index_service.get_history(benchmark_symbol, axis[0] - timedelta(days=10))
    index_prices = _forward_fill(index_closes, axis)

    # A benchmark we couldn't price is worth saying so about rather than
    # drawing a flat line at zero and letting it read as a real comparison.
    have_benchmark = any(p is not None for p in index_prices)

    benchmark_values = [0.0] * len(axis)
    benchmark_returns: list[float] = []
    if have_benchmark:
        first_price = next(p for p in index_prices if p is not None)
        filled = [p if p is not None else first_price for p in index_prices]

        # Simulate the investor's own cash flows into the index: the opening
        # position first, then every contribution on the day it happened.
        units = opening_value / filled[0] if filled[0] else 0.0
        for i, price in enumerate(filled):
            if price:
                units += flows_on_axis[i] / price
            benchmark_values[i] = max(units, 0.0) * price

        benchmark_returns = [
            filled[i] / filled[i - 1] - 1.0 if filled[i - 1] else 0.0
            for i in range(1, len(filled))
        ]

    # ── Returns ──
    portfolio_returns = returns_math.daily_returns(values, flows_on_axis)
    portfolio_growth = returns_math.growth_index(portfolio_returns)
    benchmark_growth = returns_math.growth_index(benchmark_returns) if have_benchmark else [100.0] * len(axis)

    span_days = (axis[-1] - axis[0]).days or 1

    # XIRR flows are signed from the investor's side: buys out, sales and
    # dividends in, and the closing value as the terminal inflow.
    xirr_flows: list[tuple[date, float]] = []
    if opening_value:
        xirr_flows.append((axis[0], -opening_value))
    for day, amount in sorted(daily_flow.items()):
        if axis[0] <= day <= axis[-1] and amount:
            xirr_flows.append((day, -float(amount)))

    total_dividends = Decimal(0)
    for _h, _t, dividends in priced:
        for d in dividends:
            day = _parse(d.date)
            total_dividends += d.total_amount
            if axis[0] <= day <= axis[-1]:
                xirr_flows.append((day, float(d.total_amount)))

    xirr_flows.append((axis[-1], values[-1]))

    benchmark_xirr_flows = [(d, a) for d, a in xirr_flows if d != axis[-1]]
    if have_benchmark:
        benchmark_xirr_flows.append((axis[-1], benchmark_values[-1]))

    portfolio_summary = _summarize(portfolio_returns, xirr_flows, span_days)
    benchmark_summary = (
        _summarize(benchmark_returns, benchmark_xirr_flows, span_days)
        if have_benchmark
        else ReturnSummary(
            money_weighted=None, time_weighted=None, annualized=None,
            max_drawdown=0.0, volatility=None,
        )
    )

    points = [
        PerformancePoint(
            date=day.isoformat(),
            value=round(values[i], 2),
            invested=round(invested[i], 2),
            benchmark_value=round(benchmark_values[i], 2),
            portfolio_index=round(portfolio_growth[i], 4),
            benchmark_index=round(benchmark_growth[i], 4),
        )
        for i, day in enumerate(axis)
    ]

    current_value = Decimal(str(round(values[-1], 8)))
    net_invested = Decimal(str(round(invested[-1], 8)))
    # None, never 0, when the index couldn't be priced. `current_value - 0`
    # reads as "you beat the index by your entire portfolio" — the most
    # confidently wrong number this page could print, and it printed it.
    benchmark_final = Decimal(str(round(benchmark_values[-1], 8))) if have_benchmark else None

    realized = Decimal(0)
    for _h, transactions, _d in priced:
        for t in transactions:
            if t.sale:
                # `bought_at` on a sell row is the FIFO cost of the shares it
                # consumed (set by the replay in portfolio_service), so this
                # is the same realized figure the Portfolio page reports.
                realized += (t.sold_at - t.bought_at) * t.shares

    return PerformanceResponse(
        market=market,
        currency=currency_of(tickers[0]),
        portfolio_id=portfolio_id,
        portfolio_name=portfolio_name,
        benchmark_symbol=benchmark_symbol,
        benchmark_name=benchmark_name,
        range=range_key,
        start_date=axis[0].isoformat(),
        end_date=axis[-1].isoformat(),
        days=span_days,
        points=points,
        portfolio=portfolio_summary,
        benchmark=benchmark_summary,
        beta=returns_math.beta(portfolio_returns, benchmark_returns) if have_benchmark else None,
        current_value=current_value,
        net_invested=net_invested,
        total_dividends=total_dividends,
        realized_gains=realized,
        unrealized_gains=current_value - net_invested,
        benchmark_available=have_benchmark,
        benchmark_final_value=benchmark_final,
        value_added=(current_value - benchmark_final) if benchmark_final is not None else None,
        excluded_tickers=excluded,
        insufficient_data=False,
    )
