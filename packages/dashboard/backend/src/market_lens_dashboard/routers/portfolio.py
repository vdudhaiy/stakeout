import datetime

from fastapi import Depends, HTTPException, APIRouter, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..schemas.portfolio import PortfolioResponse, StockHolding
from ..services import portfolio_service
from ..services.export_service import build_portfolio_xlsx

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


@router.get("/", response_model=PortfolioResponse)
async def get_portfolio(session: AsyncSession = Depends(get_session)):
    try:
        data = await portfolio_service.get_portfolio(session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data


# /download must be declared before /{ticker} so FastAPI doesn't swallow it as a ticker name
@router.get("/download")
async def download_portfolio(session: AsyncSession = Depends(get_session)):
    try:
        portfolio = await portfolio_service.get_portfolio(session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    xlsx_bytes = build_portfolio_xlsx(portfolio)
    filename = f"portfolio-{datetime.date.today().isoformat()}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{ticker}", response_model=StockHolding)
async def get_stock_holding(ticker: str, session: AsyncSession = Depends(get_session)):
    try:
        data = await portfolio_service.get_stock_holding(session, ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data


@router.post("/{ticker}/buy", response_model=StockHolding)
async def add_stock_purchase(
    ticker: str, shares: int, bought_at: float,
    date: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await portfolio_service.add_stock_purchase(session, ticker, shares, bought_at, date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.post("/{ticker}/sell", response_model=StockHolding)
async def sell_stock_shares(
    ticker: str, shares: int, sold_at: float,
    date: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await portfolio_service.sell_stock_shares(session, ticker, shares, sold_at, date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.delete("/{ticker}/transactions/{transaction_id}")
async def delete_transaction(ticker: str, transaction_id: int, session: AsyncSession = Depends(get_session)):
    try:
        data = await portfolio_service.delete_transaction(session, ticker, transaction_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data or {}


@router.delete("/{ticker}")
async def delete_stock_holding(ticker: str, session: AsyncSession = Depends(get_session)):
    try:
        data = await portfolio_service.delete_stock_holding(session, ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data
