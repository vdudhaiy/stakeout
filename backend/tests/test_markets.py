"""Tests for markets.snap_to_session / is_trading_day.

Trade dates arrive as free text — from a form, or a broker export that
happily writes settlement dates on weekends. A date with no session behind it
has no price bar either, which is what silently broke the performance chart
(see performance_service._project_flows). These pin the rule that moves such a
date onto a real session.

Real calendars, real dates: the point is that NYSE and NSE disagree about
which days are holidays, so mocking the calendar would test nothing.
"""

from datetime import date

import markets


# ── is_trading_day ────────────────────────────────────────────────────────

def test_a_weekday_session_is_a_trading_day():
    assert markets.is_trading_day("US", date(2026, 9, 18)) is True   # Friday


def test_a_weekend_is_not():
    assert markets.is_trading_day("US", date(2026, 9, 19)) is False  # Saturday


def test_a_us_holiday_is_not():
    assert markets.is_trading_day("US", date(2025, 12, 25)) is False  # Christmas


def test_the_calendars_disagree_about_holidays():
    """India trades on the US's Independence Day; the US trades on Holi. A
    single calendar for both markets would be wrong twice."""
    independence_day = date(2025, 7, 4)
    assert markets.is_trading_day("US", independence_day) is False
    assert markets.is_trading_day("IN", independence_day) is True


# ── snap_to_session ───────────────────────────────────────────────────────

TODAY = date(2026, 9, 22)  # a Monday, comfortably after every date below


def test_a_session_is_left_alone():
    day = date(2026, 9, 18)
    assert markets.snap_to_session("US", day, today=TODAY) == day


def test_a_saturday_fills_on_the_following_monday():
    assert markets.snap_to_session("US", date(2026, 9, 19), today=TODAY) == date(2026, 9, 21)


def test_a_sunday_fills_on_the_following_monday():
    assert markets.snap_to_session("US", date(2026, 9, 20), today=TODAY) == date(2026, 9, 21)


def test_a_holiday_fills_on_the_next_open_session():
    assert markets.snap_to_session("US", date(2025, 12, 25), today=TODAY) == date(2025, 12, 26)


def test_a_holiday_cluster_is_cleared():
    """New Year's Day 2026 is a Thursday, so the next session is the Friday."""
    assert markets.snap_to_session("US", date(2026, 1, 1), today=TODAY) == date(2026, 1, 2)


def test_an_indian_holiday_uses_the_indian_calendar():
    # Republic Day, 26 Jan 2026 (a Monday) — NSE shut, NYSE open.
    assert markets.snap_to_session("IN", date(2026, 1, 26), today=TODAY) == date(2026, 1, 27)


def test_a_closed_day_entered_today_snaps_backwards_not_into_the_future():
    """Someone recording a trade on a Saturday must not end up with a date
    that hasn't happened yet — every other date check in the app rejects
    those, and the position would vanish from the chart until Monday."""
    saturday = date(2026, 9, 19)
    snapped = markets.snap_to_session("US", saturday, today=saturday)

    assert snapped == date(2026, 9, 18)  # the Friday
    assert snapped <= saturday


def test_an_unknown_market_falls_back_to_us_rather_than_raising():
    assert markets.snap_to_session("XX", date(2026, 9, 19), today=TODAY) == date(2026, 9, 21)


def test_a_calendar_failure_returns_the_date_unchanged():
    """A trade must never be blocked by a calendar lookup."""
    from unittest.mock import patch

    day = date(2026, 9, 19)
    with patch("markets.get_calendar", side_effect=RuntimeError("no calendar")):
        assert markets.snap_to_session("US", day, today=TODAY) == day
        assert markets.is_trading_day("US", day) is True  # not a verdict either
