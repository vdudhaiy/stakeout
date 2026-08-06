"""Free, no-auth fallback for company display names, backed by the SEC's
public ticker registry (https://www.sec.gov/files/company_tickers.json).

Used by portfolio_service when yfinance's `.info` call — the flakier of the
two calls _validate_and_fetch_name makes — fails to produce a name (rate
limited, or otherwise). US-listed tickers only; the SEC has no reason to
know about NSE/BSE-listed companies, so this is a no-op for those.

The registry is a single static file covering essentially every
SEC-registered issuer, refreshed by the SEC infrequently — there's no
per-lookup rate limit to worry about, just their documented requirement to
identify the caller via User-Agent (an unidentified/default one risks being
blocked). Fetched once and cached for a day.
"""

import logging

import httpx

from cache import sec_ticker_cache

logger = logging.getLogger(__name__)

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_HEADERS = {"User-Agent": "stakeout-open-source-tracker/1.0"}
_CACHE_KEY = "ticker_map"


async def _ticker_map() -> dict[str, str]:
    """{ticker: company name} for every SEC-registered issuer.

    Empty dict on any fetch failure — callers treat that the same as "not
    found" rather than raising, since this is only ever a fallback.
    """
    cached = sec_ticker_cache.get(_CACHE_KEY)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            r = await client.get(_TICKERS_URL)
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to load SEC ticker registry: %r", e)
        return {}

    mapping = {
        row["ticker"]: row["title"]
        for row in data.values()
        if row.get("ticker") and row.get("title")
    }
    sec_ticker_cache.set(_CACHE_KEY, mapping)
    return mapping


async def company_name(ticker: str) -> str | None:
    """Company name for `ticker` from the SEC registry, or None if it's not
    a US-listed ticker the SEC knows about (an Indian .NS/.BO ticker, or a
    genuine miss).
    """
    mapping = await _ticker_map()
    return mapping.get(ticker.upper().strip())
