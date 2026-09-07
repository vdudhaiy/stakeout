"""Company logo URL via Finnhub's free /stock/profile2 endpoint.

Logos change on the order of years (a rebrand), so the DB refresh interval
here is far longer than peers_service's — most rows are effectively
write-once. Shares finnhub_client's outbound rate-limit budget with every
other Finnhub caller.

"" is a valid, cacheable answer (Finnhub has no logo on file for this
symbol) — distinct from None, which means the call itself didn't succeed
and should be retried rather than remembered.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects import postgresql, sqlite

from cache import TTLCache
from database import SessionLocal, _IS_SQLITE
from models.company_logo import CompanyLogo
from services import finnhub_client

import freshness

logger = logging.getLogger(__name__)

# Logos barely ever change — this is mostly a write-once table, so the
# refresh window is deliberately generous.
_REFRESH_INTERVAL = timedelta(days=180)

_logo_cache = TTLCache(ttl_seconds=24 * 60 * 60)  # in-process memo: 24 hours


def _upsert_statement(symbol: str, logo_url: str):
    insert = sqlite.insert if _IS_SQLITE else postgresql.insert
    stmt = insert(CompanyLogo).values(
        symbol=symbol, logo_url=logo_url, fetched_at=datetime.now(timezone.utc)
    )
    return stmt.on_conflict_do_update(
        index_elements=["symbol"],
        set_={"logo_url": stmt.excluded.logo_url, "fetched_at": stmt.excluded.fetched_at},
    )


async def _read_row(symbol: str) -> CompanyLogo | None:
    async with SessionLocal() as session:
        return await session.get(CompanyLogo, symbol)


async def _save(symbol: str, logo_url: str) -> None:
    async with SessionLocal() as session:
        await session.execute(_upsert_statement(symbol, logo_url))
        await session.commit()


def _is_fresh(row: CompanyLogo) -> bool:
    fetched_at = row.fetched_at
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched_at < _REFRESH_INTERVAL


async def _fetch_from_finnhub(symbol: str) -> str | None:
    """None means "couldn't get a fresh answer" and should be retried later;
    "" means Finnhub answered but has no logo for this symbol. Never raises."""
    data = await finnhub_client.get("/stock/profile2", {"symbol": symbol})
    if not isinstance(data, dict):
        return None
    logo = data.get("logo")
    return logo if isinstance(logo, str) else ""


async def get_logo(ticker: str) -> str | None:
    """Logo URL for `ticker`, or None if there isn't one (or nothing's
    known yet and Finnhub couldn't be reached).

    Same preference order as peers_service.get_peers: in-process cache -> a
    DB row still within `_REFRESH_INTERVAL` -> a live Finnhub call
    (persisted for next time) -> a stale DB row as a last resort -> None.
    """
    symbol = ticker.upper()
    cached = _logo_cache.get_stamped(symbol, freshness.CACHED, label="logo")
    if cached is not None:
        return cached or None

    row = await _read_row(symbol)
    if row is not None and _is_fresh(row):
        freshness.stamp(freshness.ARCHIVE, fetched_at=row.fetched_at, label="logo")
        _logo_cache.set(symbol, row.logo_url, stored_at=_epoch_of(row.fetched_at))
        return row.logo_url or None

    fresh = await _fetch_from_finnhub(symbol)
    if fresh is not None:
        freshness.stamp(freshness.LIVE, label="logo")
        await _save(symbol, fresh)
        _logo_cache.set(symbol, fresh)
        return fresh or None

    if row is not None:
        freshness.stamp(freshness.STALE, fetched_at=row.fetched_at, label="logo")
        _logo_cache.set(symbol, row.logo_url, stored_at=_epoch_of(row.fetched_at))
        return row.logo_url or None

    return None

def _epoch_of(value) -> float | None:
    """A DB timestamp as a POSIX float, or None if it can't be read."""
    if value is None:
        return None
    try:
        stamped = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return stamped.timestamp()
    except Exception:  # noqa: BLE001 — provenance is optional, the data is not
        return None

