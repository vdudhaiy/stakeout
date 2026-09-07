"""Lightweight quote snapshots via Finnhub's free /quote endpoint.

Powers PeersPanel's mini sparklines. Free-tier Finnhub doesn't expose
historical candles, so the sparkline is built from the three real,
sequential price points a single quote call actually gives us — previous
close, today's open, and the latest trade — rather than a true intraday
series.

Purely in-process cached, never persisted: a quote is stale the moment it's
fetched, so writing it to the DB would just be wrong data with a timestamp
on it (contrast with peers_service / logo_service, which cache things that
are actually slow-moving). The TTL trades a bit of staleness for call
volume — a peers panel with ten chips already draws ten calls per view.
"""

from __future__ import annotations

import asyncio

from cache import TTLCache
from services import finnhub_client

import freshness

_quote_cache = TTLCache(ttl_seconds=5 * 60)  # in-process memo: 5 minutes


async def _fetch_one(symbol: str) -> dict | None:
    cached = _quote_cache.get_stamped(symbol, freshness.CACHED, label="quote")
    if cached is not None:
        return cached or None

    data = await finnhub_client.get("/quote", {"symbol": symbol})
    # Finnhub answers an unrecognized/quoteless symbol with an all-zero
    # payload rather than an error, so a zero current price means "no quote"
    # — that's still a definite, cacheable answer, not a failed call.
    if not isinstance(data, dict) or not data.get("c"):
        _quote_cache.set(symbol, "")
        return None

    quote = {
        "open": data.get("o"),
        "high": data.get("h"),
        "low": data.get("l"),
        "close": data.get("c"),
        "prev_close": data.get("pc"),
        "change": data.get("d"),
        "change_percent": data.get("dp"),
    }
    freshness.stamp(freshness.LIVE, label="quote")
    _quote_cache.set(symbol, quote)
    return quote


async def get_quotes(tickers: list[str]) -> dict[str, dict | None]:
    """Quote snapshots for a batch of tickers, fetched concurrently.

    Returns a dict with every requested (uppercased) ticker as a key, mapped
    to a quote dict or None if Finnhub has nothing for it. Never raises —
    an individual failed lookup just maps to None like a genuine "no quote".
    """
    unique = list(dict.fromkeys(t.upper().strip() for t in tickers if t.strip()))
    results = await asyncio.gather(*(_fetch_one(t) for t in unique))
    return dict(zip(unique, results))
