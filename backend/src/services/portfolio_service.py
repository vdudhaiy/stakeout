import asyncio
import datetime
import logging
import math
from decimal import Decimal

import yfinance as yf
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from yfinance.exceptions import YFRateLimitError

from cache import dividend_sync_cache, quote_cache
from markets import MARKET_META, apply_exchange, currency_of, market_of, normalize_market
from models.portfolio import AuditEntry, Dividend, Holding, Transaction, WatchlistEntry
from schemas.portfolio import (
    AuditEntrySummary, BulkPurchaseLot, BulkSaleLot, DividendEntry, PortfolioResponse, PositionAsOf, StockHolding,
    StockPurchaseHistory, UndoResult,
)
from . import market_data_service
from .stock_service import fetch_current, get_market_status, add_stock

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_rate_limited(e: BaseException) -> bool:
    """True if `e` — or the exception it was raised while handling — is a
    yfinance rate limit. add_stock wraps its underlying errors in a plain
    ValueError, so the original type only survives via the implicit exception
    chain Python sets on `raise ... ` inside an `except` block (__context__).
    """
    return isinstance(e, YFRateLimitError) or isinstance(getattr(e, "__context__", None), YFRateLimitError)

async def _validate_and_fetch_name(ticker: str) -> str:
    """Confirms the ticker exists on yfinance and returns a display name.

    Raises ValueError if yfinance returns no history (unknown ticker) — that's
    a real "this ticker doesn't exist" and retrying won't help. A rate limit
    isn't worth retrying immediately either — the window hasn't cleared a
    moment later, so a second attempt is guaranteed to fail too and just adds
    to the block. Any other (genuinely transient) error gets one retry before
    giving up and returning an empty string so the holding can still be
    created without a display name. A holding that ends up unnamed here is
    picked up later by repair_stock_metadata, which backfills it once the
    lookup succeeds.
    """
    def _fetch() -> str:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d")
        if hist.empty:
            raise ValueError(
                f"Ticker '{ticker}' could not be found. "
                "Please check the symbol and try again."
            )
        info = stock.info
        return info.get("shortName") or info.get("longName") or ""

    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            return await asyncio.to_thread(_fetch)
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001
            last_error = e
            if _is_rate_limited(e):
                break
    logger.warning("Name lookup failed for %s; creating holding unnamed: %r", ticker, last_error)
    return ""


async def _current_price(ticker: str, is_market_open: bool | None = None) -> Decimal | None:
    """Best-effort current price for `ticker`, or None if it genuinely could not be fetched.

    Never falls back to 0 — a fabricated $0 price is indistinguishable from a
    real one downstream (stock_value, profit_loss, portfolio totals), and
    would silently misreport a fetch failure as a 100% loss. Callers must
    treat None as "unknown", not "worthless".

    Cached for quote_cache's TTL (60s): get_portfolio calls this once per
    holding on every load, and the portfolio page polls every couple minutes
    — without this, two holdings of the same ticker, two browser tabs, or two
    users watching the same stock each fire their own yfinance request within
    the same window. A failed lookup is cached too (as "unavailable") rather
    than retried on every next holding, since a real outage won't resolve in
    the next few milliseconds anyway; it naturally retries once the TTL
    expires. The 1-tuple wrapper distinguishes "not cached" (None) from
    "cached as unavailable" ((None,)) — quote_cache.get() returns None for both
    a missing key and a value that legitimately *is* None.
    """
    cache_key = f"price:{ticker}"
    cached = quote_cache.get(cache_key)
    if cached is not None:
        return cached[0]

    price: Decimal | None = None
    try:
        response = await fetch_current(yf.Ticker(ticker), is_market_open)
        close = response.data[0].close if response.data else None
        if close is not None and not math.isnan(close):
            price = Decimal(str(close))
    except Exception as e:  # noqa: BLE001
        logger.warning("Archive price fetch failed for %s: %r", ticker, e)

    if price is None:
        # Archive may not exist (e.g. deleted from dashboard) — fetch last close directly.
        try:
            def _direct() -> float | None:
                hist = yf.Ticker(ticker).history(period="5d")
                return float(hist["Close"].iloc[-1]) if not hist.empty else None
            close = await asyncio.to_thread(_direct)
            if close is not None and not math.isnan(close):
                price = Decimal(str(close))
        except Exception as e:  # noqa: BLE001
            logger.warning("Direct price fetch failed for %s: %r", ticker, e)

    quote_cache.set(cache_key, (price,))
    return price


async def _fetch_holding(session: AsyncSession, user_id: str, ticker: str) -> Holding | None:
    result = await session.execute(
        select(Holding).where(Holding.user_id == user_id, Holding.ticker == ticker)
    )
    return result.scalar_one_or_none()


async def _fetch_transactions(session: AsyncSession, holding_id: int) -> list[Transaction]:
    result = await session.execute(
        select(Transaction)
        .where(Transaction.holding_id == holding_id)
        .order_by(Transaction.date)
    )
    return list(result.scalars().all())


async def _fetch_dividends(session: AsyncSession, holding_id: int) -> list[Dividend]:
    result = await session.execute(
        select(Dividend)
        .where(Dividend.holding_id == holding_id)
        .order_by(Dividend.date)
    )
    return list(result.scalars().all())


class _FifoLot:
    """Working copy of a buy lot's FIFO state — never touches the ORM."""

    __slots__ = ("txn", "date", "shares", "bought_at", "shares_remaining")

    def __init__(self, txn: Transaction):
        self.txn = txn
        self.date = txn.date
        self.shares = txn.shares
        self.bought_at = txn.bought_at
        self.shares_remaining = txn.shares


