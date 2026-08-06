'''
Router for stock-related endpoints.
'''
from fastapi import HTTPException, APIRouter
import yfinance as yf
from schemas.stocks import OHLCVResponse, StockDetailedResponse, StockCreateResponse, IndustryStocksResponse, SectorStocksResponse, IndustryMapResponse, SectorMapResponse, MarketResponse, EPSHistoryResponse, RevenueHistoryResponse, StockResponse, IndicesResponse, ClassificationResponse, TickerSearchResponse
from services import index_service, stock_service


router = APIRouter(prefix="/stocks", tags=["Stocks"])


@router.get("/")
async def stock_root():
    '''
    Root endpoint for stocks. Provides basic information about the stocks API.
    Returns:
        dict: a dictionary containing a list of all available stocks in the archive directory.
    '''
    data = await stock_service.get_all_stocks()
    return {"stocks": data}


@router.get("/market", response_model=MarketResponse)
async def get_market_status(market: str = "US"):
    '''
    Get the current status of a stock market (open/closed).
    Args:
        market: "US" (NYSE/NASDAQ) or "IN" (NSE/BSE). Defaults to "US".
    '''
    status = await stock_service.get_market_status(market)
    return MarketResponse(status=status)


@router.get("/industries", response_model=IndustryMapResponse)
async def get_industry_map():
    '''
    Get a mapping of industry names to the tickers that belong to each.
    Returns:
        IndustryMapResponse: { industries: { industry_name: [ticker, ...] } }
    '''
    industries = await stock_service.get_industry_map()
    return IndustryMapResponse(industries=industries)


@router.get("/sectors", response_model=SectorMapResponse)
async def get_sector_map():
    '''
    Get a mapping of sector names to the tickers that belong to each.
    Returns:
        SectorMapResponse: { sectors: { sector_name: [ticker, ...] } }
    '''
    sectors = await stock_service.get_sector_map()
    return SectorMapResponse(sectors=sectors)


@router.get("/indices", response_model=IndicesResponse)
async def get_major_indices():
    '''
    Latest levels, day change, and ~3-month daily close series for the major
    US (S&P 500, Dow, NASDAQ) and Indian (NIFTY 50, SENSEX, NIFTY Bank)
    indices. Public and cached for 10 minutes — powers the home page strip.
    '''
    data = await index_service.get_major_indices()
    return IndicesResponse(**data)


@router.get("/classification", response_model=ClassificationResponse)
async def get_classification(tickers: str):
    '''
    Sector/industry classification for a comma-separated batch of tickers,
    e.g. ?tickers=AAPL,TCS.NS. Cached 24h per ticker. Powers the portfolio
    sector/industry breakdown charts (client-side, so guest portfolios —
    which never touch the database — can use it too).
    '''
    symbols = [t for t in (s.strip() for s in tickers.split(",")) if t]
    if not symbols:
        raise HTTPException(status_code=400, detail="No tickers provided")
    if len(symbols) > 100:
        raise HTTPException(status_code=400, detail="At most 100 tickers per request")
    data = await stock_service.get_classification(symbols)
    return ClassificationResponse(classification=data)


@router.get("/search", response_model=TickerSearchResponse)
async def search_tickers(q: str, exchange: str = "US"):
    '''
    Ticker/company-name autocomplete, e.g. ?q=apple&exchange=US. `exchange`
    is "US" | "IN" (defaults to "US") — results are scoped to it, and Indian
    results have their .NS/.BO suffix stripped since which exchange to
    actually use is resolved later, at add/buy time. Cached 5 minutes.
    '''
    results = await stock_service.search_tickers(q, exchange)
    return TickerSearchResponse(query=q, results=results)


@router.get("/{ticker}/current", response_model=OHLCVResponse)
async def get_current_stock_price(ticker: str):
    '''
    Get the current stock price for a given ticker.
    Args:
        ticker (str): The stock ticker symbol.
    Returns:
        OHLCVResponse: The current stock data for the specified ticker.
    '''
    try:
        return await stock_service.fetch_current(yf.Ticker(ticker))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{ticker}/intraday", response_model=OHLCVResponse)
async def get_intraday_stock_data(ticker: str):
    '''
    Get intraday stock data for a given ticker.
    Args:
        ticker (str): The stock ticker symbol.
    Returns:
        OHLCVResponse: The intraday stock data for the specified ticker.
    '''
    try:
        return await stock_service.fetch_intraday(yf.Ticker(ticker))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{ticker}", response_model=OHLCVResponse)
