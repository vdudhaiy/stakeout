"""Account deletion.

Wipes a user's app-owned data (holdings, transactions, watchlist, audit
log) and, in Supabase mode, the underlying Supabase auth account itself via
the Admin API — a local user_id has no corresponding server-side account to
delete, only the local-auth mode does (see LocalUser).
"""

import os

import httpx
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import local_auth_enabled, supabase_project_url
from models.local_auth import LocalSession, LocalUser
from models.portfolio import AuditEntry, Holding, WatchlistEntry

_ADMIN_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


async def _delete_supabase_auth_user(user_id: str) -> None:
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    base_url = supabase_project_url()
    if not secret_key or not base_url:
        raise HTTPException(
            status_code=500,
            detail="Account deletion isn't configured on this server yet — contact the maintainer.",
        )
    async with httpx.AsyncClient(timeout=_ADMIN_TIMEOUT) as client:
        resp = await client.delete(
            f"{base_url}/auth/v1/admin/users/{user_id}",
            headers={"Authorization": f"Bearer {secret_key}", "apikey": secret_key},
        )
    if resp.status_code not in (200, 204):
        raise HTTPException(status_code=502, detail="Could not delete the account with the auth provider.")


async def delete_account(session: AsyncSession, user_id: str) -> None:
    """Permanently deletes `user_id`'s account and everything it owns.

    In Supabase mode the real auth account is deleted first — if that call
    fails, nothing else is touched, so a failed deletion never leaves a
    still-usable login with wiped data.
    """
    if local_auth_enabled():
        await session.execute(delete(LocalSession).where(LocalSession.user_id == user_id))
    else:
        await _delete_supabase_auth_user(user_id)

    holdings = (await session.execute(select(Holding).where(Holding.user_id == user_id))).scalars().all()
    for holding in holdings:
        await session.delete(holding)  # cascade="all, delete-orphan" removes transactions too

    await session.execute(delete(WatchlistEntry).where(WatchlistEntry.user_id == user_id))
    await session.execute(delete(AuditEntry).where(AuditEntry.user_id == user_id))

    if local_auth_enabled():
        await session.execute(delete(LocalUser).where(LocalUser.id == user_id))

    await session.commit()