def _fifo_consume(transactions: list[Transaction]) -> tuple[list[_FifoLot], dict[int, float]]:
    """Core FIFO algorithm, pure: consumes buy lots against sells in date order.

    Returns the resulting buy lots (with shares_remaining set) and a map of
    sell transaction id -> FIFO cost per share. Raises ValueError if a sell
    would exceed the buy lots available on or before its date. `transactions`
    must be sorted oldest-first.
    """
    buy_lots = [_FifoLot(t) for t in transactions if not t.sale]
    sell_txns = [t for t in transactions if t.sale]
    sell_cost_per_share: dict[int, float] = {}

    for sell in sell_txns:
        remaining = sell.shares
        fifo_cost = 0  # bare int: stays float or Decimal depending on lot.bought_at's type
        for lot in buy_lots:
            if remaining <= 0:
                break
            if lot.date > sell.date:
                # buy_lots is date-sorted; all subsequent lots are also in the future
                break
            consumed = min(lot.shares_remaining, remaining)
            fifo_cost += consumed * lot.bought_at
            lot.shares_remaining -= consumed
            remaining -= consumed
        if remaining > 0:
            raise ValueError(
                f"Only {sell.shares - remaining} share(s) were available on or before "
                f"{sell.date} — cannot sell {sell.shares}."
            )
        sell_cost_per_share[id(sell)] = fifo_cost / sell.shares

    return buy_lots, sell_cost_per_share


def _replay_fifo(holding: Holding, transactions: list[Transaction]) -> None:
    """Reset shares_remaining on all buy lots and replay all sells in FIFO order.

    Also recalculates bought_at on each sell (FIFO cost of consumed lots) and
    updates holding.shares, holding.sold_shares, holding.average_cost.
    Raises ValueError if sells would exceed buy lots available on or before the
    sell date. Transactions must be sorted oldest-first.
    """
    buy_lots, sell_cost_per_share = _fifo_consume(transactions)

    for lot in buy_lots:
        lot.txn.shares_remaining = lot.shares_remaining
    for sell in transactions:
        if sell.sale:
            sell.bought_at = sell_cost_per_share[id(sell)]

    holding.shares = sum(lot.shares_remaining for lot in buy_lots)
    holding.sold_shares = sum(t.shares for t in transactions if t.sale)
    total_shares = sum(lot.shares for lot in buy_lots)
    total_cost = sum(lot.shares * lot.bought_at for lot in buy_lots)
    holding.average_cost = total_cost / total_shares if total_shares > 0 else 0


def _position_as_of(ticker: str, transactions: list[Transaction], as_of: str) -> "PositionAsOf":
    """Read-only FIFO replay bounded to transactions on or before `as_of`.

    Computed purely from the transaction log — never mutates or commits ORM
    state, so it's safe to call from a GET path alongside the live holding.
    """
    relevant = sorted((t for t in transactions if t.date <= as_of), key=lambda t: t.date)
    buy_lots, sell_cost_per_share = _fifo_consume(relevant)

    shares = sum(lot.shares_remaining for lot in buy_lots)
    sold_shares = sum(t.shares for t in relevant if t.sale)
    total_shares = sum(lot.shares for lot in buy_lots)
    total_cost = sum(lot.shares * lot.bought_at for lot in buy_lots)
    average_cost = total_cost / total_shares if total_shares > 0 else 0
    cost_basis = sum(lot.shares_remaining * lot.bought_at for lot in buy_lots)
    realized_gains = sum(
        (t.sold_at - sell_cost_per_share[id(t)]) * t.shares for t in relevant if t.sale
    )

    return PositionAsOf(
        ticker=ticker,
        date=as_of,
        shares=shares,
        sold_shares=sold_shares,
        average_cost=average_cost,
        cost_basis=cost_basis,
        realized_gains=realized_gains,
    )


async def _fetch_dividend_history(ticker: str) -> list[tuple[str, Decimal]]:
    """Per-share dividend history from yfinance, oldest first. [] on any failure.

    Best-effort like every other yfinance call in this module — a scrape
    hiccup degrades to "no new dividends found", not an error surfaced to
    the user.
    """
    def _fetch() -> list[tuple[str, Decimal]]:
        series = yf.Ticker(ticker).dividends
        return [(ts.date().isoformat(), Decimal(str(round(float(amt), 8)))) for ts, amt in series.items()]

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:  # noqa: BLE001
        logger.warning("Dividend history fetch failed for %s: %r", ticker, e)
        return []


async def _sync_dividends(session: AsyncSession, holding: Holding, transactions: list[Transaction]) -> int:
    """Insert any yfinance-reported dividend payments not already recorded for this holding.

    Never overwrites or re-creates an existing (holding_id, date) row, so a
    user's manual edit or deletion of an auto-fetched entry always sticks —
    this is purely an additive "fill in what's missing" pass. Returns the
    number of new rows inserted.
    """
    buys = [t for t in transactions if not t.sale]
    if not buys:
        return 0
    earliest_buy = min(t.date for t in buys)
    today = datetime.date.today().isoformat()

    history = await _fetch_dividend_history(holding.ticker)
    if not history:
        return 0

    known_dates = {d.date for d in await _fetch_dividends(session, holding.id)}

    inserted = 0
    for date, per_share in history:
        if date in known_dates or date < earliest_buy or date > today:
            continue
        # "Held as of this date" uses the same on-or-before convention as the
        # rest of the app's as-of positions (see _position_as_of) rather than
        # modeling real ex-dividend settlement (T-1) — an approximation, but
        # a consistent one.
        shares_held = _position_as_of(holding.ticker, transactions, date).shares
        if shares_held <= 0:
            continue
        session.add(Dividend(
            holding_id=holding.id, date=date, amount_per_share=per_share,
            shares_held=shares_held, total_amount=per_share * shares_held,
            source="auto",
        ))
        inserted += 1
    return inserted


