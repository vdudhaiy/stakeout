import asyncio
import datetime

import yfinance as yf
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..markets import MARKET_META, currency_of, market_of, normalize_market
from ..models.portfolio import Holding, Transaction
from ..schemas.portfolio import PortfolioResponse, StockHolding, StockPurchaseHistory
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


async def _current_price(ticker: str, is_market_open: bool | None = None) -> float:
    try:
        response = await fetch_current(yf.Ticker(ticker), is_market_open)
        return response.data[0].close if response.data else 0.0
    except Exception:
        pass
    # Archive may not exist (e.g. deleted from dashboard) — fetch last close directly.
    try:
        def _direct() -> float:
            hist = yf.Ticker(ticker).history(period="5d")
            return float(hist["Close"].iloc[-1]) if not hist.empty else 0.0
        return await asyncio.to_thread(_direct)
    except Exception:
        return 0.0


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


def _replay_fifo(holding: Holding, transactions: list[Transaction]) -> None:
    """Reset shares_remaining on all buy lots and replay all sells in FIFO order.

    Also recalculates bought_at on each sell (FIFO cost of consumed lots) and
    updates holding.shares, holding.sold_shares, holding.average_cost.
    Raises ValueError if sells would exceed buy lots available on or before the
    sell date. Transactions must be sorted oldest-first.
    """
    buy_txns = [t for t in transactions if not t.sale]
    sell_txns = [t for t in transactions if t.sale]

    for t in buy_txns:
        t.shares_remaining = t.shares

    for sell in sell_txns:
        remaining = sell.shares
        fifo_cost = 0.0
        for lot in buy_txns:
            if remaining <= 0:
                break
            if lot.date > sell.date:
                # buy_txns is date-sorted; all subsequent lots are also in the future
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
        sell.bought_at = fifo_cost / sell.shares

    holding.shares = sum(t.shares_remaining for t in buy_txns)
    holding.sold_shares = sum(t.shares for t in sell_txns)
    total_shares = sum(t.shares for t in buy_txns)
    total_cost = sum(t.shares * t.bought_at for t in buy_txns)
    holding.average_cost = total_cost / total_shares if total_shares > 0 else 0.0


async def _ensure_in_dashboard(ticker: str) -> None:
    """Fire-and-forget: add ticker to the dashboard archive if not already tracked."""
    try:
        existing = await get_all_stocks()
        if ticker not in existing:
            await add_stock(ticker)
    except Exception:
        pass


def _realized_gains(transactions: list[Transaction]) -> float:
    return sum((txn.sold_at - txn.bought_at) * txn.shares for txn in transactions if txn.sale)


def _build_stock_holding(holding: Holding, transactions: list[Transaction], price: float) -> StockHolding:
    # Actual cost of currently held shares: sum(unsold_shares * their_purchase_price) per buy lot
    cost_basis = sum(txn.shares_remaining * txn.bought_at for txn in transactions if not txn.sale)
    stock_value = holding.shares * price
    total_earned = _realized_gains(transactions)
    profit_loss = stock_value - cost_basis
    profit_loss_percentage = (profit_loss / cost_basis * 100) if cost_basis > 0 else 0.0

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

async def get_stock_holding(session: AsyncSession, user_id: str, ticker: str, price: float | None = None) -> StockHolding:
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
    session: AsyncSession, user_id: str, ticker: str, shares: int, bought_at: float,
    date: str | None = None,
) -> StockHolding:
    txn_date = _resolve_date(date)
    holding = await _fetch_holding(session, user_id, ticker)
    is_new = holding is None
    if is_new:
        company_name = await _validate_and_fetch_name(ticker)
        holding = Holding(
            user_id=user_id, ticker=ticker, market=market_of(ticker),
            company_name=company_name, shares=0, sold_shares=0, average_cost=0.0,
        )
        session.add(holding)
        await session.flush()

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
    await session.commit()
    await session.refresh(holding)

    if is_new:
        asyncio.create_task(_ensure_in_dashboard(ticker))

    return await get_stock_holding(session, user_id, ticker)


async def sell_stock_shares(
    session: AsyncSession, user_id: str, ticker: str, shares: int, sold_at: float,
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
        bought_at=0.0,   # set correctly by _replay_fifo
        sold_at=sold_at,
        shares_remaining=0,
    )
    # Merge into the date-sorted list and validate via FIFO replay before touching
    # the DB. If replay raises, nothing has been flushed so no rollback is needed.
    existing = await _fetch_transactions(session, holding.id)
    all_txns = sorted(existing + [new_txn], key=lambda t: t.date)
    _replay_fifo(holding, all_txns)

    session.add(new_txn)
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

    await session.delete(txn)
    await session.flush()

    remaining = await _fetch_transactions(session, holding.id)

    if not remaining:
        await session.delete(holding)
        await session.commit()
        # Note: the on-disk price archive is a shared cache in multi-user mode,
        # so deleting a holding never removes archive data.
        return None

    _replay_fifo(holding, remaining)
    await session.commit()
    await session.refresh(holding)
    return await get_stock_holding(session, user_id, ticker)


async def delete_stock_holding(session: AsyncSession, user_id: str, ticker: str):
    holding = await _fetch_holding(session, user_id, ticker)
    if not holding:
        raise ValueError(f"No holding found for ticker: {ticker}")
    await session.delete(holding)  # cascade="all, delete-orphan" removes transactions too
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
    prices: dict[str, float] | None = None,
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
    portfolio_value = 0.0
    realized_gains = 0.0
    total_shares = 0
    total_invested = 0.0

    for holding in holdings:
        transactions = await _fetch_transactions(session, holding.id)
        stock_holding = _build_stock_holding(holding, transactions, prices.get(holding.ticker) or 0.0)
        portfolio_holdings.append(stock_holding)

        portfolio_value += stock_holding.stock_value
        realized_gains += stock_holding.total_earned
        total_shares += stock_holding.shares
        total_invested += stock_holding.total_invested

    total_return = portfolio_value - total_invested
    return_percentage = (total_return / total_invested * 100) if total_invested > 0 else 0.0
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

