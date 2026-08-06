import os
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import BASE_DIR


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

if _IS_SQLITE:
    # SQLite does not enforce FOREIGN KEY constraints per connection unless told
    # to — unlike Postgres, which always enforces them. Without this, a write
    # that races a concurrent delete of its FK parent (e.g. a background
    # dividend-sync insert racing a holding delete) succeeds silently instead
    # of raising IntegrityError, leaving an orphaned row with no error at all.
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:  # noqa: ANN001, ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    # Import models here so their classes are registered with Base.metadata
    # before create_all runs. This avoids circular imports at module level.
    from models import local_auth, market_data, portfolio  # noqa: F401

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
        if "user_id" not in holdings_cols:
            await conn.execute(
                text("ALTER TABLE holdings ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'")
            )
        if "market" not in holdings_cols:
            await conn.execute(
                text("ALTER TABLE holdings ADD COLUMN market TEXT NOT NULL DEFAULT 'US'")
            )
            # Backfill: classify existing holdings by ticker suffix
            await conn.execute(text(
                """UPDATE holdings SET market = 'IN'
                    WHERE ticker LIKE '%.NS' OR ticker LIKE '%.BO'"""
            ))

        if "portfolio_id" not in holdings_cols:
            # Mirrors alembic 009. Two SQLite-only caveats, both dev-path only
            # (deployments are Postgres and go through Alembic):
            #  - the column stays nullable; SQLite can't add a NOT NULL column
            #    with no default to a populated table. Harmless — the model
            #    declares it NOT NULL and create_all gets fresh DBs right.
            #  - the old uq_holdings_user_ticker index can't be dropped without
            #    rebuilding the table, so an existing portfolio.db will still
            #    refuse the same ticker in two portfolios. Delete portfolio.db
            #    (or run against Postgres) to exercise that locally.
            await conn.execute(text("ALTER TABLE holdings ADD COLUMN portfolio_id INTEGER"))
            await conn.execute(text(
                """INSERT INTO portfolios (user_id, market, name, name_key, created_at)
                   SELECT DISTINCT user_id, market, 'main', 'main',
                          strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')
                     FROM holdings"""
            ))
            await conn.execute(text(
                """UPDATE holdings SET portfolio_id = (
                       SELECT p.id FROM portfolios p
                        WHERE p.user_id = holdings.user_id
                          AND p.market = holdings.market
                          AND p.name_key = 'main'
                   )"""
            ))

        result = await conn.execute(text("PRAGMA table_info(audit_log)"))
        audit_cols = {row[1] for row in result.fetchall()}
        if audit_cols and "portfolio_id" not in audit_cols:
            # NULL means "written before portfolios existed" — undo falls back
            # to the market's default, where the backfill above put everything.
            await conn.execute(text("ALTER TABLE audit_log ADD COLUMN portfolio_id INTEGER"))

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
