'''
Server-side provenance for every payload the app renders.

The problem this solves: almost nothing the frontend displays came from
upstream just now. A quote may be sixty seconds old, a fundamentals snapshot
six hours, a chart is read from an archive that a rate limit may have left a
week behind — and all four render identically. The user cannot tell current
data from a cached copy from a stale one being served because the live fetch
failed, which is exactly the distinction that decides whether they should act
on what they are looking at.

Timestamps are produced *here*, not in the browser. A frontend clock records
when the response arrived, which for anything cached at any of the app's five
layers is a different (and much more flattering) number than when the data was
actually pulled. It also can't see the difference between a fresh answer and a
week-old fallback, since both arrive as a normal 200.

Mechanics: a request-scoped ContextVar collects a stamp from each layer that
contributed, and middleware reports the *least fresh* of them on the response.
Least-fresh, not first or last, because an aggregate endpoint blends tiers —
/stocks/{ticker}/dashboard mixes a live quote with a six-hour snapshot and an
archived chart, and describing that as "live" because one part of it was is
the misreport this module exists to prevent.

Fail-soft throughout: a stamp that cannot be recorded costs a header, and no
caller should ever have to handle an error from annotating its own data.
'''

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

# Sources, ordered by distance from live. The header reports the maximum.
LIVE = "live"          # fetched from upstream during this request
CACHED = "cached"      # served from a TTL cache that has not expired
ARCHIVE = "archive"    # read from a DB table (market_data, index_history, …)
STALE = "stale"        # a superseded copy, served because a live fetch failed

_RANK = {LIVE: 0, CACHED: 1, ARCHIVE: 2, STALE: 3}


@dataclass(frozen=True)
class Stamp:
    source: str
    fetched_at: datetime | None
    # Newest data point in the payload, for series that carry their own
    # calendar. A chart pulled two minutes ago whose last bar is from Friday
    # is fresh *and* three days behind; only reporting one of those numbers
    # hides the question the user is actually asking.
    data_through: date | None = None
    label: str | None = None


_stamps: ContextVar[list[Stamp] | None] = ContextVar("freshness_stamps", default=None)

# Distinguishes "didn't say when, so it's now" (a live fetch) from "genuinely
# don't know when this was pulled" — archive rows written before market_data
# tracked a fetch time. Collapsing the two would date every legacy bar to the
# moment it was read, which is the single most misleading thing this module
# could report.
_NOW = object()


def begin() -> None:
    '''Start collecting for a request. Called by the middleware.'''
    _stamps.set([])


def stamp(
    source: str,
    fetched_at: datetime | float | None = _NOW,
    data_through: date | str | None = None,
    label: str | None = None,
) -> None:
    '''Record that `source` contributed to the current response.

    `fetched_at` accepts a datetime or a POSIX timestamp (what the caches
    store). Omitting it means "now", which is only correct for a live fetch;
    passing None explicitly means the fetch time is genuinely unknown.
    '''
    collected = _stamps.get()
    if collected is None:
        return  # outside a request (background sweep, test, script)
    try:
        collected.append(Stamp(
            source=source,
            fetched_at=_now() if fetched_at is _NOW else (
                _as_datetime(fetched_at) if fetched_at is not None else None
            ),
            data_through=_as_date(data_through),
            label=label,
        ))
    except Exception as e:  # noqa: BLE001 — provenance must never break a response
        logger.debug("Could not record freshness stamp (%s): %r", source, e)


def snapshot() -> Stamp | None:
    '''The least-fresh contribution to this response, or None if unstamped.'''
    collected = _stamps.get()
    if not collected:
        return None
    worst = max(collected, key=lambda s: (_RANK.get(s.source, 0), -_epoch(s.fetched_at)))
    # The oldest fetch time and the oldest data point may come from different
    # stamps; report each one honestly rather than whichever happened to share
    # a record with the worst source.
    oldest_fetch = min((s.fetched_at for s in collected if s.fetched_at), default=None)
    through = min((s.data_through for s in collected if s.data_through), default=None)
    return Stamp(
        source=worst.source, fetched_at=oldest_fetch, data_through=through, label=worst.label,
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _epoch(value: datetime | None) -> float:
    return value.timestamp() if value else 0.0


def _as_datetime(value: datetime | float) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromtimestamp(float(value), tz=timezone.utc)


def _as_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
