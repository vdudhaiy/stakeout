"""Tests for StockService._parse_* methods — column renaming and schema coercion."""

import pandas as pd
import pytest
from unittest.mock import MagicMock

from market_lens_dashboard.services.stock_service import StockService


def _mock_ticker(ticker="AAPL", **attrs):
    m = MagicMock()
    m.ticker = ticker
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


# ── _parse_info ───────────────────────────────────────────────────────────────

def test_parse_info_returns_dict():
    service = StockService()
    t = _mock_ticker(info={"shortName": "Apple Inc.", "sector": "Technology"})
    assert service._parse_info(t) == {"shortName": "Apple Inc.", "sector": "Technology"}


def test_parse_info_empty_dict():
    service = StockService()
    t = _mock_ticker(info={})
    assert service._parse_info(t) == {}


# ── _parse_analyst_price_targets ─────────────────────────────────────────────

def test_parse_analyst_price_targets_returns_dict():
    service = StockService()
    targets = {"current": 180.0, "mean": 200.0, "low": 160.0, "high": 220.0, "median": 195.0}
    t = _mock_ticker(analyst_price_targets=targets)
    assert service._parse_analyst_price_targets(t) == targets


def test_parse_analyst_price_targets_none_returns_empty():
    service = StockService()
    t = _mock_ticker(analyst_price_targets=None)
    assert service._parse_analyst_price_targets(t) == {}


# ── _parse_recommendations_summary ───────────────────────────────────────────

def test_parse_recommendations_summary_renames_columns():
    service = StockService()
    df = pd.DataFrame([
        {"period": "0m", "strongBuy": 10, "buy": 5, "hold": 3, "sell": 1, "strongSell": 0},
    ])
    t = _mock_ticker(recommendations_summary=df)
    result = service._parse_recommendations_summary(t)
    assert len(result) == 1
    assert result[0]["strong_buy"] == 10
    assert result[0]["strong_sell"] == 0
    assert "strongBuy" not in result[0]
    assert "strongSell" not in result[0]


def test_parse_recommendations_summary_none_returns_empty_list():
    service = StockService()
    t = _mock_ticker(recommendations_summary=None)
    assert service._parse_recommendations_summary(t) == []


def test_parse_recommendations_summary_multiple_periods():
    service = StockService()
    df = pd.DataFrame([
        {"period": "0m", "strongBuy": 10, "buy": 5, "hold": 3, "sell": 1, "strongSell": 0},
        {"period": "-1m", "strongBuy": 8, "buy": 6, "hold": 4, "sell": 2, "strongSell": 1},
    ])
    t = _mock_ticker(recommendations_summary=df)
    result = service._parse_recommendations_summary(t)
    assert len(result) == 2


# ── _parse_earnings_estimate ─────────────────────────────────────────────────

def test_parse_earnings_estimate_renames_columns():
    service = StockService()
    df = pd.DataFrame(
        [{"avg": 1.5, "low": 1.2, "high": 1.8, "numberOfAnalysts": 20,
          "yearAgoEps": 1.1, "growth": 0.05}],
        index=["0q"],
    )
    t = _mock_ticker(earnings_estimate=df)
    result = service._parse_earnings_estimate(t)
    assert len(result) == 1
    assert "number_of_analysts" in result[0]
    assert "year_ago_eps" in result[0]
    assert "numberOfAnalysts" not in result[0]
    assert "yearAgoEps" not in result[0]
    # index becomes "period" column after reset_index
    assert result[0]["period"] == "0q"


def test_parse_earnings_estimate_none_returns_empty_list():
    service = StockService()
    t = _mock_ticker(earnings_estimate=None)
    assert service._parse_earnings_estimate(t) == []


# ── _parse_revenue_estimate ───────────────────────────────────────────────────

def test_parse_revenue_estimate_renames_columns():
    service = StockService()
    df = pd.DataFrame(
        [{"avg": 100e9, "low": 90e9, "high": 110e9, "numberOfAnalysts": 15,
          "yearAgoRevenue": 80e9, "growth": 0.25}],
        index=["0q"],
    )
    t = _mock_ticker(revenue_estimate=df)
    result = service._parse_revenue_estimate(t)
    assert len(result) == 1
    assert "number_of_analysts" in result[0]
    assert "year_ago_revenue" in result[0]
    assert "numberOfAnalysts" not in result[0]
    assert "yearAgoRevenue" not in result[0]
    assert result[0]["period"] == "0q"


def test_parse_revenue_estimate_none_returns_empty_list():
    service = StockService()
    t = _mock_ticker(revenue_estimate=None)
    assert service._parse_revenue_estimate(t) == []
