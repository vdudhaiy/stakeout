"""Authentication for multi-user deployments.

Two modes, selected by environment:

1. **Cloud mode** — `SUPABASE_JWKS_URL` is set. Every request to a
   user-scoped endpoint must carry `Authorization: Bearer <supabase JWT>`.
   The token is verified against Supabase's published signing keys
   (asymmetric — ES256/RS256, audience "authenticated"), and the `sub`
   claim becomes the user id.

2. **Local mode** — `SUPABASE_JWKS_URL` is unset. All requests map to the
   single pseudo-user "local". This keeps the desktop / self-hosted
   single-user experience working with zero configuration.

Newer Supabase projects sign JWTs with per-project asymmetric keys rather
than a single shared secret, published at
Project Settings → API → JWT Keys → JWKS URL
(``https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json``).
`PyJWKClient` fetches and caches those public keys, so verification never
needs the actual signing key — only Supabase can mint tokens, but anyone can
check them.
"""

from __future__ import annotations

import os

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

LOCAL_USER_ID = "local"

_bearer = HTTPBearer(auto_error=False)

_jwks_client: jwt.PyJWKClient | None = None
_jwks_client_url: str | None = None


def _jwks_url() -> str | None:
    return os.getenv("SUPABASE_JWKS_URL") or None


def auth_enabled() -> bool:
    return _jwks_url() is not None


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client, _jwks_client_url
    url = _jwks_url()
    assert url is not None
    if _jwks_client is None or _jwks_client_url != url:
        _jwks_client = jwt.PyJWKClient(url, cache_keys=True)
        _jwks_client_url = url
    return _jwks_client


def _decode(token: str) -> str:
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
