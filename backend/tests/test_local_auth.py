"""Tests for local-auth mode: email/password signup/login/logout via HTTP,
and that issued session tokens correctly resolve through auth._decode_local.

local_auth_enabled() is True throughout these tests since SUPABASE_JWKS_URL
is never set in the test environment (conftest.py), same condition under
which the /auth router actually gets mounted in a real local deployment.
"""

import pytest
from fastapi import HTTPException

from market_lens_dashboard import auth
from market_lens_dashboard.models.local_auth import LocalSession, LocalUser


# ── local_auth_enabled ────────────────────────────────────────────────────

def test_local_auth_enabled_true_when_no_jwks_url(monkeypatch):
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)
    assert auth.local_auth_enabled() is True


def test_local_auth_enabled_false_when_jwks_url_set(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWKS_URL", "https://example.supabase.co/auth/v1/.well-known/jwks.json")
    assert auth.local_auth_enabled() is False


# ── signup ────────────────────────────────────────────────────────────────

async def test_signup_creates_account_and_returns_token(client):
    resp = await client.post("/auth/signup", json={"email": "new@example.com", "password": "hunter2222"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "new@example.com"
    assert len(data["token"]) > 20


async def test_signup_lowercases_email(client):
    resp = await client.post("/auth/signup", json={"email": "MixedCase@Example.com", "password": "hunter2222"})
    assert resp.json()["email"] == "mixedcase@example.com"


async def test_signup_duplicate_email_rejected(client):
    await client.post("/auth/signup", json={"email": "dup@example.com", "password": "hunter2222"})
    resp = await client.post("/auth/signup", json={"email": "dup@example.com", "password": "hunter2222"})
    assert resp.status_code == 400


async def test_signup_short_password_rejected(client):
    resp = await client.post("/auth/signup", json={"email": "short@example.com", "password": "abc"})
    assert resp.status_code == 400


async def test_signup_invalid_email_rejected(client):
    resp = await client.post("/auth/signup", json={"email": "not-an-email", "password": "hunter2222"})
    assert resp.status_code == 422


# ── login ─────────────────────────────────────────────────────────────────

async def test_login_success(client):
    await client.post("/auth/signup", json={"email": "login@example.com", "password": "hunter2222"})
    resp = await client.post("/auth/login", json={"email": "login@example.com", "password": "hunter2222"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "login@example.com"


async def test_login_wrong_password_rejected(client):
    await client.post("/auth/signup", json={"email": "wrongpw@example.com", "password": "hunter2222"})
    resp = await client.post("/auth/login", json={"email": "wrongpw@example.com", "password": "nope12345"})
    assert resp.status_code == 401


async def test_login_unknown_email_rejected(client):
    resp = await client.post("/auth/login", json={"email": "nobody@example.com", "password": "hunter2222"})
    assert resp.status_code == 401


# ── logout ────────────────────────────────────────────────────────────────

async def test_logout_deletes_session_row(client, db_session):
    signup = await client.post("/auth/signup", json={"email": "logout@example.com", "password": "hunter2222"})
    token = signup.json()["token"]

    resp = await client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    with pytest.raises(HTTPException):
        await auth._decode_local(token, db_session)


async def test_logout_without_token_is_a_no_op(client):
    resp = await client.post("/auth/logout")
    assert resp.status_code == 200


# ── token resolution (bypasses the client fixture's auth override) ──────────

async def test_issued_token_resolves_to_correct_user_id(db_session):
    user = LocalUser(id="user-123", email="resolve@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    db_session.add(LocalSession(token="tok-abc", user_id=user.id))
    await db_session.commit()

    assert await auth._decode_local("tok-abc", db_session) == "user-123"


async def test_unknown_token_raises_401(db_session):
    with pytest.raises(HTTPException):
        await auth._decode_local("does-not-exist", db_session)
