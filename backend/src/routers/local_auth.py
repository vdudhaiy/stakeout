"""Local email/password authentication.

Only mounted when no Supabase project is configured (see
auth.local_auth_enabled) — lets anyone testing locally create a genuine,
isolated account without needing real cloud auth. Passwords are hashed with
bcrypt; sessions are opaque tokens with no expiry (this is a dev-only auth
path, not a security boundary).
"""

import secrets
import uuid

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_session
from models.local_auth import LocalSession, LocalUser
from rate_limit import RateLimiter, by_client_ip
from schemas.local_auth import AuthResponse, ChangePasswordRequest, Credentials

router = APIRouter(prefix="/auth", tags=["Local Auth"])

_bearer = HTTPBearer(auto_error=False)

# bcrypt silently caps effective password strength at 72 bytes and raises
# ValueError past that — never a real 500 for a genuine password, only for
# junk input, so treat it as a clean rejection rather than crashing.
_MAX_PASSWORD_BYTES = 72

# A fixed hash to check against when the account doesn't exist, so login
# takes the same time either way — otherwise "user not found" (no bcrypt
# call) is measurably faster than "wrong password" (one bcrypt call), a
# timing side-channel that lets an attacker enumerate registered emails.
_DUMMY_HASH = bcrypt.hashpw(b"stakeout-timing-safety-dummy", bcrypt.gensalt()).decode()

# Signup/login are brute-force and spam-account targets; change-password is
# lower-risk (already requires a valid session) but still worth capping.
_signup_limiter = RateLimiter(max_requests=5, window_seconds=15 * 60)
_login_limiter = RateLimiter(max_requests=10, window_seconds=15 * 60)
_change_password_limiter = RateLimiter(max_requests=5, window_seconds=15 * 60)


def _hash_password(password: str) -> str:
    if len(password.encode()) > _MAX_PASSWORD_BYTES:
        raise HTTPException(status_code=400, detail=f"Password must be at most {_MAX_PASSWORD_BYTES} characters.")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, password_hash: str) -> bool:
    if len(password.encode()) > _MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(password.encode(), password_hash.encode())


async def _issue_session(session: AsyncSession, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    session.add(LocalSession(token=token, user_id=user_id))
    await session.commit()
    return token


@router.post("/signup", response_model=AuthResponse, dependencies=[Depends(by_client_ip(_signup_limiter))])
async def signup(creds: Credentials, session: AsyncSession = Depends(get_session)):
    email = creds.email.lower()
    existing = await session.execute(select(LocalUser).where(LocalUser.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="An account with that email already exists.")
    if len(creds.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    user = LocalUser(id=str(uuid.uuid4()), email=email, password_hash=_hash_password(creds.password))
    session.add(user)
    await session.flush()
    token = await _issue_session(session, user.id)
    return AuthResponse(token=token, email=user.email)


@router.post("/login", response_model=AuthResponse, dependencies=[Depends(by_client_ip(_login_limiter))])
async def login(creds: Credentials, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(LocalUser).where(LocalUser.email == creds.email.lower()))
    user = result.scalar_one_or_none()
    # Always run the bcrypt comparison, even against a dummy hash when the
    # account doesn't exist — see _DUMMY_HASH.
    password_hash = user.password_hash if user is not None else _DUMMY_HASH
    valid = _verify_password(creds.password, password_hash)
    if user is None or not valid:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = await _issue_session(session, user.id)
    return AuthResponse(token=token, email=user.email)


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
):
    if credentials is not None:
        await session.execute(delete(LocalSession).where(LocalSession.token == credentials.credentials))
        await session.commit()
    return {"message": "Signed out."}


@router.post("/change-password", response_model=AuthResponse)
async def change_password(
    body: ChangePasswordRequest,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _change_password_limiter.check(user_id)

    user = await session.get(LocalUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    if not _verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    user.password_hash = _hash_password(body.new_password)
    # Changing the password rotates every session, including this one — the
    # caller gets a fresh token back so their own tab stays signed in instead
    # of being logged out by its own request.
    await session.execute(delete(LocalSession).where(LocalSession.user_id == user_id))
    token = await _issue_session(session, user.id)
    return AuthResponse(token=token, email=user.email)
