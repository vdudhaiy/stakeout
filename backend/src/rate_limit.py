"""Lightweight in-memory rate limiting.

Single-process, in-memory by design — same reasoning as cache.py: no Redis
on Render's free tier. State resets on restart, which just resets everyone's
quota, and with several instances each holds its own window, so the
effective limit is per-instance. Both are fine for what this is: a brake on
one abusive caller, not a precise quota system.

Two things are protected, for different reasons:

**Auth endpoints** (signup/login/change-password) — brute-force deterrence.
Only mounted in local-auth mode; a real Supabase deployment never exposes
those routes and Supabase enforces its own limits server-side. Those
limiters are declared in routers/local_auth.py, next to the routes they
guard; only the machinery lives here.

**Unauthenticated data endpoints** (stocks, indicators, news, peers, logo,
quote, fx, ai) — upstream-budget protection. These are readable with no
token at all, and every one of them can end in a yfinance, Finnhub or GDELT
call whose free-tier quota is shared by every user of the app. The caches in
cache.py stop *repeat* work; they can't stop a caller from walking distinct
tickers or search terms, each of which is a legitimate cache miss and a
fresh upstream request. That's what the limits below bound.

Budgets are sized against a real page, not a guess: opening the tracker
fires roughly 25 public requests (the ticker tape alone asks for a dozen
symbols), so the read tier has to absorb several reloads a minute without
ever inconveniencing a real user. Endpoints that can start *new* upstream
work regardless of cache state get their own, much tighter budgets.

Known limitation: keyed by client IP, so users behind one NAT share a
budget. Acceptable at this size, and the read tier is loose enough that it
takes many simultaneous users to matter.
"""

from __future__ import annotations

import math
import os
import time

from fastapi import Depends, HTTPException, Request

_MAX_TRACKED_KEYS = 5000

# Every limiter ever constructed, so reset_all() can clear the lot without
# anyone having to remember to register a new one (they're process-global
# state, and a missed one leaks a burst from one test into the next).
_registry: list[RateLimiter] = []


class RateLimiter:
    """At most `max_requests` per `window_seconds`, per key (sliding window)."""

    def __init__(self, max_requests: int, window_seconds: float):
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}
        _registry.append(self)

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self._window
        hits = [t for t in self._hits.get(key, ()) if t > cutoff]
        if len(hits) >= self._max:
            self._hits[key] = hits
            # Tell the caller when to come back rather than leaving them to
            # guess and retry into the same wall: the window clears once the
            # oldest hit still inside it ages out. `hits` is empty only when
            # the limit is 0 (an endpoint switched off), in which case the
            # honest answer is the full window.
            oldest = hits[0] if hits else now
            retry_after = max(1, math.ceil(oldest + self._window - now))
            raise HTTPException(
                status_code=429,
                detail="Too many requests — please wait a bit and try again.",
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)
        self._hits[key] = hits
        # Crude bound on memory, same eviction spirit as cache.TTLCache: drop
        # a chunk of keys with no recent activity once the dict gets large.
        if len(self._hits) > _MAX_TRACKED_KEYS:
            stale = [k for k, v in self._hits.items() if not v or v[-1] < cutoff]
            for k in stale[: max(1, len(self._hits) // 8)]:
                self._hits.pop(k, None)

    def reset(self) -> None:
        """Test-only: clear all tracked state."""
        self._hits.clear()


def _trust_forwarded_for() -> bool:
    """Whether to believe X-Forwarded-For.

    Defaults to true because every supported deployment runs behind a proxy
    that sets it (Render, and docker/nginx.conf's `proxy_set_header`). An
    instance exposed directly to the internet should set
    TRUST_FORWARDED_FOR=false — otherwise a caller can spoof the header and
    hand itself a fresh budget per request, which makes every limit here
    decorative.
    """
    return os.getenv("TRUST_FORWARDED_FOR", "true").strip().lower() not in ("false", "0", "no")


def _client_ip(request: Request) -> str:
    # The leftmost X-Forwarded-For entry is the original client as recorded
    # by the first proxy in the chain. Only as trustworthy as that proxy —
    # see _trust_forwarded_for.
    if _trust_forwarded_for():
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def by_client_ip(limiter: RateLimiter):
    """FastAPI dependency factory: 429s once `limiter`'s quota is spent for
    the caller's IP. Each call site passes its own `limiter` instance, so a
    burst against /auth/login doesn't also throttle /auth/signup.
    """
    def dependency(request: Request) -> None:
        limiter.check(_client_ip(request))
    return dependency


_MINUTE = 60.0
_HOUR = 60 * 60.0

# Auth-endpoint limiters live in routers/local_auth.py, next to the routes
# they guard and the comment explaining why they're deliberately generous.

# ── Public data endpoints ─────────────────────────────────────────────────
# Read tier: cached, cheap, and fired in bursts by a normal page load. Loose
# enough for ~8 full reloads a minute, tight enough to cap a scraper at a
# few requests a second.
public_read_limiter = RateLimiter(max_requests=200, window_seconds=_MINUTE)

# Search is its own tier because the cache key is the query string: distinct
# queries are all legitimate misses, so this endpoint turns one caller into
# unbounded yfinance Search traffic. The autocomplete debounces, so a real
# user never approaches this.
search_limiter = RateLimiter(max_requests=30, window_seconds=_MINUTE)

# News keys on ticker and region — same amplification shape as search, but
# against GDELT's free tier.
news_limiter = RateLimiter(max_requests=60, window_seconds=_MINUTE)

# Archiving a new ticker is the only unauthenticated *write* to shared
# state, and it downloads years of daily history to serve it. Strictest of
# the public tiers by a wide margin.
add_stock_limiter = RateLimiter(max_requests=10, window_seconds=_HOUR)

# Each AI call is a full LLM generation. Cheap in quota terms (Ollama is
# local) but expensive in CPU and wall time, which is the scarce thing on a
# small instance.
ai_limiter = RateLimiter(max_requests=20, window_seconds=_MINUTE)


# The Performance panel's "refresh" archives any held ticker that has no
# price history yet — years of daily bars per miss. Authenticated, so it is
# keyed on user id rather than IP, and generous enough to cover a few
# genuine retries while a new portfolio fills in.
performance_backfill_limiter = RateLimiter(max_requests=8, window_seconds=_HOUR)


def reset_all() -> None:
    """Test-only: clear every limiter's tracked state.

    These are process-global, so without this one test's burst spends the
    next test's budget (see conftest's autouse fixture).
    """
    for limiter in _registry:
        limiter.reset()


# Router-level shorthand. Applied on the APIRouter rather than per route so
# a new endpoint on a public router is covered by default — forgetting to
# add a decorator is exactly how these gaps appear.
public_read = [Depends(by_client_ip(public_read_limiter))]