async def _sync_dividends_background(ticker: str, holding_id: int) -> None:
    """Fire-and-forget: seed dividend history right after a holding is first created.

    Uses its own session since the request-scoped one may already be closed
    by the time this runs (mirrors repair_all_fifo's use of SessionLocal).
    """
    from database import SessionLocal
    try:
        async with SessionLocal() as session:
            holding = await session.get(Holding, holding_id)
            if holding is None:
                return
            transactions = await _fetch_transactions(session, holding_id)
            await _sync_dividends(session, holding, transactions)
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("Background dividend sync failed for holding %s: %r", holding_id, e)
        # best-effort — dividends can still be synced later via the explicit endpoint


async def _ensure_in_dashboard(ticker: str) -> None:
    """Fire-and-forget: add ticker to the shared price archive if not already tracked.

    Checking membership only needs the archive's own symbol list — a plain DB
    read via market_data_service.get_symbols() — not stock_service.get_all_stocks(),
    which additionally (and pointlessly, for a membership check) fetches
    `.info` from yfinance for every already-tracked ticker just to build
    display names nothing here uses. `add_stock` does a real yfinance history
    fetch for a genuinely new ticker, which occasionally fails transiently —
    losing it here silently leaves the ticker with no archive data, which
    breaks the Tracker page for it (no OHLCV to serve). One retry before
    giving up, except for a rate limit — the window hasn't cleared a moment
    later, so retrying instantly just adds to the block. A ticker that still
    fails is picked up later by repair_stock_metadata.
    """
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            existing = await market_data_service.get_symbols()
            if ticker not in existing:
                await add_stock(ticker)
            return
        except Exception as e:  # noqa: BLE001
            last_error = e
            if _is_rate_limited(e):
                break
    logger.warning("Failed to ensure %s is tracked in the price archive: %r", ticker, last_error)


async def _add_to_watchlist(session: AsyncSession, user_id: str, ticker: str, company_name: str) -> None:
    """Add `ticker` to the user's dashboard watchlist, unless it's already there."""
    existing = await session.execute(
        select(WatchlistEntry).where(WatchlistEntry.user_id == user_id, WatchlistEntry.ticker == ticker)
    )
    if existing.scalar_one_or_none() is None:
        session.add(WatchlistEntry(
            user_id=user_id, ticker=ticker, market=market_of(ticker), company_name=company_name or ticker,
        ))


def _txn_snapshot(t: Transaction) -> dict:
    # bought_at/sold_at are Decimal — the JSON column can't serialize those
    # directly, so store them as strings and parse back to Decimal on undo
    # (see _undo_delete) to avoid ever routing money through float.
    return {
        "sale": t.sale, "date": t.date, "shares": t.shares,
        "bought_at": str(t.bought_at), "sold_at": str(t.sold_at),
        "shares_remaining": t.shares_remaining,
    }


def _log_audit(session: AsyncSession, user_id: str, ticker: str, action: str, payload: dict) -> None:
    session.add(AuditEntry(
        user_id=user_id, ticker=ticker, action=action, payload=payload,
        performed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    ))


def _realized_gains(transactions: list[Transaction]) -> Decimal:
    return sum((txn.sold_at - txn.bought_at) * txn.shares for txn in transactions if txn.sale)


def _dividend_to_schema(d: Dividend, ticker: str) -> DividendEntry:
    return DividendEntry(
        id=d.id, ticker=ticker, date=d.date, amount_per_share=d.amount_per_share,
        shares_held=d.shares_held, total_amount=d.total_amount, source=d.source,
    )


def _build_stock_holding(
    holding: Holding, transactions: list[Transaction], price: Decimal | None,
    dividends: list[Dividend] | None = None,
) -> StockHolding:
    """`price` is None when a live quote couldn't be fetched — never silently treated as $0.

    In that case every price-derived field (current_price, stock_value, profit_loss,
    profit_loss_percentage) is None too, so the caller/frontend can render an explicit
    "price unavailable" state instead of a fabricated -100% loss.
    """
    # Actual cost of currently held shares: sum(unsold_shares * their_purchase_price) per buy lot
    cost_basis = sum(txn.shares_remaining * txn.bought_at for txn in transactions if not txn.sale)
    total_earned = _realized_gains(transactions)

    if price is None:
        stock_value = None
        profit_loss = None
        profit_loss_percentage = None
    else:
        stock_value = holding.shares * price
        profit_loss = stock_value - cost_basis
        profit_loss_percentage = (profit_loss / cost_basis * 100) if cost_basis > 0 else 0

    trade_history = [
        StockPurchaseHistory(
            id=txn.id,
            sale=txn.sale,
            ticker=holding.ticker,
            date=txn.date,
            shares=txn.shares,
            bought_at=txn.bought_at,
            sold_at=txn.sold_at,
            shares_remaining=txn.shares_remaining,
        )
        for txn in transactions
    ]

    dividends = dividends or []
    total_dividends = sum(d.total_amount for d in dividends)
    dividend_entries = [_dividend_to_schema(d, holding.ticker) for d in dividends]

    return StockHolding(
        ticker=holding.ticker,
        market=holding.market or market_of(holding.ticker),
        currency=currency_of(holding.ticker),
        company_name=holding.company_name,
        shares=holding.shares,
        sold_shares=holding.sold_shares,
        average_cost=holding.average_cost,
        current_price=price,
        stock_value=stock_value,
        total_invested=cost_basis,
        total_earned=total_earned,
        total_dividends=total_dividends,
        profit_loss=profit_loss,
        profit_loss_percentage=profit_loss_percentage,
        trade_history=trade_history,
        dividends=dividend_entries,
    )


