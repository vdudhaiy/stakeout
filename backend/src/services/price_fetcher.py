'''
Fetch stock price data from yfinance and upsert it into the market_data table.
'''

import asyncio
import os
import logging
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone

from markets import MARKET_META, last_completed_trading_day, market_of

from . import market_data_service, yf_guard

logger = logging.getLogger(__name__)


def _archive_end_date(ticker: str | None = None) -> str:
    '''
    Return the exclusive end date to pass to yfinance so that all completed
    sessions of `ticker`'s own market are included and no partial ones are.

    yfinance end is exclusive, so to include the last completed trading day D
    we need end = D + 1 calendar day.

    The market matters. This used to ask the NYSE calendar for every ticker,
    while the staleness check that decides whether to call at all
    (stock_service.ensure_archive_current) asks the ticker's own calendar.
    For an Indian ticker those disagree for the ~10 hours between the NSE
    close and the NYSE close: the archive was judged stale for today, the
    download was capped at yesterday, Yahoo correctly returned nothing, and
    that counted as a definitive answer — so the ticker's one attempt for the
    day was spent and NSE history sat permanently a session behind.
    '''
    market = market_of(ticker) if ticker else 'US'
    last_completed = last_completed_trading_day(market)
    if last_completed is None:
        return datetime.now(timezone.utc).strftime('%Y-%m-%d')
    return (last_completed + pd.Timedelta(days=1)).strftime('%Y-%m-%d')


def _flatten_yfinance_df(df):
    '''Flatten yfinance MultiIndex columns and strip timezone from index.'''
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if hasattr(df.index, 'tz') and df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df


