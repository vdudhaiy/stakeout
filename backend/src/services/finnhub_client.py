"""Shared low-level client for Finnhub's free-tier REST API.

No pre-emptive request counting on our side — Finnhub's free tier already
enforces its own 60-calls/minute budget, and second-guessing that with a
stricter local cap would just waste headroom the plan actually has. Calls
flow through normally; a real 429 *from Finnhub* is what triggers backing
off, honoring its `Retry-After` header (or a conservative default) and
skipping outbound calls until that cooldown clears. Every caller here
(peers_service, logo_service, quote_service) already treats "no fresh data"
as routine, falling back to a cache/DB row or simply omitting the feature.

get() never raises: a missing key, an active cooldown, a 429, or any
transport failure all collapse to None.
"""

from __future__ import annotations

import logging
import time

import httpx

from config import FINNHUB_API_KEY

logger = logging.getLogger(__name__)

_BASE_URL = "https://finnhub.io/api/v1"
_TIMEOUT = 8.0

# Fallback backoff when Finnhub 429s without a Retry-After header.
_DEFAULT_COOLDOWN_SECONDS = 60.0

# time.monotonic() timestamp until which outbound calls are skipped. 0 means
# "not in cooldown". Shared process-wide, same spirit as the module-level
# TTLCache singletons in cache.py — one budget, not one per caller.
_cooldown_until = 0.0


def _enter_cooldown(retry_after: str | None) -> None:
    global _cooldown_until
    seconds = _DEFAULT_COOLDOWN_SECONDS
    if retry_after:
        try:
            seconds = max(float(retry_after), 1.0)
        except ValueError:
            pass
    _cooldown_until = time.monotonic() + seconds
    logger.warning("Finnhub rate-limited this app — backing off for %.0fs", seconds)


def in_cooldown() -> bool:
    return time.monotonic() < _cooldown_until


def cooldown_remaining() -> float:
    """Seconds until outbound calls resume; 0 when not backing off."""
    return max(0.0, _cooldown_until - time.monotonic())


def reset() -> None:
    """Test-only: clear the cooldown."""
    global _cooldown_until
    _cooldown_until = 0.0


async def get(path: str, params: dict) -> object | None:
    if not FINNHUB_API_KEY:
        return None

    if in_cooldown():
        logger.info("Finnhub still in cooldown — skipping %s", path)
        return None

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(
                f"{_BASE_URL}{path}",
                params={**params, "token": FINNHUB_API_KEY},
            )
            if r.status_code == 429:
                _enter_cooldown(r.headers.get("Retry-After"))
                return None
            r.raise_for_status()
            return r.json()
    except Exception as e:  # noqa: BLE001 — any transport/HTTP failure degrades to "no fresh data"
        logger.warning("Finnhub request to %s failed: %r", path, e)
        return None