# ── Service functions ─────────────────────────────────────────────────────────

async def get_stock_holding(session: AsyncSession, user_id: str, ticker: str, price: Decimal | None = None) -> StockHolding:
    holding = await _fetch_holding(session, user_id, ticker)
    if not holding:
        raise ValueError(f"No holding found for ticker: {ticker}")
    transactions = await _fetch_transactions(session, holding.id)
    dividends = await _fetch_dividends(session, holding.id)
    return _build_stock_holding(
        holding, transactions, price if price is not None else await _current_price(ticker), dividends,
    )


def _resolve_date(date: str | None) -> str:
    today = datetime.date.today()
    if date is None:
        return today.isoformat()
    try:
        d = datetime.date.fromisoformat(date)
    except ValueError:
        raise ValueError(f"Invalid date '{date}'. Expected yyyy-mm-dd.")
    if d > today:
        raise ValueError("Transaction date cannot be in the future.")
    return date


async def add_stock_purchase(
    session: AsyncSession, user_id: str, ticker: str, shares: int, bought_at: Decimal,
    date: str | None = None, exchange: str | None = None,
) -> StockHolding:
    ticker = apply_exchange(ticker, exchange)
    txn_date = _resolve_date(date)
    holding = await _fetch_holding(session, user_id, ticker)
    is_new = holding is None
    if is_new:
        company_name = await _validate_and_fetch_name(ticker)
        holding = Holding(
            user_id=user_id, ticker=ticker, market=market_of(ticker),
            company_name=company_name, shares=0, sold_shares=0, average_cost=Decimal(0),
        )
        session.add(holding)
        await session.flush()
        # A newly-bought ticker should show up on the dashboard too, not just the portfolio.
        await _add_to_watchlist(session, user_id, ticker, company_name)

    new_txn = Transaction(
        holding_id=holding.id,
        sale=False,
        date=txn_date,
        shares=shares,
        bought_at=bought_at,
        shares_remaining=shares,
    )
    # Merge the new buy into the date-sorted list and replay FIFO before persisting.
    # This ensures a backdated buy correctly redistributes shares_remaining on all
    # subsequent lots and recalculates bought_at on any sells that follow it.
    existing = await _fetch_transactions(session, holding.id)
    all_txns = sorted(existing + [new_txn], key=lambda t: t.date)
    _replay_fifo(holding, all_txns)

    session.add(new_txn)
    await session.flush()  # assign new_txn.id before logging it
    _log_audit(session, user_id, ticker, "insert", {"transaction_id": new_txn.id})
    await session.commit()
    await session.refresh(holding)

    if is_new:
        asyncio.create_task(_ensure_in_dashboard(ticker))
        asyncio.create_task(_sync_dividends_background(ticker, holding.id))

    return await get_stock_holding(session, user_id, ticker)


async def add_stock_purchases_bulk(
    session: AsyncSession, user_id: str, ticker: str, lots: list[BulkPurchaseLot],
    exchange: str | None = None,
) -> StockHolding:
    """Records several buy lots (e.g. backfilled purchase history) as one atomic write.

    Same FIFO-replay logic as add_stock_purchase, but replayed once across all
    new lots instead of once per lot — so a multi-row "buy more" submission
    either lands in full or, on a bad date, not at all.
    """
    if not lots:
        raise ValueError("At least one purchase is required.")

    # Resolve/validate every date up front so a bad row anywhere in the batch
    # fails before anything is written — no holding created, no transactions
    # flushed — rather than leaving earlier rows dangling in the session.
    resolved_dates = [_resolve_date(lot.date) for lot in lots]

    ticker = apply_exchange(ticker, exchange)
    holding = await _fetch_holding(session, user_id, ticker)
    is_new = holding is None
    if is_new:
        company_name = await _validate_and_fetch_name(ticker)
        holding = Holding(
            user_id=user_id, ticker=ticker, market=market_of(ticker),
            company_name=company_name, shares=0, sold_shares=0, average_cost=Decimal(0),
        )
        session.add(holding)
        await session.flush()
        # A newly-bought ticker should show up on the dashboard too, not just the portfolio.
        await _add_to_watchlist(session, user_id, ticker, company_name)

    new_txns = [
        Transaction(
            holding_id=holding.id,
            sale=False,
            date=resolved_date,
            shares=lot.shares,
            bought_at=lot.bought_at,
            shares_remaining=lot.shares,
        )
        for lot, resolved_date in zip(lots, resolved_dates)
    ]
    existing = await _fetch_transactions(session, holding.id)
    all_txns = sorted(existing + new_txns, key=lambda t: t.date)
    _replay_fifo(holding, all_txns)

    session.add_all(new_txns)
    await session.flush()  # assign new_txn.id before logging it
    for txn in new_txns:
        _log_audit(session, user_id, ticker, "insert", {"transaction_id": txn.id})
    await session.commit()
    await session.refresh(holding)

    if is_new:
        asyncio.create_task(_ensure_in_dashboard(ticker))
        asyncio.create_task(_sync_dividends_background(ticker, holding.id))

    return await get_stock_holding(session, user_id, ticker)


