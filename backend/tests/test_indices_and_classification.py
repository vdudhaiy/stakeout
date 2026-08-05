"""Tests for the home page indices endpoint, the batch sector/industry
classification endpoint, and the layered 7-day stock news feed.

yfinance and GDELT are mocked throughout — these tests are offline.
"""

import pytest
from unittest.mock import patch, AsyncMock

from cache import index_cache, info_cache, news_cache
from services import index_service, news_service, stock_service


@pytest.fixture(autouse=True)
def _clear_caches():
    index_cache.clear()
    info_cache.clear()
    news_cache.clear()
    yield
    index_cache.clear()
    info_cache.clear()
    news_cache.clear()


# ─────────────────────────────────────────────────────────────────────────────
# /stocks/indices
# ─────────────────────────────────────────────────────────────────────────────

def _fake_index(symbol, name, region, last=100.0, prev=99.0):
    return {
        "symbol": symbol, "name": name, "region": region,
        "last": last, "change": round(last - prev, 2),
        "change_pct": round((last - prev) / prev * 100, 2),
        "points": [
            {"date": "2026-07-19", "close": prev},
            {"date": "2026-07-20", "close": last},
        ],
    }


async def test_indices_endpoint_returns_quotes_and_caches(client):
    fakes = [
        _fake_index("^GSPC", "S&P 500", "US"),
        _fake_index("^NSEI", "NIFTY 50", "IN"),
    ]
    with patch.object(index_service, "_fetch_one", side_effect=fakes + [None] * 10) as fetch:
        res = await client.get("/stocks/indices")
        assert res.status_code == 200
        body = res.json()
        symbols = {q["symbol"] for q in body["indices"]}
        assert symbols == {"^GSPC", "^NSEI"}
        first_call_count = fetch.call_count
        assert first_call_count == len(index_service.MAJOR_INDICES)

        # Second request is served from cache — no new fetches
        res2 = await client.get("/stocks/indices")
        assert res2.status_code == 200
        assert fetch.call_count == first_call_count


async def test_indices_empty_result_is_not_cached(client):
    with patch.object(index_service, "_fetch_one", return_value=None) as fetch:
        res = await client.get("/stocks/indices")
        assert res.status_code == 200
        assert res.json() == {"indices": []}
        # A transient total failure must not pin an empty strip for 10 min
        await client.get("/stocks/indices")
        assert fetch.call_count == 2 * len(index_service.MAJOR_INDICES)


async def test_index_quote_shape():
    q = _fake_index("^DJI", "Dow Jones", "US", last=110.0, prev=100.0)
    assert q["change"] == 10.0
    assert q["change_pct"] == 10.0
    assert q["points"][-1]["close"] == q["last"]


# ─────────────────────────────────────────────────────────────────────────────
# /stocks/classification
# ─────────────────────────────────────────────────────────────────────────────

async def test_classification_batch_and_cache(client):
    infos = {
        "AAPL": {"sector": "Technology", "industry": "Consumer Electronics"},
        "TCS.NS": {"sector": "Technology", "industry": "IT Services"},
    }
    with patch.object(stock_service, "_get_ticker_info", side_effect=lambda t: infos[t]) as info:
        res = await client.get("/stocks/classification?tickers=AAPL,TCS.NS")
        assert res.status_code == 200
        body = res.json()["classification"]
        assert body["AAPL"]["sector"] == "Technology"
        assert body["TCS.NS"]["industry"] == "IT Services"
        assert info.call_count == 2

        # Cached for 24h — a repeat lookup fires no new yfinance calls
        res2 = await client.get("/stocks/classification?tickers=AAPL,TCS.NS")
        assert res2.status_code == 200
        assert info.call_count == 2


async def test_classification_failed_lookup_returns_nulls_and_is_not_cached(client):
    def _boom(_):
        raise RuntimeError("yfinance down")

    with patch.object(stock_service, "_get_ticker_info", side_effect=_boom) as info:
        res = await client.get("/stocks/classification?tickers=ZZZZ")
        assert res.status_code == 200
        assert res.json()["classification"]["ZZZZ"] == {"sector": None, "industry": None}
        # Failure must not be pinned in the 24h cache
        await client.get("/stocks/classification?tickers=ZZZZ")
        assert info.call_count == 2


