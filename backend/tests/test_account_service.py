"""Account deletion: local-auth mode deletes the LocalUser row directly;
Supabase mode calls the Admin API first and only touches app data if that
succeeds, so a failed provider call never leaves wiped data behind.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from models.local_auth import LocalSession, LocalUser
from models.portfolio import AuditEntry, Holding, Portfolio, WatchlistEntry
from services import account_service, portfolio_admin_service

USER_ID = "user-to-delete"


async def _seed_owned_data(db_session, user_id=USER_ID):
    portfolio = await portfolio_admin_service.ensure_default(db_session, user_id, "US")
    holding = Holding(user_id=user_id, portfolio_id=portfolio.id, ticker="AAPL", shares=10)
    db_session.add(holding)
    db_session.add(WatchlistEntry(user_id=user_id, ticker="MSFT"))
    db_session.add(AuditEntry(
        user_id=user_id, ticker="AAPL", action="insert",
        payload={"transaction_id": 1}, performed_at="2024-01-01T00:00:00Z",
    ))
    await db_session.commit()


# ── Local-auth mode ──────────────────────────────────────────────────────

async def test_local_mode_deletes_user_and_owned_data(db_session, monkeypatch):
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)
    db_session.add(LocalUser(id=USER_ID, email="del@example.com", password_hash="x"))
    await db_session.flush()
    db_session.add(LocalSession(token="tok-1", user_id=USER_ID))
    await _seed_owned_data(db_session)

    await account_service.delete_account(db_session, USER_ID)

    assert (await db_session.execute(select(LocalUser).where(LocalUser.id == USER_ID))).scalar_one_or_none() is None
    assert (await db_session.execute(select(LocalSession).where(LocalSession.user_id == USER_ID))).scalar_one_or_none() is None
    assert (await db_session.execute(select(Holding).where(Holding.user_id == USER_ID))).scalar_one_or_none() is None
    assert (await db_session.execute(select(WatchlistEntry).where(WatchlistEntry.user_id == USER_ID))).scalar_one_or_none() is None
    assert (await db_session.execute(select(AuditEntry).where(AuditEntry.user_id == USER_ID))).scalar_one_or_none() is None


async def test_local_mode_does_not_touch_other_users_data(db_session, monkeypatch):
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)
    db_session.add(LocalUser(id=USER_ID, email="del@example.com", password_hash="x"))
    await db_session.flush()
    await _seed_owned_data(db_session)
    await _seed_owned_data(db_session, user_id="someone-else")

    await account_service.delete_account(db_session, USER_ID)

    assert (await db_session.execute(select(Holding).where(Holding.user_id == "someone-else"))).scalar_one_or_none() is not None


# ── Supabase mode ─────────────────────────────────────────────────────────

def _mock_client(status_code: int):
    resp = MagicMock(status_code=status_code)
    instance = AsyncMock()
    instance.delete = AsyncMock(return_value=resp)
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=instance)


async def test_supabase_mode_deletes_auth_user_then_owned_data(db_session, monkeypatch):
    monkeypatch.setenv("SUPABASE_JWKS_URL", "https://proj.supabase.co/auth/v1/.well-known/jwks.json")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "secret-key")
    await _seed_owned_data(db_session)

    with patch("services.account_service.httpx.AsyncClient", _mock_client(204)):
        await account_service.delete_account(db_session, USER_ID)

    assert (await db_session.execute(select(Holding).where(Holding.user_id == USER_ID))).scalar_one_or_none() is None


async def test_supabase_mode_missing_service_key_raises_and_keeps_data(db_session, monkeypatch):
    monkeypatch.setenv("SUPABASE_JWKS_URL", "https://proj.supabase.co/auth/v1/.well-known/jwks.json")
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    await _seed_owned_data(db_session)

    with pytest.raises(HTTPException) as exc:
        await account_service.delete_account(db_session, USER_ID)
    assert exc.value.status_code == 500
    assert (await db_session.execute(select(Holding).where(Holding.user_id == USER_ID))).scalar_one_or_none() is not None


async def test_supabase_mode_admin_api_failure_raises_and_keeps_data(db_session, monkeypatch):
    monkeypatch.setenv("SUPABASE_JWKS_URL", "https://proj.supabase.co/auth/v1/.well-known/jwks.json")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "secret-key")
    await _seed_owned_data(db_session)

    with patch("services.account_service.httpx.AsyncClient", _mock_client(401)):
        with pytest.raises(HTTPException) as exc:
            await account_service.delete_account(db_session, USER_ID)
    assert exc.value.status_code == 502
    assert (await db_session.execute(select(Holding).where(Holding.user_id == USER_ID))).scalar_one_or_none() is not None


# ── Router ────────────────────────────────────────────────────────────────

async def test_delete_account_endpoint_removes_data(client, db_session):
    # Local-auth mode is the test env's default (no SUPABASE_JWKS_URL set).
    await _seed_owned_data(db_session, user_id="test-user")  # matches conftest's TEST_USER_ID

    resp = await client.delete("/account")
    assert resp.status_code == 200
    assert (await db_session.execute(select(Holding).where(Holding.user_id == "test-user"))).scalar_one_or_none() is None
