'''
Fetch Stock Price Data using yfinance library.
'''

import yfinance as yf
import os
import logging
import pandas as pd
from datetime import timedelta
import dotenv

dotenv.load_dotenv()
ARCHIVE_DATA_DIR = os.getenv("ARCHIVE_DATA_DIR")

logger = logging.getLogger(__name__)

def _flatten_yfinance_df(df):
    '''Flatten yfinance MultiIndex columns and strip timezone from index.'''
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if hasattr(df.index, 'tz') and df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df


def _read_price_csv(file_path):
    '''Read a price CSV, handling both flat and yfinance multi-level formats.'''
    with open(file_path) as f:
        first_line = f.readline().strip()

    if first_line.startswith('Price'):
        df = pd.read_csv(file_path, header=[0, 1], index_col=0)
        df = df.dropna(how='all')
        df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index)
    else:
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)

    return df


def fetch_historical_price_data(ticker, start_date, end_date=None, interval='1d'):
    '''
    Download historical price data for a given ticker and date range.

    Parameters:
    ticker (str): The stock ticker symbol.
    start_date (str): The start date in 'YYYY-MM-DD' format.
    end_date (str): The end date in 'YYYY-MM-DD' format. Default is today's date.
    interval (str): The interval for the historical data (e.g., '1d', '1wk', '1mo'). Default is '1d'.

    Returns:
    None
    '''
    if end_date is None:
        end_date = (pd.Timestamp.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    save_file_name = ARCHIVE_DATA_DIR + f"{ticker}_{start_date}_{end_date}.csv"
    try:
        data = yf.download(ticker, start=start_date, end=end_date, interval=interval)
        data = _flatten_yfinance_df(data)
        data.to_csv(save_file_name)
    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        return None


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
        current_price = stock.info['currentPrice']
        return current_price
    except Exception as e:
        logger.error(f"Error fetching current price for {ticker}: {e}")
        return None


def append_price_data(ticker):
    '''
    Append new price data (from last price fetch) to the existing historical price data CSV file.

    Example: If a file AAPL_2020-01-01_2023-01-01.csv exists, and the last price fetch was on 2023-01-02, this function will append the new price data for 2023-01-02 to the existing file.

    Parameters:
    ticker (str): The stock ticker symbol.
    
    Returns:
    None
    '''

    existing_files = [
        f for f in os.listdir(ARCHIVE_DATA_DIR)
        if f.startswith(ticker)
    ]

    if not existing_files:
        logger.warning(
            f"No existing price data file found for {ticker}. "
            "Please fetch historical data first."
        )
        return

    existing_files.sort()
    latest_file = existing_files[-1]
    latest_file_path = os.path.join(ARCHIVE_DATA_DIR, latest_file)

    try:
        existing_df = _read_price_csv(latest_file_path)

        if existing_df.empty:
            logger.warning(f"Existing file for {ticker} is empty.")
            return

        last_date = existing_df.index.max()
        logger.debug(f"Last date in existing file for {ticker}: {last_date.date()}")

        # If last date is today or later (e.g. weekend), no need to append
        if last_date.date() >= pd.Timestamp.now().date():
            logger.info(f"Price data for {ticker} is already up to date.")
            return

        # Start fetching from the next day
        start_date = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")

        new_df = _flatten_yfinance_df(yf.download(
            ticker,
            start=start_date,
            interval="1d",
            progress=False
        ))

        new_df = new_df[new_df.index > last_date]

        if new_df.empty:
            logger.info(f"No new data available for {ticker}. Price data is already up to date.")
            return

        # Combine existing and new data
        combined_df = pd.concat([existing_df, new_df])

        # Remove duplicates by date
        combined_df = combined_df[~combined_df.index.duplicated(keep="last")]

        # Sort by date just in case
        combined_df.sort_index(inplace=True)

        # Save back to same file
        combined_df.to_csv(latest_file_path)

        logger.info(
            f"Appended {len(new_df)} new rows for {ticker}."
        )

    except Exception as e:
        logger.error(f"Error appending price data for {ticker}: {e}")
    
