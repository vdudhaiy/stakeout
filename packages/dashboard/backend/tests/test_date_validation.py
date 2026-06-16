"""Tests for _resolve_date — the transaction-date parser/validator."""

import datetime
import pytest

from market_lens_dashboard.services.portfolio_service import _resolve_date


def test_none_returns_today():
    assert _resolve_date(None) == datetime.date.today().isoformat()


def test_today_is_accepted():
    today = datetime.date.today().isoformat()
    assert _resolve_date(today) == today


def test_valid_past_date_returned_unchanged():
    assert _resolve_date("2024-01-15") == "2024-01-15"


def test_future_date_raises():
    future = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="future"):
        _resolve_date(future)


def test_slash_separated_format_raises():
    with pytest.raises(ValueError, match="Invalid date"):
        _resolve_date("2024/01/15")


def test_dmy_format_raises():
    with pytest.raises(ValueError, match="Invalid date"):
        _resolve_date("15-01-2024")


def test_partial_date_raises():
    with pytest.raises(ValueError, match="Invalid date"):
        _resolve_date("2024-01")


def test_non_date_string_raises():
    with pytest.raises(ValueError, match="Invalid date"):
        _resolve_date("not-a-date")
