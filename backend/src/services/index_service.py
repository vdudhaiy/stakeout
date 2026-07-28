"""Major market index quotes for the home page.

Fetches a fixed set of headline US and Indian indices from Yahoo Finance
(via yfinance) and returns the latest level, day change, and a ~3-month
daily close series for sparkline charts. Results are cached for 10 minutes
(index_cache) — the home page is public and may be hit by anonymous
visitors, so this endpoint must stay cheap under load.

Index symbols use Yahoo's caret prefix (^GSPC, ^NSEI, …). These are not
tradeable tickers and never appear in watchlists or portfolios, so they
bypass the market_data archive entirely.
"""

from __future__ import annotations

import asyncio
import logging

from cache import index_cache

logger = logging.getLogger(__name__)

# (symbol, display name, region). Order here is the display order.
MAJOR_INDICES: list[tuple[str, str, str]] = [
    ("^GSPC", "S&P 500", "US"),
    ("^DJI", "Dow Jones", "US"),
    ("^IXIC", "NASDAQ Composite", "US"),
    ("^NSEI", "NIFTY 50", "IN"),
    ("^BSESN", "BSE SENSEX", "IN"),
    ("^NSEBANK", "NIFTY Bank", "IN"),
]

_CACHE_KEY = "indices:v1"


def _fetch_one(symbol: str, name: str, region: str) -> dict | None:
    """Blocking yfinance fetch for a single index. Runs in a worker thread."""
    import yfinance as yf

    try:
        hist = yf.Ticker(symbol).history(period="3mo", interval="1d")
    except Exception as e:  # noqa: BLE001
        logger.warning("Index fetch failed for %s: %r", symbol, e)
        return None
    if hist is None or hist.empty or "Close" not in hist:
        return None

    closes = hist["Close"].dropna()
    if closes.empty:
        return None

    points = [
        {"date": idx.strftime("%Y-%m-%d"), "close": round(float(val), 2)}
        for idx, val in closes.items()
    ]
    last = points[-1]["close"]
    prev = points[-2]["close"] if len(points) > 1 else None
    change = round(last - prev, 2) if prev is not None else None
    change_pct = round((last - prev) / prev * 100, 2) if prev else None

    return {
        "symbol": symbol,
        "name": name,
        "region": region,
        "last": last,
        "change": change,
        "change_pct": change_pct,
        "points": points,
    }


async def get_major_indices() -> dict:
    """All major indices, fetched concurrently and cached for 10 minutes.

    Indices whose fetch fails are simply omitted rather than failing the
    whole response — a partially rendered strip beats an error banner.
    """
    cached = index_cache.get(_CACHE_KEY)
    if cached is not None:
        return cached

    results = await asyncio.gather(
        *(asyncio.to_thread(_fetch_one, sym, name, region) for sym, name, region in MAJOR_INDICES)
    )
    indices = [r for r in results if r is not None]

    result = {"indices": indices}
    # Don't cache a fully empty result for the full TTL — a transient Yahoo
    # outage would otherwise blank the home page strip for 10 minutes.
    if indices:
        index_cache.set(_CACHE_KEY, result)
    return result
