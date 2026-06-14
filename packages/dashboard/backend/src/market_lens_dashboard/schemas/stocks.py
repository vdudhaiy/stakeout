'''
Schema for stocks.
'''

from pydantic import BaseModel
from typing import List, Optional
import datetime


class MarketResponse(BaseModel):
    status: bool



class OHLCV(BaseModel):
    date: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    volume: Optional[int] = None


class OHLCVResponse(BaseModel):
    ticker: str
    data: List[OHLCV]


class IncomeStatement(BaseModel):
    annual: Optional[dict] = None
    quarterly: Optional[dict] = None
    ttm: Optional[dict] = None


class Calendar(BaseModel):
    earnings_date: Optional[list[str]] = None
    earnings_high: Optional[float] = None
    earnings_low: Optional[float] = None
    earnings_average: Optional[float] = None
    revenue_high: Optional[Optional[int]] = None
    revenue_low: Optional[int] = None
    revenue_average: Optional[int] = None
    dividend_date: Optional[str] = None
    ex_dividend_date: Optional[str] = None


class AnalystPriceTargets(BaseModel):
    current: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    mean: Optional[float] = None
    median: Optional[float] = None


class RecommendationPeriod(BaseModel):
    period: Optional[str] = None
    strong_buy: Optional[int] = None
    buy: Optional[int] = None
    hold: Optional[int] = None
    sell: Optional[int] = None
    strong_sell: Optional[int] = None


class UpgradeDowngrade(BaseModel):
    date: Optional[datetime.date] = None
    firm: Optional[str] = None
    to_grade: Optional[str] = None
    from_grade: Optional[str] = None
    action: Optional[str] = None


class EarningsEstimateRow(BaseModel):
    period: Optional[str] = None                # e.g. "0q", "+1q", "0y", "+1y"
    number_of_analysts: Optional[float] = None
    avg: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    year_ago_eps: Optional[float] = None
    growth: Optional[float] = None


class RevenueEstimateRow(BaseModel):
    period: Optional[str] = None
    number_of_analysts: Optional[float] = None
    avg: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    year_ago_revenue: Optional[float] = None
    growth: Optional[float] = None


class EarningsHistoryRow(BaseModel):
    date: Optional[datetime.date] = None
    eps_estimate: Optional[float] = None
    eps_actual: Optional[float] = None
    eps_difference: Optional[float] = None
    surprise_percent: Optional[float] = None


class GrowthEstimateRow(BaseModel):
    period: Optional[str] = None                # e.g. "0q", "+1q", "0y", "+1y", "+5y", "-5y"
    stock: Optional[float] = None
    industry: Optional[float] = None
    sector: Optional[float] = None
    index: Optional[float] = None


class ValuationMeasures(BaseModel):
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    price_to_sales: Optional[float] = None
    price_to_book: Optional[float] = None
    enterprise_to_revenue: Optional[float] = None
    enterprise_to_ebitda: Optional[float] = None
    enterprise_value: Optional[float] = None
    peg_ratio: Optional[float] = None


class StockDetailedResponse(BaseModel):
    ticker: str
    info: Optional[dict] = None
    analyst_price_targets: Optional[dict] = None
    recommendations_summary: Optional[list[RecommendationPeriod]] = None
    earnings_estimate: Optional[list[EarningsEstimateRow]] = None
    revenue_estimate: Optional[list[RevenueEstimateRow]] = None


class StockCreateResponse(BaseModel):
    exist: bool
    ohlcv: OHLCVResponse
    details: StockDetailedResponse


class IndustryStocksResponse(BaseModel):
    industry: str
    ohlcv: List[OHLCVResponse]


class SectorStocksResponse(BaseModel):
    sector: str
    ohlcv: List[OHLCVResponse]


class IndustryMapResponse(BaseModel):
    industries: dict[str, list[str]]


class SectorMapResponse(BaseModel):
    sectors: dict[str, list[str]]


class EPSHistoryRow(BaseModel):
    date: Optional[datetime.date] = None
    surprise_percent: Optional[float] = None
    eps_growth: Optional[float] = None


class EPSHistoryResponse(BaseModel):
    ticker: str
    earnings_history: List[EPSHistoryRow]


class RevenueHistoryRow(BaseModel):
    date: Optional[datetime.date] = None
    revenue: Optional[float] = None
    percent_change: Optional[float] = None


class RevenueHistoryResponse(BaseModel):
    ticker: str
    revenue_history: List[RevenueHistoryRow]


class StockResponse(BaseModel):
    ticker: str
    ohlcv: List[OHLCV]
    info: Optional[dict] = None
    analyst_price_targets: Optional[dict] = None
    recommendations_summary: Optional[list[RecommendationPeriod]] = None
    earnings_estimate: Optional[list[EarningsEstimateRow]] = None
    revenue_estimate: Optional[list[RevenueEstimateRow]] = None
    earnings_history: Optional[list[EPSHistoryRow]] = None
    revenue_history: Optional[list[RevenueHistoryRow]] = None