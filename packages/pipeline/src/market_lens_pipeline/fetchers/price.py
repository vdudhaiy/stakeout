'''
Fetch Stock Price Data using yfinance library.
'''

import yfinance as yf
import os
import logging
import pandas as pd
import pandas_market_calendars as mcal
import dotenv
from pathlib import Path
from datetime import datetime, timezone, timedelta

dotenv.load_dotenv()

_REPO_ROOT = Path(__file__).resolve().parents[5]
ARCHIVE_DATA_DIR = _REPO_ROOT / os.getenv("ARCHIVE_DATA_DIR", "data/archive_stock_data/")

logger = logging.getLogger(__name__)

def _archive_end_date() -> str:
    '''
    Return the exclusive end date to pass to yfinance so that all completed NYSE
    sessions are included and no partial (in-progress) candles are.

    yfinance end is exclusive, so to include the last completed trading day D we
    need end = D + 1 calendar day.  We determine D by comparing each session's
    market_close (UTC-aware, from pandas_market_calendars) against UTC now —
    identical logic to the dashboard's _last_completed_trading_day(), but kept
    here so the pipeline is self-contained.
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


def _patch_nan_daily_bars(ticker: str, data: pd.DataFrame) -> pd.DataFrame:
    '''
    For each completed NYSE trading day in `data` whose Close is NaN, attempt to
    reconstruct the daily OHLCV from hourly data and patch it in place.
    Dates beyond the last fully-closed session are left untouched.
    '''
    nyse = mcal.get_calendar('NYSE')
    now_utc = datetime.now(timezone.utc)
    schedule = nyse.schedule(
        start_date=(now_utc - timedelta(days=10)).date(),
        end_date=now_utc.date(),
    )
    if schedule.empty:
        return data
    closed = schedule[schedule['market_close'] <= pd.Timestamp(now_utc)]
    if closed.empty:
        return data
    last_completed = pd.Timestamp(closed.index[-1].date())

    nan_mask = data['Close'].isna() & (data.index <= last_completed)
    if not nan_mask.any():
        return data

    for ts in data.index[nan_mask]:
        synthesised = _synthesise_daily_from_hourly(ticker, ts)
        if synthesised:
            for col, val in synthesised.items():
                if col in data.columns:
                    data.loc[ts, col] = val
            logger.info(f"Synthesised daily bar for {ticker} on {ts.date()} from hourly data.")

    return data


def fetch_historical_price_data(ticker, start_date=None, end_date=None, interval='1d', force_refresh=False):
    '''
    Download historical price data for a given ticker and date range.

    Parameters:
    ticker (str): The stock ticker symbol.
    start_date (str): The start date in 'YYYY-MM-DD' format. Default is '2023-01-01' or the value of ARCHIVE_START_DATE environment variable.
    end_date (str): The end date in 'YYYY-MM-DD' format. Default is today's date.
    interval (str): The interval for the historical data (e.g., '1d', '1wk', '1mo'). Default is '1d'.
    force_refresh (bool): If True, forces re-download of data even if it already exists in the archive. Default is False.

    Returns:
    None
    '''
    # First check if ticker file exists in archive
    if any(ARCHIVE_DATA_DIR.glob(f"{ticker}_*.csv")) and not force_refresh:
        logger.info(f"Historical price data for {ticker} already exists in archive. Skipping download.")
        return

    if start_date is None:
        start_date = pd.Timestamp(os.getenv("ARCHIVE_START_DATE", "2023-01-01")).strftime("%Y-%m-%d")
    if end_date is None:
        end_date = _archive_end_date()

    save_file_name = ARCHIVE_DATA_DIR / f"{ticker}_{start_date}_{end_date}.csv"
    try:
        data = yf.download(ticker, start=start_date, end=end_date, interval=interval)
        data = _flatten_yfinance_df(data)
        data = _patch_nan_daily_bars(ticker, data)
        data = data.dropna(subset=['Close'])
        data.to_csv(save_file_name)
    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        raise


def fetch_current_price(ticker):
    '''
    Fetch the current price of a stock.

    Parameters:
    ticker (str): The stock ticker symbol.

    Returns:
    float: The current price of the stock.
    '''
    try:
        stock = yf.Ticker(ticker)
        current_price = stock.get_info['currentPrice']
        return current_price
    except Exception as e:
        logger.error(f"Error fetching current price for {ticker}: {e}")
        return None


def append_price_data(ticker):
    '''
    Refresh price data for a ticker by re-fetching all data from ARCHIVE_START_DATE to yesterday.
    Replaces any existing archive file for the ticker.

    Parameters:
    ticker (str): The stock ticker symbol.

    Returns:
    None
    '''
    start_date = pd.Timestamp(os.getenv("ARCHIVE_START_DATE", "2023-01-01")).strftime("%Y-%m-%d")
    end_date = _archive_end_date()

    for f in ARCHIVE_DATA_DIR.glob(f"{ticker}_*.csv"):
        f.unlink()
        logger.debug(f"Removed old archive file: {f.name}")

    save_file_name = ARCHIVE_DATA_DIR / f"{ticker}_{start_date}_{end_date}.csv"
    try:
        data = yf.download(ticker, start=start_date, end=end_date, interval="1d", progress=False)
        data = _flatten_yfinance_df(data)
        data = _patch_nan_daily_bars(ticker, data)
        data = data.dropna(subset=['Close'])
        data.to_csv(save_file_name)
        logger.info(f"Re-fetched {len(data)} rows for {ticker} ({start_date} to {end_date}, exclusive).")
    except Exception as e:
        logger.error(f"Error re-fetching price data for {ticker}: {e}")
    
