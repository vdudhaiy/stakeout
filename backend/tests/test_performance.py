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


def _mock_data(
    closes: dict[str, dict[date, float]],
    index: dict[date, float],
    *,
    archive_behind: bool = False,
):
    """Patch every external the service reads.

    The archive top-up is patched out too: it would otherwise reach for the
    module-level SessionLocal (which has no tables here) on every test.
    `archive_behind` drives the "the archive hasn't caught up" branch.
    """
    return (
        patch("services.performance_service.market_data_service.get_closes",
              new_callable=AsyncMock, return_value=closes),
        patch("services.performance_service.index_service.get_history",
              new_callable=AsyncMock, return_value=index),
        patch("services.performance_service.stock_service.ensure_archive_current",
              new_callable=AsyncMock, return_value=False),
        patch("services.performance_service.stock_service.archive_is_behind",
              new_callable=AsyncMock, return_value=archive_behind),
    )


# ── empty / degenerate cases ──────────────────────────────────────────────

async def test_no_holdings_reports_insufficient_data(db_session, pid):
    closes, index, topup, behind = _mock_data({}, {})
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.insufficient_data is True
    assert result.points == []
    assert result.portfolio.money_weighted is None


async def test_a_holding_with_no_archive_history_is_excluded_not_silently_dropped(db_session, pid):
    """The totals here would otherwise disagree with the Portfolio page for
    no visible reason."""
    day = date(2024, 1, 1)
    await _add_holding(db_session, pid, "OBSCURE", transactions=[(False, day, 10, 5.0)])

    closes, index, topup, behind = _mock_data({}, {})
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.insufficient_data is True
    assert result.excluded_tickers == ["OBSCURE"]


async def test_a_single_day_of_history_is_not_enough_to_chart(db_session, pid):
    day = date(2024, 1, 1)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, day, 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": {day: 100.0}}, {day: 4000.0})
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.insufficient_data is True


# ── value series ──────────────────────────────────────────────────────────

