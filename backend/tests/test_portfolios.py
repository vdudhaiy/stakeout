"""Multiple named portfolios per market.

The motivating case is test_same_ticker_in_two_portfolios_keeps_separate_fifo:
holding the same stock through two brokers must not share one lot queue, or a
sale from one silently consumes the other's oldest lot and every downstream
figure (cost basis, realized gains, net P&L) describes a position the user
doesn't have.
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from cache import quote_cache
from models.portfolio import AuditEntry, Holding, Portfolio
from schemas.portfolio import BulkPurchaseLot
from services import portfolio_admin_service, portfolio_service

USER_ID = "test-user"
OTHER_USER = "someone-else"


@pytest.fixture(autouse=True)
def _clear_quote_cache():
    quote_cache.clear()
    yield
    quote_cache.clear()


@pytest_asyncio.fixture
async def two_portfolios(db_session):
    """A US "main" (the default) plus a second US portfolio named "Zerodha"."""
    main = await portfolio_admin_service.ensure_default(db_session, USER_ID, "US")
    second = await portfolio_admin_service.create(db_session, USER_ID, "US", "Zerodha")
    return main.id, second.id


async def _buy(session, portfolio_id, ticker, shares, price, date):
    with patch("services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value="Apple Inc."):
        with patch("services.portfolio_service._current_price",
                   new_callable=AsyncMock, return_value=Decimal("200.0")):
            with patch("services.portfolio_service.asyncio.create_task"):
                return await portfolio_service.add_stock_purchase(
                    session, USER_ID, portfolio_id, ticker,
                    shares=shares, bought_at=Decimal(price), date=date,
                )


# ── ensure_default / resolve ─────────────────────────────────────────────────

async def test_ensure_default_creates_main_once(db_session):
    first = await portfolio_admin_service.ensure_default(db_session, USER_ID, "US")
    second = await portfolio_admin_service.ensure_default(db_session, USER_ID, "US")

    assert first.id == second.id
    assert first.name == "main"
    rows = (await db_session.execute(select(Portfolio))).scalars().all()
    assert len(rows) == 1


async def test_ensure_default_is_per_market(db_session):
    us = await portfolio_admin_service.ensure_default(db_session, USER_ID, "US")
    india = await portfolio_admin_service.ensure_default(db_session, USER_ID, "IN")

    assert us.id != india.id
    assert {us.market, india.market} == {"US", "IN"}


async def test_ensure_default_returns_oldest_when_main_was_renamed(db_session):
    original = await portfolio_admin_service.ensure_default(db_session, USER_ID, "US")
    await portfolio_admin_service.rename(db_session, original, "Primary")
    await portfolio_admin_service.create(db_session, USER_ID, "US", "Secondary")

    # "Default" is the first portfolio created, not whatever is called "main".
    assert (await portfolio_admin_service.ensure_default(db_session, USER_ID, "US")).id == original.id


async def test_resolve_rejects_another_users_portfolio(db_session):
    theirs = await portfolio_admin_service.ensure_default(db_session, OTHER_USER, "US")

    with pytest.raises(ValueError, match="not found"):
        await portfolio_admin_service.resolve(db_session, USER_ID, theirs.id)


async def test_resolve_falls_back_to_market_default(db_session):
    mine = await portfolio_admin_service.ensure_default(db_session, USER_ID, "IN")
    resolved = await portfolio_admin_service.resolve(db_session, USER_ID, None, "IN")
    assert resolved.id == mine.id


async def test_resolve_rejects_market_mismatch(db_session):
    us = await portfolio_admin_service.ensure_default(db_session, USER_ID, "US")
    with pytest.raises(ValueError, match="market"):
        await portfolio_admin_service.resolve(db_session, USER_ID, us.id, "IN")


# ── create / rename / delete ─────────────────────────────────────────────────

async def test_create_rejects_duplicate_name_case_insensitively(db_session):
    await portfolio_admin_service.create(db_session, USER_ID, "US", "Zerodha")
    with pytest.raises(FileExistsError):
        await portfolio_admin_service.create(db_session, USER_ID, "US", "  zerodha ")


async def test_same_name_allowed_in_different_markets(db_session):
    a = await portfolio_admin_service.create(db_session, USER_ID, "US", "Broker")
    b = await portfolio_admin_service.create(db_session, USER_ID, "IN", "Broker")
    assert a.id != b.id


async def test_create_rejects_blank_and_overlong_names(db_session):
    with pytest.raises(ValueError, match="empty"):
        await portfolio_admin_service.create(db_session, USER_ID, "US", "   ")
    with pytest.raises(ValueError, match="longer than"):
        await portfolio_admin_service.create(db_session, USER_ID, "US", "x" * 41)


async def test_rename_to_its_own_name_is_allowed(db_session):
    p = await portfolio_admin_service.create(db_session, USER_ID, "US", "Zerodha")
    renamed = await portfolio_admin_service.rename(db_session, p, "ZERODHA")
    assert renamed.name == "ZERODHA"


async def test_rename_rejects_a_name_already_taken(db_session):
    await portfolio_admin_service.create(db_session, USER_ID, "US", "Zerodha")
    other = await portfolio_admin_service.create(db_session, USER_ID, "US", "IBKR")
    with pytest.raises(FileExistsError):
        await portfolio_admin_service.rename(db_session, other, "Zerodha")


async def test_delete_removes_holdings_and_audit_entries(db_session, two_portfolios):
    _main_id, second_id = two_portfolios
    await _buy(db_session, second_id, "AAPL", 10, "150.0", "2024-01-01")

    second = await portfolio_admin_service.resolve(db_session, USER_ID, second_id)
    await portfolio_admin_service.delete(db_session, second)

    assert (await db_session.execute(
        select(Holding).where(Holding.portfolio_id == second_id)
    )).scalar_one_or_none() is None
    # Audit rows pointing at deleted holdings would sit un-undoable at the top
    # of the undo stack, so they go with the portfolio.
    assert (await db_session.execute(
        select(AuditEntry).where(AuditEntry.portfolio_id == second_id)
    )).scalar_one_or_none() is None


async def test_delete_refuses_the_markets_last_portfolio(db_session):
    only = await portfolio_admin_service.ensure_default(db_session, USER_ID, "US")
    with pytest.raises(ValueError, match="only"):
        await portfolio_admin_service.delete(db_session, only)


async def test_delete_leaves_the_other_markets_portfolios_alone(db_session, two_portfolios):
    _main_id, second_id = two_portfolios
    india = await portfolio_admin_service.ensure_default(db_session, USER_ID, "IN")

    second = await portfolio_admin_service.resolve(db_session, USER_ID, second_id)
    await portfolio_admin_service.delete(db_session, second)

    assert (await db_session.execute(
        select(Portfolio).where(Portfolio.id == india.id)
    )).scalar_one_or_none() is not None


# ── the point of the whole feature ───────────────────────────────────────────

async def test_same_ticker_in_two_portfolios_keeps_separate_fifo(db_session, two_portfolios):
    """Selling from one portfolio must not consume the other's oldest lot."""
    main_id, second_id = two_portfolios

    await _buy(db_session, main_id, "AAPL", 100, "100.0", "2024-01-01")     # cheap, older
    await _buy(db_session, second_id, "AAPL", 100, "200.0", "2024-02-01")   # pricier, newer

    with patch("services.portfolio_service._current_price",
               new_callable=AsyncMock, return_value=Decimal("300.0")):
        sold = await portfolio_service.sell_stock_shares(
            db_session, USER_ID, second_id, "AAPL",
            shares=50, sold_at=Decimal("250.0"), date="2024-03-01",
        )

    # FIFO inside the second portfolio only: 50 @ $200 -> $50/share realized.
    assert float(sold.total_earned) == pytest.approx(50 * 50.0)

    with patch("services.portfolio_service._current_price",
               new_callable=AsyncMock, return_value=Decimal("300.0")):
        untouched = await portfolio_service.get_stock_holding(db_session, main_id, "AAPL")

    assert untouched.shares == 100
    assert float(untouched.average_cost) == pytest.approx(100.0)
    assert float(untouched.total_earned) == pytest.approx(0.0)