def _synthesise_daily_from_hourly(ticker: str, date: pd.Timestamp) -> dict | None:
    '''
    Reconstruct a daily OHLCV bar from hourly data for a completed trading day
    where the Yahoo Finance daily bar still shows NaN.
    yf.Ticker.history returns a tz-aware index in the *exchange's* local time,
    so between_time is bounded by that market's own session rather than a
    hardcoded 09:30-16:00 — which on an NSE ticker clipped the first fifteen
    minutes of the day and took the session's real open with it.
    '''
    session_open, session_close = MARKET_META[market_of(ticker)]['sessions']['regular']
    try:
        start = date.strftime('%Y-%m-%d')
        end = (date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        hourly = yf.Ticker(ticker).history(interval='1h', start=start, end=end)
        if hourly.empty:
            return None
        regular = hourly.between_time(session_open, session_close)
        if regular.empty:
            return None
        return {
            'Open':   float(regular.iloc[0]['Open']),
            'High':   float(regular['High'].max()),
            'Low':    float(regular['Low'].min()),
            'Close':  float(regular.iloc[-1]['Close']),
            'Volume': int(regular['Volume'].sum()),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not synthesise daily bar for {ticker} on {date.date()}: {e}")
        return None


def _patch_nan_daily_bars(ticker: str, data: pd.DataFrame) -> tuple[pd.DataFrame, set]:
    '''
    For each completed trading day in `data` whose Close is NaN, attempt to
    reconstruct the daily OHLCV from hourly data and patch it in place.
    Dates beyond the last fully-closed session are left untouched.

    "Completed" is judged against `ticker`'s own market, for the same reason
    as _archive_end_date.

    Returns the patched DataFrame plus the set of dates that were synthesised
    (the caller tags those rows with a distinct `source` on upsert).
    '''
    last_completed = last_completed_trading_day(market_of(ticker))
    if last_completed is None:
        return data, set()

    nan_mask = data['Close'].isna() & (data.index <= last_completed)
    if not nan_mask.any():
        return data, set()

    synthetic_dates = set()
    for ts in data.index[nan_mask]:
        synthesised = _synthesise_daily_from_hourly(ticker, ts)
        if synthesised:
            for col, val in synthesised.items():
                if col in data.columns:
                    data.loc[ts, col] = val
            synthetic_dates.add(pd.Timestamp(ts).date())
            logger.info(f"Synthesised daily bar for {ticker} on {ts.date()} from hourly data.")

    return data, synthetic_dates


def _download(ticker: str, start_date: str, end_date: str, interval: str = '1d') -> tuple[pd.DataFrame, set]:
    '''Blocking yfinance download + cleanup. Always run via asyncio.to_thread — never call directly from a coroutine.'''
    data = yf.download(ticker, start=start_date, end=end_date, interval=interval, progress=False)
    data = _flatten_yfinance_df(data)
    data, synthetic_dates = _patch_nan_daily_bars(ticker, data)
    data = data.dropna(subset=['Close'])
    return data, synthetic_dates


async def fetch_historical_price_data(ticker, start_date=None, end_date=None, interval='1d', force_refresh=False):
    '''
    Download historical price data for a given ticker and date range, and
    upsert it into the market_data table.

    Parameters:
    ticker (str): The stock ticker symbol.
    start_date (str): The start date in 'YYYY-MM-DD' format. Default is '2023-01-01' or the value of ARCHIVE_START_DATE environment variable.
    end_date (str): The end date in 'YYYY-MM-DD' format. Default is today's date.
    interval (str): The interval for the historical data (e.g., '1d', '1wk', '1mo'). Default is '1d'.
    force_refresh (bool): If True, forces re-download of data even if it already exists in the archive. Default is False.

    Returns:
    None
    '''
    if not force_refresh and await market_data_service.has_data(ticker):
        logger.info(f"Historical price data for {ticker} already exists in archive. Skipping download.")
        return

    if start_date is None:
        start_date = pd.Timestamp(os.getenv("ARCHIVE_START_DATE", "2023-01-01")).strftime("%Y-%m-%d")
    if end_date is None:
        end_date = _archive_end_date(ticker)

    try:
        # Behind the backoff like every other yfinance call. This is the
        # single biggest one the app makes — years of daily bars — so leaving
        # it outside meant the heaviest request neither tripped the cooldown
        # nor respected one.
        with yf_guard.guard():
            data, synthetic_dates = await asyncio.to_thread(
                _download, ticker, start_date, end_date, interval
            )
        if data.empty:
            # Never upsert zero rows: their absence is what makes get_all_stocks()
            # correctly treat this ticker as untracked, rather than tracked
            # forever with an empty archive (e.g. invalid ticker, wrong exchange
            # suffix, or delisted).
            raise ValueError(f"No historical price data found for ticker: {ticker}")
        await market_data_service.upsert_ohlcv(ticker, data, synthetic_dates=synthetic_dates)
    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        raise


# How far back before the newest archived bar an incremental refresh restarts.
# Covers Yahoo restating a recently-published bar, and the window
# _patch_nan_daily_bars looks at, without re-pulling years of settled history.
_REFRESH_OVERLAP_DAYS = 7


async def append_price_data(ticker) -> bool:
    '''
    Bring a ticker's archive up to the last completed trading day.

    Fetches only the gap since the newest bar already stored (plus a few days
    of overlap, which the upsert absorbs) rather than the whole series from
    ARCHIVE_START_DATE: the settled history never changes, so re-downloading
    it on every refresh spent the upstream budget to learn one new bar, and a
    watchlist of N tickers did that N times the first time anyone loaded the
    app after a session closed. Only a ticker with no archive at all falls
    back to a full fetch.

    Upserts only once the new data is confirmed non-empty, so a transient
    fetch failure (network blip, rate limit, etc.) can never wipe out a
    previously-good archive.

    Parameters:
    ticker (str): The stock ticker symbol.

    Returns:
    bool: whether Yahoo gave a *definitive* answer — rows, or a credible
    "nothing new yet". False means the request itself failed and is worth
    retrying. The caller uses this to decide whether to burn the ticker's
    one attempt for the session: recording a failed request as an attempt is
    what let a rate-limited archive sit weeks out of date, since it could
    then only try again the following trading day.
    '''
    archive_start = pd.Timestamp(os.getenv("ARCHIVE_START_DATE", "2023-01-01"))
    last_archived = await market_data_service.get_last_date(ticker)
    if last_archived is None:
        start = archive_start
    else:
        start = max(archive_start, pd.Timestamp(last_archived) - pd.Timedelta(days=_REFRESH_OVERLAP_DAYS))

    start_date = start.strftime("%Y-%m-%d")
    end_date = _archive_end_date(ticker)

    if start_date >= end_date:
        # Nothing has closed since the newest archived bar — the caller's
        # staleness check raced the session boundary. Asking anyway would
        # return an empty frame and look like a failure.
        return True

    try:
        with yf_guard.guard():
            data, synthetic_dates = await asyncio.to_thread(
                _download, ticker, start_date, end_date
            )
    except Exception as e:  # noqa: BLE001
        # Transient: keep serving the existing archive, and tell the caller
        # this doesn't count as having asked.
        logger.error(f"Error re-fetching price data for {ticker}: {e}")
        return False

    if data.empty:
        # Yahoo answered and had nothing for the window — usually the day's
        # bar simply isn't published yet. A definitive answer, so it does
        # count as having asked.
        logger.info(f"No new price data for {ticker} ({start_date} to {end_date}, exclusive).")
        return True

    await market_data_service.upsert_ohlcv(ticker, data, synthetic_dates=synthetic_dates)
    logger.info(f"Re-fetched {len(data)} rows for {ticker} ({start_date} to {end_date}, exclusive).")
    return True
