"""Tests for build_portfolio_xlsx — verifies the function produces a valid XLSX
file, and that its Transaction History sheet round-trips through the bulk
import feature (see import_service's module docstring)."""

import io

import pandas as pd
import pytest

from services.export_service import build_portfolio_xlsx
from services import import_service
from schemas.portfolio import (
    PortfolioResponse, StockHolding, StockPurchaseHistory,
)


def _empty_portfolio():
    return PortfolioResponse(
        portfolio_value=0.0, realized_gains=0.0, total_shares=0,
        total_invested=0.0, total_return=0.0, return_percentage=0.0,
        net_profit_loss=0.0, holdings=[],
    )


def _sample_holding(ticker="AAPL", company_name="Apple Inc."):
    buy = StockPurchaseHistory(
        id=1, sale=False, ticker=ticker, date="2024-01-01",
        shares=100, bought_at=150.0, sold_at=0.0, shares_remaining=80,
    )
    sell = StockPurchaseHistory(
        id=2, sale=True, ticker=ticker, date="2024-06-01",
        shares=20, bought_at=150.0, sold_at=185.0, shares_remaining=0,
    )
    return StockHolding(
        ticker=ticker, company_name=company_name, shares=80, sold_shares=20,
        average_cost=150.0, current_price=175.0, stock_value=14000.0,
        total_invested=12000.0, total_earned=700.0,
        profit_loss=2000.0, profit_loss_percentage=16.67,
        trade_history=[buy, sell],
    )


def _indian_holding(ticker="RELIANCE.NS", company_name="Reliance Industries"):
    buy = StockPurchaseHistory(
        id=1, sale=False, ticker=ticker, date="2024-02-01",
        shares=5, bought_at=2500.0, sold_at=0.0, shares_remaining=5,
    )
    return StockHolding(
        ticker=ticker, market="IN", currency="INR", company_name=company_name,
        shares=5, sold_shares=0, average_cost=2500.0, current_price=2600.0, stock_value=13000.0,
        total_invested=12500.0, total_earned=0.0,
        profit_loss=500.0, profit_loss_percentage=4.0,
        trade_history=[buy],
    )


def _portfolio_with_holdings(*holdings):
    total_value = sum(h.stock_value for h in holdings)
    total_invested = sum(h.total_invested for h in holdings)
    total_earned = sum(h.total_earned for h in holdings)
    total_shares = sum(h.shares for h in holdings)
    total_return = total_value - total_invested
    return_pct = (total_return / total_invested * 100) if total_invested else 0.0
    return PortfolioResponse(
        portfolio_value=total_value, realized_gains=total_earned,
        total_shares=total_shares, total_invested=total_invested,
        total_return=total_return, return_percentage=return_pct,
        net_profit_loss=total_return + total_earned,
        holdings=list(holdings),
    )


# ── output type ───────────────────────────────────────────────────────────────

def test_returns_bytes():
    assert isinstance(build_portfolio_xlsx(_empty_portfolio()), bytes)


def test_output_is_non_empty():
    assert len(build_portfolio_xlsx(_empty_portfolio())) > 0


# ── XLSX validity (ZIP magic bytes) ──────────────────────────────────────────

def test_empty_portfolio_is_valid_xlsx():
    result = build_portfolio_xlsx(_empty_portfolio())
    assert result[:2] == b"PK", "XLSX files are ZIP archives starting with PK magic bytes"


def test_portfolio_with_one_holding_is_valid_xlsx():
    p = _portfolio_with_holdings(_sample_holding())
    result = build_portfolio_xlsx(p)
    assert result[:2] == b"PK"
    assert len(result) > 2000   # should be a real file, not trivially small


def test_portfolio_with_multiple_holdings_is_valid_xlsx():
    msft = _sample_holding("MSFT", "Microsoft Corp.")
    p = _portfolio_with_holdings(_sample_holding(), msft)
    result = build_portfolio_xlsx(p)
    assert result[:2] == b"PK"


# ── edge cases ────────────────────────────────────────────────────────────────

def test_holding_with_no_transactions():
    holding = StockHolding(
        ticker="GOOGL", company_name="Alphabet", shares=10, sold_shares=0,
        average_cost=100.0, current_price=120.0, stock_value=1200.0,
        total_invested=1000.0, total_earned=0.0,
        profit_loss=200.0, profit_loss_percentage=20.0,
        trade_history=[],
    )
    p = _portfolio_with_holdings(holding)
    result = build_portfolio_xlsx(p)
    assert result[:2] == b"PK"