async def test_two_portfolios_can_hold_the_same_ticker(db_session, two_portfolios):
    main_id, second_id = two_portfolios
    await _buy(db_session, main_id, "AAPL", 5, "100.0", "2024-01-01")
    await _buy(db_session, second_id, "AAPL", 7, "110.0", "2024-01-01")

    rows = (await db_session.execute(select(Holding).where(Holding.ticker == "AAPL"))).scalars().all()
    assert {r.portfolio_id for r in rows} == {main_id, second_id}
    assert sorted(r.shares for r in rows) == [5, 7]


# ── aggregates ───────────────────────────────────────────────────────────────

async def test_combined_totals_are_the_sum_of_the_per_portfolio_ones(db_session, two_portfolios):
    main_id, second_id = two_portfolios
    await _buy(db_session, main_id, "AAPL", 10, "100.0", "2024-01-01")
    await _buy(db_session, second_id, "AAPL", 20, "150.0", "2024-01-01")

    result = await portfolio_service.get_portfolio(
        db_session, USER_ID, "US", prices={"AAPL": Decimal("200.0")},
    )

    assert [p.id for p in result.portfolios] == [main_id, second_id]
    assert float(result.total_invested) == pytest.approx(
        sum(float(p.total_invested) for p in result.portfolios)
    )
    assert float(result.portfolio_value) == pytest.approx(
        sum(float(p.portfolio_value) for p in result.portfolios)
    )
    assert float(result.net_profit_loss) == pytest.approx(
        sum(float(p.net_profit_loss) for p in result.portfolios)
    )
    # 10*100 + 20*150 = 4000 invested; 30 shares @ 200 = 6000
    assert float(result.total_invested) == pytest.approx(4000.0)
    assert float(result.portfolio_value) == pytest.approx(6000.0)


