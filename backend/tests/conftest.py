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

from market_lens_dashboard import markets
from market_lens_dashboard.auth import get_current_user, get_optional_user
from market_lens_dashboard.database import Base, get_session
from market_lens_dashboard.models import local_auth as _local_auth  # noqa: F401 — registers models with Base
from market_lens_dashboard.models import portfolio as _  # noqa: F401 — registers models with Base
from market_lens_dashboard.main import app

TEST_USER_ID = "test-user"


@pytest.fixture(autouse=True)
def _clear_calendar_cache():
    """markets.get_calendar() memoizes resolved calendars in a module-level dict.

    Without clearing it, a mocked calendar cached by one test leaks into every
    later test that requests the same market, regardless of what it patches.
    """
    markets._calendar_cache.clear()
    yield
    markets._calendar_cache.clear()


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

    Auth is also overridden to a fixed test user — routes require a real
    Supabase JWT outside of tests, but these tests exercise routing/business
    logic, not token verification (that's covered separately, if at all, by
    mocking jwt.decode directly).

    The app lifespan's init_db / repair_all_fifo are patched out so they don't
    try to use the module-level engine (a separate in-memory instance).
    """
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_current_user] = lambda: TEST_USER_ID
    app.dependency_overrides[get_optional_user] = lambda: TEST_USER_ID

    with patch("market_lens_dashboard.main.init_db", new_callable=AsyncMock):
        with patch("market_lens_dashboard.main.repair_all_fifo", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                yield c

    app.dependency_overrides.clear()
