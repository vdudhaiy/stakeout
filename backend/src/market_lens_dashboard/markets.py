"""Market (exchange) awareness: US vs India.

Tickers are classified by their Yahoo Finance suffix:
- ``.NS`` → NSE (National Stock Exchange of India)
- ``.BO`` → BSE (Bombay Stock Exchange)
- anything else → US (NYSE / NASDAQ)

Each market carries its own trading calendar, session hours, timezone and
native currency. Everything downstream (market-status pill, "last completed
trading day", portfolio grouping) keys off this module so adding a third
market later is a one-dict change.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pandas_market_calendars as mcal

MARKET_US = "US"
MARKET_IN = "IN"
VALID_MARKETS = (MARKET_US, MARKET_IN)

MARKET_META = {
    MARKET_US: {
        "label": "US · NYSE/NASDAQ",
        "currency": "USD",
        "timezone": "America/New_York",
        "calendar_candidates": ("NYSE",),
        "sessions": {
            "pre": ("04:00", "09:30"),
            "regular": ("09:30", "16:00"),
            "post": ("16:00", "20:00"),
        },
        "index_ticker": "^GSPC",
        "index_label": "S&P 500",
    },
    MARKET_IN: {
        "label": "India · NSE/BSE",
        "currency": "INR",
        "timezone": "Asia/Kolkata",
        # pandas_market_calendars exposes Indian exchanges under different
        # names across versions; try in order until one resolves.
        "calendar_candidates": ("NSE", "BSE", "XBOM"),
        "sessions": {
            "pre": ("09:00", "09:15"),
            "regular": ("09:15", "15:30"),
            "post": ("15:40", "16:00"),
        },
        "index_ticker": "^NSEI",
        "index_label": "NIFTY 50",
    },
}

_calendar_cache: dict[str, object] = {}


def market_of(ticker: str) -> str:
    t = ticker.upper()
    if t.endswith(".NS") or t.endswith(".BO"):
        return MARKET_IN
    return MARKET_US


def currency_of(ticker: str) -> str:
    return MARKET_META[market_of(ticker)]["currency"]


# Exchange the user picks in the "add ticker" UI -> Yahoo Finance suffix.
# "US" carries no suffix, so it's intentionally absent from this map.
EXCHANGE_SUFFIXES = {"NSE": ".NS", "BSE": ".BO"}


def apply_exchange(ticker: str, exchange: str | None) -> str:
    """Append the Yahoo Finance suffix for `exchange` to a bare ticker.

    Lets the frontend collect "ticker" and "exchange" as separate fields
    instead of requiring the user to type ".NS"/".BO" themselves. Idempotent:
    a ticker that already carries a market suffix, or an unset/US exchange,
    passes through unchanged.
    """
    ticker = ticker.upper().strip()
    if not exchange:
        return ticker
    suffix = EXCHANGE_SUFFIXES.get(exchange.upper())
    if not suffix or ticker.endswith((".NS", ".BO")):
        return ticker
    return f"{ticker}{suffix}"


def normalize_market(market: str | None) -> str:
    m = (market or MARKET_US).upper()
    return m if m in VALID_MARKETS else MARKET_US


def get_calendar(market: str):
    market = normalize_market(market)
    cached = _calendar_cache.get(market)
    if cached is not None:
        return cached
    last_err: Exception | None = None
    for name in MARKET_META[market]["calendar_candidates"]:
        try:
            cal = mcal.get_calendar(name)
            _calendar_cache[market] = cal
            return cal
        except Exception as e:  # noqa: BLE001 — calendar name not in this version
            last_err = e
    raise RuntimeError(f"No trading calendar available for market {market}") from last_err


def is_market_open(market: str) -> bool:
    cal = get_calendar(market)
    now = datetime.now(timezone.utc)
    schedule = cal.schedule(start_date=now.date(), end_date=now.date())
    if schedule.empty:
        return False
    row = schedule.iloc[0]
    return bool(row["market_open"] <= pd.Timestamp(now) <= row["market_close"])


def last_completed_trading_day(market: str) -> pd.Timestamp | None:
    """Most recent trading day whose session has fully closed (UTC-safe)."""
    cal = get_calendar(market)
    now_utc = datetime.now(timezone.utc)
    schedule = cal.schedule(
        start_date=(now_utc - timedelta(days=10)).date(),
        end_date=now_utc.date(),
    )
    if schedule.empty:
        return None
    closed = schedule[schedule["market_close"] <= pd.Timestamp(now_utc)]
    if closed.empty:
        return None
    return pd.Timestamp(closed.index[-1].date())
