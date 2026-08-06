"""Portfolio containers: list, create, rename, delete.

Deliberately a separate prefix from /portfolio, which is about the positions
*inside* one. /portfolio/{ticker} would otherwise swallow any collection route
declared after it (see the ordering note in portfolio.py).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_session
from schemas.portfolio import PortfolioMeta
from services import portfolio_admin_service

router = APIRouter(prefix="/portfolios", tags=["Portfolios"])


class PortfolioCreate(BaseModel):
    market: str = "US"
    # A JSON body rather than the query params the buy/sell routes use —
    # names are free text and routinely contain spaces and '&'.
    name: str = Field(min_length=1)


class PortfolioRename(BaseModel):
    name: str = Field(min_length=1)


def _meta(p) -> PortfolioMeta:
    return PortfolioMeta(id=p.id, name=p.name, market=p.market, created_at=p.created_at)


@router.get("/", response_model=list[PortfolioMeta])
async def list_portfolios(
    market: str | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """Every portfolio the user has, in tab order (creation order).

    Creates the market's default "main" if they have none yet — this is the
    bootstrap for both brand-new accounts and users who predate portfolios.
    """
    portfolios = await portfolio_admin_service.list_for_user(session, user_id, market)
    return [_meta(p) for p in portfolios]


@router.post("/", response_model=PortfolioMeta, status_code=201)
async def create_portfolio(
    body: PortfolioCreate,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    try:
        portfolio = await portfolio_admin_service.create(session, user_id, body.market, body.name)
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _meta(portfolio)


@router.patch("/{portfolio_id}", response_model=PortfolioMeta)
async def rename_portfolio(
    portfolio_id: int,
    body: PortfolioRename,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    try:
        portfolio = await portfolio_admin_service.resolve(session, user_id, portfolio_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    try:
        portfolio = await portfolio_admin_service.rename(session, portfolio, body.name)
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _meta(portfolio)


@router.delete("/{portfolio_id}")
async def delete_portfolio(
    portfolio_id: int,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """Permanently deletes a portfolio and every position in it.

    The frontend gates this behind three separate confirmations; the API
    itself only refuses to remove a market's last portfolio.
    """
    try:
        portfolio = await portfolio_admin_service.resolve(session, user_id, portfolio_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    name = portfolio.name
    try:
        await portfolio_admin_service.delete(session, portfolio)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": f"Portfolio '{name}' deleted."}
