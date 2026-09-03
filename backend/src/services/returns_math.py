"""Portfolio return mathematics — pure functions, no I/O, no ORM.

Split out from performance_service so the arithmetic can be tested against
worked examples directly, without a database or a price archive in the way.
Every function here takes plain numbers and dates and returns plain numbers.

Two return measures live here, and they answer different questions. Both are
reported, because either one alone is misleading:

- **Money-weighted (XIRR)** — what *this investor* earned, timing included.
  Putting most of the money in right before a rally shows up here. It's the
  honest answer to "how did I do?".
- **Time-weighted (TWR)** — what the *holdings* earned, with the effect of
  deposit and withdrawal timing removed. It's the only measure that can be
  compared like-for-like against an index, because an index has no deposits.

Convention throughout: a cash flow is signed from the investor's point of
view, so a buy (money leaving the pocket) is **negative** and a sale or
dividend is **positive**. The portfolio's current value is a positive
terminal flow — the money you would have if you liquidated today.
"""

from __future__ import annotations

import math
from datetime import date

# Actual/365 fixed. Matches Excel's XIRR, which is what anyone checking
# these numbers against a spreadsheet will be using.
_DAYS_PER_YEAR = 365.0

# Trading days in a year, for annualizing a daily volatility figure.
_TRADING_DAYS = 252

# Below this, any *annualized* figure — XIRR or CAGR — is noise dressed as a
# forecast: a 0.6% gain over two days annualizes to several thousand percent.
# Both measures share the threshold so the page can't report one and withhold
# the other.
MIN_ANNUALIZATION_DAYS = 30

# A rate below -100% is meaningless (you cannot lose more than everything)
# and 1 + r hits zero there, so the search is bounded just above it.
_MIN_RATE = -0.999999
_MAX_RATE = 1e6


def xnpv(rate: float, flows: list[tuple[date, float]]) -> float:
    """Net present value of dated cash flows at `rate`, discounted Actual/365."""
    if not flows:
        return 0.0
    origin = flows[0][0]
    total = 0.0
    for when, amount in flows:
        years = (when - origin).days / _DAYS_PER_YEAR
        total += amount / (1.0 + rate) ** years
    return total


def xirr(flows: list[tuple[date, float]]) -> float | None:
    """Money-weighted annualized return of dated cash flows, or None.

    None means the question has no answer rather than that something failed:
    fewer than two flows, every flow the same sign (you can't have a return
    on money that never came back), or all flows on one day.

    Solved by bisection rather than Newton-Raphson. Newton is faster but
    diverges on exactly the shapes real portfolios produce — a large late
    deposit, or a position bought and sold within days — and a silently wrong
    rate is far worse here than a few extra iterations.
    """
    flows = sorted((d, float(a)) for d, a in flows if a)
    if len(flows) < 2:
        return None
    if flows[0][0] == flows[-1][0]:
        return None
    if all(a > 0 for _, a in flows) or all(a < 0 for _, a in flows):
        return None

    low, high = _MIN_RATE, 1.0
    npv_low = xnpv(low, flows)
    if not math.isfinite(npv_low):
        return None

    # Expand the upper bound until the NPV changes sign. A portfolio that
    # multiplied quickly can have a genuine IRR in the hundreds of percent.
    npv_high = xnpv(high, flows)
    while npv_low * npv_high > 0:
        high *= 4.0
        if high > _MAX_RATE:
            return None
        npv_high = xnpv(high, flows)
        if not math.isfinite(npv_high):
            return None

    for _ in range(200):
        mid = (low + high) / 2.0
        npv_mid = xnpv(mid, flows)
        if abs(npv_mid) < 1e-9 or (high - low) < 1e-10:
            return mid
        if npv_low * npv_mid <= 0:
            high = mid
        else:
            low, npv_low = mid, npv_mid
    return (low + high) / 2.0


