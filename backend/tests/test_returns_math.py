"""Tests for services.returns_math — the arithmetic behind the Performance page.

These are the numbers a user will check against a spreadsheet, so the cases
below are mostly worked examples with an answer known independently of the
implementation. The most important property in the file is that a deposit
never reads as a gain (see the time-weighted section) — getting that wrong
would flatter every portfolio that ever added money.
"""

from datetime import date

import pytest

from services import returns_math as rm


# ── xirr ──────────────────────────────────────────────────────────────────

def test_single_year_doubling_is_a_100_percent_return():
    flows = [(date(2021, 1, 1), -1000.0), (date(2022, 1, 1), 2000.0)]
    assert rm.xirr(flows) == pytest.approx(1.0, abs=1e-6)


def test_single_year_ten_percent_gain():
    flows = [(date(2021, 1, 1), -1000.0), (date(2022, 1, 1), 1100.0)]
    assert rm.xirr(flows) == pytest.approx(0.10, abs=1e-6)


def test_a_loss_gives_a_negative_rate():
    flows = [(date(2021, 1, 1), -1000.0), (date(2022, 1, 1), 900.0)]
    assert rm.xirr(flows) == pytest.approx(-0.10, abs=1e-6)


def test_half_year_gain_is_annualized_upward():
    """+10% over ~6 months is ~21% a year, not 10% — the whole point of XIRR."""
    flows = [(date(2021, 1, 1), -1000.0), (date(2021, 7, 2), 1100.0)]
    rate = rm.xirr(flows)
    assert rate == pytest.approx(0.21, abs=0.01)


def test_timing_of_a_second_deposit_changes_the_answer():
    """Two portfolios ending at the same value, one of which put most of its
    money in late, must not report the same return."""
    early = [(date(2021, 1, 1), -2000.0), (date(2022, 1, 1), 2400.0)]
    late = [
        (date(2021, 1, 1), -1000.0),
        (date(2021, 12, 1), -1000.0),
        (date(2022, 1, 1), 2400.0),
    ]
    assert rm.xirr(late) > rm.xirr(early)


def test_npv_at_the_solved_rate_is_zero():
    flows = [
        (date(2020, 1, 15), -5000.0),
        (date(2020, 6, 1), -2500.0),
        (date(2021, 3, 10), 1200.0),
        (date(2022, 9, 30), 9000.0),
    ]
    rate = rm.xirr(flows)
    assert rate is not None
    assert rm.xnpv(rate, flows) == pytest.approx(0.0, abs=1e-6)


def test_flows_are_sorted_before_solving():
    """Callers append the terminal value last, but dividends can be inserted
    out of order — the origin date must still be the earliest flow."""
    unordered = [(date(2022, 1, 1), 1100.0), (date(2021, 1, 1), -1000.0)]
    assert rm.xirr(unordered) == pytest.approx(0.10, abs=1e-6)


def test_all_outflows_has_no_answer():
    flows = [(date(2021, 1, 1), -1000.0), (date(2022, 1, 1), -500.0)]
    assert rm.xirr(flows) is None


def test_all_inflows_has_no_answer():
    flows = [(date(2021, 1, 1), 1000.0), (date(2022, 1, 1), 500.0)]
    assert rm.xirr(flows) is None


def test_a_single_flow_has_no_answer():
    assert rm.xirr([(date(2021, 1, 1), -1000.0)]) is None


def test_flows_all_on_one_day_have_no_answer():
    """Bought and sold the same day: a rate of return per year is undefined,
    and the naive formula would divide by a zero time span."""
    flows = [(date(2021, 1, 1), -1000.0), (date(2021, 1, 1), 1100.0)]
    assert rm.xirr(flows) is None


def test_a_total_wipeout_does_not_hang_or_explode():
    flows = [(date(2021, 1, 1), -1000.0), (date(2022, 1, 1), 0.01)]
    rate = rm.xirr(flows)
    assert rate is not None
    assert -1.0 < rate < -0.99


def test_a_very_large_gain_still_solves():
    """A rate in the hundreds of percent is real for a small early position;
    the bracket has to expand to find it."""
    flows = [(date(2021, 1, 1), -100.0), (date(2022, 1, 1), 50_000.0)]
    rate = rm.xirr(flows)
    assert rate == pytest.approx(499.0, rel=0.01)


# ── daily_returns ─────────────────────────────────────────────────────────

def test_a_plain_gain_with_no_flows():
    assert rm.daily_returns([100.0, 110.0], [0.0, 0.0]) == pytest.approx([0.10])


