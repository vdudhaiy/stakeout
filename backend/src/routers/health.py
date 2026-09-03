'''
Health-check and metadata endpoints for the dashboard backend API.
'''
import cache
from fastapi import APIRouter

from config import FINNHUB_API_KEY
from services import finnhub_client, yf_guard

router = APIRouter()


@router.get("/health")
async def health_check():
    '''
    Health-check endpoint to verify that the API is running.

    `status` is always "ok" while the process is serving — this is what the
    platform's health check polls, and a backing-off upstream is not a
    reason to have the instance replaced.

    `upstream` is the part worth reading by hand. Both providers back off
    silently on a 429 and degrade to cached or archived data, which is the
    right behaviour but makes "rate-limited" and "broken" look identical
    from the outside. Without this you can only tell them apart by reading
    logs; here, a non-zero `cooldown_seconds` says plainly that responses
    are being served from cache and roughly how long that lasts.
    '''
    return {
        "status": "ok",
        "upstream": {
            "yfinance": {
                "rate_limited": yf_guard.in_cooldown(),
                "cooldown_seconds": round(yf_guard.cooldown_remaining()),
            },
            "finnhub": {
                "configured": bool(FINNHUB_API_KEY),
                "rate_limited": finnhub_client.in_cooldown(),
                "cooldown_seconds": round(finnhub_client.cooldown_remaining()),
            },
        },
        # Entry counts, not contents. Enough to tell a cold process (all
        # zeros — every request is about to go upstream) from a warm one,
        # and to spot a cache that isn't being populated at all.
        "cache_entries": {
            name: len(value._store)
            for name in dir(cache)
            if isinstance(value := getattr(cache, name), cache.TTLCache)
        },
    }
