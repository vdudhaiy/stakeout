'''
Fetch stock price data from yfinance and upsert it into the market_data table.
'''

import asyncio
import os
import logging
import pandas as pd
import pandas_market_calendars as mcal
import yfinance as yf
from datetime import datetime, timezone, timedelta

from . import market_data_service

logger = logging.getLogger(__name__)


def _archive_end_date() -> str:
    '''
    Return the exclusive end date to pass to yfinance so that all completed NYSE
    sessions are included and no partial (in-progress) candles are.

    yfinance end is exclusive, so to include the last completed trading day D we
    need end = D + 1 calendar day. We determine D by comparing each session's
    market_close (UTC-aware, from pandas_market_calendars) against UTC now —
    identical logic to the dashboard's _last_completed_trading_day().
    '''
    nyse = mcal.get_calendar('NYSE')
    now_utc = datetime.now(timezone.utc)
    schedule = nyse.schedule(
        start_date=(now_utc - timedelta(days=10)).date(),
        end_date=now_utc.date(),
    )
    if schedule.empty:
        return now_utc.strftime('%Y-%m-%d')
    closed = schedule[schedule['market_close'] <= pd.Timestamp(now_utc)]
    if closed.empty:
        return now_utc.strftime('%Y-%m-%d')
    last_completed = pd.Timestamp(closed.index[-1].date())
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
    yf.Ticker.history returns tz-aware (America/New_York) index so between_time
    compares local ET time, correctly bounding the regular session.
    '''
    try:
        start = date.strftime('%Y-%m-%d')
        end = (date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        hourly = yf.Ticker(ticker).history(interval='1h', start=start, end=end)
        if hourly.empty:
            return None
        regular = hourly.between_time('09:30', '16:00')
        if regular.empty:
            return None
        return {
            'Open':   float(regular.iloc[0]['Open']),
            'High':   float(regular['High'].max()),
            'Low':    float(regular['Low'].min()),
            'Close':  float(regular.iloc[-1]['Close']),
            'Volume': int(regular['Volume'].sum()),
        }
    except Exception as e:
        logger.warning(f"Could not synthesise daily bar for {ticker} on {date.date()}: {e}")
        return None


def _patch_nan_daily_bars(ticker: str, data: pd.DataFrame) -> tuple[pd.DataFrame, set]:
    '''
    For each completed NYSE trading day in `data` whose Close is NaN, attempt to
    reconstruct the daily OHLCV from hourly data and patch it in place.
    Dates beyond the last fully-closed session are left untouched.

    Returns the patched DataFrame plus the set of dates that were synthesised
    (the caller tags those rows with a distinct `source` on upsert).
    '''
    nyse = mcal.get_calendar('NYSE')
    now_utc = datetime.now(timezone.utc)
    schedule = nyse.schedule(
        start_date=(now_utc - timedelta(days=10)).date(),
        end_date=now_utc.date(),
    )
    if schedule.empty:
        return data, set()
    closed = schedule[schedule['market_close'] <= pd.Timestamp(now_utc)]
    if closed.empty:
        return data, set()
    last_completed = pd.Timestamp(closed.index[-1].date())

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
        end_date = _archive_end_date()

    try:
        data, synthetic_dates = await asyncio.to_thread(_download, ticker, start_date, end_date, interval)
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


async def append_price_data(ticker):
    '''
    Refresh price data for a ticker by re-fetching all data from ARCHIVE_START_DATE
    to the last completed trading day and upserting it — but only once the new
    data is confirmed non-empty, so a transient fetch failure (network blip,
    rate limit, etc.) can never wipe out a previously-good archive.

    Parameters:
    ticker (str): The stock ticker symbol.

    Returns:
    None
    '''
    start_date = pd.Timestamp(os.getenv("ARCHIVE_START_DATE", "2023-01-01")).strftime("%Y-%m-%d")
    end_date = _archive_end_date()

    try:
        data, synthetic_dates = await asyncio.to_thread(_download, ticker, start_date, end_date)
        if data.empty:
            raise ValueError(f"No historical price data found for ticker: {ticker}")
    except Exception as e:
        logger.error(f"Error re-fetching price data for {ticker}: {e}")
        return  # keep serving the existing archive rather than destroying it

    await market_data_service.upsert_ohlcv(ticker, data, synthetic_dates=synthetic_dates)
    logger.info(f"Re-fetched {len(data)} rows for {ticker} ({start_date} to {end_date}, exclusive).")
