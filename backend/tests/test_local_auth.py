"""Tests for local-auth mode: email/password signup/login/logout via HTTP,
and that issued session tokens correctly resolve through auth._decode_local.

local_auth_enabled() is True throughout these tests since SUPABASE_JWKS_URL
is never set in the test environment (conftest.py), same condition under
which the /auth router actually gets mounted in a real local deployment.
"""

import pytest
from fastapi import HTTPException

import auth
from models.local_auth import LocalSession, LocalUser
from routers.local_auth import (
    _change_password_limiter,
    _hash_password,
    _login_limiter,
    _signup_limiter,
    _verify_password,
)


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """The signup/login/change-password limiters are module-level singletons
    (see rate_limit.py) — without resetting them, hits accumulate across
    every test in this file and later tests start seeing 429s that have
    nothing to do with what they're actually testing."""
    for limiter in (_signup_limiter, _login_limiter, _change_password_limiter):
        limiter.reset()
    yield


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


async def test_signup_oversized_password_rejected_cleanly(client):
    # bcrypt raises past 72 bytes — must come back as a clean 400, not a 500.
    resp = await client.post("/auth/signup", json={"email": "huge@example.com", "password": "a" * 200})
    assert resp.status_code == 400


async def test_signup_rate_limited_after_five_per_ip(client):
    for i in range(5):
        resp = await client.post("/auth/signup", json={"email": f"rl{i}@example.com", "password": "hunter2222"})
        assert resp.status_code == 200
    resp = await client.post("/auth/signup", json={"email": "rl-sixth@example.com", "password": "hunter2222"})
    assert resp.status_code == 429


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


async def test_login_oversized_password_rejected_cleanly_not_500(client):
    await client.post("/auth/signup", json={"email": "oversize@example.com", "password": "hunter2222"})
    resp = await client.post("/auth/login", json={"email": "oversize@example.com", "password": "a" * 200})
    assert resp.status_code == 401


async def test_login_unknown_email_still_runs_bcrypt_compare(client, monkeypatch):
    # Regression guard for the timing side-channel: login must not short-
    # circuit on a missing user without ever calling _verify_password —
    # patch it to prove it's invoked (against the dummy hash) even when
    # there's no account to check.
    import routers.local_auth as local_auth_module

    calls = []
    original = local_auth_module._verify_password

    def spy(password, password_hash):
        calls.append(password_hash)
        return original(password, password_hash)

    monkeypatch.setattr(local_auth_module, "_verify_password", spy)

    resp = await client.post("/auth/login", json={"email": "definitely-nobody@example.com", "password": "whatever1"})
    assert resp.status_code == 401
    assert calls == [local_auth_module._DUMMY_HASH]


async def test_login_rate_limited_after_ten_per_ip(client):
    await client.post("/auth/signup", json={"email": "rllogin@example.com", "password": "hunter2222"})
    for _ in range(10):
        resp = await client.post("/auth/login", json={"email": "rllogin@example.com", "password": "wrongpass1"})
        assert resp.status_code == 401
    resp = await client.post("/auth/login", json={"email": "rllogin@example.com", "password": "hunter2222"})
    assert resp.status_code == 429


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


# ── change-password ──────────────────────────────────────────────────────
# client's get_current_user override always resolves to "test-user" (see
# conftest.py), so these seed a LocalUser with that id directly.

async def test_change_password_success_rotates_session(client, db_session):
    user = LocalUser(id="test-user", email="change@example.com", password_hash=_hash_password("oldpass123"))
    db_session.add(user)
    await db_session.flush()
    db_session.add(LocalSession(token="pre-existing-token", user_id="test-user"))
    await db_session.commit()

    resp = await client.post(
        "/auth/change-password",
        json={"current_password": "oldpass123", "new_password": "newpass456"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "change@example.com"
    assert len(data["token"]) > 20

    await db_session.refresh(user)
    assert _verify_password("newpass456", user.password_hash)
    assert not _verify_password("oldpass123", user.password_hash)

    # Every prior session — including ones from other devices — is revoked.
    with pytest.raises(HTTPException):
        await auth._decode_local("pre-existing-token", db_session)


async def test_change_password_wrong_current_password_rejected(client, db_session):
    user = LocalUser(id="test-user", email="wrongcur@example.com", password_hash=_hash_password("oldpass123"))
    db_session.add(user)
    await db_session.commit()

    resp = await client.post(
        "/auth/change-password",
        json={"current_password": "notright1", "new_password": "newpass456"},
    )
    assert resp.status_code == 401

    await db_session.refresh(user)
    assert _verify_password("oldpass123", user.password_hash)  # unchanged


async def test_change_password_new_password_too_short_rejected(client, db_session):
    user = LocalUser(id="test-user", email="short2@example.com", password_hash=_hash_password("oldpass123"))
    db_session.add(user)
    await db_session.commit()

    resp = await client.post(
        "/auth/change-password",
        json={"current_password": "oldpass123", "new_password": "short"},
    )
    assert resp.status_code == 400


async def test_change_password_rate_limited_after_five(client, db_session):
    user = LocalUser(id="test-user", email="rlchange@example.com", password_hash=_hash_password("oldpass123"))
    db_session.add(user)
    await db_session.commit()

    for _ in range(5):
        resp = await client.post(
            "/auth/change-password",
            json={"current_password": "wrong-on-purpose", "new_password": "newpass456"},
        )
        assert resp.status_code == 401
    resp = await client.post(
        "/auth/change-password",
        json={"current_password": "oldpass123", "new_password": "newpass456"},
    )
    assert resp.status_code == 429
