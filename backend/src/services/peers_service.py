"""Company peers via Finnhub's free /stock/peers endpoint.

Peer groups are GICS-based and change rarely, so they're persisted in the
company_peers table (see models.peers) instead of only living in an
in-memory cache — a process restart shouldn't have to re-spend Finnhub's
free-tier quota to re-derive something that was already known. A short
in-process TTLCache sits in front of the DB read purely to avoid a query on
every request within the same window.

The actual HTTP call and outbound rate-limit budget live in
services.finnhub_client, shared with every other Finnhub-backed feature (see
services.logo_service) — a 429 or any other failure never raises past this
module: callers always get a list (possibly empty, possibly stale).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects import postgresql, sqlite

from cache import TTLCache
from database import SessionLocal, _IS_SQLITE
from models.peers import CompanyPeers
from services import finnhub_client

logger = logging.getLogger(__name__)

# How stale a DB row can be before we bother asking Finnhub for a fresh
# list. GICS peer groups don't move week to week, so this is deliberately
# generous — it's the main lever keeping this feature inside the free tier.
_REFRESH_INTERVAL = timedelta(days=7)

_peers_cache = TTLCache(ttl_seconds=60 * 60)  # in-process memo: 1 hour


def _upsert_statement(symbol: str, peer_list: list[str]):
    insert = sqlite.insert if _IS_SQLITE else postgresql.insert
    stmt = insert(CompanyPeers).values(
        symbol=symbol, peers=peer_list, fetched_at=datetime.now(timezone.utc)
    )
    return stmt.on_conflict_do_update(
        index_elements=["symbol"],
        set_={"peers": stmt.excluded.peers, "fetched_at": stmt.excluded.fetched_at},
    )


async def _read_row(symbol: str) -> CompanyPeers | None:
    async with SessionLocal() as session:
        return await session.get(CompanyPeers, symbol)


async def _save(symbol: str, peer_list: list[str]) -> None:
    async with SessionLocal() as session:
        await session.execute(_upsert_statement(symbol, peer_list))
        await session.commit()


def _is_fresh(row: CompanyPeers) -> bool:
    fetched_at = row.fetched_at
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched_at < _REFRESH_INTERVAL


async def _fetch_from_finnhub(symbol: str) -> list[str] | None:
    """None means "couldn't get a fresh answer" — quota spent, no key
    configured, or the request itself failed. Never raises."""
    data = await finnhub_client.get("/stock/peers", {"symbol": symbol})
    if not isinstance(data, list):
        return None
    return [p for p in data if isinstance(p, str) and p.upper() != symbol.upper()]


async def get_peers(ticker: str) -> list[str]:
    """Peer tickers for `ticker`, freshest available within budget.

    Preference order: in-process cache -> a DB row still within
    `_REFRESH_INTERVAL` -> a live Finnhub call (persisted for next time) ->
    a stale DB row as a last resort (better than blanking the panel because
    Finnhub is down or the quota's spent for this minute) -> empty list.
    """
    symbol = ticker.upper()
    cached = _peers_cache.get(symbol)
    if cached is not None:
        return cached

    row = await _read_row(symbol)
    if row is not None and _is_fresh(row):
        _peers_cache.set(symbol, row.peers)
        return row.peers

    fresh = await _fetch_from_finnhub(symbol)
    if fresh is not None:
        await _save(symbol, fresh)
        _peers_cache.set(symbol, fresh)
        return fresh

    # Finnhub didn't come through this time — fall back to whatever's on
    # record, however old, rather than showing nothing.
    if row is not None:
        _peers_cache.set(symbol, row.peers)
        return row.peers

    return []
