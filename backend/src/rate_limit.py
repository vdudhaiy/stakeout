"""Lightweight in-memory rate limiting for auth endpoints.

Single-process, in-memory by design — same reasoning as cache.py: no Redis
on Render's free tier, and these endpoints are low-volume enough that a
per-(IP, limiter) sliding window is more than sufficient. State resets on
restart, which just resets everyone's quota — not a concern here.

Scoped to local-auth mode's own endpoints (signup/login/change-password) —
a real Supabase deployment never mounts those routes at all, and Supabase
enforces its own rate limits server-side for the calls the frontend makes
to it directly.
"""

from __future__ import annotations

import time

from fastapi import HTTPException, Request

_MAX_TRACKED_KEYS = 5000


class RateLimiter:
    """At most `max_requests` per `window_seconds`, per key (sliding window)."""

    def __init__(self, max_requests: int, window_seconds: float):
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self._window
        hits = [t for t in self._hits.get(key, ()) if t > cutoff]
        if len(hits) >= self._max:
            self._hits[key] = hits
            raise HTTPException(status_code=429, detail="Too many attempts — please wait a bit and try again.")
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


def _client_ip(request: Request) -> str:
    # Best-effort — trusts the platform's reverse proxy to set this (Render
    # does). Not hardened against a client spoofing the header on a deployment
    # with no proxy in front of it; this is a brute-force deterrent for a
    # dev-convenience auth path, not a hardened security boundary (see
    # local_auth.py's own docstring).
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
