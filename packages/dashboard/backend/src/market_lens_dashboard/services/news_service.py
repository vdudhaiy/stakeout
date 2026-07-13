"""Market and per-stock news with layered free sources.

Primary source: GDELT DOC 2.0 API (free, no key, global coverage).
Fallback:       Yahoo Finance news via yfinance.

Per-stock news is assembled in priority order:
  1. the company itself
  2. its industry / technology
  3. the market it trades on
De-duplicated by URL/title, capped, and cached for 15 minutes.

GDELT caveats handled here:
- Query terms shorter than ~3 chars or pure tickers match poorly, so we
  query on the company *name* plus finance context terms.
- `sourcelang:english` keeps results readable; `sourcecountry` biases
  market news to US / India as requested.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from urllib.parse import quote_plus

import httpx

from ..cache import news_cache
from ..markets import MARKET_IN, MARKET_US, market_of

logger = logging.getLogger(__name__)

_GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
_TIMEOUT = httpx.Timeout(8.0, connect=4.0)
_HEADERS = {"User-Agent": "stakeout-open-source-tracker/1.0"}


def _parse_gdelt_date(raw: str | None) -> str | None:
    # GDELT format: 20260713T101500Z
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").isoformat() + "Z"
    except ValueError:
        return None


async def _gdelt_articles(query: str, max_records: int = 12, timespan: str = "3d") -> list[dict]:
    params = (
        f"?query={quote_plus(query)}"
        f"&mode=ArtList&format=json&maxrecords={max_records}"
        f"&timespan={timespan}&sort=DateDesc"
    )
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
        r = await client.get(_GDELT + params)
        r.raise_for_status()
        data = r.json()
    articles = []
    for a in data.get("articles", []):
        if not a.get("url") or not a.get("title"):
            continue
        articles.append(
            {
                "title": a["title"],
                "url": a["url"],
                "source": a.get("domain") or a.get("sourcecountry") or "",
                "published_at": _parse_gdelt_date(a.get("seendate")),
                "image": a.get("socialimage") or None,
                "provider": "gdelt",
            }
        )
    return articles


async def _yahoo_articles(ticker: str, limit: int = 10) -> list[dict]:
    def _fetch() -> list[dict]:
        import yfinance as yf

        items = yf.Ticker(ticker).news or []
        out = []
        for item in items[:limit]:
            content = item.get("content", item)  # yfinance >=0.2.5x nests under "content"
            title = content.get("title")
            url = (
                (content.get("canonicalUrl") or {}).get("url")
                or (content.get("clickThroughUrl") or {}).get("url")
                or item.get("link")
            )
            if not title or not url:
                continue
            pub = content.get("pubDate") or content.get("displayTime")
            thumb = None
            thumbnail = content.get("thumbnail") or {}
            resolutions = thumbnail.get("resolutions") or []
            if resolutions:
                thumb = resolutions[0].get("url")
            out.append(
                {
                    "title": title,
                    "url": url,
                    "source": (content.get("provider") or {}).get("displayName", "Yahoo Finance"),
                    "published_at": pub,
                    "image": thumb,
                    "provider": "yahoo",
                }
            )
        return out

    return await asyncio.to_thread(_fetch)


def _dedupe(articles: list[dict], cap: int) -> list[dict]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    out = []
    for a in articles:
        url = a["url"].split("?")[0].rstrip("/")
        title_key = a["title"].strip().lower()[:80]
        if url in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(title_key)
        out.append(a)
        if len(out) >= cap:
            break
    return out


async def get_market_news(region: str = "all", limit: int = 12) -> dict:
    """Headlines for the stock market at large. US and India are prioritized."""
    region = region.lower()
    key = f"market:{region}:{limit}"
    cached = news_cache.get(key)
    if cached is not None:
        return cached

    queries: list[tuple[str, str]] = []
    if region in ("all", "us"):
        queries.append(("us", '("stock market" OR "wall street" OR nasdaq OR "S&P 500") sourcecountry:US sourcelang:english'))
    if region in ("all", "in"):
        queries.append(("in", '("stock market" OR sensex OR nifty OR "dalal street") sourcecountry:IN sourcelang:english'))
    if region == "all":
        queries.append(("global", '"stock market" sourcelang:english'))

    per_query = max(4, limit // max(len(queries), 1) + 2)
    articles: list[dict] = []
    for tag, q in queries:
        try:
            batch = await _gdelt_articles(q, max_records=per_query)
            for a in batch:
                a["region"] = tag
            articles.extend(batch)
        except Exception as e:  # noqa: BLE001
            logger.warning("GDELT market news (%s) failed: %s", tag, e)

    if not articles:
        # Fallback: index-level news from Yahoo
        for tag, idx in (("us", "^GSPC"), ("in", "^NSEI")):
            if region in ("all", tag):
                try:
                    batch = await _yahoo_articles(idx, limit=6)
                    for a in batch:
                        a["region"] = tag
                    articles.extend(batch)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Yahoo market news (%s) failed: %s", tag, e)

    result = {"region": region, "articles": _dedupe(articles, limit)}
    news_cache.set(key, result)
    return result


async def get_stock_news(
    ticker: str,
    company_name: str | None = None,
    industry: str | None = None,
    limit: int = 12,
) -> dict:
    """Layered news for one stock: company → industry → its market."""
    ticker = ticker.upper()
    key = f"stock:{ticker}:{limit}"
    cached = news_cache.get(key)
    if cached is not None:
        return cached

    market = market_of(ticker)

    # Resolve company/industry from yfinance if the caller didn't supply them
    if not company_name or not industry:
        def _info() -> tuple[str | None, str | None]:
            import yfinance as yf

            info = yf.Ticker(ticker).info or {}
            return (
                info.get("displayName") or info.get("shortName") or info.get("longName"),
                info.get("industry") or info.get("sector"),
            )

        try:
            fetched_name, fetched_industry = await asyncio.to_thread(_info)
            company_name = company_name or fetched_name
            industry = industry or fetched_industry
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not resolve info for %s: %s", ticker, e)

    layers: list[tuple[str, str]] = []
    base_symbol = ticker.split(".")[0]
    if company_name:
        layers.append(("company", f'"{company_name}" (stock OR shares OR earnings OR market) sourcelang:english'))
    else:
        layers.append(("company", f'"{base_symbol}" stock sourcelang:english'))
    if industry:
        layers.append(("industry", f'"{industry}" (industry OR sector OR technology) sourcelang:english'))
    if market == MARKET_IN:
        layers.append(("market", '(sensex OR nifty OR "indian stock market") sourcelang:english'))
    else:
        layers.append(("market", '("stock market" OR "wall street") sourcecountry:US sourcelang:english'))

    articles: list[dict] = []
    remaining = limit
    for tag, q in layers:
        if remaining <= 0:
            break
        take = max(3, remaining // 2) if tag != "company" else max(6, remaining)
        try:
            batch = await _gdelt_articles(q, max_records=take)
        except Exception as e:  # noqa: BLE001
            logger.warning("GDELT stock news (%s/%s) failed: %s", ticker, tag, e)
            batch = []
        for a in batch:
            a["layer"] = tag
        before = len(articles)
        articles = _dedupe(articles + batch, limit)
        remaining = limit - len(articles)
        if tag == "company" and len(articles) == before:
            # GDELT had nothing on the company — pull Yahoo's per-ticker feed
            try:
                yahoo = await _yahoo_articles(ticker, limit=8)
                for a in yahoo:
                    a["layer"] = "company"
                articles = _dedupe(articles + yahoo, limit)
                remaining = limit - len(articles)
            except Exception as e:  # noqa: BLE001
                logger.warning("Yahoo stock news (%s) failed: %s", ticker, e)

    result = {
        "ticker": ticker,
        "company_name": company_name,
        "industry": industry,
        "market": market,
        "articles": articles,
    }
    news_cache.set(key, result)
    return result
