"""Tests for services.performance_service and the /performance router.

The price archive and the benchmark history are mocked at the call site
(same treatment test_stock_service gives market_data_service), so these run
offline against a portfolio whose correct answers are known by construction.

The scenarios are deliberately arithmetic-checkable: a stock that doubles, a
benchmark that doesn't move, a deposit made late. Each one pins a property
that would be easy to break and hard to notice — most importantly that a
contribution is never counted as a gain, and that the benchmark comparison
follows the user's own cash flows rather than the whole period.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from models.portfolio import Dividend, Holding, Transaction
from services import performance_service

USER_ID = "test-user"  # matches conftest's TEST_USER_ID


# ── fixtures / helpers ────────────────────────────────────────────────────

def _days(start: date, n: int) -> list[date]:
    """`n` consecutive calendar days. The service treats whatever dates the
    archive holds as its trading calendar, so these stand in for sessions."""
    return [start + timedelta(days=i) for i in range(n)]


def _flat(dates: list[date], value: float) -> dict[date, float]:
    return {d: value for d in dates}


def _ramp(dates: list[date], first: float, last: float) -> dict[date, float]:
    """Linear price path from `first` to `last` across `dates`."""
    if len(dates) == 1:
        return {dates[0]: first}
    step = (last - first) / (len(dates) - 1)
    return {d: first + step * i for i, d in enumerate(dates)}


async def _add_holding(session, pid, ticker, market="US", transactions=(), dividends=()):
    holding = Holding(
        user_id=USER_ID, portfolio_id=pid, ticker=ticker, market=market,
        company_name=ticker, shares=0, sold_shares=0, average_cost=Decimal(0),
    )
    session.add(holding)
    await session.flush()
    for sale, day, shares, price in transactions:
        session.add(Transaction(
            holding_id=holding.id, sale=sale, date=day.isoformat(), shares=shares,
            bought_at=Decimal(0) if sale else Decimal(str(price)),
            sold_at=Decimal(str(price)) if sale else Decimal(0),
            shares_remaining=0 if sale else shares,
        ))
    for day, per_share, shares_held in dividends:
        session.add(Dividend(
            holding_id=holding.id, date=day.isoformat(),
            amount_per_share=Decimal(str(per_share)), shares_held=shares_held,
            total_amount=Decimal(str(per_share)) * shares_held, source="manual",
        ))
    await session.commit()
    return holding


def _mock_data(closes: dict[str, dict[date, float]], index: dict[date, float]):
    """Patch both data sources the service reads."""
    return (
        patch("services.performance_service.market_data_service.get_closes",
              new_callable=AsyncMock, return_value=closes),
        patch("services.performance_service.index_service.get_history",
              new_callable=AsyncMock, return_value=index),
    )


# ── empty / degenerate cases ──────────────────────────────────────────────

async def test_no_holdings_reports_insufficient_data(db_session, pid):
    closes, index = _mock_data({}, {})
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.insufficient_data is True
    assert result.points == []
    assert result.portfolio.money_weighted is None


async def test_a_holding_with_no_archive_history_is_excluded_not_silently_dropped(db_session, pid):
    """The totals here would otherwise disagree with the Portfolio page for
    no visible reason."""
    day = date(2024, 1, 1)
    await _add_holding(db_session, pid, "OBSCURE", transactions=[(False, day, 10, 5.0)])

    closes, index = _mock_data({}, {})
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.insufficient_data is True
    assert result.excluded_tickers == ["OBSCURE"]


async def test_a_single_day_of_history_is_not_enough_to_chart(db_session, pid):
    day = date(2024, 1, 1)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, day, 10, 100.0)])

    closes, index = _mock_data({"AAPL": {day: 100.0}}, {day: 4000.0})
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.insufficient_data is True


# ── value series ──────────────────────────────────────────────────────────

async def test_value_series_tracks_shares_times_price(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index = _mock_data({"AAPL": _ramp(axis, 100.0, 140.0)}, _flat(axis, 4000.0))
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    values = [p.value for p in result.points]
    assert values[0] == pytest.approx(1000.0)
    assert values[-1] == pytest.approx(1400.0)
    assert result.current_value == pytest.approx(Decimal("1400"))


async def test_a_holding_bought_mid_window_is_worth_nothing_before_it_was_bought(db_session, pid):
    """The chart starts at the first transaction of the whole portfolio, so a
    second position added later must contribute zero until the day it was
    actually bought."""
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])
    await _add_holding(db_session, pid, "MSFT", transactions=[(False, axis[2], 5, 200.0)])

    closes, index = _mock_data(
        {"AAPL": _flat(axis, 100.0), "MSFT": _flat(axis, 200.0)}, _flat(axis, 4000.0),
    )
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    values = [p.value for p in result.points]
    assert values[:2] == [pytest.approx(1000.0), pytest.approx(1000.0)]  # AAPL only
    assert values[2] == pytest.approx(2000.0)                            # + MSFT


async def test_a_sale_reduces_the_value_series(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[
        (False, axis[0], 10, 100.0),
        (True, axis[3], 4, 100.0),
    ])

    closes, index = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    values = [p.value for p in result.points]
    assert values[2] == pytest.approx(1000.0)
    assert values[-1] == pytest.approx(600.0)


async def test_a_missing_price_bar_holds_the_last_known_price(db_session, pid):
    """A day with no published bar is not a day the holding was worthless."""
    axis = _days(date(2024, 1, 1), 4)
    prices = {axis[0]: 100.0, axis[1]: 100.0, axis[3]: 120.0}  # axis[2] missing
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index = _mock_data({"AAPL": prices, "OTHER": _flat(axis, 1.0)}, _flat(axis, 4000.0))
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    by_date = {p.date: p.value for p in result.points}
    assert by_date[axis[2].isoformat()] == pytest.approx(1000.0)


# ── contributions vs returns ──────────────────────────────────────────────

async def test_a_deposit_is_not_reported_as_a_gain(db_session, pid):
    """Buying more at an unchanged price doubles the value and must leave the
    time-weighted return at zero."""
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[
        (False, axis[0], 10, 100.0),
        (False, axis[2], 10, 100.0),
    ])

    closes, index = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.points[-1].value == pytest.approx(2000.0)
    assert result.portfolio.time_weighted == pytest.approx(0.0, abs=1e-9)
    assert result.net_invested == pytest.approx(Decimal("2000"))


async def test_time_weighted_return_matches_the_price_move(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index = _mock_data({"AAPL": _ramp(axis, 100.0, 150.0)}, _flat(axis, 4000.0))
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.portfolio.time_weighted == pytest.approx(0.50, abs=1e-9)


async def test_dividends_are_income_not_a_contribution(db_session, pid):
    """Counting a dividend as money added would make income look like a
    deposit and quietly depress every return figure on the page."""
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(
        db_session, pid, "AAPL",
        transactions=[(False, axis[0], 10, 100.0)],
        dividends=[(axis[2], 2.0, 10)],
    )

    closes, index = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.total_dividends == pytest.approx(Decimal("20"))
    assert result.net_invested == pytest.approx(Decimal("1000"))
    # Flat price, but the dividend is real money back, so the money-weighted
    # return is positive.
    assert result.portfolio.money_weighted > 0


# ── benchmark comparison ──────────────────────────────────────────────────

async def test_benchmark_follows_the_users_own_cash_flows(db_session, pid):
    """Half the money goes in before the index doubles and half after, so the
    benchmark-equivalent value must land between the two extremes — not at
    the 4000 that "the index doubled, so double everything" would give.

    units = 1000/100 (early) + 1000/200 (late) = 15, worth 15 * 200 = 3000.
    """
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[
        (False, axis[0], 10, 100.0),
        (False, axis[3], 10, 100.0),
    ])
    index_levels = dict(zip(axis, [100.0, 100.0, 100.0, 200.0, 200.0]))

    closes, index = _mock_data({"AAPL": _flat(axis, 100.0)}, index_levels)
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.benchmark_final_value == pytest.approx(Decimal("3000"))
    assert result.net_invested == pytest.approx(Decimal("2000"))


async def test_beating_the_benchmark_shows_positive_value_added(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    # Stock doubles; index is flat.
    closes, index = _mock_data({"AAPL": _ramp(axis, 100.0, 200.0)}, _flat(axis, 4000.0))
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.current_value == pytest.approx(Decimal("2000"))
    assert result.benchmark_final_value == pytest.approx(Decimal("1000"))
    assert result.value_added == pytest.approx(Decimal("1000"))


async def test_lagging_the_benchmark_shows_negative_value_added(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index = _mock_data({"AAPL": _flat(axis, 100.0)}, _ramp(axis, 100.0, 200.0))
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.benchmark_final_value == pytest.approx(Decimal("2000"))
    assert result.value_added == pytest.approx(Decimal("-1000"))


async def test_both_growth_series_start_at_the_same_base(db_session, pid):
    """They share a base so the two lines are directly comparable on one chart."""
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index = _mock_data({"AAPL": _ramp(axis, 100.0, 150.0)}, _ramp(axis, 100.0, 110.0))
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.points[0].portfolio_index == pytest.approx(100.0)
    assert result.points[0].benchmark_index == pytest.approx(100.0)
    assert result.points[-1].portfolio_index == pytest.approx(150.0, abs=0.01)
    assert result.points[-1].benchmark_index == pytest.approx(110.0, abs=0.01)


async def test_an_unavailable_benchmark_degrades_rather_than_drawing_a_fake_line(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index = _mock_data({"AAPL": _flat(axis, 100.0)}, {})
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.insufficient_data is False
    assert result.benchmark.time_weighted is None or result.benchmark.time_weighted == 0.0
    assert result.beta is None


async def test_indian_portfolios_are_benchmarked_against_nifty(db_session, pid, db_engine):
    from services import portfolio_admin_service
    portfolio = await portfolio_admin_service.ensure_default(db_session, USER_ID, "IN")
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, portfolio.id, "TCS.NS", market="IN",
                       transactions=[(False, axis[0], 10, 100.0)])

    closes, index = _mock_data({"TCS.NS": _flat(axis, 100.0)}, _flat(axis, 22000.0))
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "IN")

    assert result.benchmark_symbol == "^NSEI"
    assert result.benchmark_name == "NIFTY 50"
    assert result.currency == "INR"


# ── ranges and caching ────────────────────────────────────────────────────

async def test_range_narrows_the_window(db_session, pid):
    axis = _days(date.today() - timedelta(days=800), 800)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes, index:
        full = await performance_service.get_performance(db_session, USER_ID, "US", range_key="max")
        windowed = await performance_service.get_performance(db_session, USER_ID, "US", range_key="1y")

    assert len(windowed.points) < len(full.points)
    assert windowed.range == "1y"


async def test_contributions_made_before_the_window_are_not_counted_inside_it(db_session, pid):
    """A "1y" view of a position bought two years ago opens with the shares
    already held — counting that original purchase again would double the
    invested figure."""
    axis = _days(date.today() - timedelta(days=800), 800)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes, index:
        windowed = await performance_service.get_performance(db_session, USER_ID, "US", range_key="1y")

    assert windowed.net_invested == pytest.approx(Decimal("1000"))


async def test_a_window_opens_at_market_value_not_cost_basis(db_session, pid):
    """The position tripled before the window opened. A "1y" view has to
    start from what it was worth that morning (3000), not what was paid for
    it two years earlier (1000) — otherwise the capital already at risk is
    understated and the windowed return is inflated.
    """
    axis = _days(date.today() - timedelta(days=800), 800)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])
    # 100 until the last ~year, then 300 for the whole window.
    prices = {d: (100.0 if i < 400 else 300.0) for i, d in enumerate(axis)}

    closes, index = _mock_data({"AAPL": prices}, _flat(axis, 4000.0))
    with closes, index:
        windowed = await performance_service.get_performance(db_session, USER_ID, "US", range_key="1y")

    assert windowed.points[0].value == pytest.approx(3000.0)
    assert windowed.points[0].invested == pytest.approx(3000.0)
    # Flat prices across the window, so no return was earned inside it.
    assert windowed.portfolio.time_weighted == pytest.approx(0.0, abs=1e-9)
    assert windowed.portfolio.money_weighted == pytest.approx(0.0, abs=1e-3)


async def test_a_window_starts_the_benchmark_from_the_same_capital(db_session, pid):
    """Both paths must begin the window with the same amount of money, or
    the comparison flatters whichever one starts richer."""
    axis = _days(date.today() - timedelta(days=800), 800)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])
    prices = {d: (100.0 if i < 400 else 300.0) for i, d in enumerate(axis)}

    closes, index = _mock_data({"AAPL": prices}, _flat(axis, 4000.0))
    with closes, index:
        windowed = await performance_service.get_performance(db_session, USER_ID, "US", range_key="1y")

    assert windowed.points[0].benchmark_value == pytest.approx(windowed.points[0].value)
    # Flat index and flat prices inside the window — neither path gained.
    assert windowed.value_added == pytest.approx(Decimal("0"), abs=Decimal("0.01"))


async def test_an_unknown_range_falls_back_to_max_rather_than_erroring(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes, index:
        result = await performance_service.get_performance(db_session, USER_ID, "US", range_key="nonsense")

    assert result.range == "max"


async def test_a_second_request_is_served_from_cache(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes as mock_closes, index:
        await performance_service.get_performance(db_session, USER_ID, "US")
        await performance_service.get_performance(db_session, USER_ID, "US")

    assert mock_closes.await_count == 1


async def test_invalidate_forces_a_recompute(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes as mock_closes, index:
        await performance_service.get_performance(db_session, USER_ID, "US")
        performance_service.invalidate(USER_ID)
        await performance_service.get_performance(db_session, USER_ID, "US")

    assert mock_closes.await_count == 2


async def test_one_users_cache_is_not_dropped_by_anothers_trade(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes as mock_closes, index:
        await performance_service.get_performance(db_session, USER_ID, "US")
        performance_service.invalidate("someone-else")
        await performance_service.get_performance(db_session, USER_ID, "US")

    assert mock_closes.await_count == 1


# ── router ────────────────────────────────────────────────────────────────

async def test_route_returns_a_payload_and_a_private_cache_header(client):
    with patch("routers.performance.performance_service.get_performance",
               new_callable=AsyncMock) as mock_get:
        mock_get.return_value = performance_service._empty("US", None, None, "max")
        resp = await client.get("/performance/")

    assert resp.status_code == 200
    assert resp.json()["insufficient_data"] is True
    # Never `public` — this is one user's holdings.
    assert resp.headers["cache-control"].startswith("private")


async def test_route_rejects_a_portfolio_the_user_does_not_own(client):
    resp = await client.get("/performance/?portfolio_id=999999")
    assert resp.status_code == 404


async def test_ranges_route_lists_the_windows_the_server_accepts(client):
    resp = await client.get("/performance/ranges")
    assert resp.status_code == 200
    assert resp.json()["ranges"] == list(performance_service.RANGES)
