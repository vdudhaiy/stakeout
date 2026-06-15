from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import BASE_DIR

DATABASE_URL = f"sqlite+aiosqlite:///{BASE_DIR / 'portfolio.db'}"

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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migrate existing databases: add company_name if the column is absent.
        # create_all only creates missing tables, it does not alter existing ones.
        result = await conn.execute(text("PRAGMA table_info(holdings)"))
        existing = {row[1] for row in result.fetchall()}
        if "company_name" not in existing:
            await conn.execute(
                text("ALTER TABLE holdings ADD COLUMN company_name TEXT NOT NULL DEFAULT ''")
            )
