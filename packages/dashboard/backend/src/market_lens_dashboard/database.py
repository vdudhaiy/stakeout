import os
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import BASE_DIR


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        # Normalize legacy postgres:// scheme and bare postgresql:// to the
        # asyncpg driver variant that SQLAlchemy async requires.
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://") and "+asyncpg" not in url:
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    return f"sqlite+aiosqlite:///{BASE_DIR / 'portfolio.db'}"


DATABASE_URL = _database_url()
_IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    # Import models here so their classes are registered with Base.metadata
    # before create_all runs. This avoids circular imports at module level.
    from .models import portfolio  # noqa: F401

    if not _IS_SQLITE:
        # PostgreSQL: schema is managed entirely by Alembic.
        # Run `alembic upgrade head` before starting the server (e.g. as a
        # Render pre-deploy command). Nothing to do here at runtime.
        return

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migrate existing SQLite databases: add columns introduced after the
        # initial release. create_all only creates missing tables; it does not
        # alter existing ones, so we patch manually.
        result = await conn.execute(text("PRAGMA table_info(holdings)"))
        holdings_cols = {row[1] for row in result.fetchall()}
        if "company_name" not in holdings_cols:
            await conn.execute(
                text("ALTER TABLE holdings ADD COLUMN company_name TEXT NOT NULL DEFAULT ''")
            )

        result = await conn.execute(text("PRAGMA table_info(transactions)"))
        txn_cols = {row[1] for row in result.fetchall()}
        if "shares_remaining" not in txn_cols:
            await conn.execute(
                text("ALTER TABLE transactions ADD COLUMN shares_remaining INTEGER NOT NULL DEFAULT 0")
            )
            # Seed buy lots with their full share count so cost_basis is non-zero
            # immediately. A FIFO repair pass in the startup lifespan will then
            # reduce these to the correct unsold amounts for users who have sold.
            await conn.execute(
                text("UPDATE transactions SET shares_remaining = shares WHERE sale = FALSE")
            )
