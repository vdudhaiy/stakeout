"""Authentication for multi-user deployments.

Two modes, selected by environment:

1. **Cloud mode** — `SUPABASE_JWT_SECRET` is set. Every request to a
   user-scoped endpoint must carry `Authorization: Bearer <supabase JWT>`.
   The token is verified locally (HS256, audience "authenticated") with no
   network round-trip to Supabase, and the `sub` claim becomes the user id.

2. **Local mode** — `SUPABASE_JWT_SECRET` is unset. All requests map to the
   single pseudo-user "local". This keeps the desktop / self-hosted
   single-user experience working with zero configuration.

Supabase issues JWTs signed with the project's *JWT secret* (Project
Settings → API → JWT Secret). The anon/service keys are NOT the secret —
don't put those here.
"""

from __future__ import annotations

import os

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

LOCAL_USER_ID = "local"

_bearer = HTTPBearer(auto_error=False)


def _jwt_secret() -> str | None:
    return os.getenv("SUPABASE_JWT_SECRET") or None


def auth_enabled() -> bool:
    return _jwt_secret() is not None


def _decode(token: str) -> str:
    secret = _jwt_secret()
    assert secret is not None
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired — please sign in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return str(payload["sub"])


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """FastAPI dependency: resolve the current user id.

    Raises 401 in cloud mode when no valid token is presented.
    """
    if not auth_enabled():
        return LOCAL_USER_ID
    if credentials is None:
        raise HTTPException(status_code=401, detail="Sign in to access your data")
    return _decode(credentials.credentials)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str | None:
    """Like get_current_user but returns None instead of raising.

    Used by endpoints that behave differently for signed-in users but are
    still readable anonymously.
    """
    if not auth_enabled():
        return LOCAL_USER_ID
    if credentials is None:
        return None
    try:
        return _decode(credentials.credentials)
    except HTTPException:
        return None