async def test_classification_rejects_empty_and_oversized(client):
    res = await client.get("/stocks/classification?tickers=,,")
    assert res.status_code == 400
    too_many = ",".join(f"T{i}" for i in range(101))
    res = await client.get(f"/stocks/classification?tickers={too_many}")
    assert res.status_code == 400


async def test_classification_cache_is_shared_across_industry_sector_and_batch_lookups():
    """_cached_classification is the single source of truth behind
    get_classification, get_industry_map, and get_sector_map — a lookup
    warmed by one is reused by the others instead of refetching `.info`."""
    with patch.object(stock_service, "_get_ticker_info",
                       return_value={"sector": "Technology", "industry": "Consumer Electronics"}) as info:
        await stock_service.get_classification(["AAPL"])
        assert info.call_count == 1

        with patch("services.market_data_service.get_symbols",
                   new_callable=AsyncMock, return_value=["AAPL"]):
            industry_map = await stock_service.get_industry_map()
            sector_map = await stock_service.get_sector_map()

    assert industry_map == {"Consumer Electronics": ["AAPL"]}
    assert sector_map == {"Technology": ["AAPL"]}
    assert info.call_count == 1  # both maps served from the cache get_classification warmed


# ─────────────────────────────────────────────────────────────────────────────
# Layered stock news (company → industry → sector → market, 7d, newest first)
# ─────────────────────────────────────────────────────────────────────────────

def _article(title, published_at):
    return {
        "title": title,
        "url": f"https://example.com/{title.replace(' ', '-')}",
        "source": "example.com",
        "published_at": published_at,
        "image": None,
        "provider": "gdelt",
    }


async def test_stock_news_layers_use_7d_window_and_sort_newest_first():
    per_layer = {
        # deliberately out of order across layers: sorting must interleave them
        "company": [_article("company old", "2026-07-15T08:00:00Z")],
        "industry": [_article("industry new", "2026-07-20T10:00:00Z")],
        "sector": [_article("sector mid", "2026-07-18T12:00:00Z")],
        "market": [_article("market undated", None)],
    }
    calls: list[str] = []

    async def fake_gdelt(query, max_records=12, timespan="3d"):
        assert timespan == "7d"  # requirement: last week of headlines
        if "Consumer Electronics" in query:
            calls.append("industry")
            return [dict(a) for a in per_layer["industry"]]
        if '"Technology" sector' in query:
            calls.append("sector")
            return [dict(a) for a in per_layer["sector"]]
        if "Apple" in query:
            calls.append("company")
            return [dict(a) for a in per_layer["company"]]
        calls.append("market")
        return [dict(a) for a in per_layer["market"]]

    with patch.object(news_service, "_gdelt_articles", side_effect=fake_gdelt), \
         patch.object(news_service, "_google_news_articles", new=AsyncMock(return_value=[])):
        result = await news_service.get_stock_news(
            "AAPL",
            company_name="Apple",
            sector="Technology",
            industry="Consumer Electronics",
            limit=12,
        )

    assert calls == ["company", "industry", "sector", "market"]
    assert result["sector"] == "Technology"
    titles = [a["title"] for a in result["articles"]]
    # newest first, undated last
    assert titles == ["industry new", "sector mid", "company old", "market undated"]
    layers = {a["title"]: a["layer"] for a in result["articles"]}
    assert layers["sector mid"] == "sector"


async def test_stock_news_skips_sector_layer_when_same_as_industry():
    async def fake_gdelt(query, max_records=12, timespan="3d"):
        return []

    with patch.object(news_service, "_gdelt_articles", side_effect=fake_gdelt) as gd, \
         patch.object(news_service, "_yahoo_articles", new=AsyncMock(return_value=[])), \
         patch.object(news_service, "_google_news_articles", new=AsyncMock(return_value=[])):
        await news_service.get_stock_news(
            "AAPL", company_name="Apple", sector="Technology", industry="Technology", limit=6,
        )
    queried = " | ".join(c.args[0] for c in gd.call_args_list)
    assert '"Technology" sector' not in queried  # no redundant duplicate layer


