from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_session
from services.account_service import delete_account

router = APIRouter(tags=["Account"])


@router.delete("/account")
async def delete_my_account(
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    """Permanently deletes the signed-in user's account and all owned data."""
    await delete_account(session, user_id)
    return {"message": "Account deleted."}