def daily_returns(values: list[float], flows: list[float]) -> list[float]:
    """Time-weighted daily returns from a value series and its external flows.

    `values[i]` is the portfolio's market value at the close of day i;
    `flows[i]` is the net external money added that day (positive for a
    deposit/buy, negative for a withdrawal/sale). The flow is removed from
    the day's change so that adding money never registers as a gain:

        r_i = (V_i - F_i) / V_{i-1} - 1

    Flows are treated as end-of-day. The alternative — pricing each trade at
    its actual execution price mid-day — is the more precise Modified Dietz
    treatment, but it needs an intraday value the daily archive simply does
    not have, and the difference is a rounding error over any period long
    enough to be worth charting.

    Days where the previous value was zero (before the first buy, or after a
    full liquidation) contribute a flat 0.0: there was no capital at risk, so
    there is no return to measure, and dividing by zero would otherwise
    manufacture an infinite one.
    """
    returns: list[float] = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        if prev <= 0:
            returns.append(0.0)
            continue
        returns.append((values[i] - flows[i]) / prev - 1.0)
    return returns


def growth_index(returns: list[float], base: float = 100.0) -> list[float]:
    """Compound `returns` into a "growth of `base`" series, starting at `base`.

    This is what makes a portfolio and an index directly comparable on one
    chart: both start at 100 and every later point is pure return, with the
    portfolio's deposits already stripped out by `daily_returns`.
    """
    series = [base]
    level = base
    for r in returns:
        level *= (1.0 + r)
        series.append(level)
    return series


def total_return(returns: list[float]) -> float:
    """Cumulative time-weighted return over the whole period, as a fraction."""
    level = 1.0
    for r in returns:
        level *= (1.0 + r)
    return level - 1.0


def annualized(total: float, days: int) -> float | None:
    """Annualize a cumulative return spanning `days` calendar days (CAGR).

    None for periods under a month: annualizing a two-week result produces a
    confidently enormous number that means nothing, and publishing it would
    be the single most misleading figure on the page.
    """
    if days < MIN_ANNUALIZATION_DAYS:
        return None
    if total <= -1.0:
        return -1.0
    return (1.0 + total) ** (_DAYS_PER_YEAR / days) - 1.0


def max_drawdown(series: list[float]) -> tuple[float, int | None, int | None]:
    """Largest peak-to-trough fall in `series`.

    Returns (drawdown as a negative fraction, peak index, trough index).
    Run this on a growth index rather than on raw portfolio value — a
    withdrawal is not a loss, and raw value can't tell the two apart.
    """
    if not series:
        return 0.0, None, None
    peak = series[0]
    peak_i = 0
    worst = 0.0
    worst_peak_i: int | None = None
    worst_i: int | None = None
    for i, value in enumerate(series):
        if value > peak:
            peak, peak_i = value, i
        elif peak > 0:
            drop = value / peak - 1.0
            if drop < worst:
                worst, worst_peak_i, worst_i = drop, peak_i, i
    return worst, worst_peak_i, worst_i


def volatility(returns: list[float]) -> float | None:
    """Annualized standard deviation of daily returns, as a fraction.

    None below 20 observations — a standard deviation from a handful of days
    is noise wearing a statistic's clothes.
    """
    if len(returns) < 20:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(_TRADING_DAYS)


def sharpe(returns: list[float], risk_free_rate: float = 0.0) -> float | None:
    """Annualized excess return per unit of volatility.

    Deliberately defaults to a 0% risk-free rate, and the caller passes one
    explicitly if it has a better number. Guessing a T-bill yield we don't
    actually fetch would make this look more precise than it is.
    """
    vol = volatility(returns)
    if vol is None or vol == 0:
        return None
    total = total_return(returns)
    ann = annualized(total, max(len(returns), 1) * int(_DAYS_PER_YEAR / _TRADING_DAYS))
    if ann is None:
        return None
    return (ann - risk_free_rate) / vol


def beta(portfolio: list[float], benchmark: list[float]) -> float | None:
    """Sensitivity of the portfolio's daily returns to the benchmark's.

    1.0 means it moved with the index; above that, more sharply. None when
    there are too few paired observations, or the benchmark never moved.
    """
    pairs = [(p, b) for p, b in zip(portfolio, benchmark)]
    if len(pairs) < 20:
        return None
    mean_p = sum(p for p, _ in pairs) / len(pairs)
    mean_b = sum(b for _, b in pairs) / len(pairs)
    covariance = sum((p - mean_p) * (b - mean_b) for p, b in pairs)
    variance = sum((b - mean_b) ** 2 for _, b in pairs)
    if variance == 0:
        return None
    return covariance / variance