async def test_each_holding_reports_the_portfolio_it_belongs_to(db_session, two_portfolios):
    main_id, second_id = two_portfolios
    await _buy(db_session, main_id, "AAPL", 1, "100.0", "2024-01-01")
    await _buy(db_session, second_id, "AAPL", 2, "100.0", "2024-01-01")

    result = await portfolio_service.get_portfolio(
        db_session, USER_ID, "US", prices={"AAPL": Decimal("100.0")},
    )
    assert {h.portfolio_id for h in result.holdings} == {main_id, second_id}


async def test_an_empty_portfolio_still_gets_a_zeroed_stats_row(db_session, two_portfolios):
    main_id, second_id = two_portfolios
    await _buy(db_session, main_id, "AAPL", 1, "100.0", "2024-01-01")

    result = await portfolio_service.get_portfolio(
        db_session, USER_ID, "US", prices={"AAPL": Decimal("100.0")},
    )
    empty = next(p for p in result.portfolios if p.id == second_id)
    assert float(empty.portfolio_value) == 0.0
    assert float(empty.total_invested) == 0.0
    assert empty.total_shares == 0


async def test_scoping_to_one_portfolio_excludes_the_other(db_session, two_portfolios):
    main_id, second_id = two_portfolios
    await _buy(db_session, main_id, "AAPL", 10, "100.0", "2024-01-01")
    await _buy(db_session, second_id, "MSFT", 5, "300.0", "2024-01-01")

    result = await portfolio_service.get_portfolio(
        db_session, USER_ID, "US",
        prices={"AAPL": Decimal("100.0"), "MSFT": Decimal("300.0")},
        portfolio_id=main_id,
    )
    assert [h.ticker for h in result.holdings] == ["AAPL"]
    assert [p.id for p in result.portfolios] == [main_id]


async def test_price_is_fetched_once_for_a_ticker_held_twice(db_session, two_portfolios):
    main_id, second_id = two_portfolios
    await _buy(db_session, main_id, "AAPL", 1, "100.0", "2024-01-01")
    await _buy(db_session, second_id, "AAPL", 1, "100.0", "2024-01-01")

    with patch("services.portfolio_service.get_market_status",
               new_callable=AsyncMock, return_value=False):
        with patch("services.portfolio_service._current_price",
                   new_callable=AsyncMock, return_value=Decimal("150.0")) as mock_price:
            await portfolio_service.get_portfolio(db_session, USER_ID, "US")

    assert mock_price.await_count == 1


# ── dividends ────────────────────────────────────────────────────────────────

