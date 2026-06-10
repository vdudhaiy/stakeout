'''
Read relevant stock data from the data/ directory and returns it in a format suitable for the endpoint to use.
'''

import os
from pathlib import Path
import pandas as pd
import yfinance as yf
from ..config import ARCHIVE_DATA_DIR
from ..schemas.stocks import *
import pandas_market_calendars as mcal
from datetime import datetime, time, timezone, timedelta

# Tracks the last _last_completed_trading_day we already attempted to fetch for each ticker.
# Prevents hammering yfinance when Yahoo Finance hasn't published the day's data yet;
# the attempt resets automatically once a newer completed trading day becomes available.
_update_attempted: dict[str, pd.Timestamp] = {}

async def _last_completed_trading_day() -> pd.Timestamp | None:
    '''
    Return the most recent NYSE trading day whose market session has fully closed,
    using UTC-aware timestamps throughout so server timezone is irrelevant.
    '''
    nyse = mcal.get_calendar('NYSE')
    now_utc = datetime.now(timezone.utc)
    schedule = nyse.schedule(
        start_date=(now_utc - timedelta(days=10)).date(),
        end_date=now_utc.date(),
    )
    if schedule.empty:
        return None
    closed = schedule[schedule['market_close'] <= pd.Timestamp(now_utc)]
    if closed.empty:
        return None
    return pd.Timestamp(closed.index[-1].date())


async def get_market_status():
    '''
    Check if the stock market is currently open or closed.
    Returns:
        bool: True if the market is open, False if it is closed.
    '''
    nyse = mcal.get_calendar('NYSE')

    now = datetime.now(timezone.utc)

    schedule = nyse.schedule(
        start_date=now.date(),
        end_date=now.date(),
    )

    if schedule.empty:
        return False

    market_open = schedule.iloc[0]["market_open"]
    market_close = schedule.iloc[0]["market_close"]

    return market_open <= now <= market_close


async def get_all_stocks():
    '''
    Get a list of all available stocks in the system.
    Returns:
        list: A list of stock ticker symbols available in the archive directory.
    '''
    files = os.listdir(ARCHIVE_DATA_DIR)
    tickers = set(f.split("_")[0] for f in files if f.endswith(".csv"))
    return sorted(tickers)


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
        # Fetch data from yfinance and save to archive directory using pipeline's price fetcher
        from market_lens_pipeline.fetchers.price import fetch_historical_price_data
        fetch_historical_price_data(ticker)
        ohlcv = await fetch(ticker)  # Return the fetched data
        service = StockService()
        stock = yf.Ticker(ticker)
        detailed_info = service.get_stock_details(stock)  # Get detailed info for the stock
        return StockCreateResponse(exist=False, ohlcv=ohlcv, details=detailed_info)
    except Exception as e:
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
        files = os.listdir(ARCHIVE_DATA_DIR)
        ticker_files = [f for f in files if f.startswith(ticker) and f.endswith(".csv")]
        if not ticker_files:
            raise ValueError(f"No CSV data found for ticker: {ticker}")
        for f in ticker_files:
            os.remove(os.path.join(ARCHIVE_DATA_DIR, f))
        return {"message": f"Stock data for {ticker} deleted successfully."}
    except Exception as e:
        raise ValueError(f"Error deleting stock data for {ticker}: {str(e)}")


async def fetch(ticker: str, days: int = 30):
    '''
    Fetch stock data for a given ticker and number of days. If data is outdated, use pipeline's price fetcher to get the latest data and update the archive. Ensure that no new data is fetched if the current date is a weekend.
    Args:
        ticker (str): The stock ticker symbol.
        days (int, optional): The number of days of data to retrieve. Defaults to 30.
    Returns:
        OHLCVResponse: The stock data for the specified ticker and time period.
    '''
    files = os.listdir(ARCHIVE_DATA_DIR)
    ticker_files = sorted(f for f in files if f.startswith(ticker) and f.endswith(".csv"))
    if not ticker_files:
        raise ValueError(f"No CSV data found for ticker: {ticker}")
    
    def _read_archive(path: str, n: int) -> tuple[pd.DataFrame, list]:
        d = pd.read_csv(path)
        d.columns = [col.lower() for col in d.columns]
        d = d.dropna(subset=['close'])  # ignore rows Yahoo Finance hasn't finalised yet
        return d, d.tail(n).to_dict(orient='records')

    file_path = os.path.join(ARCHIVE_DATA_DIR, ticker_files[-1])
    _, records = _read_archive(file_path, days)
    if not records:
        raise ValueError(f"No confirmed OHLCV data found for ticker: {ticker}")
    last_date = pd.to_datetime(records[-1]['date'])

    last_completed = await _last_completed_trading_day()
    already_attempted = _update_attempted.get(ticker)
    need_update = (
        last_completed is not None
        and last_date.date() < last_completed.date()
        and (already_attempted is None or already_attempted.date() < last_completed.date())
    )
    if need_update:
        _update_attempted[ticker] = last_completed
        from market_lens_pipeline.fetchers.price import append_price_data
        append_price_data(ticker)
        # Re-discover: append_price_data deletes the old file and writes a new one
        ticker_files = sorted(f for f in os.listdir(ARCHIVE_DATA_DIR) if f.startswith(ticker) and f.endswith(".csv"))
        file_path = os.path.join(ARCHIVE_DATA_DIR, ticker_files[-1])
        _, records = _read_archive(file_path, days)

    return OHLCVResponse(
        ticker=ticker,
        data=[OHLCV(**row) for row in records]
    )


