import datetime
from decimal import Decimal

from fastapi import Depends, HTTPException, APIRouter, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_session
from ..schemas.portfolio import AuditEntrySummary, PortfolioResponse, PositionAsOf, StockHolding, UndoResult
from ..services import portfolio_service
from ..services.export_service import build_portfolio_xlsx

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


@router.get("/", response_model=PortfolioResponse)
async def get_portfolio(
    market: str | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    try:
        data = await portfolio_service.get_portfolio(session, user_id, market)
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
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """FIFO-derived shares/cost-basis/realized-gains per holding as of `date`.

    Computed purely from the transaction log — no live prices involved.
    """
    try:
        data = await portfolio_service.get_portfolio_as_of(session, user_id, date, market)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.get("/{ticker}", response_model=StockHolding)
async def get_stock_holding(
    ticker: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    try:
        data = await portfolio_service.get_stock_holding(session, user_id, ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data


@router.get("/{ticker}/history/{date}", response_model=PositionAsOf)
async def get_position_as_of(
    ticker: str,
    date: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """FIFO-derived shares/cost-basis/realized-gains for `ticker` as of `date`."""
    try:
        data = await portfolio_service.get_position_as_of(session, user_id, ticker, date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.post("/{ticker}/buy", response_model=StockHolding)
async def add_stock_purchase(
    ticker: str, shares: int, bought_at: Decimal,
    date: str | None = None,
    exchange: str | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    try:
        data = await portfolio_service.add_stock_purchase(session, user_id, ticker, shares, bought_at, date, exchange)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.post("/{ticker}/sell", response_model=StockHolding)
async def sell_stock_shares(
    ticker: str, shares: int, sold_at: Decimal,
    date: str | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    try:
        data = await portfolio_service.sell_stock_shares(session, user_id, ticker, shares, sold_at, date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.delete("/{ticker}/transactions/{transaction_id}")
async def delete_transaction(
    ticker: str, transaction_id: int,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    try:
        data = await portfolio_service.delete_transaction(session, user_id, ticker, transaction_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data or {}


@router.delete("/{ticker}")
async def delete_stock_holding(
    ticker: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    try:
        data = await portfolio_service.delete_stock_holding(session, user_id, ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data
