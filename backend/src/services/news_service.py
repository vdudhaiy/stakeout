"""Market and per-stock news with layered free sources.

Primary source: GDELT DOC 2.0 API (free, no key, global coverage).
Second layer:   Google News RSS (free, no key, query-based like GDELT —
                backfills English-language headlines GDELT misses, which
                matters most for India-listed companies).
Third layer:    curated publisher RSS feeds (ET Markets, LiveMint, Hindu
                BusinessLine for India; Dow Jones and CNBC for the US) —
                only consulted when the query-based sources above are empty.
Last resort:    Yahoo Finance news via yfinance.

Per-stock news is assembled in priority order:
  1. the company itself
  2. its industry / technology
  3. the market it trades on
De-duplicated by URL/title, capped, and cached for 15 minutes.

GDELT caveats handled here:
- Query terms shorter than ~3 chars or pure tickers match poorly, so we
  query on the company *name* plus finance context terms.
- `sourcelang:english` keeps results readable; `sourcecountry` biases
  market news to US / India as requested. GDELT's India coverage skews
  toward local-language outlets even with that filter, which is the main
  reason the Google News layer exists.

Google News RSS note: its feed is published for personal, non-commercial
feed-reader use per Google's stated terms; article links are Google
redirect URLs rather than publisher URLs.
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import httpx

from cache import news_cache
from markets import MARKET_IN, MARKET_US, market_of

logger = logging.getLogger(__name__)

_GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
_TIMEOUT = httpx.Timeout(8.0, connect=4.0)
_HEADERS = {"User-Agent": "stakeout-open-source-tracker/1.0"}

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
_GOOGLE_NEWS_LOCALE = {
    MARKET_US: ("en-US", "US", "US:en"),
    MARKET_IN: ("en-IN", "IN", "IN:en"),
}

# Curated homepage/section feeds, verified live and updating same-day (some
# well-known candidates — Moneycontrol's RSS, the old feeds.a.dj.com WSJ
# feed — turned out to be abandoned and stuck on stale 2024/2025 items, so
# they're deliberately excluded here).
_CURATED_FEEDS: dict[str, list[str]] = {
    MARKET_US: [
        "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    ],
    MARKET_IN: [
        "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "https://www.livemint.com/rss/markets",
        "https://www.thehindubusinessline.com/markets/feeder/default.rss",
    ],
}


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


def _parse_rss_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).isoformat()
    except (TypeError, ValueError):
        return None


def _parse_rss_items(xml_bytes: bytes, provider: str, limit: int) -> list[dict]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    articles = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        if not title or not url:
            continue
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else ""
        if not source and " - " in title:
            # Google News titles are "Headline - Publisher" with no <source>
            # tag of their own, so split the publisher back out.
            title, _, source = title.rpartition(" - ")
        articles.append(
            {
                "title": title,
                "url": url,
                "source": source,
                "published_at": _parse_rss_date(item.findtext("pubDate")),
                "image": None,
                "provider": provider,
            }
        )
        if len(articles) >= limit:
            break
    return articles


async def _google_news_articles(query: str, market: str, max_records: int = 12) -> list[dict]:
    hl, gl, ceid = _GOOGLE_NEWS_LOCALE.get(market, _GOOGLE_NEWS_LOCALE[MARKET_US])
    params = f"?q={quote_plus(query)}&hl={hl}&gl={gl}&ceid={ceid}"
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
        r = await client.get(_GOOGLE_NEWS_RSS + params)
        r.raise_for_status()
    return _parse_rss_items(r.content, "google_news", max_records)


async def _curated_feed_articles(market: str, per_feed_limit: int = 8) -> list[dict]:
    articles: list[dict] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
        for url in _CURATED_FEEDS.get(market, []):
            try:
                r = await client.get(url)
                r.raise_for_status()
                articles.extend(_parse_rss_items(r.content, "curated_rss", per_feed_limit))
            except Exception as e:  # noqa: BLE001
                logger.warning("Curated RSS feed failed (%s): %r", url, e)
    return articles


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

    markets: list[str] = []
    if region in ("all", "us"):
        markets.append(MARKET_US)
    if region in ("all", "in"):
        markets.append(MARKET_IN)

    queries: list[tuple[str, str]] = []
    if MARKET_US in markets:
        queries.append(("us", '("stock market" OR "wall street" OR nasdaq OR "S&P 500") sourcecountry:US sourcelang:english'))
    if MARKET_IN in markets:
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
            logger.warning("GDELT market news (%s) failed: %r", tag, e)

    # Second layer: Google News RSS on the same topics, tagged by region.
    google_topics = {
        MARKET_US: ("us", '"stock market" OR "wall street" OR nasdaq OR "S&P 500"'),
        MARKET_IN: ("in", '"stock market" OR sensex OR nifty OR "dalal street"'),
    }
    for market in markets:
        tag, q = google_topics[market]
        try:
            batch = await _google_news_articles(q, market, max_records=per_query)
            for a in batch:
                a["region"] = tag
            articles.extend(batch)
        except Exception as e:  # noqa: BLE001
            logger.warning("Google News market news (%s) failed: %r", tag, e)

    # Third layer: curated publisher RSS — only worth the extra requests when
    # both query-based sources above came back empty for a region.
    if not articles:
        for market in markets:
            tag = "us" if market == MARKET_US else "in"
            try:
                batch = await _curated_feed_articles(market)
                for a in batch:
                    a["region"] = tag
                articles.extend(batch)
            except Exception as e:  # noqa: BLE001
                logger.warning("Curated RSS market news (%s) failed: %r", tag, e)

    if not articles:
        # Last resort: index-level news from Yahoo
        for tag, idx in (("us", "^GSPC"), ("in", "^NSEI")):
            if region in ("all", tag):
                try:
                    batch = await _yahoo_articles(idx, limit=6)
                    for a in batch:
                        a["region"] = tag
                    articles.extend(batch)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Yahoo market news (%s) failed: %r", tag, e)

    deduped = _dedupe(articles, limit)
    result = {"region": region, "articles": deduped}
    # Don't cache a fully empty result for the full TTL — every source
    # failing/rate-limiting at once is transient, and caching it would blank
    # headlines for 15 minutes instead of retrying on the next request.
    if deduped:
        news_cache.set(key, result)
    return result


_STOCK_NEWS_TIMESPAN = "7d"  # the tracker shows the last week of headlines


def _published_sort_key(article: dict) -> str:
    # ISO-8601 strings sort chronologically; undated articles sink to the
    # bottom rather than floating unpredictably.
    return article.get("published_at") or ""


async def get_stock_news(
    ticker: str,
    company_name: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
    limit: int = 12,
) -> dict:
    """Layered news for one stock: company → industry → sector → its market.

    All layers pull from the last 7 days, and the merged, de-duplicated list
    is sorted most-recent-first regardless of which layer an article came
    from — the tracker's carousel expects a single reverse-chronological feed.
    """
    ticker = ticker.upper()
    key = f"stock:{ticker}:{limit}"
    cached = news_cache.get(key)
    if cached is not None:
        return cached

    market = market_of(ticker)

    # Resolve company/sector/industry from yfinance if the caller didn't supply them
    if not company_name or not sector or not industry:
        def _info() -> tuple[str | None, str | None, str | None]:
            import yfinance as yf

            info = yf.Ticker(ticker).info or {}
            return (
                info.get("displayName") or info.get("shortName") or info.get("longName"),
                info.get("sector"),
                info.get("industry"),
            )

        try:
            fetched_name, fetched_sector, fetched_industry = await asyncio.to_thread(_info)
            company_name = company_name or fetched_name
            sector = sector or fetched_sector
            industry = industry or fetched_industry
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not resolve info for %s: %r", ticker, e)

    layers: list[tuple[str, str]] = []
    base_symbol = ticker.split(".")[0]
    if company_name:
        layers.append(("company", f'"{company_name}" (stock OR shares OR earnings OR market) sourcelang:english'))
    else:
        layers.append(("company", f'"{base_symbol}" stock sourcelang:english'))
    if industry:
        layers.append(("industry", f'"{industry}" (industry OR stocks OR companies OR market) sourcelang:english'))
    # Sector is broader than industry — only query it separately when it adds
    # information (e.g. industry "Semiconductors" under sector "Technology").
    if sector and sector.lower() != (industry or "").lower():
        layers.append(("sector", f'"{sector}" sector (stocks OR market OR economy) sourcelang:english'))
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
            batch = await _gdelt_articles(q, max_records=take, timespan=_STOCK_NEWS_TIMESPAN)
        except Exception as e:  # noqa: BLE001
            logger.warning("GDELT stock news (%s/%s) failed: %r", ticker, tag, e)
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
                logger.warning("Yahoo stock news (%s) failed: %r", ticker, e)

    # Second layer: Google News RSS, backfilling anything still missing after
    # GDELT (and its Yahoo per-ticker fallback) — most useful for India-listed
    # companies where GDELT's source coverage is thinner.
    if remaining > 0:
        google_layers: list[tuple[str, str]] = []
        if company_name:
            google_layers.append(("company", f'"{company_name}" stock OR shares OR earnings'))
        if industry:
            google_layers.append(("industry", f'"{industry}" stocks OR market'))
        google_layers.append(
            ("market", "sensex OR nifty" if market == MARKET_IN else '"stock market" OR "wall street"')
        )
        for tag, q in google_layers:
            if remaining <= 0:
                break
            try:
                batch = await _google_news_articles(q, market, max_records=max(4, remaining))
            except Exception as e:  # noqa: BLE001
                logger.warning("Google News stock news (%s/%s) failed: %r", ticker, tag, e)
                batch = []
            for a in batch:
                a["layer"] = tag
            articles = _dedupe(articles + batch, limit)
            remaining = limit - len(articles)

    # One reverse-chronological feed across all layers, newest on top.
    articles.sort(key=_published_sort_key, reverse=True)

    result = {
        "ticker": ticker,
        "company_name": company_name,
        "sector": sector,
        "industry": industry,
        "market": market,
        "articles": articles,
    }
    # Same reasoning as get_market_news: don't lock in an empty result for
    # the full TTL when every layer above came back empty.
    if articles:
        news_cache.set(key, result)
    return result