async def test_stock_news_empty_result_is_not_cached():
    async def empty(*args, **kwargs):
        return []

    with patch.object(news_service, "_gdelt_articles", side_effect=empty) as gdelt, \
         patch.object(news_service, "_yahoo_articles", new=AsyncMock(return_value=[])), \
         patch.object(news_service, "_google_news_articles", side_effect=empty):
        result = await news_service.get_stock_news(
            "AAPL", company_name="Apple", sector="Technology", industry="Consumer Electronics", limit=6,
        )
        assert result["articles"] == []
        first_call_count = gdelt.call_count

        # Every layer coming back empty at once is transient (rate-limiting,
        # an outage) — it must not pin an empty carousel for 15 minutes.
        await news_service.get_stock_news(
            "AAPL", company_name="Apple", sector="Technology", industry="Consumer Electronics", limit=6,
        )
        assert gdelt.call_count == 2 * first_call_count


async def test_stock_news_google_layer_backfills_when_gdelt_is_empty():
    async def fake_gdelt(query, max_records=12, timespan="3d"):
        return []

    async def fake_google(query, market, max_records=12):
        return [
            {
                "title": "Apple shares rise on earnings beat",
                "url": "https://example.com/apple-earnings",
                "source": "Reuters",
                "published_at": "2026-07-20T10:00:00",
                "image": None,
                "provider": "google_news",
            }
        ]

    with patch.object(news_service, "_gdelt_articles", side_effect=fake_gdelt), \
         patch.object(news_service, "_yahoo_articles", new=AsyncMock(return_value=[])), \
         patch.object(news_service, "_google_news_articles", side_effect=fake_google):
        result = await news_service.get_stock_news(
            "AAPL", company_name="Apple", sector="Technology", industry="Consumer Electronics", limit=6,
        )

    assert [a["title"] for a in result["articles"]] == ["Apple shares rise on earnings beat"]
    assert result["articles"][0]["layer"] == "company"


# ─────────────────────────────────────────────────────────────────────────────
# Market news: Google News layer + curated RSS fallback tier
# ─────────────────────────────────────────────────────────────────────────────

async def test_market_news_falls_back_to_curated_rss_when_query_sources_are_empty():
    async def empty(*args, **kwargs):
        return []

    async def fake_curated(market, per_feed_limit=8):
        return [
            {
                "title": f"Curated headline for {market}",
                "url": f"https://example.com/{market}",
                "source": "curated.example",
                "published_at": "2026-07-22T09:00:00",
                "image": None,
                "provider": "curated_rss",
            }
        ]

    with patch.object(news_service, "_gdelt_articles", side_effect=empty), \
         patch.object(news_service, "_google_news_articles", side_effect=empty), \
         patch.object(news_service, "_yahoo_articles", side_effect=empty), \
         patch.object(news_service, "_curated_feed_articles", side_effect=fake_curated):
        result = await news_service.get_market_news(region="us", limit=12)

    assert [a["title"] for a in result["articles"]] == ["Curated headline for US"]
    assert result["articles"][0]["region"] == "us"


async def test_market_news_empty_result_is_not_cached():
    async def empty(*args, **kwargs):
        return []

    with patch.object(news_service, "_gdelt_articles", side_effect=empty) as gdelt, \
         patch.object(news_service, "_google_news_articles", side_effect=empty), \
         patch.object(news_service, "_curated_feed_articles", side_effect=empty), \
         patch.object(news_service, "_yahoo_articles", side_effect=empty):
        result = await news_service.get_market_news(region="us", limit=12)
        assert result["articles"] == []
        first_call_count = gdelt.call_count

        # Every source failing/rate-limiting at once is transient — it must
        # not pin an empty headlines feed for 15 minutes.
        await news_service.get_market_news(region="us", limit=12)
        assert gdelt.call_count == 2 * first_call_count


async def test_market_news_skips_curated_rss_when_google_news_has_results():
    async def empty(*args, **kwargs):
        return []

    async def fake_google(query, market, max_records=12):
        return [
            {
                "title": "Wall Street rallies",
                "url": "https://example.com/rally",
                "source": "example.com",
                "published_at": "2026-07-22T09:00:00",
                "image": None,
                "provider": "google_news",
            }
        ]

    with patch.object(news_service, "_gdelt_articles", side_effect=empty), \
         patch.object(news_service, "_google_news_articles", side_effect=fake_google), \
         patch.object(news_service, "_curated_feed_articles") as curated:
        result = await news_service.get_market_news(region="us", limit=12)

    curated.assert_not_called()
    assert [a["title"] for a in result["articles"]] == ["Wall Street rallies"]