async def sell_stock_shares_bulk(
    session: AsyncSession, user_id: str, ticker: str, lots: list[BulkSaleLot],
) -> StockHolding:
    """Records several sell lots (different dates/prices) as one atomic write.

    Same FIFO-replay logic as sell_stock_shares, but replayed once across all
    new lots instead of once per lot — a multi-row sale either lands in full
    or, on a bad date or an oversell, not at all.
    """
    if not lots:
        raise ValueError("At least one sale is required.")

    # Resolve every date up front so a bad row anywhere in the batch fails
    # before anything is written.
    resolved_dates = [_resolve_date(lot.date) for lot in lots]

    holding = await _fetch_holding(session, user_id, ticker)
    if not holding:
        raise ValueError(f"No holding found for ticker: {ticker}")

    # Upfront guard: no sale date may precede the earliest buy.
    earliest_row = await session.execute(
        select(Transaction.date)
        .where(Transaction.holding_id == holding.id, Transaction.sale == False)  # noqa: E712
        .order_by(Transaction.date)
        .limit(1)
    )
    earliest_buy = earliest_row.scalar_one_or_none()
    for txn_date in resolved_dates:
        if earliest_buy and txn_date < earliest_buy:
            raise ValueError(
                f"Sale date {txn_date} is before the earliest purchase on {earliest_buy}."
            )

    new_txns = [
        Transaction(
            holding_id=holding.id,
            sale=True,
            date=resolved_date,
            shares=lot.shares,
            bought_at=Decimal(0),   # set correctly by _replay_fifo
            sold_at=lot.sold_at,
            shares_remaining=0,
        )
        for lot, resolved_date in zip(lots, resolved_dates)
    ]
    # Merge into the date-sorted list and validate via FIFO replay before touching
    # the DB — raises if any sale (individually or combined) exceeds shares
    # available as of its date. Nothing has been flushed yet, so no rollback needed.
    existing = await _fetch_transactions(session, holding.id)
    all_txns = sorted(existing + new_txns, key=lambda t: t.date)
    _replay_fifo(holding, all_txns)

    session.add_all(new_txns)
    await session.flush()  # assign new_txn.id before logging it
    for txn in new_txns:
        _log_audit(session, user_id, ticker, "insert", {"transaction_id": txn.id})
    await session.commit()
    await session.refresh(holding)
    return await get_stock_holding(session, user_id, ticker)


async def sell_stock_shares(
    session: AsyncSession, user_id: str, ticker: str, shares: int, sold_at: Decimal,
    date: str | None = None,
) -> StockHolding:
    txn_date = _resolve_date(date)
    holding = await _fetch_holding(session, user_id, ticker)
    if not holding:
        raise ValueError(f"No holding found for ticker: {ticker}")

    # Upfront guard: sell date must not precede the earliest buy.
    earliest_row = await session.execute(
        select(Transaction.date)
        .where(Transaction.holding_id == holding.id, Transaction.sale == False)  # noqa: E712
        .order_by(Transaction.date)
        .limit(1)
    )
    earliest_buy = earliest_row.scalar_one_or_none()
    if earliest_buy and txn_date < earliest_buy:
        raise ValueError(
            f"Sale date {txn_date} is before the earliest purchase on {earliest_buy}."
        )

    new_txn = Transaction(
        holding_id=holding.id,
        sale=True,
        date=txn_date,
        shares=shares,
        bought_at=Decimal(0),   # set correctly by _replay_fifo
        sold_at=sold_at,
        shares_remaining=0,
    )
    # Merge into the date-sorted list and validate via FIFO replay before touching
    # the DB. If replay raises, nothing has been flushed so no rollback is needed.
    existing = await _fetch_transactions(session, holding.id)
    all_txns = sorted(existing + [new_txn], key=lambda t: t.date)
    _replay_fifo(holding, all_txns)

    session.add(new_txn)
    await session.flush()  # assign new_txn.id before logging it
    _log_audit(session, user_id, ticker, "insert", {"transaction_id": new_txn.id})
    await session.commit()
    await session.refresh(holding)
    return await get_stock_holding(session, user_id, ticker)


async def delete_transaction(session: AsyncSession, user_id: str, ticker: str, transaction_id: int) -> StockHolding:
    holding = await _fetch_holding(session, user_id, ticker)
    if not holding:
        raise ValueError(f"No holding found for ticker: {ticker}")

    result = await session.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.holding_id == holding.id,
        )
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise ValueError(f"Transaction {transaction_id} not found for {ticker}.")

    txn_snapshot = _txn_snapshot(txn)
    await session.delete(txn)
    await session.flush()

    remaining = await _fetch_transactions(session, holding.id)

    if not remaining:
        holding_snapshot = {"company_name": holding.company_name, "market": holding.market}
        await session.delete(holding)
        _log_audit(session, user_id, ticker, "delete",
                   {"holding": holding_snapshot, "transactions": [txn_snapshot]})
        await session.commit()
        # Note: the on-disk price archive is a shared cache in multi-user mode,
        # so deleting a holding never removes archive data.
        return None

    _replay_fifo(holding, remaining)
    _log_audit(session, user_id, ticker, "delete", {"holding": None, "transactions": [txn_snapshot]})
    await session.commit()
    await session.refresh(holding)
    return await get_stock_holding(session, user_id, ticker)


