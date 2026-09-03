'''
Read relevant stock data from the market_data table and returns it in a format suitable for the endpoint to use.
'''

import asyncio
import logging
import pandas as pd
import yfinance as yf
from . import company_profile_service, market_data_service, yf_guard
from cache import TTLCache, quote_cache, single_flight
from markets import MARKET_META, market_of, normalize_market
import markets as _markets
from schemas.stocks import *
import pandas_market_calendars as mcal
from datetime import datetime, time, timezone, timedelta

logger = logging.getLogger(__name__)


def _session_bounds(ticker: str) -> tuple[time, time]:
    '''Regular-session open/close times in the exchange's local timezone.'''
    sessions = MARKET_META[market_of(ticker)]["sessions"]["regular"]
    h1, m1 = map(int, sessions[0].split(":"))
    h2, m2 = map(int, sessions[1].split(":"))
    return time(h1, m1), time(h2, m2)

# The last completed trading day already attempted per ticker. Prevents
# hammering yfinance in the gap between a session closing and Yahoo
# publishing its daily bar; the marker resets itself once a newer completed
# trading day comes around.
#
# Authoritative copy lives in the archive_refresh table — this dict is only
# a read-through memo in front of it. It used to be the sole record, which
# meant every restart of the free-tier host (many a day) re-spent one
# upstream call per tracked symbol re-learning what it had just forgotten.
# Bounded, because market_data holds every symbol any user ever archived.
_UPDATE_ATTEMPTED_MAX = 4096
_update_attempted: dict[str, pd.Timestamp] = {}


async def _last_update_attempt(ticker: str) -> pd.Timestamp | None:
    cached = _update_attempted.get(ticker)
    if cached is not None:
        return cached
    marker = await market_data_service.get_refresh_marker(ticker)
    if marker is None:
        return None
    stamp = pd.Timestamp(marker)
    _update_attempted[ticker] = stamp
    return stamp


