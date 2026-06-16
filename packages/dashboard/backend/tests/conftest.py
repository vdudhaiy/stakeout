import os

# Must be set before any app module is imported so the module-level engine
# uses an in-memory database rather than writing to the real portfolio.db.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from market_lens_dashboard.database import Base, get_session
from market_lens_dashboard.models import portfolio as _  # noqa: F401 — registers models with Base
from market_lens_dashboard.main import app


@pytest_asyncio.fixture
async def db_engine():
    """Fresh in-memory SQLite engine with all tables created. Isolated per test."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Async session bound to the per-test in-memory database."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine):
    """HTTP test client with get_session overridden to use the per-test DB.

    The app lifespan's init_db / repair_all_fifo are patched out so they don't
    try to use the module-level engine (a separate in-memory instance).
    """
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override

    with patch("market_lens_dashboard.main.init_db", new_callable=AsyncMock):
        with patch("market_lens_dashboard.main.repair_all_fifo", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                yield c

    app.dependency_overrides.clear()
