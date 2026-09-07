'''
Async access to the service_state key/value table (models/service_state.py).

Same shape as market_data_service: short-lived, self-opened sessions, and
fail-soft on every path. A caller reaching for persisted state always has a
working in-memory answer already — losing the persisted copy costs one
forgotten fact across a restart, never a failed request — so nothing here
raises.
'''

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects import postgresql, sqlite

from database import SessionLocal, _IS_SQLITE
from models.service_state import ServiceState

logger = logging.getLogger(__name__)


async def get(key: str) -> tuple[str, datetime] | None:
    '''The stored value and its write time, or None if unset/unreadable.'''
    try:
        async with SessionLocal() as session:
            result = await session.execute(
                select(ServiceState.value, ServiceState.updated_at).where(ServiceState.key == key)
            )
            row = result.first()
    except Exception as e:  # noqa: BLE001 — degrades to "nothing stored"
        logger.warning("service_state read failed for %s: %r", key, e)
        return None
    if row is None:
        return None
    value, updated_at = row
    # SQLite hands back naive datetimes even from a timezone=True column.
    if updated_at is not None and updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return value, updated_at


async def set(key: str, value: str) -> None:  # noqa: A001 — mirrors the cache API
    '''Upsert `key`. Never raises.'''
    insert = sqlite.insert if _IS_SQLITE else postgresql.insert
    stmt = insert(ServiceState).values(
        key=key, value=value, updated_at=datetime.now(timezone.utc)
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["key"],
        set_={"value": stmt.excluded.value, "updated_at": stmt.excluded.updated_at},
    )
    try:
        async with SessionLocal() as session:
            await session.execute(stmt)
            await session.commit()
    except Exception as e:  # noqa: BLE001 — the in-process copy still holds
        logger.warning("service_state write failed for %s: %r", key, e)


async def clear(key: str) -> None:
    '''Remove `key`. Never raises.'''
    try:
        async with SessionLocal() as session:
            await session.execute(delete(ServiceState).where(ServiceState.key == key))
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("service_state clear failed for %s: %r", key, e)
