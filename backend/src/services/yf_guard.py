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

Two things make the cooldown more than a fixed sleep:

*Escalation.* A refusal arriving soon after a cooldown ended means the
previous wait was too short — the throttle is sustained, not a blip. Each
such refusal doubles the wait (capped), and a clean stretch resets it. A flat
120s against a multi-hour throttle is just a slow-motion version of the retry
storm this module exists to prevent.

*Persistence.* The deadline is mirrored into service_state, because the
free-tier host recycles the process many times a day — and the restart is
usually triggered by the page load that then immediately re-hits Yahoo. An
in-memory-only cooldown is therefore forgotten at exactly the moment it
matters most. The in-process values stay authoritative; the table is a
restore hint read once at startup.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

from yfinance.exceptions import YFRateLimitError

logger = logging.getLogger(__name__)

# Yahoo sends no Retry-After, so this is a judgement call: long enough to
# actually clear a throttle, short enough that one false positive doesn't
# blank the app for a whole page session.
_COOLDOWN_SECONDS = 120.0

# Ceiling on the escalated wait. Past roughly this long the app is better off
# serving archived data and re-testing occasionally than backing off further —
# a cooldown that outlives the user's whole visit protects nothing.
_MAX_COOLDOWN_SECONDS = 1800.0

# How long after a cooldown ends a fresh refusal still counts as "the same
# throttle". Beyond this the level resets, so an unrelated 429 next week
# starts from the base wait rather than inheriting today's escalation.
_ESCALATION_MEMORY_SECONDS = 900.0

_STATE_KEY = "yf_guard:cooldown"

_cooldown_until = 0.0        # monotonic deadline
_level = 0                   # consecutive refusals within the escalation window
_cooldown_ended_at = 0.0     # monotonic time the last cooldown expired


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


def cooldown_until_utc() -> datetime | None:
    """Wall-clock end of the active cooldown, or None. For status reporting."""
    remaining = cooldown_remaining()
    if remaining <= 0:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=remaining)


def level() -> int:
    """Current escalation step (0 = base wait). Exposed for tests and status."""
    return _level


def check() -> None:
    """Raise YFRateLimitError if a cooldown is active, before any I/O.

    Raised bare: YFRateLimitError.__init__ takes no arguments and supplies
    its own message. The remaining time goes to the log instead.
    """
    if in_cooldown():
        logger.info("yfinance backoff active for another %.0fs — call skipped", cooldown_remaining())
        raise YFRateLimitError()


def _next_duration() -> float:
    """Escalate if this refusal is a continuation of the last throttle."""
    global _level
    now = time.monotonic()
    # _cooldown_ended_at is 0.0 on a cold process, which is "long ago" here.
    continues = _cooldown_until > 0 and (now - _cooldown_ended_at) <= _ESCALATION_MEMORY_SECONDS
    _level = _level + 1 if continues else 0
    return min(_COOLDOWN_SECONDS * (2 ** _level), _MAX_COOLDOWN_SECONDS)


def note(e: BaseException) -> bool:
    """Enter the cooldown if `e` is a rate limit. Returns whether it was."""
    global _cooldown_until, _cooldown_ended_at
    if not is_rate_limit_error(e):
        return False
    duration = _next_duration()
    now = time.monotonic()
    _cooldown_until = now + duration
    _cooldown_ended_at = _cooldown_until
    logger.warning(
        "yfinance rate-limited this app — backing off for %.0fs (escalation level %d)",
        duration, _level,
    )
    _persist(duration)
    return True


def _persist(duration: float) -> None:
    """Mirror the deadline into service_state, fire and forget.

    note() is called from a synchronous `except` block inside guard(), so the
    write cannot be awaited here. Scheduling it is enough: the in-process
    deadline is already set and is what every check consults — the row only
    matters if this process dies before the cooldown ends, and if there is no
    running loop there is no server to restart anyway.
    """
    ends_at = datetime.now(timezone.utc) + timedelta(seconds=duration)
    payload = f"{ends_at.isoformat()}|{_level}"

    async def _write() -> None:
        from . import service_state_service
        await service_state_service.set(_STATE_KEY, payload)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no loop (tests, scripts) — the in-process deadline still holds
    task = loop.create_task(_write())
    _pending.add(task)
    task.add_done_callback(_pending.discard)


# asyncio keeps only a weak reference to a bare task; without this the
# persist write can be collected before it runs.
_pending: set[asyncio.Task] = set()


async def restore() -> None:
    """Re-enter a cooldown that was still running when the process died.

    Called once from the app lifespan. A deadline already in the past is
    cleared rather than restored, and its escalation level is kept only while
    inside the escalation window, so yesterday's throttle doesn't make
    today's first refusal start at a half-hour wait.
    """
    global _cooldown_until, _level, _cooldown_ended_at
    from . import service_state_service

    stored = await service_state_service.get(_STATE_KEY)
    if stored is None:
        return
    raw, _written_at = stored
    ends_at_text, _, level_text = raw.partition("|")
    try:
        ends_at = datetime.fromisoformat(ends_at_text)
        stored_level = int(level_text or 0)
    except ValueError:
        logger.warning("Ignoring unparseable yf_guard cooldown state: %r", raw)
        await service_state_service.clear(_STATE_KEY)
        return

    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=timezone.utc)
    remaining = (ends_at - datetime.now(timezone.utc)).total_seconds()

    if remaining <= 0:
        # Expired while we were down. Keep the level only if the expiry is
        # recent enough to still count as the same throttle, so a restart
        # inside a sustained one doesn't hand back a fresh escalation budget.
        if remaining > -_ESCALATION_MEMORY_SECONDS:
            _level = stored_level
            _cooldown_until = time.monotonic()  # non-zero: a cooldown did happen
            _cooldown_ended_at = time.monotonic() + remaining
        else:
            await service_state_service.clear(_STATE_KEY)
        return

    _level = stored_level
    _cooldown_until = time.monotonic() + remaining
    _cooldown_ended_at = _cooldown_until
    logger.warning(
        "Restored yfinance backoff from a previous process — %.0fs remaining (level %d)",
        remaining, _level,
    )


def reset() -> None:
    """Test-only: clear the cooldown and its escalation history."""
    global _cooldown_until, _level, _cooldown_ended_at
    _cooldown_until = 0.0
    _level = 0
    _cooldown_ended_at = 0.0


@contextlib.contextmanager
def guard() -> Iterator[None]:
    """Refuse outbound calls during a cooldown; start one on a fresh 429."""
    check()
    try:
        yield
    except Exception as e:  # noqa: BLE001 — inspected, then re-raised unchanged
        note(e)
        raise
