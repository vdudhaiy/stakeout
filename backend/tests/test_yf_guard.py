"""Tests for services.yf_guard — the process-wide yfinance backoff.

Finnhub calls already back off on a 429 (services.finnhub_client); yfinance
had no equivalent, so once Yahoo started refusing us every later request
went straight back out and was refused too. These cover the refusal path
and, importantly, that an unrelated failure never triggers it.
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from yfinance.exceptions import YFRateLimitError

from services import yf_guard


# conftest's autouse fixture resets the cooldown around every test.

def test_starts_out_of_cooldown():
    assert not yf_guard.in_cooldown()


def test_a_rate_limit_starts_a_cooldown():
    assert yf_guard.note(YFRateLimitError()) is True
    assert yf_guard.in_cooldown()
    assert yf_guard.cooldown_remaining() > 0


def test_an_unrelated_error_does_not_start_a_cooldown():
    assert yf_guard.note(ValueError("no data for ticker")) is False
    assert not yf_guard.in_cooldown()


def test_sees_a_rate_limit_through_a_wrapping_value_error():
    """stock_service.add_stock re-raises as a plain ValueError, so the
    original type only survives on __context__."""
    try:
        try:
            raise YFRateLimitError()
        except YFRateLimitError:
            raise ValueError("Error creating stock data for AAPL")
    except ValueError as wrapped:
        assert yf_guard.is_rate_limit_error(wrapped)
        assert yf_guard.note(wrapped) is True


def test_check_raises_while_in_cooldown_and_is_silent_otherwise():
    yf_guard.check()  # not in cooldown — must not raise
    yf_guard.note(YFRateLimitError())
    with pytest.raises(YFRateLimitError):
        yf_guard.check()


def test_guard_refuses_the_block_without_running_it():
    yf_guard.note(YFRateLimitError())
    ran = False
    with pytest.raises(YFRateLimitError):
        with yf_guard.guard():
            ran = True
    assert ran is False


def test_guard_starts_a_cooldown_when_the_block_is_rate_limited():
    with pytest.raises(YFRateLimitError):
        with yf_guard.guard():
            raise YFRateLimitError()
    assert yf_guard.in_cooldown()


def test_guard_re_raises_other_errors_unchanged_and_stays_available():
    with pytest.raises(ValueError, match="unrelated"):
        with yf_guard.guard():
            raise ValueError("unrelated")
    assert not yf_guard.in_cooldown()


def test_reset_clears_the_cooldown():
    yf_guard.note(YFRateLimitError())
    yf_guard.reset()
    assert not yf_guard.in_cooldown()


# ── escalation ───────────────────────────────────────────────────────────────
#
# A refusal arriving right after a cooldown ended means the wait was too
# short — the throttle is sustained, not a blip. A flat 120s against a
# multi-hour throttle is a slow-motion version of the retry storm this module
# exists to prevent.

def test_a_first_refusal_uses_the_base_wait():
    yf_guard.note(YFRateLimitError())

    assert yf_guard.level() == 0
    assert yf_guard.cooldown_remaining() == pytest.approx(yf_guard._COOLDOWN_SECONDS, abs=2)


def test_a_refusal_soon_after_a_cooldown_doubles_the_wait():
    yf_guard.note(YFRateLimitError())
    _expire_cooldown()

    yf_guard.note(YFRateLimitError())

    assert yf_guard.level() == 1
    assert yf_guard.cooldown_remaining() == pytest.approx(yf_guard._COOLDOWN_SECONDS * 2, abs=2)


def test_escalation_keeps_compounding_and_stops_at_the_ceiling():
    for _ in range(12):
        yf_guard.note(YFRateLimitError())
        _expire_cooldown()

    yf_guard.note(YFRateLimitError())
    assert yf_guard.cooldown_remaining() <= yf_guard._MAX_COOLDOWN_SECONDS + 1


def test_a_refusal_long_after_the_last_one_starts_over():
    """Yesterday's throttle must not make today's first refusal open at half
    an hour."""
    yf_guard.note(YFRateLimitError())
    _expire_cooldown(ago=yf_guard._ESCALATION_MEMORY_SECONDS + 60)

    yf_guard.note(YFRateLimitError())

    assert yf_guard.level() == 0
    assert yf_guard.cooldown_remaining() == pytest.approx(yf_guard._COOLDOWN_SECONDS, abs=2)


def test_reset_clears_the_escalation_history_too():
    yf_guard.note(YFRateLimitError())
    _expire_cooldown()
    yf_guard.note(YFRateLimitError())
    assert yf_guard.level() == 1

    yf_guard.reset()
    yf_guard.note(YFRateLimitError())
    assert yf_guard.level() == 0


def _expire_cooldown(ago: float = 1.0) -> None:
    """Pretend the active cooldown ended `ago` seconds in the past.

    Cheaper and more deterministic than sleeping through a real 120s wait,
    and it exercises the same monotonic arithmetic the module uses.
    """
    now = time.monotonic()
    yf_guard._cooldown_until = now - ago
    yf_guard._cooldown_ended_at = now - ago


# ── persistence across a restart ─────────────────────────────────────────────
#
# The free-tier host recycles many times a day, and the restart is usually
# triggered by the page load that then immediately re-hits Yahoo. A cooldown
# held only in memory is therefore forgotten at exactly the moment it matters.

async def test_restore_reinstates_a_cooldown_that_outlived_the_process():
    ends_at = datetime.now(timezone.utc) + timedelta(seconds=300)
    with patch("services.service_state_service.get", new_callable=AsyncMock,
               return_value=(f"{ends_at.isoformat()}|2", datetime.now(timezone.utc))):
        await yf_guard.restore()

    assert yf_guard.in_cooldown()
    assert yf_guard.cooldown_remaining() == pytest.approx(300, abs=5)
    assert yf_guard.level() == 2


async def test_restore_does_not_reinstate_an_expired_cooldown():
    ends_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    with patch("services.service_state_service.get", new_callable=AsyncMock,
               return_value=(f"{ends_at.isoformat()}|1", datetime.now(timezone.utc))), \
         patch("services.service_state_service.clear", new_callable=AsyncMock):
        await yf_guard.restore()

    assert not yf_guard.in_cooldown()


async def test_a_recently_expired_cooldown_keeps_its_escalation_level():
    """Restarting inside a sustained throttle must not hand back a fresh
    escalation budget — otherwise every restart resets the backoff to 120s,
    which is how a throttle becomes self-sustaining."""
    ends_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    with patch("services.service_state_service.get", new_callable=AsyncMock,
               return_value=(f"{ends_at.isoformat()}|3", datetime.now(timezone.utc))), \
         patch("services.service_state_service.clear", new_callable=AsyncMock):
        await yf_guard.restore()

    yf_guard.note(YFRateLimitError())
    assert yf_guard.level() == 4


async def test_a_long_expired_cooldown_is_cleared_rather_than_carried():
    ends_at = datetime.now(timezone.utc) - timedelta(
        seconds=yf_guard._ESCALATION_MEMORY_SECONDS + 600
    )
    with patch("services.service_state_service.get", new_callable=AsyncMock,
               return_value=(f"{ends_at.isoformat()}|3", datetime.now(timezone.utc))), \
         patch("services.service_state_service.clear", new_callable=AsyncMock) as cleared:
        await yf_guard.restore()

    cleared.assert_awaited_once()
    yf_guard.note(YFRateLimitError())
    assert yf_guard.level() == 0


async def test_restore_is_a_no_op_with_nothing_stored():
    with patch("services.service_state_service.get", new_callable=AsyncMock, return_value=None):
        await yf_guard.restore()

    assert not yf_guard.in_cooldown()


async def test_unparseable_stored_state_is_discarded_not_obeyed():
    with patch("services.service_state_service.get", new_callable=AsyncMock,
               return_value=("garbage", datetime.now(timezone.utc))), \
         patch("services.service_state_service.clear", new_callable=AsyncMock) as cleared:
        await yf_guard.restore()

    assert not yf_guard.in_cooldown()
    cleared.assert_awaited_once()
