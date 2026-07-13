"""Latest published GitHub release tag, shown in the frontend footer.

Queries the GitHub REST API (unauthenticated, no token needed for public
repos) and caches the result — the tag only changes when a new release is
cut, so there's no reason to hit GitHub on every dashboard load.
"""

from __future__ import annotations

import logging

import httpx

from ..cache import version_cache

logger = logging.getLogger(__name__)

REPO = "vdudhaiy/stakeout"
_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
_CACHE_KEY = "latest_release_tag"


async def get_latest_release_tag() -> str | None:
    """Returns the tag name of the latest GitHub release, or None on failure."""
    cached = version_cache.get(_CACHE_KEY)
    if cached is not None:
        return cached

    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(url, headers={"Accept": "application/vnd.github+json"})
            r.raise_for_status()
            tag = r.json().get("tag_name")
    except Exception as e:  # noqa: BLE001 — GitHub down/rate-limited, fall back to local version
        logger.warning("Failed to fetch latest release tag: %s", e)
        return None

    if tag:
        version_cache.set(_CACHE_KEY, tag)
    return tag