async def test_dividend_sync_throttle_is_per_portfolio(db_session, two_portfolios):
    """Syncing one portfolio's AAPL must not lock the other's out for the day."""
    main_id, second_id = two_portfolios
    await _buy(db_session, main_id, "AAPL", 10, "100.0", "2024-01-01")
    await _buy(db_session, second_id, "AAPL", 10, "100.0", "2024-01-01")

    with patch("services.portfolio_service._sync_dividends",
               new_callable=AsyncMock, return_value=0) as mock_sync:
        await portfolio_service.sync_dividends(db_session, USER_ID, main_id, "AAPL")
        await portfolio_service.sync_dividends(db_session, USER_ID, second_id, "AAPL")
        await portfolio_service.sync_dividends(db_session, USER_ID, main_id, "AAPL")

    # Two distinct portfolios synced; the repeat of the first was throttled.
    assert mock_sync.await_count == 2


# ── undo across the migration boundary ───────────────────────────────────────

async def test_undo_works_for_a_legacy_audit_row_without_a_portfolio(db_session, pid):
    """Rows written before portfolios existed have portfolio_id NULL; the
    migration put their holdings in the market default, so undo looks there."""
    holding = await _buy(db_session, pid, "AAPL", 10, "100.0", "2024-01-01")
    assert holding.shares == 10

    entry = (await db_session.execute(
        select(AuditEntry).order_by(AuditEntry.id.desc()).limit(1)
    )).scalar_one()
    entry.portfolio_id = None  # simulate a pre-009 row
    await db_session.commit()

    result = await portfolio_service.undo_last_action(db_session, USER_ID)
    assert result.ticker == "AAPL"
    assert (await db_session.execute(
        select(Holding).where(Holding.ticker == "AAPL")
    )).scalar_one_or_none() is None


async def test_undo_targets_the_right_portfolio(db_session, two_portfolios):
    main_id, second_id = two_portfolios
    await _buy(db_session, main_id, "AAPL", 10, "100.0", "2024-01-01")
    await _buy(db_session, second_id, "AAPL", 7, "100.0", "2024-01-01")

    await portfolio_service.undo_last_action(db_session, USER_ID)

    remaining = (await db_session.execute(select(Holding).where(Holding.ticker == "AAPL"))).scalars().all()
    assert [(h.portfolio_id, h.shares) for h in remaining] == [(main_id, 10)]


# ── HTTP surface ─────────────────────────────────────────────────────────────

async def test_list_portfolios_bootstraps_a_default_per_market(client):
    resp = await client.get("/portfolios/")
    assert resp.status_code == 200
    body = resp.json()
    assert {p["market"] for p in body} == {"US", "IN"}
    assert {p["name"] for p in body} == {"main"}


async def test_create_rename_delete_round_trip(client):
    created = await client.post("/portfolios/", json={"market": "US", "name": "Zerodha"})
    assert created.status_code == 201
    pid = created.json()["id"]

    dupe = await client.post("/portfolios/", json={"market": "US", "name": "zerodha"})
    assert dupe.status_code == 409

    renamed = await client.patch(f"/portfolios/{pid}", json={"name": "IBKR"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "IBKR"

    deleted = await client.delete(f"/portfolios/{pid}")
    assert deleted.status_code == 200

    listed = await client.get("/portfolios/?market=US")
    assert [p["name"] for p in listed.json()] == ["main"]


async def test_delete_last_portfolio_in_market_is_rejected(client):
    listed = await client.get("/portfolios/?market=US")
    only = listed.json()[0]["id"]
    resp = await client.delete(f"/portfolios/{only}")
    assert resp.status_code == 400


async def test_routes_reject_a_portfolio_id_owned_by_someone_else(client, db_session):
    theirs = await portfolio_admin_service.ensure_default(db_session, OTHER_USER, "US")

    assert (await client.get(f"/portfolio/?portfolio_id={theirs.id}")).status_code == 404
    assert (await client.patch(f"/portfolios/{theirs.id}", json={"name": "Mine"})).status_code == 404
    assert (await client.delete(f"/portfolios/{theirs.id}")).status_code == 404


async def test_unknown_portfolio_id_is_404(client):
    assert (await client.get("/portfolio/?portfolio_id=999999")).status_code == 404
