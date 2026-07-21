"""Accounts for local-auth mode (see ..auth.local_auth_enabled).

Only ever populated in the local SQLite database — a real Supabase
deployment never mounts the router that writes to these tables, so they
simply don't exist there (no Alembic migration for Postgres).
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LocalUser(Base):
    """A locally created account. `id` is a UUID string so it's a drop-in
    replacement for a Supabase `sub` claim everywhere user_id is stored."""

    __tablename__ = "local_users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class LocalSession(Base):
    """An issued login session. No expiry — this is a dev-only auth path,
    not a security boundary; sessions live until an explicit logout."""

    __tablename__ = "local_sessions"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
