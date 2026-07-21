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

from ..database import get_session
from ..models.local_auth import LocalSession, LocalUser
from ..schemas.local_auth import AuthResponse, Credentials

router = APIRouter(prefix="/auth", tags=["Local Auth"])

_bearer = HTTPBearer(auto_error=False)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


async def _issue_session(session: AsyncSession, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    session.add(LocalSession(token=token, user_id=user_id))
    await session.commit()
    return token


@router.post("/signup", response_model=AuthResponse)
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


@router.post("/login", response_model=AuthResponse)
async def login(creds: Credentials, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(LocalUser).where(LocalUser.email == creds.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not _verify_password(creds.password, user.password_hash):
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
