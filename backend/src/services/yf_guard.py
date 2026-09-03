"""Process-wide backoff for yfinance, mirroring services.finnhub_client.

Finnhub calls already back off on a 429 and skip outbound requests until the
cooldown clears. yfinance had no equivalent: once Yahoo started rate-limiting
us, every subsequent request went straight back out and was refused, so a
brief throttle became a sustained one and the retries piled up against the
worker pool.

Usage — wrap the block that talks to yfinance:

    with yf_guard.guard():
        df = await asyncio.to_thread(stock.history, ...)

`guard()` raises YFRateLimitError *without* going out while a cooldown is
active, and starts one when Yahoo refuses a live call. Callers already treat
that exception as "no fresh data" and fall back to the archive or a cached
value, so nothing needs new error handling.

Deliberately not a request counter: Yahoo publishes no quota, so the only
honest signal is a refusal we actually received.
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Iterator

from yfinance.exceptions import YFRateLimitError

logger = logging.getLogger(__name__)

# Yahoo sends no Retry-After, so this is a judgement call: long enough to
# actually clear a throttle, short enough that one false positive doesn't
# blank the app for a whole page session.
_COOLDOWN_SECONDS = 120.0

_cooldown_until = 0.0


def is_rate_limit_error(e: BaseException) -> bool:
    """True if `e` — or the exception it was raised while handling — is a
    yfinance rate limit. Callers like stock_service.add_stock wrap their
    underlying errors in a plain ValueError, so the original type only
    survives via the implicit chain Python sets on a `raise` inside an
    `except` block (__context__).
    """
    return isinstance(e, YFRateLimitError) or isinstance(getattr(e, "__context__", None), YFRateLimitError)


def in_cooldown() -> bool:
    return time.monotonic() < _cooldown_until


def cooldown_remaining() -> float:
    return max(0.0, _cooldown_until - time.monotonic())


def check() -> None:
    """Raise YFRateLimitError if a cooldown is active, before any I/O.

    Raised bare: YFRateLimitError.__init__ takes no arguments and supplies
    its own message. The remaining time goes to the log instead.
    """
    if in_cooldown():
        logger.info("yfinance backoff active for another %.0fs — call skipped", cooldown_remaining())
        raise YFRateLimitError()


def note(e: BaseException) -> bool:
    """Enter the cooldown if `e` is a rate limit. Returns whether it was."""
    global _cooldown_until
    if not is_rate_limit_error(e):
        return False
    _cooldown_until = time.monotonic() + _COOLDOWN_SECONDS
    logger.warning("yfinance rate-limited this app — backing off for %.0fs", _COOLDOWN_SECONDS)
    return True


def reset() -> None:
    """Test-only: clear the cooldown."""
    global _cooldown_until
    _cooldown_until = 0.0


@contextlib.contextmanager
def guard() -> Iterator[None]:
    """Refuse outbound calls during a cooldown; start one on a fresh 429."""
    check()
    try:
        yield
    except Exception as e:  # noqa: BLE001 — inspected, then re-raised unchanged
        note(e)
        raise