async def delete_stock_holding(session: AsyncSession, user_id: str, ticker: str):
    holding = await _fetch_holding(session, user_id, ticker)
    if not holding:
        raise ValueError(f"No holding found for ticker: {ticker}")
    transactions = await _fetch_transactions(session, holding.id)
    holding_snapshot = {"company_name": holding.company_name, "market": holding.market}
    txn_snapshots = [_txn_snapshot(t) for t in transactions]
    await session.delete(holding)  # cascade="all, delete-orphan" removes transactions too
    _log_audit(session, user_id, ticker, "delete",
               {"holding": holding_snapshot, "transactions": txn_snapshots})
    await session.commit()
    return {"message": f"Holding for {ticker} deleted successfully."}


async def repair_all_fifo() -> None:
    """Replay FIFO for every holding to fix shares_remaining after a schema migration.

    Safe to call on every startup — _replay_fifo is idempotent.
    """
    from database import SessionLocal
    async with SessionLocal() as session:
        result = await session.execute(select(Holding))
        holdings = list(result.scalars().all())
        for holding in holdings:
            transactions = await _fetch_transactions(session, holding.id)
            if not transactions:
                continue
            try:
                _replay_fifo(holding, transactions)
            except ValueError:
                pass  # corrupt state — leave as-is rather than crashing startup
        await session.commit()


# Gap between per-ticker yfinance calls in repair_stock_metadata. This is a
# background task, not a user-facing one, so there's no cost to taking it
# slow — spacing calls out means Yahoo sees sporadic traffic instead of a
# burst, which is exactly the shape rate limiters are built to catch. A tight
# loop over every broken ticker at once (worse, right at startup, alongside
# whatever else is firing at boot) is the single biggest self-inflicted risk
# here.
_REPAIR_TICKER_DELAY_SECONDS = 2.0


async def repair_stock_metadata() -> None:
    """Backfills two things that can fall through the fire-and-forget/best-effort
    work add_stock_purchase(s) does for a brand-new holding: a transient
    yfinance failure on the `.info` lookup leaves Holding.company_name empty
    (shows as a bare ticker in the portfolio instead of a name), and a
    transient failure fetching the initial price history leaves the ticker
    missing from the shared archive (breaks the Tracker page for it — no
    OHLCV data to serve). Both now get a retry at the point they first run
    (see _validate_and_fetch_name / _ensure_in_dashboard), but anything that
    already slipped through before that fix — or still fails twice — stays
    broken forever with nothing else to revisit it. This backfills those.

    Safe to call repeatedly (e.g. every startup) — a holding that's already
    complete is a no-op. The name backfill does real yfinance I/O per
    affected ticker, spaced out by _REPAIR_TICKER_DELAY_SECONDS (see its
    comment), so the caller should run this as a background task rather than
    await it. The archive-coverage check itself is a plain DB read
    (market_data_service.get_symbols(), no yfinance call) — only tickers
    actually missing from the archive hit yfinance, via add_stock.
    """
    from database import SessionLocal

    async with SessionLocal() as session:
        result = await session.execute(select(Holding.ticker, Holding.company_name))
        rows = result.all()
    if not rows:
        return

    all_tickers = {ticker for ticker, _ in rows}
    unnamed_tickers = {ticker for ticker, name in rows if not name}

    for i, ticker in enumerate(unnamed_tickers):
        if i > 0:
            await asyncio.sleep(_REPAIR_TICKER_DELAY_SECONDS)
        try:
            name = await _validate_and_fetch_name(ticker)
        except ValueError:
            continue  # ticker itself no longer resolves — nothing to backfill
        if not name:
            continue
        async with SessionLocal() as session:
            await session.execute(
                update(Holding).where(Holding.ticker == ticker, Holding.company_name == "").values(company_name=name)
            )
            # The watchlist entry got the same treatment at buy time — it just
            # fell back to the bare ticker instead of staying truly empty.
            await session.execute(
                update(WatchlistEntry)
                .where(WatchlistEntry.ticker == ticker, WatchlistEntry.company_name.in_(("", ticker)))
                .values(company_name=name)
            )
            await session.commit()

    try:
        archived = await market_data_service.get_symbols()
    except Exception as e:  # noqa: BLE001
        logger.warning("repair_stock_metadata: could not list the price archive: %r", e)
        return

    for i, ticker in enumerate(all_tickers - set(archived)):
        if i > 0:
            await asyncio.sleep(_REPAIR_TICKER_DELAY_SECONDS)
        try:
            await add_stock(ticker)
        except Exception as e:  # noqa: BLE001
            logger.warning("repair_stock_metadata: failed to backfill archive for %s: %r", ticker, e)