def test_negative_pnl_holding():
    buy = StockPurchaseHistory(
        id=1, sale=False, ticker="XYZ", date="2024-01-01",
        shares=100, bought_at=50.0, sold_at=0.0, shares_remaining=100,
    )
    losing = StockHolding(
        ticker="XYZ", company_name="XYZ Corp.", shares=100, sold_shares=0,
        average_cost=50.0, current_price=30.0, stock_value=3000.0,
        total_invested=5000.0, total_earned=0.0,
        profit_loss=-2000.0, profit_loss_percentage=-40.0,
        trade_history=[buy],
    )
    p = _portfolio_with_holdings(losing)
    result = build_portfolio_xlsx(p)
    assert result[:2] == b"PK"


# ── Transaction History matches the import format ─────────────────────────────
#
# The sheet's first six columns are meant to be byte-for-byte what
# import_service expects (see both modules' docstrings), so an exported file
# can be re-uploaded through Import as-is. _read_table is exercised directly
# here rather than re-implementing header/value assertions by hand — it's
# the same code path a real re-upload goes through.

def _read_transaction_sheet(xlsx_bytes: bytes):
    df, had_header = import_service._read_table("portfolio-export.xlsx", xlsx_bytes)
    assert had_header is True
    return df


def test_transaction_sheet_headers_match_import_format():
    p = _portfolio_with_holdings(_sample_holding())
    df = _read_transaction_sheet(build_portfolio_xlsx(p))
    assert list(df.columns)[:6] == ["Market", "Stock", "Date", "Number", "Buy/Sell", "Price"]


def test_transaction_sheet_buy_row_matches_source_transaction():
    p = _portfolio_with_holdings(_sample_holding())
    df = _read_transaction_sheet(build_portfolio_xlsx(p))
    buy_row = df[df["Buy/Sell"] == "BUY"].iloc[0]
    assert buy_row["Market"] == "US"
    assert buy_row["Stock"] == "AAPL"
    assert buy_row["Date"] == "2024-01-01"
    assert buy_row["Number"] == "100"
    assert float(buy_row["Price"]) == pytest.approx(150.0)


def test_transaction_sheet_sell_row_matches_source_transaction():
    p = _portfolio_with_holdings(_sample_holding())
    df = _read_transaction_sheet(build_portfolio_xlsx(p))
    sell_row = df[df["Buy/Sell"] == "SELL"].iloc[0]
    assert sell_row["Number"] == "20"
    assert float(sell_row["Price"]) == pytest.approx(185.0)   # sold_at, not bought_at


def test_transaction_sheet_indian_holding_uses_bare_ticker_and_market_in():
    p = _portfolio_with_holdings(_indian_holding())
    df = _read_transaction_sheet(build_portfolio_xlsx(p))
    row = df.iloc[0]
    assert row["Market"] == "IN"
    assert row["Stock"] == "RELIANCE"   # suffix stripped — market column already says IN


def test_transaction_sheet_round_trips_through_preview_parsing():
    """The full pipeline a real re-upload goes through: read the exported
    bytes, parse every row, and confirm each one is valid with no errors —
    the actual point of matching the import format."""
    p = _portfolio_with_holdings(_sample_holding(), _indian_holding())
    xlsx_bytes = build_portfolio_xlsx(p)

    df, had_header = import_service._read_table("portfolio-export.xlsx", xlsx_bytes)
    rows = import_service._parse_rows(df, had_header)

    assert len(rows) == 3   # 2 AAPL transactions + 1 RELIANCE buy
    assert all(r["valid"] for r in rows), [r["error"] for r in rows if not r["valid"]]
    tickers = {r["ticker"] for r in rows}
    assert tickers == {"AAPL", "RELIANCE.NS"}   # bare "RELIANCE" + market "IN" resolves back to the .NS ticker


def test_transaction_sheet_picked_over_portfolio_summary_sheet_on_reimport():
    """Guards the actual failure mode this format-matching exists to avoid:
    without sheet-aware reading, re-uploading an export would silently parse
    the unrelated holdings-summary sheet (listed first in the workbook)
    instead of the transaction log."""
    p = _portfolio_with_holdings(_sample_holding())
    xlsx_bytes = build_portfolio_xlsx(p)

    df, had_header = import_service._read_table("portfolio-export.xlsx", xlsx_bytes)
    assert had_header is True
    assert "Buy/Sell" in df.columns   # only the Transaction History sheet has this


def test_empty_portfolio_transaction_sheet_has_no_data_rows():
    xlsx_bytes = build_portfolio_xlsx(_empty_portfolio())
    # No transactions at all — reading straight back would find only the
    # header-shaped Portfolio sheet (also empty), which is a legitimate
    # "nothing to import" case, not an error.
    sheets = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=None, engine="openpyxl")
    txn_df = sheets["Transaction History"]
    assert len(txn_df) == 0