async def test_value_series_tracks_shares_times_price(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": _ramp(axis, 100.0, 140.0)}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
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

    closes, index, topup, behind = _mock_data(
        {"AAPL": _flat(axis, 100.0), "MSFT": _flat(axis, 200.0)}, _flat(axis, 4000.0),
    )
    with closes, index, topup, behind:
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

    closes, index, topup, behind = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    values = [p.value for p in result.points]
    assert values[2] == pytest.approx(1000.0)
    assert values[-1] == pytest.approx(600.0)


async def test_a_missing_price_bar_holds_the_last_known_price(db_session, pid):
    """A day with no published bar is not a day the holding was worthless."""
    axis = _days(date(2024, 1, 1), 4)
    prices = {axis[0]: 100.0, axis[1]: 100.0, axis[3]: 120.0}  # axis[2] missing
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": prices, "OTHER": _flat(axis, 1.0)}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
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

    closes, index, topup, behind = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.points[-1].value == pytest.approx(2000.0)
    assert result.portfolio.time_weighted == pytest.approx(0.0, abs=1e-9)
    assert result.net_invested == pytest.approx(Decimal("2000"))


async def test_time_weighted_return_matches_the_price_move(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": _ramp(axis, 100.0, 150.0)}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.portfolio.time_weighted == pytest.approx(0.50, abs=1e-9)


async def test_dividends_are_income_not_a_contribution(db_session, pid):
    """Counting a dividend as money added would make income look like a
    deposit and quietly depress every return figure on the page."""
    # Long enough to clear the annualization floor — a money-weighted return
    # is withheld below a month, and this test is about its sign.
    axis = _days(date(2024, 1, 1), 40)
    await _add_holding(
        db_session, pid, "AAPL",
        transactions=[(False, axis[0], 10, 100.0)],
        dividends=[(axis[2], 2.0, 10)],
    )

    closes, index, topup, behind = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
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

    closes, index, topup, behind = _mock_data({"AAPL": _flat(axis, 100.0)}, index_levels)
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.benchmark_final_value == pytest.approx(Decimal("3000"))
    assert result.net_invested == pytest.approx(Decimal("2000"))


async def test_beating_the_benchmark_shows_positive_value_added(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    # Stock doubles; index is flat.
    closes, index, topup, behind = _mock_data({"AAPL": _ramp(axis, 100.0, 200.0)}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.current_value == pytest.approx(Decimal("2000"))
    assert result.benchmark_final_value == pytest.approx(Decimal("1000"))
    assert result.value_added == pytest.approx(Decimal("1000"))


async def test_lagging_the_benchmark_shows_negative_value_added(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": _flat(axis, 100.0)}, _ramp(axis, 100.0, 200.0))
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.benchmark_final_value == pytest.approx(Decimal("2000"))
    assert result.value_added == pytest.approx(Decimal("-1000"))


async def test_both_growth_series_start_at_the_same_base(db_session, pid):
    """They share a base so the two lines are directly comparable on one chart."""
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": _ramp(axis, 100.0, 150.0)}, _ramp(axis, 100.0, 110.0))
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.points[0].portfolio_index == pytest.approx(100.0)
    assert result.points[0].benchmark_index == pytest.approx(100.0)
    assert result.points[-1].portfolio_index == pytest.approx(150.0, abs=0.01)
    assert result.points[-1].benchmark_index == pytest.approx(110.0, abs=0.01)


async def test_an_unavailable_benchmark_degrades_rather_than_drawing_a_fake_line(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": _flat(axis, 100.0)}, {})
    with closes, index, topup, behind:
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

    closes, index, topup, behind = _mock_data({"TCS.NS": _flat(axis, 100.0)}, _flat(axis, 22000.0))
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "IN")

    assert result.benchmark_symbol == "^NSEI"
    assert result.benchmark_name == "NIFTY 50"
    assert result.currency == "INR"


# ── ranges and caching ────────────────────────────────────────────────────

async def test_range_narrows_the_window(db_session, pid):
    axis = _days(date.today() - timedelta(days=800), 800)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
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

    closes, index, topup, behind = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
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

    closes, index, topup, behind = _mock_data({"AAPL": prices}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
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

    closes, index, topup, behind = _mock_data({"AAPL": prices}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
        windowed = await performance_service.get_performance(db_session, USER_ID, "US", range_key="1y")

    assert windowed.points[0].benchmark_value == pytest.approx(windowed.points[0].value)
    # Flat index and flat prices inside the window — neither path gained.
    assert windowed.value_added == pytest.approx(Decimal("0"), abs=Decimal("0.01"))


async def test_an_unknown_range_falls_back_to_max_rather_than_erroring(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US", range_key="nonsense")

    assert result.range == "max"


async def test_a_second_request_is_served_from_cache(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes as mock_closes, index, topup, behind:
        await performance_service.get_performance(db_session, USER_ID, "US")
        await performance_service.get_performance(db_session, USER_ID, "US")

    assert mock_closes.await_count == 1


async def test_invalidate_forces_a_recompute(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes as mock_closes, index, topup, behind:
        await performance_service.get_performance(db_session, USER_ID, "US")
        performance_service.invalidate(USER_ID)
        await performance_service.get_performance(db_session, USER_ID, "US")

    assert mock_closes.await_count == 2


async def test_one_users_cache_is_not_dropped_by_anothers_trade(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes as mock_closes, index, topup, behind:
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


# ── stale archive ─────────────────────────────────────────────────────────
# The bug this section exists for: four positions bought over a weekend, all
# priced fine on the Portfolio page, and the panel insisting there was no
# history. The archive had been filled up to the Friday before the first buy
# and never advanced, because only the Tracker's fetch() ever topped it up.

async def test_an_archive_that_stops_before_the_first_buy_reports_itself_as_stale(db_session, pid):
    """Not "you have no history" — the user has plenty, we just hadn't
    downloaded it. The two need opposite messages."""
    axis = _days(date(2024, 1, 1), 10)
    bought = axis[-1] + timedelta(days=2)          # after every archived bar
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, bought, 10, 100.0)])

    closes, index, topup, behind = _mock_data(
        {"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0), archive_behind=True,
    )
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.insufficient_data is True
    assert result.stale_archive is True
    # Not excluded: the ticker *is* in the archive, just not recently enough.
    assert result.excluded_tickers == []


async def test_a_genuinely_new_portfolio_is_not_blamed_on_the_archive(db_session, pid):
    axis = _days(date(2024, 1, 1), 10)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[-1], 10, 100.0)])

    closes, index, topup, behind = _mock_data(
        {"AAPL": {axis[-1]: 100.0}}, _flat(axis, 4000.0), archive_behind=False,
    )
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.insufficient_data is True
    assert result.stale_archive is False


async def test_a_healthy_chart_never_claims_a_stale_archive(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.insufficient_data is False
    assert result.stale_archive is False


async def test_the_archive_is_topped_up_for_every_held_ticker_before_charting(db_session, pid):
    """The Portfolio page prices from live quotes and never advances the
    archive, so this panel has to do it or it reads a frozen one."""
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])
    await _add_holding(db_session, pid, "MSFT", transactions=[(False, axis[0], 5, 200.0)])

    closes, index, topup, behind = _mock_data(
        {"AAPL": _flat(axis, 100.0), "MSFT": _flat(axis, 200.0)}, _flat(axis, 4000.0),
    )
    with closes, index, topup as mock_topup, behind:
        await performance_service.get_performance(db_session, USER_ID, "US")

    assert {c.args[0] for c in mock_topup.await_args_list} == {"AAPL", "MSFT"}


# ── benchmark unavailable ─────────────────────────────────────────────────
# A missing index used to be treated as one worth $0, so value_added came out
# as the entire portfolio and the page announced a win it never measured.

async def test_an_unavailable_benchmark_reports_no_comparison_rather_than_a_fake_one(db_session, pid):
    axis = _days(date(2024, 1, 1), 40)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": _ramp(axis, 100.0, 120.0)}, {})
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.benchmark_available is False
    assert result.benchmark_final_value is None
    assert result.value_added is None
    # The portfolio's own figures are still perfectly measurable.
    assert result.current_value == pytest.approx(Decimal("1200"))


async def test_an_available_benchmark_still_reports_a_comparison(db_session, pid):
    axis = _days(date(2024, 1, 1), 40)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": _flat(axis, 100.0)}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.benchmark_available is True
    assert result.value_added == pytest.approx(Decimal("0"))


# ── short windows ─────────────────────────────────────────────────────────

async def test_a_two_day_old_portfolio_withholds_its_annualized_figures(db_session, pid):
    """XIRR is an annual rate by construction. Two days at +0.6% annualizes to
    several thousand percent — arithmetically right, completely useless."""
    axis = _days(date(2024, 1, 1), 3)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": _ramp(axis, 100.0, 100.6)}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.portfolio.money_weighted is None
    assert result.portfolio.annualized is None
    # The cumulative figure is honest over any span, so it stays.
    assert result.portfolio.time_weighted == pytest.approx(0.006, abs=1e-4)


async def test_a_long_enough_window_still_reports_a_money_weighted_return(db_session, pid):
    axis = _days(date(2024, 1, 1), 200)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    closes, index, topup, behind = _mock_data({"AAPL": _ramp(axis, 100.0, 150.0)}, _flat(axis, 4000.0))
    with closes, index, topup, behind:
        result = await performance_service.get_performance(db_session, USER_ID, "US")

    assert result.portfolio.money_weighted is not None
    assert result.portfolio.annualized is not None


# ── backfill ──────────────────────────────────────────────────────────────
# ensure_archive_current deliberately skips a ticker with an empty archive —
# there is nothing to extend. That is exactly the state a holding lands in
# when its first-buy backfill lost a race with a rate limit, and nothing ever
# retried it. This is the user-triggered retry.

async def test_backfill_archives_only_the_holdings_that_have_no_history(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])
    await _add_holding(db_session, pid, "MSFT", transactions=[(False, axis[0], 5, 200.0)])

    with patch("services.performance_service.market_data_service.get_closes",
               new_callable=AsyncMock, return_value={"MSFT": _flat(axis, 200.0)}):
        with patch("services.performance_service.stock_service.add_stock",
                   new_callable=AsyncMock) as mock_add:
            # Success is decided by re-reading the archive, not by add_stock
            # returning without raising.
            with patch("services.performance_service.market_data_service.has_data",
                       new_callable=AsyncMock, return_value=True):
                archived = await performance_service.backfill_missing_archives(
                    db_session, USER_ID, "US",
                )

    assert archived == ["AAPL"]
    mock_add.assert_awaited_once_with("AAPL")


async def test_backfill_keeps_going_when_one_ticker_fails(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])
    await _add_holding(db_session, pid, "MSFT", transactions=[(False, axis[0], 5, 200.0)])

    async def flaky(ticker):
        if ticker == "AAPL":
            raise ValueError("rate limited")

    async def landed(ticker):
        return ticker != "AAPL"

    with patch("services.performance_service.market_data_service.get_closes",
               new_callable=AsyncMock, return_value={}):
        with patch("services.performance_service.stock_service.add_stock",
                   new_callable=AsyncMock, side_effect=flaky):
            with patch("services.performance_service.market_data_service.has_data",
                       new_callable=AsyncMock, side_effect=landed):
                archived = await performance_service.backfill_missing_archives(
                    db_session, USER_ID, "US",
                )

    assert archived == ["MSFT"]   # the failure stays reported as excluded


async def test_backfill_is_a_no_op_for_a_fully_archived_portfolio(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    with patch("services.performance_service.market_data_service.get_closes",
               new_callable=AsyncMock, return_value={"AAPL": _flat(axis, 100.0)}):
        with patch("services.performance_service.stock_service.add_stock",
                   new_callable=AsyncMock) as mock_add:
            archived = await performance_service.backfill_missing_archives(
                db_session, USER_ID, "US",
            )

    assert archived == []
    mock_add.assert_not_called()   # nothing missing, so nothing is even attempted


# ── route ─────────────────────────────────────────────────────────────────

async def test_refresh_triggers_a_backfill_and_bypasses_the_cache(client):
    with patch("routers.performance.performance_service.get_performance",
               new_callable=AsyncMock) as mock_get:
        mock_get.return_value = performance_service._empty("US", None, None, "max")
        with patch("routers.performance.performance_service.backfill_missing_archives",
                   new_callable=AsyncMock, return_value=["AAPL"]) as mock_backfill:
            with patch("routers.performance.performance_service.invalidate") as mock_invalidate:
                resp = await client.get("/performance/?refresh=true")

    assert resp.status_code == 200
    mock_backfill.assert_awaited_once()
    mock_invalidate.assert_called_once()


async def test_a_plain_load_does_not_backfill(client):
    with patch("routers.performance.performance_service.get_performance",
               new_callable=AsyncMock) as mock_get:
        mock_get.return_value = performance_service._empty("US", None, None, "max")
        with patch("routers.performance.performance_service.backfill_missing_archives",
                   new_callable=AsyncMock) as mock_backfill:
            resp = await client.get("/performance/")

    assert resp.status_code == 200
    mock_backfill.assert_not_called()


async def test_refresh_is_rate_limited_per_user(client):
    """Each miss is a multi-year download, so this can't be a free retry loop."""
    from rate_limit import performance_backfill_limiter

    with patch("routers.performance.performance_service.get_performance",
               new_callable=AsyncMock) as mock_get:
        mock_get.return_value = performance_service._empty("US", None, None, "max")
        with patch("routers.performance.performance_service.backfill_missing_archives",
                   new_callable=AsyncMock, return_value=[]):
            statuses = []
            for _ in range(performance_backfill_limiter._max + 2):
                statuses.append((await client.get("/performance/?refresh=true")).status_code)

    assert statuses[0] == 200
    assert statuses[-1] == 429


# ── backfill decides by the archive, not by exceptions ────────────────────
# add_stock does more than archive prices, so it can raise *after* the rows
# have landed. Reporting that as a failure left a ticker looking unfetchable
# when it had in fact just been fetched — which is what made "Fetch now" look
# like it did nothing.

async def test_backfill_counts_a_ticker_whose_rows_landed_despite_an_error(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    with patch("services.performance_service.market_data_service.get_closes",
               new_callable=AsyncMock, return_value={}):
        with patch("services.performance_service.stock_service.add_stock",
                   new_callable=AsyncMock, side_effect=ValueError("details scrape failed")):
            with patch("services.performance_service.market_data_service.has_data",
                       new_callable=AsyncMock, return_value=True):
                archived = await performance_service.backfill_missing_archives(
                    db_session, USER_ID, "US",
                )

    assert archived == ["AAPL"]


async def test_backfill_reports_a_ticker_whose_rows_never_landed(db_session, pid):
    axis = _days(date(2024, 1, 1), 5)
    await _add_holding(db_session, pid, "AAPL", transactions=[(False, axis[0], 10, 100.0)])

    with patch("services.performance_service.market_data_service.get_closes",
               new_callable=AsyncMock, return_value={}):
        with patch("services.performance_service.stock_service.add_stock",
                   new_callable=AsyncMock, side_effect=ValueError("rate limited")):
            with patch("services.performance_service.market_data_service.has_data",
                       new_callable=AsyncMock, return_value=False):
                archived = await performance_service.backfill_missing_archives(
                    db_session, USER_ID, "US",
                )

    assert archived == []
