"""Portfolio CRUD and resolution.

A user has one or more named portfolios per market. This module owns creating,
renaming and deleting them, plus the two lookups every other portfolio code
path starts with:

  - ``resolve`` turns a caller-supplied ``portfolio_id`` (or ``None``) into a
    Portfolio the caller is actually allowed to touch. **Every route that
    accepts a portfolio_id from the client must go through it** — the id is a
    bare integer, so without the ownership check a user could write into
    someone else's portfolio by guessing.
  - ``ensure_default`` creates the market's "main" portfolio on demand. There
    is no first-login hook anywhere in the app (Supabase users never sign up
    through this backend), so default portfolios are created lazily instead of
    at account creation, and every entry point must tolerate them not existing
    yet.

Kept separate from portfolio_service.py, which is already large and is about
positions and FIFO rather than the containers holding them.
"""

import datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from markets import VALID_MARKETS, normalize_market
from models.portfolio import AuditEntry, Portfolio, portfolio_name_key

DEFAULT_PORTFOLIO_NAME = "main"

# Long enough for "Zerodha — long term", short enough to keep the tab bar sane.
MAX_NAME_LENGTH = 40


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def validate_name(name: str) -> str:
    """Returns the cleaned display name, or raises ValueError."""
    cleaned = " ".join((name or "").split())  # collapse internal runs of whitespace too
    if not cleaned:
        raise ValueError("Portfolio name cannot be empty.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise ValueError(f"Portfolio name cannot be longer than {MAX_NAME_LENGTH} characters.")
    return cleaned


async def _by_name(session: AsyncSession, user_id: str, market: str, name_key: str) -> Portfolio | None:
    result = await session.execute(
        select(Portfolio).where(
            Portfolio.user_id == user_id,
            Portfolio.market == market,
            Portfolio.name_key == name_key,
        )
    )
    return result.scalar_one_or_none()


async def ensure_default(session: AsyncSession, user_id: str, market: str | None = None) -> Portfolio:
    """The market's default portfolio, creating "main" if the user has none.

    Idempotent and safe to call on every request. "Default" means the
    lowest-id portfolio in the market rather than the one literally named
    "main", so a user who renames or deletes it still has a sensible default.

    Commits when it creates one, so read-only paths (which never commit) don't
    discard it. Callers must therefore resolve their portfolio *before* making
    other pending changes on the session — which every route does, since the
    portfolio is what the rest of the request operates on.
    """
    market = normalize_market(market)
    result = await session.execute(
        select(Portfolio)
        .where(Portfolio.user_id == user_id, Portfolio.market == market)
        .order_by(Portfolio.id)
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    portfolio = Portfolio(
        user_id=user_id, market=market,
        name=DEFAULT_PORTFOLIO_NAME, name_key=portfolio_name_key(DEFAULT_PORTFOLIO_NAME),
        created_at=_now(),
    )
    session.add(portfolio)
    try:
        await session.commit()
    except IntegrityError:
        # Two first-ever requests raced and both tried to create "main".
        # uq_portfolios_user_market_name means exactly one won — take theirs.
        await session.rollback()
        winner = await _by_name(session, user_id, market, portfolio_name_key(DEFAULT_PORTFOLIO_NAME))
        if winner is None:  # pragma: no cover — only if the constraint is missing
            raise
        return winner
    await session.refresh(portfolio)
    return portfolio


async def resolve(
    session: AsyncSession, user_id: str, portfolio_id: int | None, market: str | None = None,
) -> Portfolio:
    """The portfolio a request should act on.

    With no `portfolio_id`, falls back to `market`'s default — this is what
    keeps every pre-existing client (and the AI chat context) working unchanged.
    With one, verifies it belongs to `user_id` before returning it.
    """
    if portfolio_id is None:
        return await ensure_default(session, user_id, market)

    result = await session.execute(select(Portfolio).where(Portfolio.id == portfolio_id))
    portfolio = result.scalar_one_or_none()
    # Same message either way: a wrong id and someone else's id are
    # indistinguishable to the caller, so a probe learns nothing.
    if portfolio is None or portfolio.user_id != user_id:
        raise ValueError(f"Portfolio {portfolio_id} not found.")
    if market is not None and portfolio.market != normalize_market(market):
        raise ValueError(
            f"Portfolio '{portfolio.name}' belongs to the {portfolio.market} market, "
            f"not {normalize_market(market)}."
        )
    return portfolio


async def list_for_user(
    session: AsyncSession, user_id: str, market: str | None = None,
) -> list[Portfolio]:
    """Every portfolio the user has, ordered by creation (id).

    Ensures the requested market's default exists first — for `market=None`,
    both markets' defaults — so a brand-new account always sees tabs.
    """
    for m in ([normalize_market(market)] if market is not None else VALID_MARKETS):
        await ensure_default(session, user_id, m)

    query = select(Portfolio).where(Portfolio.user_id == user_id)
    if market is not None:
        query = query.where(Portfolio.market == normalize_market(market))
    result = await session.execute(query.order_by(Portfolio.id))
    return list(result.scalars().all())


async def create(session: AsyncSession, user_id: str, market: str, name: str) -> Portfolio:
    name = validate_name(name)
    market = normalize_market(market)
    name_key = portfolio_name_key(name)

    # Every account is supposed to have a "main" per market. If the user's
    # first-ever call is a create rather than a list, make sure they still get
    # one — otherwise the new portfolio silently becomes the market's default
    # and can never be deleted.
    await ensure_default(session, user_id, market)

    if await _by_name(session, user_id, market, name_key) is not None:
        raise FileExistsError(f"You already have a portfolio named '{name}' in this market.")

    portfolio = Portfolio(
        user_id=user_id, market=market, name=name, name_key=name_key, created_at=_now(),
    )
    session.add(portfolio)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise FileExistsError(f"You already have a portfolio named '{name}' in this market.")
    await session.refresh(portfolio)
    return portfolio


async def rename(session: AsyncSession, portfolio: Portfolio, name: str) -> Portfolio:
    name = validate_name(name)
    name_key = portfolio_name_key(name)

    clash = await _by_name(session, portfolio.user_id, portfolio.market, name_key)
    if clash is not None and clash.id != portfolio.id:
        raise FileExistsError(f"You already have a portfolio named '{name}' in this market.")

    portfolio.name = name
    portfolio.name_key = name_key
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise FileExistsError(f"You already have a portfolio named '{name}' in this market.")
    await session.refresh(portfolio)
    return portfolio


async def delete(session: AsyncSession, portfolio: Portfolio) -> None:
    """Permanently deletes a portfolio and everything in it.

    Holdings cascade to their transactions and dividends. The portfolio's audit
    entries go too: they reference holdings that no longer exist, so leaving
    them would put un-undoable rows at the top of the user's undo stack.

    Refuses to remove a market's last portfolio — ensure_default would just
    recreate one on the next request, and the UI needs at least one tab.
    """
    count = await session.scalar(
        select(func.count())
        .select_from(Portfolio)
        .where(Portfolio.user_id == portfolio.user_id, Portfolio.market == portfolio.market)
    )
    if (count or 0) <= 1:
        raise ValueError(
            f"'{portfolio.name}' is your only {portfolio.market} portfolio — "
            "create another one before deleting it."
        )

    await session.execute(sa_delete(AuditEntry).where(AuditEntry.portfolio_id == portfolio.id))
    await session.delete(portfolio)
    await session.commit()
