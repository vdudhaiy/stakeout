'''
Service layer for computing the "facts" that feed the AI Explanation Layer.

Pure, deterministic computation only — no LLM calls happen here. Everything
in the dict returned by build_fact_sheet is auditable data Stakeout already
has: indicator values, a rule-based classification of what they mean, and a
historical backtest stat. The LLM (see llm_service.py) only narrates this
dict; it never sees raw price ticks or invents a number that isn't in here.
'''

from __future__ import annotations

import pandas as pd

from . import indicators_service, market_data_service, news_service

_MIN_RECOVERY_OCCURRENCES = 3  # below this, a "recovery rate" is noise, not a stat


# ── Classification helpers ──────────────────────────────────────────────────

def classify_rsi(value: float | None) -> str | None:
    if value is None:
        return None
    if value >= 70:
        return "overbought"
    if value <= 30:
        return "oversold"
    return "neutral"


def classify_bollinger(
    close: float | None, upper: float | None, middle: float | None, lower: float | None,
) -> str | None:
    if close is None or upper is None or middle is None or lower is None:
        return None
    if close > upper:
        return "above_upper"
    if close < lower:
        return "below_lower"
    return "upper_half" if close >= middle else "lower_half"


def classify_macd(recent: list[dict]) -> str | None:
    '''
    `recent` is the last few MACD points (dicts with "macd"/"signal" keys),
    oldest first. Detects a crossover in the most recent two valid points,
    otherwise just reports which side of the signal line MACD is on.
    '''
    valid = [p for p in recent if p.get("macd") is not None and p.get("signal") is not None]
    if not valid:
        return None
    if len(valid) >= 2:
        prev, curr = valid[-2], valid[-1]
        prev_diff = prev["macd"] - prev["signal"]
        curr_diff = curr["macd"] - curr["signal"]
        if prev_diff <= 0 < curr_diff:
            return "bullish_cross"
        if prev_diff >= 0 > curr_diff:
            return "bearish_cross"
    latest = valid[-1]
    return "above_signal" if latest["macd"] >= latest["signal"] else "below_signal"


def sma_trend(close: float | None, sma50: float | None, sma200: float | None) -> str | None:
    if close is None or sma50 is None or sma200 is None:
        return None
    if close > sma50 and close > sma200:
        return "above_both"
    if close < sma50 and close < sma200:
        return "below_both"
    return "mixed"


def volume_vs_average(df: pd.DataFrame, window: int = 20) -> float | None:
    '''Latest volume vs the trailing `window`-day average, as a signed % diff.'''
    if len(df) < window + 1:
        return None
    avg = df["volume"].iloc[-(window + 1):-1].mean()
    latest = df["volume"].iloc[-1]
    if not avg or pd.isna(avg) or pd.isna(latest):
        return None
    return round((latest - avg) / avg * 100, 1)


# ── Historical RSI-recovery backtest ────────────────────────────────────────

def rsi_recovery_stats(
    closes: list[float],
    rsi_values: list[float | None],
    oversold: float = 30.0,
    horizon_days: int = 10,
) -> dict | None:
    '''
    For every historical day the RSI first crossed *below* `oversold` (i.e.
    was >= oversold the previous day), check whether the close price
    `horizon_days` trading days later was higher. Returns None when there
    are too few such events (< _MIN_RECOVERY_OCCURRENCES) to say anything
    meaningful — a tiny sample must never be dressed up as a solid stat.
    '''
    occurrences = 0
    recoveries = 0
    returns: list[float] = []
    last_entry_index = len(rsi_values) - horizon_days
    for i in range(1, max(last_entry_index, 1)):
        prev, curr = rsi_values[i - 1], rsi_values[i]
        if prev is None or curr is None:
            continue
        if prev >= oversold > curr:
            entry_close = closes[i]
            exit_close = closes[i + horizon_days]
            if not entry_close:
                continue
            occurrences += 1
            pct = (exit_close - entry_close) / entry_close * 100
            returns.append(pct)
            if exit_close > entry_close:
                recoveries += 1

    if occurrences < _MIN_RECOVERY_OCCURRENCES:
        return None

    return {
        "occurrences": occurrences,
        "horizon_days": horizon_days,
        "recovered_pct": round(recoveries / occurrences * 100, 1),
        "avg_return_pct": round(sum(returns) / len(returns), 1),
    }


# ── Confidence ───────────────────────────────────────────────────────────────

def confidence(history_days: int, recovery_occurrences: int, has_news: bool) -> str:
    '''Rule-based, not model-generated — the LLM narrates this, it doesn't decide it.'''
    if history_days >= 200 and recovery_occurrences >= _MIN_RECOVERY_OCCURRENCES:
        level = "high"
    elif history_days >= 60:
        level = "medium"
    else:
        level = "low"
    if level == "high" and not has_news:
        level = "medium"  # no corroborating news layer — pull back one notch
    return level


# ── Orchestrator ─────────────────────────────────────────────────────────────

async def build_fact_sheet(ticker: str) -> dict:
    '''
    Load full history, compute every indicator, classify the latest values,
    and assemble the single JSON-serializable "facts" dict that both the LLM
    prompt and the frontend's "view the numbers" disclosure are built from.

    Raises ValueError (same convention as the rest of the services layer) if
    the ticker has no archived data — the router converts this to a 404.
    '''
    ticker = ticker.upper()
    records = await market_data_service.get_ohlcv(ticker, days=0)
    if not records:
        raise ValueError(f"Data for ticker '{ticker}' not found.")
    df = pd.DataFrame(records)

    sma_50 = indicators_service.compute_sma(df, 50)
    sma_200 = indicators_service.compute_sma(df, 200)
    rsi_points = indicators_service.compute_rsi(df, 14)
    macd_points = indicators_service.compute_macd(df)
    bb_points = indicators_service.compute_bollinger(df)

    close = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-2]) if len(df) > 1 else None
    change_pct = round((close - prev_close) / prev_close * 100, 2) if prev_close else None

    latest_rsi = rsi_points[-1].value
    latest_bb = bb_points[-1]
    macd_tail = [{"macd": p.macd, "signal": p.signal} for p in macd_points[-3:]]

    recovery = rsi_recovery_stats(
        df["close"].tolist(), [p.value for p in rsi_points],
    )

    headlines: list[str] = []
    try:
        news = await news_service.get_stock_news(ticker, limit=3)
        headlines = [a["title"] for a in news.get("articles", [])[:3]]
    except Exception:
        pass  # best-effort — an insight is still useful without headlines

    return {
        "ticker": ticker,
        "as_of": df["date"].iloc[-1],
        "history_days": len(df),
        "close": close,
        "change_pct": change_pct,
        "rsi": round(latest_rsi, 1) if latest_rsi is not None else None,
        "rsi_zone": classify_rsi(latest_rsi),
        "bollinger_position": classify_bollinger(close, latest_bb.upper, latest_bb.middle, latest_bb.lower),
        "macd_signal": classify_macd(macd_tail),
        "sma_trend": sma_trend(close, sma_50[-1].value, sma_200[-1].value),
        "volume_vs_avg_pct": volume_vs_average(df),
        "rsi_recovery": recovery,
        "headlines": headlines,
        "confidence": confidence(len(df), recovery["occurrences"] if recovery else 0, bool(headlines)),
    }
