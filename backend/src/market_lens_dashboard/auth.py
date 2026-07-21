"""Authentication.

Two paths, chosen automatically by whether a Supabase project is configured:

1. **Cloud (Supabase)** — `SUPABASE_JWKS_URL` is set. Every request to a
   user-scoped endpoint must carry `Authorization: Bearer <supabase JWT>`.
   The token is verified against Supabase's published signing keys
   (asymmetric — ES256/RS256, audience "authenticated"), and the `sub`
   claim becomes the user id.

   Newer Supabase projects sign JWTs with per-project asymmetric keys
   rather than a single shared secret, published at
   Project Settings → API → JWT Keys → JWKS URL
   (``https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json``).
   `PyJWKClient` fetches and caches those public keys, so verification
   never needs the actual signing key — only Supabase can mint tokens, but
   anyone can check them.

2. **Local** — `SUPABASE_JWKS_URL` is unset. There's no Supabase project to
   verify against, so the app runs its own minimal email/password auth
   (see routers/local_auth.py), backed by the local database. Tokens here
   are opaque session tokens looked up in the `local_sessions` table, not
   JWTs — this lets anyone testing locally create a genuine, isolated
   account with zero cloud setup.

Both paths resolve to the same thing: a `user_id` string the rest of the
app treats identically, whether it's a Supabase UUID or a locally
generated one.
"""

from __future__ import annotations

import os

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .models.local_auth import LocalSession

_bearer = HTTPBearer(auto_error=False)

_jwks_client: jwt.PyJWKClient | None = None
_jwks_client_url: str | None = None


def _jwks_url() -> str | None:
    return os.getenv("SUPABASE_JWKS_URL") or None


def local_auth_enabled() -> bool:
    """True when no Supabase project is configured, so the app falls back
    to its own local email/password accounts."""
    return _jwks_url() is None


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client, _jwks_client_url
    url = _jwks_url()
    assert url is not None, "SUPABASE_JWKS_URL must be set"
    if _jwks_client is None or _jwks_client_url != url:
        _jwks_client = jwt.PyJWKClient(url, cache_keys=True)
        _jwks_client_url = url
    return _jwks_client


def _decode_supabase(token: str) -> str:
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWKClientError:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired — please sign in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return str(payload["sub"])


async def _decode_local(token: str, session: AsyncSession) -> str:
    result = await session.execute(select(LocalSession).where(LocalSession.token == token))
    local_session = result.scalar_one_or_none()
    if local_session is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return local_session.user_id


async def _decode(token: str, session: AsyncSession) -> str:
    if local_auth_enabled():
        return await _decode_local(token, session)
    return _decode_supabase(token)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> str:
    """FastAPI dependency: resolve the current user id. Raises 401 if no valid token is presented."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Sign in to access your data")
    return await _decode(credentials.credentials, session)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> str | None:
    """Like get_current_user but returns None instead of raising.

    Used by endpoints that behave differently for signed-in users but are
    still readable anonymously.
    """
    if credentials is None:
        return None
    try:
        return await _decode(credentials.credentials, session)
    except HTTPException:
        return None