async def get_portfolio(
    session: AsyncSession, user_id: str, market: str | None = None,
    prices: dict[str, Decimal | None] | None = None,
) -> PortfolioResponse:
    query = select(Holding).where(Holding.user_id == user_id)
    if market is not None:
        query = query.where(Holding.market == normalize_market(market))
    result = await session.execute(query)
    holdings = result.scalars().all()

    if not prices:
        # One market-status call per exchange; all price fetches run in parallel
        open_by_market = {
            m: await get_market_status(m)
            for m in {h.market or market_of(h.ticker) for h in holdings}
        }
        fetched = await asyncio.gather(
            *[_current_price(h.ticker, open_by_market.get(h.market or market_of(h.ticker))) for h in holdings]
        )
        prices = {h.ticker: p for h, p in zip(holdings, fetched)}

    portfolio_holdings: list[StockHolding] = []
    portfolio_value = 0
    realized_gains = 0
    total_shares = 0
    total_invested = 0
    total_dividends = 0

    for holding in holdings:
        transactions = await _fetch_transactions(session, holding.id)
        dividends = await _fetch_dividends(session, holding.id)
        # prices.get(...) may be None (quote unavailable) — _build_stock_holding
        # propagates that as an explicit "unavailable" state rather than $0, and
        # holdings with no price are excluded below rather than counted as worthless.
        stock_holding = _build_stock_holding(holding, transactions, prices.get(holding.ticker), dividends)
        portfolio_holdings.append(stock_holding)

        if stock_holding.stock_value is not None:
            portfolio_value += stock_holding.stock_value
        realized_gains += stock_holding.total_earned
        total_shares += stock_holding.shares
        total_invested += stock_holding.total_invested
        total_dividends += stock_holding.total_dividends

    total_return = portfolio_value - total_invested
    return_percentage = (total_return / total_invested * 100) if total_invested > 0 else 0
    net_profit_loss = total_return + realized_gains + total_dividends

    return PortfolioResponse(
        market=normalize_market(market) if market is not None else None,
        currency=MARKET_META[normalize_market(market)]["currency"] if market is not None else "USD",
        portfolio_value=portfolio_value,
        realized_gains=realized_gains,
        total_shares=total_shares,
        total_invested=total_invested,
        total_return=total_return,
        return_percentage=return_percentage,
        total_dividends=total_dividends,
        net_profit_loss=net_profit_loss,
        holdings=portfolio_holdings,
    )


async def _undo_insert(session: AsyncSession, user_id: str, entry: AuditEntry) -> None:
    txn_id = entry.payload["transaction_id"]
    result = await session.execute(select(Transaction).where(Transaction.id == txn_id))
    txn = result.scalar_one_or_none()
    if txn is None:
        return  # already gone (e.g. this holding was since deleted) — nothing to reverse

    holding = await _fetch_holding(session, user_id, entry.ticker)
    await session.delete(txn)
    await session.flush()

    remaining = await _fetch_transactions(session, holding.id)
    if not remaining:
        await session.delete(holding)
    else:
        _replay_fifo(holding, remaining)


async def _undo_delete(session: AsyncSession, user_id: str, entry: AuditEntry) -> None:
    holding = await _fetch_holding(session, user_id, entry.ticker)
    if holding is None:
        holding_snapshot = entry.payload["holding"]
        if holding_snapshot is None:
            raise ValueError(
                f"Cannot undo: holding for {entry.ticker} no longer exists and "
                "no snapshot was recorded to recreate it."
            )
        holding = Holding(
            user_id=user_id, ticker=entry.ticker,
            market=holding_snapshot["market"], company_name=holding_snapshot["company_name"],
            shares=0, sold_shares=0, average_cost=Decimal(0),
        )
        session.add(holding)
        await session.flush()

    for snapshot in entry.payload["transactions"]:
        # bought_at/sold_at were stringified for JSON storage — see _txn_snapshot.
        txn_fields = {**snapshot, "bought_at": Decimal(snapshot["bought_at"]), "sold_at": Decimal(snapshot["sold_at"])}
        session.add(Transaction(holding_id=holding.id, **txn_fields))
    await session.flush()

    transactions = await _fetch_transactions(session, holding.id)
    _replay_fifo(holding, transactions)