def test_a_deposit_is_not_a_gain():
    """Value went 100 -> 210, but 100 of that was cash the user added. The
    return is 10%, and reporting 110% here would be the single worst bug on
    the page."""
    assert rm.daily_returns([100.0, 210.0], [0.0, 100.0]) == pytest.approx([0.10])


def test_a_withdrawal_is_not_a_loss():
    assert rm.daily_returns([200.0, 120.0], [0.0, -100.0]) == pytest.approx([0.10])


def test_days_before_any_capital_contribute_no_return():
    returns = rm.daily_returns([0.0, 0.0, 100.0, 110.0], [0.0, 0.0, 100.0, 0.0])
    assert returns == pytest.approx([0.0, 0.0, 0.10])


def test_a_fully_liquidated_portfolio_does_not_divide_by_zero():
    returns = rm.daily_returns([100.0, 0.0, 0.0], [0.0, -100.0, 0.0])
    assert returns[-1] == 0.0


def test_an_empty_series_has_no_returns():
    assert rm.daily_returns([], []) == []


# ── growth_index / total_return / annualized ──────────────────────────────

def test_growth_index_starts_at_the_base_and_compounds():
    assert rm.growth_index([0.10, 0.10]) == pytest.approx([100.0, 110.0, 121.0])


def test_total_return_compounds_rather_than_sums():
    assert rm.total_return([0.10, 0.10]) == pytest.approx(0.21)


def test_a_gain_then_an_equal_percentage_loss_is_a_net_loss():
    assert rm.total_return([0.50, -0.50]) == pytest.approx(-0.25)


def test_annualizing_a_two_year_double():
    assert rm.annualized(1.0, 730) == pytest.approx(0.4142, abs=1e-3)


def test_annualizing_is_refused_for_very_short_periods():
    """Annualizing a fortnight produces a confident, enormous, meaningless
    number — better to show nothing."""
    assert rm.annualized(0.05, 14) is None


def test_the_annualization_floor_is_shared_so_both_measures_agree():
    """XIRR and CAGR are both annual rates; withholding one while publishing
    the other is how "+8796.1% per year" reached a real screen."""
    assert rm.MIN_ANNUALIZATION_DAYS >= 28
    assert rm.annualized(0.05, rm.MIN_ANNUALIZATION_DAYS - 1) is None
    assert rm.annualized(0.05, rm.MIN_ANNUALIZATION_DAYS) is not None


def test_annualized_floors_at_total_loss():
    assert rm.annualized(-1.0, 400) == -1.0


# ── max_drawdown ──────────────────────────────────────────────────────────

def test_max_drawdown_finds_the_peak_to_trough_fall():
    drawdown, peak, trough = rm.max_drawdown([100.0, 120.0, 60.0, 80.0])
    assert drawdown == pytest.approx(-0.50)
    assert (peak, trough) == (1, 2)


def test_a_monotonically_rising_series_has_no_drawdown():
    drawdown, _peak, _trough = rm.max_drawdown([100.0, 110.0, 120.0])
    assert drawdown == 0.0


def test_max_drawdown_of_an_empty_series_is_zero():
    assert rm.max_drawdown([]) == (0.0, None, None)


def test_max_drawdown_prefers_the_deeper_of_two_falls():
    drawdown, _peak, _trough = rm.max_drawdown([100.0, 90.0, 100.0, 130.0, 91.0, 120.0])
    assert drawdown == pytest.approx(-0.30)


# ── volatility / sharpe / beta ────────────────────────────────────────────

def test_volatility_needs_a_meaningful_sample():
    assert rm.volatility([0.01] * 19) is None


def test_a_constant_return_series_has_zero_volatility():
    assert rm.volatility([0.01] * 30) == pytest.approx(0.0)


def test_volatility_is_annualized():
    returns = [0.01, -0.01] * 30
    vol = rm.volatility(returns)
    assert vol is not None and vol > 0.1


def test_sharpe_is_none_without_volatility():
    assert rm.sharpe([0.01] * 30) is None


def test_beta_of_a_series_that_moves_exactly_with_the_benchmark_is_one():
    benchmark = [0.01, -0.02, 0.03, -0.01] * 10
    assert rm.beta(benchmark, benchmark) == pytest.approx(1.0)


def test_beta_of_a_doubly_sensitive_series_is_two():
    benchmark = [0.01, -0.02, 0.03, -0.01] * 10
    portfolio = [r * 2 for r in benchmark]
    assert rm.beta(portfolio, benchmark) == pytest.approx(2.0)


def test_beta_needs_a_moving_benchmark():
    assert rm.beta([0.01] * 30, [0.0] * 30) is None


def test_beta_needs_enough_paired_observations():
    assert rm.beta([0.01] * 5, [0.01] * 5) is None
