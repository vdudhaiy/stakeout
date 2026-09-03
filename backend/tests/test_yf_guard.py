"""Tests for services.yf_guard — the process-wide yfinance backoff.

Finnhub calls already back off on a 429 (services.finnhub_client); yfinance
had no equivalent, so once Yahoo started refusing us every later request
went straight back out and was refused too. These cover the refusal path
and, importantly, that an unrelated failure never triggers it.
"""

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