async def undo_last_action(session: AsyncSession, user_id: str) -> UndoResult:
    """Reverses the most recent not-yet-undone mutation for this user.

    Undo is a strict LIFO stack — always the latest action, never an
    arbitrary past one — so a reversal can never leave FIFO cost-basis state
    inconsistent with transactions that were replayed on top of it.
    """
    result = await session.execute(
        select(AuditEntry)
        .where(AuditEntry.user_id == user_id, AuditEntry.undone == False)  # noqa: E712
        .order_by(AuditEntry.id.desc())
        .limit(1)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise ValueError("Nothing to undo.")

    if entry.action == "insert":
        await _undo_insert(session, user_id, entry)
    else:
        await _undo_delete(session, user_id, entry)

    entry.undone = True
    await session.commit()
    return UndoResult(ticker=entry.ticker, action=entry.action)


async def list_audit_log(session: AsyncSession, user_id: str, limit: int = 20) -> list[AuditEntrySummary]:
    result = await session.execute(
        select(AuditEntry)
        .where(AuditEntry.user_id == user_id)
        .order_by(AuditEntry.id.desc())
        .limit(limit)
    )
    return [
        AuditEntrySummary(
            id=e.id, ticker=e.ticker, action=e.action, performed_at=e.performed_at, undone=e.undone,
        )
        for e in result.scalars().all()
    ]


async def get_position_as_of(session: AsyncSession, user_id: str, ticker: str, date: str) -> PositionAsOf:
    """FIFO position for one ticker as of `date`, derived purely from the transaction log."""
    date = _resolve_date(date)
    holding = await _fetch_holding(session, user_id, ticker)
    if not holding:
        raise ValueError(f"No holding found for ticker: {ticker}")
    transactions = await _fetch_transactions(session, holding.id)
    return _position_as_of(ticker, transactions, date)


async def get_portfolio_as_of(
    session: AsyncSession, user_id: str, date: str, market: str | None = None,
) -> list[PositionAsOf]:
    """FIFO position for every holding as of `date`, derived purely from the transaction log.

    Tickers with no transactions on or before `date` are omitted rather than
    returned as zero rows — they didn't exist in the portfolio yet.
    """
    date = _resolve_date(date)
    query = select(Holding).where(Holding.user_id == user_id)
    if market is not None:
        query = query.where(Holding.market == normalize_market(market))
    result = await session.execute(query)
    holdings = result.scalars().all()

    positions = []
    for holding in holdings:
        transactions = await _fetch_transactions(session, holding.id)
        position = _position_as_of(holding.ticker, transactions, date)
        if position.shares > 0 or position.sold_shares > 0:
            positions.append(position)
    return positions


# ── Dividends ─────────────────────────────────────────────────────────────────

def _validate_dividend_date(date: str, transactions: list[Transaction]) -> None:
    today = datetime.date.today().isoformat()
    if date > today:
        raise ValueError("Dividend date cannot be in the future.")
    buys = [t for t in transactions if not t.sale]
    if buys and date < min(t.date for t in buys):
        raise ValueError(f"Dividend date {date} is before the earliest purchase.")


def _parse_dividend_date(date: str) -> str:
    try:
        return datetime.date.fromisoformat(date).isoformat()
    except ValueError:
        raise ValueError(f"Invalid date '{date}'. Expected yyyy-mm-dd.")


async def get_dividends(session: AsyncSession, user_id: str, ticker: str) -> list[DividendEntry]:
    holding = await _fetch_holding(session, user_id, ticker)
    if not holding:
        raise ValueError(f"No holding found for ticker: {ticker}")
    dividends = await _fetch_dividends(session, holding.id)
    return [_dividend_to_schema(d, ticker) for d in dividends]


async def sync_dividends(session: AsyncSession, user_id: str, ticker: str) -> list[DividendEntry]:
    """Explicit re-sync from yfinance, throttled to at most once per day per (user, ticker).

    Returns the full current dividend list regardless of whether the throttle
    skipped a fresh fetch — the "Sync" button always shows the latest known
    state, it just won't hammer yfinance on repeated clicks.
    """
    holding = await _fetch_holding(session, user_id, ticker)
    if not holding:
        raise ValueError(f"No holding found for ticker: {ticker}")

    cache_key = f"{user_id}:{ticker}"
    if dividend_sync_cache.get(cache_key) is None:
        transactions = await _fetch_transactions(session, holding.id)
        await _sync_dividends(session, holding, transactions)
        await session.commit()
        dividend_sync_cache.set(cache_key, True)

    dividends = await _fetch_dividends(session, holding.id)
    return [_dividend_to_schema(d, ticker) for d in dividends]


async def add_dividend(
    session: AsyncSession, user_id: str, ticker: str, date: str,
    amount_per_share: Decimal, shares_held: int | None = None,
) -> DividendEntry:
    holding = await _fetch_holding(session, user_id, ticker)
    if not holding:
        raise ValueError(f"No holding found for ticker: {ticker}")

    date = _parse_dividend_date(date)
    transactions = await _fetch_transactions(session, holding.id)
    _validate_dividend_date(date, transactions)

    if shares_held is None:
        shares_held = _position_as_of(ticker, transactions, date).shares
    if shares_held <= 0:
        raise ValueError(f"No shares of {ticker} were held on {date}.")

    existing = await _fetch_dividends(session, holding.id)
    if any(d.date == date for d in existing):
        raise ValueError(f"A dividend entry for {date} already exists.")

    entry = Dividend(
        holding_id=holding.id, date=date, amount_per_share=amount_per_share,
        shares_held=shares_held, total_amount=amount_per_share * shares_held,
        source="manual",
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return _dividend_to_schema(entry, ticker)


async def update_dividend(
    session: AsyncSession, user_id: str, ticker: str, dividend_id: int,
    date: str | None = None, amount_per_share: Decimal | None = None, shares_held: int | None = None,
) -> DividendEntry:
    holding = await _fetch_holding(session, user_id, ticker)
    if not holding:
        raise ValueError(f"No holding found for ticker: {ticker}")

    result = await session.execute(
        select(Dividend).where(Dividend.id == dividend_id, Dividend.holding_id == holding.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise ValueError(f"Dividend entry {dividend_id} not found for {ticker}.")

    transactions = await _fetch_transactions(session, holding.id)

    if date is not None:
        date = _parse_dividend_date(date)
        _validate_dividend_date(date, transactions)
        existing = await _fetch_dividends(session, holding.id)
        if any(d.id != dividend_id and d.date == date for d in existing):
            raise ValueError(f"A dividend entry for {date} already exists.")
        entry.date = date

    if amount_per_share is not None:
        entry.amount_per_share = amount_per_share
    if shares_held is not None:
        entry.shares_held = shares_held

    entry.total_amount = entry.amount_per_share * entry.shares_held
    entry.source = "manual"  # any edit is treated as a manual override going forward

    await session.commit()
    await session.refresh(entry)
    return _dividend_to_schema(entry, ticker)


async def delete_dividend(session: AsyncSession, user_id: str, ticker: str, dividend_id: int) -> None:
    holding = await _fetch_holding(session, user_id, ticker)
    if not holding:
        raise ValueError(f"No holding found for ticker: {ticker}")

    result = await session.execute(
        select(Dividend).where(Dividend.id == dividend_id, Dividend.holding_id == holding.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise ValueError(f"Dividend entry {dividend_id} not found for {ticker}.")

    await session.delete(entry)
    await session.commit()