async def fetch_current(ticker: str):
    '''
    Fetch the current stock price for a given ticker.
    Args:
        ticker (str): The stock ticker symbol.
    Returns:
        OHLCVResponse: The current stock data for the specified ticker.
    '''
    try:
        stock = yf.Ticker(ticker)
        is_market_open = await get_market_status()

        if is_market_open:
            df_current = stock.history(
                interval="1m",
                period="1d",
                prepost=True
            )
            # Convert index and filter to Regular Trading Hours only
            df = df_current.copy()
            df.index = pd.to_datetime(df.index)
            df = df.between_time("09:30", "16:00")

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
            df_current = stock.history(
                interval="1m",
                period="2d",
                prepost=True
            )
            today = pd.Timestamp.now(tz=df_current.index.tz).date()
            df_current = df_current[
                df_current.index.date == today
            ]
            # Convert index and filter to outside Regular Trading Hours only
            df = df_current.copy()
            df.index = pd.to_datetime(df.index)
            mask = ((df.index.time >= time(9, 30)) & (df.index.time <= time(16, 0)))
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
    except Exception as e:
        raise ValueError(f"Error fetching current stock data for {ticker}: {str(e)}")


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


async def fetch_detailed(ticker: str):
    '''
    Fetch detailed stock information for a given ticker.
    Args:
        ticker (str): The stock ticker symbol.
    Returns:
        StockDetailedResponse: Detailed information about the stock, including financials, calendar events, analyst price targets, and recommendations.
    '''
    service = StockService()
    stock = yf.Ticker(ticker)
    return service.get_stock_details(stock)


async def get_industry_map() -> dict:
    '''
    Build a mapping of industry names to the tickers that belong to each.
    Returns:
        dict: { industry_name: [ticker, ...] } sorted alphabetically.
    '''
    result: dict[str, list[str]] = {}
    for ticker in await get_all_stocks():
        try:
            info = yf.Ticker(ticker).info
            industry = info.get("industry")
            if industry:
                result.setdefault(industry, []).append(ticker)
        except Exception:
            pass
    return {k: sorted(v) for k, v in sorted(result.items())}


async def get_sector_map() -> dict:
    '''
    Build a mapping of sector names to the tickers that belong to each.
    Returns:
        dict: { sector_name: [ticker, ...] } sorted alphabetically.
    '''
    result: dict[str, list[str]] = {}
    for ticker in await get_all_stocks():
        try:
            info = yf.Ticker(ticker).info
            sector = info.get("sector")
            if sector:
                result.setdefault(sector, []).append(ticker)
        except Exception:
            pass
    return {k: sorted(v) for k, v in sorted(result.items())}


async def fetch_industry_stocks(industry: str):
    '''
    Fetch stock data for all stocks in a given industry.
    Args:
        industry (str): The industry to filter stocks by.
    Returns:
        IndustryStocksResponse: A list of stocks in the specified industry along with their OHLCV data.
    '''
    response = {"industry": industry, "ohlcv": []}
    for ticker in await get_all_stocks():
        stock = yf.Ticker(ticker)
        if stock.info.get("industry", "").lower() == industry.lower():
            ohlcv_data = await fetch(ticker)
            response["ohlcv"].append(ohlcv_data)
    return IndustryStocksResponse(**response)


async def fetch_sector_stocks(sector: str):
    '''
    Fetch stock data for all stocks in a given sector.
    Args:
        sector (str): The sector to filter stocks by.
    Returns:
        SectorStocksResponse: A list of stocks in the specified sector along with their OHLCV data.
    '''
    response = {"sector": sector, "ohlcv": []}
    for ticker in await get_all_stocks():
        stock = yf.Ticker(ticker)
        if stock.info.get("sector", "").lower() == sector.lower():
            ohlcv_data = await fetch(ticker)
            response["ohlcv"].append(ohlcv_data)
    return SectorStocksResponse(**response)


async def fetch_eps_history(ticker: str):
    '''
    Fetch EPS history for a given ticker.
    Args:
        ticker (str): The stock ticker symbol.
    Returns:
        EPSHistoryResponse: A list of earnings history responses for the specified ticker.
    '''
    try:
        stock = yf.Ticker(ticker)
        earnings = stock.get_earnings_dates()
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
        # Reset index to turn the earnings date into a column, and rename it to "date"
        earnings = earnings.reset_index().rename(columns={"Earnings Date": "date"})
        earnings["date"] = pd.to_datetime(earnings["date"]).dt.date
        # Return both % increase and surprise % for the last 4 quarters
        earnings_history = earnings.tail(4).to_dict(orient="records")
        return EPSHistoryResponse(ticker=ticker, earnings_history=[EPSHistoryRow(**row) for row in earnings_history])
    except Exception as e:
        raise ValueError(f"Error fetching earnings history for {ticker}: {str(e)}")


async def fetch_revenue_history(ticker: str):
    '''
    Fetch revenue history for a given ticker.
    Args:
        ticker (str): The stock ticker symbol.
    Returns:
        RevenueHistoryResponse: A list of revenue history responses for the specified ticker.
    '''
    try:
        stock = yf.Ticker(ticker)
        income_stmt = stock.quarterly_income_stmt
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
        return RevenueHistoryResponse(ticker=ticker, revenue_history=[RevenueHistoryRow(**row) for row in revenue_history])
    except Exception as e:
        raise ValueError(f"Error fetching revenue history for {ticker}: {str(e)}")