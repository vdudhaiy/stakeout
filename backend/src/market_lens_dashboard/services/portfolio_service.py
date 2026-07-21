import asyncio
import datetime
from decimal import Decimal

import yfinance as yf
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..markets import MARKET_META, apply_exchange, currency_of, market_of, normalize_market
from ..models.portfolio import AuditEntry, Holding, Transaction, WatchlistEntry
from ..schemas.portfolio import (
    AuditEntrySummary, PortfolioResponse, PositionAsOf, StockHolding, StockPurchaseHistory, UndoResult,
)
from .stock_service import fetch_current, get_market_status, add_stock, get_all_stocks


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _validate_and_fetch_name(ticker: str) -> str:
    """Confirms the ticker exists on yfinance and returns a display name.

    Raises ValueError if yfinance returns no history (unknown ticker).
    On any other unexpected error, returns an empty string so the holding
    can still be created without a display name.
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

    try:
        return await asyncio.to_thread(_fetch)
    except ValueError:
        raise
    except Exception:
        return ""


async def _current_price(ticker: str, is_market_open: bool | None = None) -> Decimal | None:
    """Best-effort current price for `ticker`, or None if it genuinely could not be fetched.

    Never falls back to 0 — a fabricated $0 price is indistinguishable from a
    real one downstream (stock_value, profit_loss, portfolio totals), and
    would silently misreport a fetch failure as a 100% loss. Callers must
    treat None as "unknown", not "worthless".
    """
    try:
        response = await fetch_current(yf.Ticker(ticker), is_market_open)
        if response.data and response.data[0].close is not None:
            return Decimal(str(response.data[0].close))
    except Exception:
        pass
    # Archive may not exist (e.g. deleted from dashboard) — fetch last close directly.
    try:
        def _direct() -> float | None:
            hist = yf.Ticker(ticker).history(period="5d")
            return float(hist["Close"].iloc[-1]) if not hist.empty else None
        close = await asyncio.to_thread(_direct)
        if close is not None:
            return Decimal(str(close))
    except Exception:
        pass
    return None


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


async def _ensure_in_dashboard(ticker: str) -> None:
    """Fire-and-forget: add ticker to the shared price archive if not already tracked."""
    try:
        existing = await get_all_stocks()
        if ticker not in existing:
            await add_stock(ticker)
    except Exception:
        pass


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


def _build_stock_holding(holding: Holding, transactions: list[Transaction], price: Decimal | None) -> StockHolding:
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
        profit_loss=profit_loss,
        profit_loss_percentage=profit_loss_percentage,
        trade_history=trade_history,
    )


# ── Service functions ─────────────────────────────────────────────────────────

async def get_stock_holding(session: AsyncSession, user_id: str, ticker: str, price: Decimal | None = None) -> StockHolding:
    holding = await _fetch_holding(session, user_id, ticker)
    if not holding:
        raise ValueError(f"No holding found for ticker: {ticker}")
    transactions = await _fetch_transactions(session, holding.id)
    return _build_stock_holding(holding, transactions, price if price is not None else await _current_price(ticker))


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
    from ..database import SessionLocal
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

    for holding in holdings:
        transactions = await _fetch_transactions(session, holding.id)
        # prices.get(...) may be None (quote unavailable) — _build_stock_holding
        # propagates that as an explicit "unavailable" state rather than $0, and
        # holdings with no price are excluded below rather than counted as worthless.
        stock_holding = _build_stock_holding(holding, transactions, prices.get(holding.ticker))
        portfolio_holdings.append(stock_holding)

        if stock_holding.stock_value is not None:
            portfolio_value += stock_holding.stock_value
        realized_gains += stock_holding.total_earned
        total_shares += stock_holding.shares
        total_invested += stock_holding.total_invested

    total_return = portfolio_value - total_invested
    return_percentage = (total_return / total_invested * 100) if total_invested > 0 else 0
    net_profit_loss = total_return + realized_gains

    return PortfolioResponse(
        market=normalize_market(market) if market is not None else None,
        currency=MARKET_META[normalize_market(market)]["currency"] if market is not None else "USD",
        portfolio_value=portfolio_value,
        realized_gains=realized_gains,
        total_shares=total_shares,
        total_invested=total_invested,
        total_return=total_return,
        return_percentage=return_percentage,
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

