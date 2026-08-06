import datetime
from decimal import Decimal

from fastapi import Depends, HTTPException, APIRouter, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_session
from markets import apply_exchange, market_of
from schemas.portfolio import (
    AuditEntrySummary, BulkPurchaseLot, BulkSaleLot, DividendEntry, ImportApplyRow, ImportPreviewResult,
    PortfolioImportResult, PortfolioResponse, PositionAsOf, StockHolding, UndoResult,
)
from services import import_service, portfolio_admin_service, portfolio_service
from services.export_service import build_portfolio_xlsx

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


async def _scope(
    session: AsyncSession, user_id: str, portfolio_id: int | None, market: str | None = None,
) -> int:
    """Resolve the portfolio a request acts on, to its id.

    This is where a client-supplied portfolio_id is checked for ownership —
    every route taking one must go through here. Omitting it selects the
    market's default portfolio, which is what keeps pre-multi-portfolio
    clients working unchanged.

    `market` is only forwarded when there is no explicit id: it is a fallback
    for choosing the default, and validating it against a given id would
    reject legitimate combinations (a bare Indian ticker reads as "US" until
    its exchange suffix is applied).
    """
    try:
        portfolio = await portfolio_admin_service.resolve(
            session, user_id, portfolio_id, None if portfolio_id is not None else market,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return portfolio.id


@router.get("/", response_model=PortfolioResponse)
async def get_portfolio(
    market: str | None = None,
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """Positions and aggregates for `market`.

    Without `portfolio_id` this spans every portfolio in the market: top-level
    figures are the combined totals, `portfolios` holds the per-portfolio
    breakdown, and each holding carries the portfolio it belongs to.
    """
    if portfolio_id is not None:
        portfolio_id = await _scope(session, user_id, portfolio_id)
    else:
        # Make sure the market has at least its default portfolio, so a brand
        # new account gets a tab rather than an empty response.
        await portfolio_admin_service.ensure_default(session, user_id, market)
    try:
        data = await portfolio_service.get_portfolio(session, user_id, market, portfolio_id=portfolio_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data


# /download and /audit must be declared before /{ticker} so FastAPI doesn't swallow them as a ticker name
@router.get("/download")
async def download_portfolio(
    market: str | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """Every portfolio in `market`, as one workbook — see export_service."""
    try:
        portfolio = await portfolio_service.get_portfolio(session, user_id, market)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    xlsx_bytes = build_portfolio_xlsx(portfolio)
    filename = f"portfolio-{datetime.date.today().isoformat()}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import/preview", response_model=ImportPreviewResult)
async def preview_portfolio_import(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """Parses an uploaded .csv or .xlsx file (columns: market, stock, date,
    number, buy/sell, price, and an optional portfolio — see import_service's
    module docstring for the exact format) and flags rows that exactly
    duplicate an existing transaction or an earlier row in the same file.
    Nothing is written yet — the frontend resolves flagged duplicates with
    the user, then calls /import/apply with each row's include/skip decision.

    A non-empty `blocking_errors` means the file must be corrected and
    re-uploaded; /import/apply will refuse it as it stands.
    """
    content = await file.read()
    try:
        return await import_service.preview_import(session, user_id, file.filename or "upload", content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/import/apply", response_model=PortfolioImportResult)
async def apply_portfolio_import(
    rows: list[ImportApplyRow],
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """Applies rows previously returned by /import/preview. Best-effort per
    row: a malformed row, an unknown ticker, or an oversell is reported in
    the response instead of failing the whole batch; rows with
    include=False (the user skipped them, usually a duplicate) are reported
    as "skipped" rather than applied.

    The exception is portfolio names, which are re-resolved here and reject
    the whole request (400) if any fail — misfiling transactions into the
    wrong portfolio is not something to report row-by-row after the fact.
    """
    try:
        return await import_service.apply_import(session, user_id, rows)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/audit", response_model=list[AuditEntrySummary])
async def get_audit_log(
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """Recent buy/sell/delete mutations for this user, newest first."""
    return await portfolio_service.list_audit_log(session, user_id, limit)


@router.post("/undo", response_model=UndoResult)
async def undo_last_action(
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """Reverses the most recent buy/sell/delete for this user (LIFO undo stack)."""
    try:
        data = await portfolio_service.undo_last_action(session, user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.get("/history/{date}", response_model=list[PositionAsOf])
async def get_portfolio_as_of(
    date: str,
    market: str | None = None,
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """FIFO-derived shares/cost-basis/realized-gains per holding as of `date`.

    Computed purely from the transaction log — no live prices involved.
    """
    if portfolio_id is not None:
        portfolio_id = await _scope(session, user_id, portfolio_id)
    try:
        data = await portfolio_service.get_portfolio_as_of(
            session, user_id, date, market, portfolio_id=portfolio_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.get("/{ticker}", response_model=StockHolding)
async def get_stock_holding(
    ticker: str,
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    scope = await _scope(session, user_id, portfolio_id, market_of(ticker))
    try:
        data = await portfolio_service.get_stock_holding(session, scope, ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data


@router.get("/{ticker}/history/{date}", response_model=PositionAsOf)
async def get_position_as_of(
    ticker: str,
    date: str,
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """FIFO-derived shares/cost-basis/realized-gains for `ticker` as of `date`."""
    scope = await _scope(session, user_id, portfolio_id, market_of(ticker))
    try:
        data = await portfolio_service.get_position_as_of(session, scope, ticker, date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.get("/{ticker}/dividends", response_model=list[DividendEntry])
async def get_dividends(
    ticker: str,
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """Dividend payments recorded for this holding, oldest first. Read-only — no yfinance call."""
    scope = await _scope(session, user_id, portfolio_id, market_of(ticker))
    try:
        data = await portfolio_service.get_dividends(session, scope, ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data


@router.post("/{ticker}/dividends/sync", response_model=list[DividendEntry])
async def sync_dividends(
    ticker: str,
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """Fetch new dividend payments from yfinance (throttled to once/day per portfolio+ticker).

    Never overwrites or resurrects an existing entry, so prior manual edits/deletes stick.
    """
    scope = await _scope(session, user_id, portfolio_id, market_of(ticker))
    try:
        data = await portfolio_service.sync_dividends(session, user_id, scope, ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data


@router.post("/{ticker}/dividends", response_model=DividendEntry)
async def add_dividend(
    ticker: str, date: str, amount_per_share: Decimal,
    shares_held: int | None = None,
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """Manually record a dividend payment. shares_held defaults to the FIFO position as of `date`."""
    scope = await _scope(session, user_id, portfolio_id, market_of(ticker))
    try:
        data = await portfolio_service.add_dividend(session, scope, ticker, date, amount_per_share, shares_held)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.put("/{ticker}/dividends/{dividend_id}", response_model=DividendEntry)
async def update_dividend(
    ticker: str, dividend_id: int,
    date: str | None = None, amount_per_share: Decimal | None = None, shares_held: int | None = None,
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    scope = await _scope(session, user_id, portfolio_id, market_of(ticker))
    try:
        data = await portfolio_service.update_dividend(
            session, scope, ticker, dividend_id, date, amount_per_share, shares_held,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.delete("/{ticker}/dividends/{dividend_id}")
async def delete_dividend(
    ticker: str, dividend_id: int,
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    scope = await _scope(session, user_id, portfolio_id, market_of(ticker))
    try:
        await portfolio_service.delete_dividend(session, scope, ticker, dividend_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {}


@router.post("/{ticker}/buy", response_model=StockHolding)
async def add_stock_purchase(
    ticker: str, shares: int, bought_at: Decimal,
    date: str | None = None,
    exchange: str | None = None,
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    scope = await _scope(session, user_id, portfolio_id, market_of(apply_exchange(ticker, exchange)))
    try:
        data = await portfolio_service.add_stock_purchase(
            session, user_id, scope, ticker, shares, bought_at, date, exchange,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.post("/{ticker}/buy/bulk", response_model=StockHolding)
async def add_stock_purchases_bulk(
    ticker: str, lots: list[BulkPurchaseLot],
    exchange: str | None = None,
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """Records several buy lots (different dates/prices) for `ticker` in one atomic write.

    Meant for backfilling purchase history — e.g. transferring an existing
    portfolio in — without a round trip per historical transaction.
    """
    scope = await _scope(session, user_id, portfolio_id, market_of(apply_exchange(ticker, exchange)))
    try:
        data = await portfolio_service.add_stock_purchases_bulk(session, user_id, scope, ticker, lots, exchange)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.post("/{ticker}/sell", response_model=StockHolding)
async def sell_stock_shares(
    ticker: str, shares: int, sold_at: Decimal,
    date: str | None = None,
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    scope = await _scope(session, user_id, portfolio_id, market_of(ticker))
    try:
        data = await portfolio_service.sell_stock_shares(session, user_id, scope, ticker, shares, sold_at, date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.post("/{ticker}/sell/bulk", response_model=StockHolding)
async def sell_stock_shares_bulk(
    ticker: str, lots: list[BulkSaleLot],
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """Records several sell lots (different dates/prices) for `ticker` in one atomic write."""
    scope = await _scope(session, user_id, portfolio_id, market_of(ticker))
    try:
        data = await portfolio_service.sell_stock_shares_bulk(session, user_id, scope, ticker, lots)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.delete("/{ticker}/transactions/{transaction_id}")
async def delete_transaction(
    ticker: str, transaction_id: int,
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    scope = await _scope(session, user_id, portfolio_id, market_of(ticker))
    try:
        data = await portfolio_service.delete_transaction(session, user_id, scope, ticker, transaction_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data or {}


@router.delete("/{ticker}")
async def delete_stock_holding(
    ticker: str,
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    scope = await _scope(session, user_id, portfolio_id, market_of(ticker))
    try:
        data = await portfolio_service.delete_stock_holding(session, user_id, scope, ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data