async def _note_update_attempt(ticker: str, when: pd.Timestamp) -> None:
    if len(_update_attempted) >= _UPDATE_ATTEMPTED_MAX:
        # Drop the entries pinned to the oldest trading day: they are the
        # least likely to be re-checked before they'd expire anyway. Losing
        # one only costs a DB read, not an upstream call.
        for stale in sorted(_update_attempted, key=_update_attempted.get)[: _UPDATE_ATTEMPTED_MAX // 8]:
            _update_attempted.pop(stale, None)
    _update_attempted[ticker] = when
    await market_data_service.set_refresh_marker(ticker, when.date())


# Static-ish per-ticker snapshots (info, estimates, recommendations, display
# names). Uses the shared TTLCache rather than a private class: the bespoke
# one this replaces had no size cap, and each entry holds a full yfinance
# `.info` dict, so on the 512 MB free tier it grew until the process was
# killed and restarted — which then cost a cold fetch of everything.
_snapshot_cache = TTLCache(ttl_seconds=6 * 3600, max_entries=1024)

# How long a superseded snapshot is kept around to serve when a live fetch
# can't be made at all. Yahoo rate-limits in bursts, and analyst targets from
# this morning are a far better answer than a blank panel — or, as it was, an
# error that took the whole page down with it. Same stale-while-unavailable
# idea as index_service's `_STALE_KEY`.
_SNAPSHOT_STALE_TTL = 7 * 24 * 3600


async def _cached_snapshot(key: str, produce):
    """Serve `key` from cache, else `produce()` it, else serve a stale copy.

    Three tiers: the 6-hour entry, a live fetch (coalesced, so a page load
    asking from several components makes one call), and a week-old copy used
    only when the live fetch raises. The stale tier is what makes a reload
    during a yfinance cooldown show yesterday's fundamentals instead of
    nothing.
    """
    cached = _snapshot_cache.get(key)
    if cached is not None:
        return cached

    async def _load():
        try:
            result = await produce()
        except Exception:  # noqa: BLE001 — re-raised below unless we can cover it
            stale = _snapshot_cache.get(f"stale:{key}")
            if stale is not None:
                logger.info("Serving stale snapshot for %s", key)
                return stale
            raise
        _snapshot_cache.set(key, result)
        _snapshot_cache.set(f"stale:{key}", result, _SNAPSHOT_STALE_TTL)
        return result

    return await single_flight(key, _load)

async def _last_completed_trading_day(market: str = "US") -> pd.Timestamp | None:
    '''
    Return the most recent trading day (for the given market) whose session has
    fully closed, using UTC-aware timestamps so server timezone is irrelevant.
    '''
    return await asyncio.to_thread(_markets.last_completed_trading_day, market)


async def get_market_status(market: str = "US"):
    '''
    Check if the given stock market ("US" or "IN") is currently open.
    Returns:
        bool: True if the market is open, False if it is closed.
    '''
    return await asyncio.to_thread(_markets.is_market_open, normalize_market(market))


async def is_tracked(ticker: str) -> bool:
    '''
    Whether the shared archive already holds price rows for `ticker`.

    The membership check callers actually want. They used to ask
    get_all_stocks() and test the key, which fetched `.info` — yfinance's
    single most rate-limit-prone call — for *every* archived symbol just to
    answer a yes/no about one of them.
    '''
    return await market_data_service.has_data(ticker)


async def display_name(ticker: str) -> str:
    '''
    Company display name for one ticker.

    Shares company_profile_service's cached, DB-persisted `.info` lookup
    with the sector/industry path below — the two used to make separate
    `.info` calls for the same ticker. Never raises: an unknown name
    degrades to the ticker itself.
    '''
    profile = await company_profile_service.get_profile(ticker)
    return profile["name"] or ticker


async def get_all_stocks():
    '''
    Get a list of all available stocks in the system.
    Returns:
        dict: A dictionary mapping stock ticker symbols to their display names.
    '''
    cached = _snapshot_cache.get("all_stocks")
    if cached is not None:
        return cached
    tickers = await market_data_service.get_symbols()
    if not tickers:
        return {}

    # Per-ticker cached lookups, resolved concurrently. Previously this was
    # one blocking thread walking every symbol in series, so a cold cache
    # meant N sequential `.info` scrapes before the request could answer —
    # and one failure anywhere aborted the whole map.
    names = await asyncio.gather(*(display_name(t) for t in tickers))
    stocks = dict(zip(tickers, names))
    _snapshot_cache.set("all_stocks", stocks)
    return stocks


async def add_stock(ticker: str):
    '''
    Add stock data for a given ticker.
    Args:
        ticker (str): The stock ticker symbol.
    Returns:
        OHLCVResponse: The stock data for the specified ticker and time period.
        StockDetailedResponse: Detailed information about the stock, including financials, calendar events, analyst price targets, and recommendations.
    '''
    try:
        # Fetch data from yfinance and upsert into the market_data table
        from .price_fetcher import fetch_historical_price_data
        await fetch_historical_price_data(ticker)
        _snapshot_cache.invalidate("all_stocks")
        ohlcv = await fetch(ticker)  # Return the fetched data
        service = StockService()
        stock = yf.Ticker(ticker)
        detailed_info = await asyncio.to_thread(service.get_stock_details, stock)  # Get detailed info for the stock
        return StockCreateResponse(exist=False, ohlcv=ohlcv, details=detailed_info)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Error creating stock data for {ticker}: {str(e)}")


async def delete_stock(ticker: str):
    '''
    Delete stock data for a given ticker.
    Args:
        ticker (str): The stock ticker symbol.
    Returns:
        dict: A message indicating whether the deletion was successful.
    '''
    try:
        deleted = await market_data_service.delete_symbol(ticker)
        if not deleted:
            raise ValueError(f"No data found for ticker: {ticker}")
        _snapshot_cache.invalidate_prefix(f"{ticker}:")
        _snapshot_cache.invalidate("all_stocks")
        return {"message": f"Stock data for {ticker} deleted successfully."}
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Error deleting stock data for {ticker}: {str(e)}")


# 15-minute bars: anything shorter than the bar interval is a request that
# cannot return new information.
_INTRADAY_TTL = 15 * 60


async def fetch_intraday(stock: yf.Ticker):
    '''
    Fetch intraday stock data for a given ticker.

    Cached for one bar interval and coalesced, for the same reason as
    fetch_current: this is a 5-day 15-minute history pull that the tracker
    fired on every ticker switch and every reload in 1D mode.

    Args:
        stock (yf.Ticker): The yfinance Ticker object.
    '''
    key = f"intraday:{stock.ticker}"
    cached = quote_cache.get(key)
    if cached is not None:
        value, error = cached
        if error is not None:
            raise ValueError(error)
        return value

    async def _load():
        try:
            with yf_guard.guard():
                result = await _fetch_intraday_live(stock)
        except Exception as e:  # noqa: BLE001 — cached briefly, then re-raised
            quote_cache.set(key, (None, str(e)), _CURRENT_TTL_ERROR)
            raise
        quote_cache.set(key, (result, None), _INTRADAY_TTL)
        return result

    return await single_flight(key, _load)


async def _fetch_intraday_live(stock: yf.Ticker):
    '''The uncached body of fetch_intraday — always goes out to yfinance.'''
    try:
        df_current = await asyncio.to_thread(
            stock.history, interval="15m", period="5d", prepost=True
        )
        df = df_current.copy()
        df.index = pd.to_datetime(df.index)
        # Keep only regular trading hours (exchange-local: 9:30-16:00 US, 9:15-15:30 IN)
        _open_t, _close_t = _session_bounds(stock.ticker)
        mask = (df.index.time >= _open_t) & (df.index.time <= _close_t)
        df = df[mask]
        if df.empty:
            raise ValueError(f"No intraday data available for {stock.ticker}")
        # Use the most recent trading day that has data (handles closed/weekend)
        last_date = df.index.normalize()[-1]
        df = df[df.index.normalize() == last_date]
        return OHLCVResponse(
            ticker=stock.ticker,
            data=[OHLCV(
                date=row.name.strftime("%Y-%m-%dT%H:%M"),
                open=float(row["Open"]) if not pd.isna(row["Open"]) else None,
                high=float(row["High"]) if not pd.isna(row["High"]) else None,
                low=float(row["Low"]) if not pd.isna(row["Low"]) else None,
                close=float(row["Close"]) if not pd.isna(row["Close"]) else None,
                volume=int(row["Volume"]) if not pd.isna(row["Volume"]) else None,
            ) for _, row in df.iterrows()]
        )
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Error fetching current stock data for {stock.ticker}: {str(e)}")


async def ensure_archive_current(ticker: str) -> bool:
    """Bring `ticker`'s price archive up to the last completed session.

    Returns whether a top-up actually ran, so the caller knows to re-read.
    Never raises: the archive being behind is a degraded state, not an error,
    and every caller has something older to show instead.

    This used to live inline in fetch(), which meant the archive only ever
    advanced for tickers someone opened on the Tracker. A portfolio-only user
    could hold a stock for weeks with its history frozen at the day it was
    added — invisible on the Portfolio page, which prices from live quotes,
    but fatal to anything reading the archive (see performance_service).

    Cheap when there is nothing to do: two indexed reads and a date compare.
    The attempt marker means at most one download per ticker per trading day
    even when Yahoo hasn't published the bar yet, and single_flight collapses
    concurrent callers onto one.
    """
    try:
        last_completed = await _last_completed_trading_day(market_of(ticker))
        if last_completed is None:
            return False
        last_archived = await market_data_service.get_last_date(ticker)
        if last_archived is None or last_archived >= last_completed.date():
            return False  # nothing archived at all, or already current

        already_attempted = await _last_update_attempt(ticker)
        if already_attempted is not None and already_attempted.date() >= last_completed.date():
            return False  # already asked for this session; Yahoo just hasn't published

        await _note_update_attempt(ticker, last_completed)
        from .price_fetcher import append_price_data
        # Coalesced: a page load asks for the same ticker from several
        # components at once, and without this each of them starts its own
        # download of the same gap.
        await single_flight(f"append:{ticker}", lambda: append_price_data(ticker))
        return True
    except Exception as e:  # noqa: BLE001 — a stale archive must never fail the caller
        logger.warning("Archive top-up failed for %s: %r", ticker, e)
        return False


async def archive_is_behind(ticker: str) -> bool:
    """Whether `ticker`'s archive still stops short of the last completed
    session. Used to explain an empty chart honestly rather than blaming the
    user for having no history."""
    try:
        last_completed = await _last_completed_trading_day(market_of(ticker))
        last_archived = await market_data_service.get_last_date(ticker)
    except Exception:  # noqa: BLE001
        return False
    if last_completed is None or last_archived is None:
        return False
    return last_archived < last_completed.date()


async def fetch(ticker: str, days: int = 30):
    '''
    Fetch stock data for a given ticker and number of days. If data is outdated, fetch the latest data and update the archive. Ensure that no new data is fetched if the current date is a weekend.
    Args:
        ticker (str): The stock ticker symbol.
        days (int, optional): The number of days of data to retrieve. Defaults to 30.
    Returns:
        OHLCVResponse: The stock data for the specified ticker and time period.
    '''
    records = await market_data_service.get_ohlcv(ticker, days)
    if not records:
        raise ValueError(f"No data found for ticker: {ticker}")

    if await ensure_archive_current(ticker):
        records = await market_data_service.get_ohlcv(ticker, days)

    return OHLCVResponse(
        ticker=ticker,
        data=[OHLCV(**row) for row in records]
    )


# How long a "current price" answer stays good. While the session is open the
# number really is moving, so this stays short; once it has closed the only
# thing that can still change is a thin after-hours print, which nothing in
# the UI refreshes faster than this anyway. A failure is remembered briefly
# too, so a symbol Yahoo has nothing for doesn't get re-asked on every poll.
_CURRENT_TTL_OPEN = 60
_CURRENT_TTL_CLOSED = 5 * 60
_CURRENT_TTL_ERROR = 60


async def fetch_current(stock: yf.Ticker, is_market_open: bool | None = None):
    '''
    Fetch the current stock price for a given ticker.

    Cached and coalesced. This is by far the hottest upstream call in the
    app — the ticker tape asks for a dozen symbols on every mount, the
    tracker polls the selected one, and both restart from scratch on a page
    reload — and it was the one quote path with no cache at all, so two
    reloads spent two dozen fresh yfinance requests. Callers within the TTL
    now spend none, and concurrent callers for the same ticker share one.

    Args:
        stock (yf.Ticker): The yfinance Ticker object.
        is_market_open: Pre-fetched market status. If None, fetches it internally.
    Returns:
        OHLCVResponse: The current stock data for the specified ticker.
    '''
    ticker = stock.ticker
    if is_market_open is None:
        is_market_open = await get_market_status(market_of(ticker))

    # Keyed on the session state as well as the ticker: the open and closed
    # branches below answer different questions, so one must not serve the
    # other's cached value across a session boundary.
    key = f"current:{ticker}:{'open' if is_market_open else 'closed'}"
    cached = quote_cache.get(key)
    if cached is not None:
        value, error = cached
        if error is not None:
            raise ValueError(error)
        return value

    async def _load():
        try:
            with yf_guard.guard():
                result = await _fetch_current_live(stock, is_market_open)
        except Exception as e:  # noqa: BLE001 — classified, then handled below
            if yf_guard.is_rate_limit_error(e):
                # Serve the last archived close rather than erroring: the
                # archive is already the honest answer while we're backing
                # off, and it costs no upstream call.
                fallback = await _last_archived_close(ticker)
                if fallback is not None:
                    quote_cache.set(key, (fallback, None), _CURRENT_TTL_ERROR)
                    return fallback
            quote_cache.set(key, (None, str(e)), _CURRENT_TTL_ERROR)
            raise
        quote_cache.set(
            key, (result, None),
            _CURRENT_TTL_OPEN if is_market_open else _CURRENT_TTL_CLOSED,
        )
        return result

    return await single_flight(key, _load)


async def _last_archived_close(ticker: str) -> OHLCVResponse | None:
    """The newest bar already in the archive, or None. Never touches yfinance."""
    try:
        records = await market_data_service.get_ohlcv(ticker, 1)
    except Exception as e:  # noqa: BLE001 — a fallback that fails is just no fallback
        logger.warning("Archive fallback failed for %s: %r", ticker, e)
        return None
    if not records:
        return None
    return OHLCVResponse(ticker=ticker, data=[OHLCV(**records[-1])])


async def _fetch_current_live(stock: yf.Ticker, is_market_open: bool | None = None):
    '''The uncached body of fetch_current — always goes out to yfinance.'''
    try:
        ticker = stock.ticker
        if is_market_open is None:
            is_market_open = await get_market_status(market_of(ticker))
        _open_t, _close_t = _session_bounds(ticker)

        if is_market_open:
            df_current = await asyncio.to_thread(
                stock.history, interval="1m", period="1d", prepost=True
            )
            # Convert index and filter to Regular Trading Hours only
            df = df_current.copy()
            df.index = pd.to_datetime(df.index)
            df = df.between_time(_open_t, _close_t)

            if df.empty:
                raise ValueError(f"No intraday data available for {ticker}")

            session_open = df.iloc[0]["Open"]
            session_high = df["High"].max()
            session_low = df["Low"].min()
            session_volume = df["Volume"].sum()

            last_row = df.iloc[-1]
            current_price = last_row["Close"]
            today = df.index[-1].date().isoformat()

            return OHLCVResponse(
                ticker=ticker,
                data=[OHLCV(
                    date=today,
                    open=float(session_open),
                    high=float(session_high),
                    low=float(session_low),
                    close=float(current_price),
                    volume=int(session_volume),
                )]
            )
        else:
            last_data = await fetch(ticker, days=1)
            if not last_data.data:
                raise ValueError(f"No data available for {ticker} to determine current price")
            df_current = await asyncio.to_thread(
                stock.history, interval="1m", period="2d", prepost=True
            )
            today = pd.Timestamp.now(tz=df_current.index.tz).date()
            df_current = df_current[
                df_current.index.date == today
            ]
            # Convert index and filter to outside Regular Trading Hours only
            df = df_current.copy()
            df.index = pd.to_datetime(df.index)
            mask = ((df.index.time >= _open_t) & (df.index.time <= _close_t))
            df = df[~mask]
            if df.empty:
                return last_data  # Return last known data if no after-hours data is available
            last_row = df.iloc[-1]
            current_price = last_row["Close"]
            today = df.index[-1].strftime("%Y-%m-%dT%H:%M")
            return OHLCVResponse(
                ticker=ticker,
                data=[OHLCV(
                    date=today,
                    open=None,
                    high=None,
                    low=None,
                    close=float(current_price),
                    volume=None,
                )]
            )
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Error fetching current stock data for {stock.ticker}: {str(e)}")


class StockService:
    def get_stock_details(self, ticker: str) -> StockDetailedResponse:
        '''
        Get detailed stock information for a given ticker.
        Args:
            ticker (str): The stock ticker symbol.
        Returns:
            StockDetailedResponse: Detailed information about the stock, including financials, calendar events, analyst price targets, and recommendations.
        '''
        return StockDetailedResponse(
            ticker=ticker.ticker,
            info=self._parse_info(ticker),
            analyst_price_targets=self._parse_analyst_price_targets(ticker),
            recommendations_summary=self._parse_recommendations_summary(ticker),
            earnings_estimate=self._parse_earnings_estimate(ticker),
            revenue_estimate=self._parse_revenue_estimate(ticker),
        )

    def _parse_info(self, ticker: yf.Ticker) -> dict:
        return ticker.info if ticker.info else {}

    def _parse_analyst_price_targets(self, ticker: yf.Ticker) -> dict:
        return ticker.analyst_price_targets if ticker.analyst_price_targets is not None else {}

    def _parse_recommendations_summary(self, ticker: yf.Ticker) -> list:
        if ticker.recommendations_summary is None:
            return []
        df = ticker.recommendations_summary.copy()
        df = df.rename(columns={"strongBuy": "strong_buy", "strongSell": "strong_sell"})
        return df.to_dict(orient="records")

    def _parse_earnings_estimate(self, ticker: yf.Ticker) -> list:
        if ticker.earnings_estimate is None:
            return []
        df = ticker.earnings_estimate.copy()
        df.index.name = "period"
        df = df.reset_index()
        df = df.rename(columns={
            "numberOfAnalysts": "number_of_analysts",
            "yearAgoEps": "year_ago_eps",
        })
        return df.to_dict(orient="records")

    def _parse_revenue_estimate(self, ticker: yf.Ticker) -> list:
        if ticker.revenue_estimate is None:
            return []
        df = ticker.revenue_estimate.copy()
        df.index.name = "period"
        df = df.reset_index()
        df = df.rename(columns={
            "numberOfAnalysts": "number_of_analysts",
            "yearAgoRevenue": "year_ago_revenue",
        })
        return df.to_dict(orient="records")


async def fetch_detailed(stock: yf.Ticker):
    '''
    Fetch detailed stock information for a given ticker.
    Args:
        stock (yf.Ticker): The yfinance Ticker object.
    Returns:
        StockDetailedResponse: Detailed information about the stock, including financials, calendar events, analyst price targets, and recommendations.
    '''
    async def _produce():
        with yf_guard.guard():
            return await asyncio.to_thread(StockService().get_stock_details, stock)

    return await _cached_snapshot(f"{stock.ticker}:detailed", _produce)


async def _cached_classification(ticker: str) -> dict:
    '''
    Sector/industry for a single ticker.

    Delegates to company_profile_service, which holds the cache (in-process,
    then the company_profile table) and the single `.info` call all three of
    these fields come from. Persisting matters more than the TTL here: the
    24-hour in-memory cache this replaced was lost on every restart, and the
    free-tier host restarts far more often than a company changes sector.

    Never raises: an unknown classification degrades to
    {"sector": None, "industry": None}, and is not cached as an answer.
    '''
    profile = await company_profile_service.get_profile(ticker)
    return {"sector": profile["sector"] or None, "industry": profile["industry"] or None}


async def get_classification(tickers: list[str]) -> dict:
    '''
    Sector/industry classification for a batch of tickers, for the portfolio
    breakdown charts.
    Returns:
        dict: { ticker: { "sector": str|None, "industry": str|None } }
    '''
    unique = list(dict.fromkeys(raw.upper().strip() for raw in tickers if raw.strip()))
    entries = await asyncio.gather(*(_cached_classification(t) for t in unique))
    return dict(zip(unique, entries))


_SEARCH_QUOTE_TYPES = {"EQUITY", "ETF"}


async def search_tickers(query: str, exchange: str | None = None) -> list[dict]:
    '''
    Ticker/company-name autocomplete for the "add ticker" UI, backed by
    Yahoo Finance's search endpoint (yf.Search). Scoped to `exchange`
    ("US" | "IN", defaults to "US") so a search made while the user has
    India selected only returns Indian-listed matches (NSE and BSE both —
    the two exchanges aren't a separate choice), and "US" excludes them.

    Indian results have their .NS/.BO suffix stripped before returning —
    ticker resolution (which of NSE/BSE to actually use) happens later, at
    add/buy time, not in this list — so the autocomplete list should never
    show the suffix. Yahoo's search returns NSE and BSE as separate quotes
    with no guaranteed ordering between them, so a company listed on both
    is deduped by base symbol and the NSE listing always wins (the app
    defaults to NSE), regardless of which one Yahoo happened to return
    first. A company listed only on BSE still surfaces under its BSE
    listing rather than being dropped.

    Cached 5 minutes per (exchange, query). Best-effort: any yfinance/Yahoo
    failure degrades to an empty list rather than a 5xx, since this only
    powers suggestions — manual ticker entry still works regardless.
    '''
    from cache import search_cache

    query = query.strip()
    if not query:
        return []

    exchange = (exchange or "US").upper()
    cache_key = f"{exchange}:{query.lower()}"
    cached = search_cache.get(cache_key)
    if cached is not None:
        return cached

    def _search() -> list[dict]:
        return yf.Search(query, max_results=25, news_count=0, lists_count=0).quotes

    try:
        with yf_guard.guard():
            quotes = await asyncio.to_thread(_search)
    except Exception as e:  # noqa: BLE001
        logger.warning("Ticker search failed for query %r: %r", query, e)
        return []

    results: list[dict] = []

    if exchange == "IN":
        # Keyed by base symbol (suffix stripped) so a dual-listed company
        # collapses to one entry. Dict insertion order tracks first-seen
        # relevance order from Yahoo; re-assigning an existing key's value
        # (the NSE upgrade below) doesn't change its position.
        by_symbol: dict[str, dict] = {}
        for q in quotes:
            symbol = q.get("symbol") or ""
            if q.get("quoteType") not in _SEARCH_QUOTE_TYPES or not symbol:
                continue
            is_nse = symbol.endswith(".NS")
            if not is_nse and not symbol.endswith(".BO"):
                continue
            base = symbol[:-3]  # strip ".NS" or ".BO" — both 3 characters
            existing = by_symbol.get(base)
            if existing is None or (is_nse and not existing["_nse"]):
                by_symbol[base] = {
                    "symbol": base,
                    "name": q.get("shortname") or q.get("longname") or base,
                    "exchange": q.get("exchDisp") or q.get("exchange") or "",
                    "_nse": is_nse,
                }
        for entry in by_symbol.values():
            results.append({"symbol": entry["symbol"], "name": entry["name"], "exchange": entry["exchange"]})
            if len(results) >= 8:
                break
    else:
        seen: set[str] = set()
        for q in quotes:
            symbol = q.get("symbol") or ""
            if q.get("quoteType") not in _SEARCH_QUOTE_TYPES or not symbol or symbol.endswith((".NS", ".BO")):
                continue  # "US" exchange — skip Indian-listed matches
            if symbol in seen:
                continue
            seen.add(symbol)
            results.append({
                "symbol": symbol,
                "name": q.get("shortname") or q.get("longname") or symbol,
                "exchange": q.get("exchDisp") or q.get("exchange") or "",
            })
            if len(results) >= 8:
                break

    search_cache.set(cache_key, results)
    return results


async def get_industry_map() -> dict:
    '''
    Build a mapping of industry names to the tickers that belong to each.
    Returns:
        dict: { industry_name: [ticker, ...] } sorted alphabetically.
    '''
    # get_symbols() rather than get_all_stocks(): this only needs the ticker
    # set, and get_all_stocks() would additionally fetch `.info` for every
    # ticker just to build display names this loop throws away.
    result: dict[str, list[str]] = {}
    for ticker in await market_data_service.get_symbols():
        industry = (await _cached_classification(ticker))["industry"]
        if industry:
            result.setdefault(industry, []).append(ticker)
    return {k: sorted(v) for k, v in sorted(result.items())}


async def get_sector_map() -> dict:
    '''
    Build a mapping of sector names to the tickers that belong to each.
    Returns:
        dict: { sector_name: [ticker, ...] } sorted alphabetically.
    '''
    result: dict[str, list[str]] = {}
    for ticker in await market_data_service.get_symbols():
        sector = (await _cached_classification(ticker))["sector"]
        if sector:
            result.setdefault(sector, []).append(ticker)
    return {k: sorted(v) for k, v in sorted(result.items())}


async def fetch_eps_history(stock: yf.Ticker):
    '''
    Fetch EPS history for a given ticker.
    Args:
        stock (yf.Ticker): The yfinance Ticker object.
    Returns:
        EPSHistoryResponse: A list of earnings history responses for the specified ticker.
    '''
    async def _produce():
        ticker = stock.ticker
        with yf_guard.guard():
            earnings = await asyncio.to_thread(stock.get_earnings_dates)
        if earnings is None or earnings.empty:
            raise ValueError(f"No earnings history data found for ticker: {ticker}")
        # Remove future earnings rows
        earnings = earnings[earnings["Reported EPS"].notna()].copy()
        # Sort oldest -> newest so pct_change works correctly
        earnings = earnings.sort_index(ascending=True)
        # Calculate % increase from past quarter to current quarter for each row
        earnings["eps_growth"] = (earnings["Reported EPS"].pct_change()*100).round(2)
        # Remove 'Reported EPS' and 'EPS Estimate' columns if they exist
        earnings = earnings.drop(columns=["Reported EPS", "EPS Estimate"], errors="ignore")
        earnings = earnings.rename(columns={"Surprise(%)": "surprise_percent"})
        # Reset index to turn the earnings date into a column named "date".
        # Rename the index first so the column name is predictable regardless of yfinance version.
        earnings.index.name = "date"
        earnings = earnings.reset_index()
        earnings["date"] = pd.to_datetime(earnings["date"]).dt.date
        # Return both % increase and surprise % for the last 4 quarters
        earnings_history = earnings.tail(4).to_dict(orient="records")
        return EPSHistoryResponse(
            ticker=ticker, earnings_history=[EPSHistoryRow(**row) for row in earnings_history]
        )

    try:
        return await _cached_snapshot(f"{stock.ticker}:eps", _produce)
    except Exception as e:  # noqa: BLE001 — the router turns this into a 404
        raise ValueError(f"Error fetching earnings history for {stock.ticker}: {e}")


async def fetch_revenue_history(stock: yf.Ticker):
    '''
    Fetch revenue history for a given ticker.
    Args:
        stock (yf.Ticker): The yfinance Ticker object.
    Returns:
        RevenueHistoryResponse: A list of revenue history responses for the specified ticker.
    '''
    async def _produce():
        ticker = stock.ticker
        with yf_guard.guard():
            income_stmt = await asyncio.to_thread(lambda: stock.quarterly_income_stmt)
        if income_stmt is None or income_stmt.empty:
            raise ValueError(f"No revenue history data found for ticker: {ticker}")
        # Remove future revenue rows
        revenue = income_stmt.loc["Total Revenue"].dropna().copy()
        # Sort oldest -> newest so pct_change works correctly
        revenue = revenue.sort_index(ascending=True)
        # Calculate % increase from past quarter to current quarter for each row
        revenue = revenue.to_frame().rename(columns={"Total Revenue": "revenue"})
        revenue["percent_change"] = (revenue["revenue"].pct_change()*100).round(2)
        # Reset index to turn the date into a column named "date"
        revenue.index.name = "date"
        revenue = revenue.reset_index()
        revenue["date"] = pd.to_datetime(revenue["date"]).dt.date
        # Return both revenue and % increase for the last 4 quarters
        revenue_history = revenue.tail(4).to_dict(orient="records")
        return RevenueHistoryResponse(
            ticker=ticker, revenue_history=[RevenueHistoryRow(**row) for row in revenue_history]
        )

    try:
        return await _cached_snapshot(f"{stock.ticker}:revenue", _produce)
    except Exception as e:  # noqa: BLE001 — the router turns this into a 404
        raise ValueError(f"Error fetching revenue history for {stock.ticker}: {e}")
    

async def fetch_stock_dashboard(ticker: str, days: int = 30):
    '''
    Fetch all relevant stock data for a given ticker to be displayed on the stock dashboard.
    Args:
        ticker (str): The stock ticker symbol.
        days (int): The number of days of OHLCV data to include.
    Returns:
        StockResponse: A comprehensive response containing the stock's OHLCV data and detailed information for the dashboard.
    '''
    stock = yf.Ticker(ticker)

    # The archive is the only part with no fallback: without price rows there
    # is no chart and nothing worth rendering, so this is the one failure that
    # is allowed to fail the request.
    try:
        ohlcv = await fetch(ticker, days)
    except Exception as e:  # noqa: BLE001 — surfaced as a domain error
        raise ValueError(f"Error fetching dashboard data for {ticker}: {e}")

    # Everything below is supplementary and comes from yfinance scrapes that
    # rate-limit in bursts. A reload used to take the whole page down when any
    # one of them 429'd — including the chart, which had already been read
    # from the archive and needed no network at all. Each degrades on its own.
    try:
        detailed = await fetch_detailed(stock)
    except Exception as e:  # noqa: BLE001
        logger.warning("Detail fetch failed for %s: %r", ticker, e)
        detailed = StockDetailedResponse(ticker=ticker)
    try:
        eps = await fetch_eps_history(stock)
    except Exception as e:  # noqa: BLE001
        logger.warning("EPS history fetch failed for %s: %r", ticker, e)
        eps = None
    try:
        revenue = await fetch_revenue_history(stock)
    except Exception as e:  # noqa: BLE001
        logger.warning("Revenue history fetch failed for %s: %r", ticker, e)
        revenue = None

    return StockResponse(
        ticker=ticker,
        ohlcv=ohlcv.data,
        info=detailed.info,
        analyst_price_targets=detailed.analyst_price_targets,
        recommendations_summary=detailed.recommendations_summary,
        earnings_estimate=detailed.earnings_estimate,
        revenue_estimate=detailed.revenue_estimate,
        earnings_history=eps.earnings_history if eps else None,
        revenue_history=revenue.revenue_history if revenue else None,
    )
