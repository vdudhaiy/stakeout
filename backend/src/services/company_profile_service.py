"""Display name, sector and industry for a ticker — fetched once, kept.

All three come out of a single yfinance `.info` call. They used to be read
by two separate code paths that each made their own `.info` call for the
same ticker, and each only remembered the answer in memory: `.info` is the
most rate-limit-prone call yfinance offers, and the free-tier host restarts
often enough that a 24-hour in-memory TTL rarely survived to be used. So
this is now one call, persisted (models.company_profile), the same
DB-backed pattern as peers_service and logo_service.

Preference order mirrors those two: in-process cache -> a DB row still
within _REFRESH_INTERVAL -> a live yfinance call (persisted for next time)
-> a stale DB row as a last resort -> empty fields. Never raises.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import yfinance as yf
from sqlalchemy.dialects import postgresql, sqlite

from cache import info_cache, single_flight
from database import SessionLocal, _IS_SQLITE
from models.company_profile import CompanyProfile
from services import yf_guard

import freshness

logger = logging.getLogger(__name__)

# Names, sectors and industries move on the order of a rebrand or a GICS
# reclassification. A month is already far more often than they change; it
# exists only so a row fetched during an outage eventually gets corrected.
_REFRESH_INTERVAL = timedelta(days=30)

_EMPTY = {"name": "", "sector": "", "industry": ""}


def _upsert_statement(symbol: str, profile: dict):
    insert = sqlite.insert if _IS_SQLITE else postgresql.insert
    stmt = insert(CompanyProfile).values(
        symbol=symbol,
        name=profile["name"],
        sector=profile["sector"],
        industry=profile["industry"],
        fetched_at=datetime.now(timezone.utc),
    )
    return stmt.on_conflict_do_update(
        index_elements=["symbol"],
        set_={
            "name": stmt.excluded.name,
            "sector": stmt.excluded.sector,
            "industry": stmt.excluded.industry,
            "fetched_at": stmt.excluded.fetched_at,
        },
    )


async def _read_row(symbol: str) -> CompanyProfile | None:
    try:
        async with SessionLocal() as session:
            return await session.get(CompanyProfile, symbol)
    except Exception as e:  # noqa: BLE001 — a cache that can't be read is just a miss
        logger.warning("Company profile read failed for %s: %r", symbol, e)
        return None


async def _save(symbol: str, profile: dict) -> None:
    try:
        async with SessionLocal() as session:
            await session.execute(_upsert_statement(symbol, profile))
            await session.commit()
    except Exception as e:  # noqa: BLE001 — failing to persist must not fail the lookup
        logger.warning("Company profile write failed for %s: %r", symbol, e)


def _is_fresh(row: CompanyProfile) -> bool:
    fetched_at = row.fetched_at
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched_at < _REFRESH_INTERVAL


def _as_dict(row: CompanyProfile) -> dict:
    return {"name": row.name or "", "sector": row.sector or "", "industry": row.industry or ""}


def _fetch_info(symbol: str) -> dict:
    info = yf.Ticker(symbol).info or {}
    return {
        "name": info.get("displayName") or info.get("shortName") or info.get("longName") or "",
        "sector": info.get("sector") or "",
        "industry": info.get("industry") or "",
    }


async def _fetch_from_yfinance(symbol: str) -> dict | None:
    """None means the call didn't succeed and should be retried later."""
    try:
        with yf_guard.guard():
            return await asyncio.to_thread(_fetch_info, symbol)
    except Exception as e:  # noqa: BLE001 — degrades to "no fresh data"
        logger.warning("Company profile lookup failed for %s: %r", symbol, e)
        return None


async def get_profile(ticker: str) -> dict:
    """{"name", "sector", "industry"} for `ticker`, freshest within budget.

    Fields are always present; "" means "not known". Never raises.
    """
    symbol = ticker.upper().strip()
    if not symbol:
        return dict(_EMPTY)

    cache_key = f"profile:{symbol}"
    cached = info_cache.get_stamped(cache_key, freshness.CACHED, label="profile")
    if cached is not None:
        return cached

    async def _load() -> dict:
        row = await _read_row(symbol)
        if row is not None and _is_fresh(row):
            profile = _as_dict(row)
            freshness.stamp(freshness.ARCHIVE, fetched_at=row.fetched_at, label="profile")
            info_cache.set(cache_key, profile, stored_at=_epoch_of(row.fetched_at))
            return profile

        fresh = await _fetch_from_yfinance(symbol)
        if fresh is not None and any(fresh.values()):
            freshness.stamp(freshness.LIVE, label="profile")
            await _save(symbol, fresh)
            info_cache.set(cache_key, fresh)
            return fresh

        # yfinance didn't come through — an old row beats nothing, and an
        # all-empty answer is deliberately not cached so it retries rather
        # than pinning the ticker to "unknown" for the full TTL.
        if row is not None:
            profile = _as_dict(row)
            freshness.stamp(freshness.STALE, fetched_at=row.fetched_at, label="profile")
            info_cache.set(cache_key, profile, stored_at=_epoch_of(row.fetched_at))
            return profile
        return dict(_EMPTY)

    return await single_flight(cache_key, _load)

def _epoch_of(value) -> float | None:
    """A DB timestamp as a POSIX float, or None if it can't be read."""
    if value is None:
        return None
    try:
        stamped = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return stamped.timestamp()
    except Exception:  # noqa: BLE001 — provenance is optional, the data is not
        return None



async def get_profiles(tickers: list[str]) -> dict[str, dict]:
    """Profiles for a batch, resolved concurrently. Every requested
    (uppercased) ticker appears as a key."""
    unique = list(dict.fromkeys(t.upper().strip() for t in tickers if t.strip()))
    profiles = await asyncio.gather(*(get_profile(t) for t in unique))
    return dict(zip(unique, profiles))
