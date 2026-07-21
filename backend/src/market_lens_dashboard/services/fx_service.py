"""Foreign-exchange rates with layered free fallbacks.

Source order (all free, no API key):
1. frankfurter.dev  — ECB reference rates, clean JSON, generous limits
2. open.er-api.com  — ExchangeRate-API open endpoint, daily rates
3. Yahoo Finance    — via yfinance ("USDINR=X" style pairs), last resort

Rates are cached for 1 hour. FX display conversion doesn't need
tick-level precision — these are daily reference rates and the UI labels
them as such.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from ..cache import fx_cache

logger = logging.getLogger(__name__)

SUPPORTED = {"USD", "INR"}

_TIMEOUT = httpx.Timeout(6.0, connect=4.0)


async def _from_frankfurter(base: str, quote: str) -> float | None:
    url = f"https://api.frankfurter.dev/v1/latest?from={base}&to={quote}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        rate = data.get("rates", {}).get(quote)
        return float(rate) if rate else None


async def _from_erapi(base: str, quote: str) -> float | None:
    url = f"https://open.er-api.com/v6/latest/{base}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        if data.get("result") != "success":
            return None
        rate = data.get("rates", {}).get(quote)
        return float(rate) if rate else None


async def _from_yfinance(base: str, quote: str) -> float | None:
    def _fetch() -> float | None:
        import yfinance as yf  # local import: heavy module

        pair = yf.Ticker(f"{base}{quote}=X")
        hist = pair.history(period="1d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])

    return await asyncio.to_thread(_fetch)


async def get_rate(base: str, quote: str) -> dict:
    """Return {base, quote, rate, source}. Raises ValueError on bad input."""
    base, quote = base.upper(), quote.upper()
    if base not in SUPPORTED or quote not in SUPPORTED:
        raise ValueError(f"Unsupported currency pair {base}/{quote}")
    if base == quote:
        return {"base": base, "quote": quote, "rate": 1.0, "source": "identity"}

    key = f"{base}/{quote}"
    cached = fx_cache.get(key)
    if cached is not None:
        return cached

    for source, fetcher in (
        ("frankfurter", _from_frankfurter),
        ("er-api", _from_erapi),
        ("yahoo", _from_yfinance),
    ):
        try:
            rate = await fetcher(base, quote)
        except Exception as e:  # noqa: BLE001 — fall through to next source
            logger.warning("FX source %s failed for %s: %s", source, key, e)
            continue
        if rate and rate > 0:
            result = {"base": base, "quote": quote, "rate": rate, "source": source}
            fx_cache.set(key, result)
            # Cache the inverse too — saves a round-trip when the user flips
            fx_cache.set(
                f"{quote}/{base}",
                {"base": quote, "quote": base, "rate": 1.0 / rate, "source": source},
            )
            return result

    raise RuntimeError(f"All FX sources failed for {key}")
