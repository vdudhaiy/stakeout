"""Currency conversion rates (see fx_service for source fallback chain)."""

from fastapi import APIRouter, HTTPException, Response

from ..services import fx_service

router = APIRouter(prefix="/fx", tags=["FX"])


@router.get("/{base}/{quote}")
async def get_rate(base: str, quote: str, response: Response):
    try:
        data = await fx_service.get_rate(base, quote)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    response.headers["Cache-Control"] = "public, max-age=1800"
    return data
