'''
Router for stock-related endpoints.
'''
from fastapi import HTTPException, APIRouter
from ..schemas.stocks import OHLCVResponse, StockDetailedResponse, StockCreateResponse, IndustryStocksResponse, SectorStocksResponse, IndustryMapResponse, SectorMapResponse, MarketResponse
from ..services import stock_service


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
async def get_market_status():
    '''
    Get the current status of the stock market (open/closed).
    '''
    status = await stock_service.get_market_status()
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


@router.get("/{ticker}/current", response_model=OHLCVResponse)
async def get_current_stock_price(ticker: str):
    '''
    Get the current stock price for a given ticker.
    Args:
        ticker (str): The stock ticker symbol.
    Returns:
        OHLCVResponse: The current stock data for the specified ticker.
    '''
    return await stock_service.fetch_current(ticker)


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


@router.delete("/{ticker}")
async def delete_stock(ticker: str):
    '''
    Delete stock data for a given ticker.
    Args:
        ticker (str): The stock ticker symbol.
    Returns:
        dict: A message indicating whether the deletion was successful.
    '''
    try:
        await stock_service.delete_stock(ticker)
        return {"message": f"Stock data for {ticker} deleted successfully."}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
        data = await stock_service.fetch_detailed(ticker)
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