async def get_stock(ticker: str, days: int = 30):
    '''
    Get stock data for a given ticker and number of days.
    Args:
        ticker (str): The stock ticker symbol.
        days (int, optional): The number of days of data to retrieve. Defaults to 30.
    Returns:
            OHLCVResponse: The stock data for the specified ticker and time period.
    '''
    try:
        data = await stock_service.fetch(ticker, days)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data


@router.post("/{ticker}", response_model=StockCreateResponse)
async def add_stock(ticker: str):
    '''
    Add stock data for a given ticker.
    Args:
        ticker (str): The stock ticker symbol.
    Returns:
        StockCreateResponse: The stock data for the specified ticker and time period, along with detailed information about the stock, including financials, calendar events, analyst price targets, and recommendations.
    '''
    try:
        all_stocks = await stock_service.get_all_stocks()
        if ticker in all_stocks:
            return StockCreateResponse(exist=True, ohlcv=OHLCVResponse(ticker=ticker, data=[]), details=StockDetailedResponse(ticker=ticker))
        return await stock_service.add_stock(ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# Temporarily disabled. market_data is a cache shared by every user, and this
# route has no auth dependency — any unauthenticated caller could wipe a
# symbol's entire OHLCV history out from under other users' holdings and
# watchlists. Nothing in the frontend calls it (the dashboard's remove button
# hits DELETE /watchlist/{ticker}; removing a holding hits DELETE
# /portfolio/{ticker}), so disabling it costs nothing today.
#
# Before re-enabling: require auth AND only delete when no Holding or
# WatchlistEntry in any user still references the symbol — i.e. make it a
# garbage-collect of orphaned archive rows, not an unconditional wipe.
# services.stock_service.delete_stock is left in place for that.
#
# @router.delete("/{ticker}")
# async def delete_stock(ticker: str):
#     '''
#     Delete stock data for a given ticker.
#     Args:
#         ticker (str): The stock ticker symbol.
#     Returns:
#         dict: A message indicating whether the deletion was successful.
#     '''
#     try:
#         await stock_service.delete_stock(ticker)
#         return {"message": f"Stock data for {ticker} deleted successfully."}
#     except ValueError as e:
#         raise HTTPException(status_code=404, detail=str(e))


@router.get("/{ticker}/details", response_model=StockDetailedResponse)
async def get_stock_details(ticker: str):
    '''
    Get detailed stock information for a given ticker.
    Args:
        ticker (str): The stock ticker symbol.
    Returns:
        StockDetailedResponse: Detailed information about the stock, including financials, calendar events, analyst price targets, and recommendations.
    '''
    try:
        data = await stock_service.fetch_detailed(yf.Ticker(ticker))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data


@router.get("/{industry}", response_model=IndustryStocksResponse)
async def get_industry_stocks(industry: str):
    '''
    Get stock data for all stocks in a given industry.
    Args:
        industry (str): The industry to filter stocks by.
    Returns:
        IndustryStocksResponse: A list of stocks in the specified industry along with their OHLCV data.
    '''
    try:
        data = await stock_service.fetch_industry_stocks(industry)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data


@router.get("/{sector}", response_model=SectorStocksResponse)
async def get_sector_stocks(sector: str):
    '''
    Get stock data for all stocks in a given sector.
    Args:
        sector (str): The sector to filter stocks by.
    Returns:
        SectorStocksResponse: A list of stocks in the specified sector along with their OHLCV data.
    '''
    try:
        data = await stock_service.fetch_sector_stocks(sector)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data


@router.get("/{ticker}/eps", response_model=EPSHistoryResponse)
async def get_eps_history(ticker: str):
    '''
    Get EPS history for a given ticker.
    Args:
        ticker (str): The stock ticker symbol.
    Returns:
        EPSHistoryResponse: A list of earnings history responses for the specified ticker.
    '''
    try:
        data = await stock_service.fetch_eps_history(yf.Ticker(ticker))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data


@router.get("/{ticker}/revenue", response_model=RevenueHistoryResponse)
async def get_revenue_history(ticker: str):
    '''
    Get revenue history for a given ticker.
    Args:
        ticker (str): The stock ticker symbol.
    Returns:
        RevenueHistoryResponse: A list of revenue history responses for the specified ticker.
    '''
    try:
        data = await stock_service.fetch_revenue_history(yf.Ticker(ticker))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data


@router.get("/{ticker}/dashboard", response_model=StockResponse)
async def get_stock_dashboard(ticker: str, days: int = 30):
    '''
    Get all dashboard data for a given ticker.
    Args:
        ticker (str): The stock ticker symbol.
        days (int): The number of days of OHLCV data to include.
    Returns:
        StockResponse: All dashboard data for the specified ticker, including OHLCV data, financials, calendar events, analyst price targets, and recommendations.
    '''
    try:
        data = await stock_service.fetch_stock_dashboard(ticker, days)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data