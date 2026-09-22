"""Tests for import_service — bulk portfolio import from CSV/XLSX, with
duplicate detection across a two-phase preview/apply flow.

_parse_rows / _parse_date / _flag_duplicates are tested directly (pure or
DB-read-only, no writes). preview_import / apply_import are tested against
the real in-memory DB via db_session, same pattern as
test_portfolio_service.py: yfinance-touching calls inside
add_stock_purchases_bulk / sell_stock_shares_bulk (_validate_and_fetch_name,
the background asyncio.create_task calls) are mocked so these stay offline.
"""

import datetime
import io
from decimal import Decimal
from unittest.mock import patch, AsyncMock

import pandas as pd
import pytest

from models.portfolio import Holding, Transaction
from schemas.portfolio import ImportApplyRow
from services import import_service

USER_ID = "test-user"
TODAY = datetime.date.today().isoformat()
FUTURE = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()


def _csv(rows: list[list[str]]) -> bytes:
    return "\n".join(",".join(row) for row in rows).encode()


def _xlsx(rows: list[list[str]]) -> bytes:
    df = pd.DataFrame(rows[1:], columns=rows[0])
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def _xlsx_no_header(rows: list[list[str]]) -> bytes:
    """Like _xlsx, but `rows` are all data — no header row written."""
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, header=False, engine="openpyxl")
    return buf.getvalue()


def _xlsx_multi_sheet(sheets: dict[str, list[list[str]]]) -> bytes:
    """sheets maps sheet name -> rows (first row is that sheet's header)."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, rows in sheets.items():
            pd.DataFrame(rows[1:], columns=rows[0]).to_excel(writer, sheet_name=name, index=False)
    return buf.getvalue()


_HEADER = ["market", "stock", "date", "number", "buy/sell", "price"]


# ── _read_table ──────────────────────────────────────────────────────────────

def test_read_table_unsupported_extension_raises():
    with pytest.raises(ValueError, match="Unsupported file type"):
        import_service._read_table("portfolio.txt", b"whatever")


def test_read_table_empty_csv_raises():
    with pytest.raises(ValueError, match="Could not read"):
        import_service._read_table("portfolio.csv", b"")


def test_read_table_reads_xlsx():
    content = _xlsx([_HEADER, ["US", "AAPL", TODAY, "10", "buy", "150.00"]])
    df, had_header = import_service._read_table("portfolio.xlsx", content)
    assert had_header is True
    assert list(df.columns) == _HEADER
    assert df.iloc[0]["stock"] == "AAPL"


def test_read_table_picks_the_transaction_sheet_out_of_a_multi_sheet_workbook():
    # Mirrors export_service's own two-sheet layout: an unrelated holdings
    # summary sheet listed first, transaction data listed second.
    content = _xlsx_multi_sheet({
        "Portfolio": [
            ["Ticker", "Company", "Shares", "Avg Cost", "Current Price"],
            ["AAPL", "Apple Inc.", "10", "150.00", "175.00"],
        ],
        "Transaction History": [
            _HEADER,
            ["US", "AAPL", TODAY, "10", "buy", "150.00"],
        ],
    })
    df, had_header = import_service._read_table("export.xlsx", content)
    assert had_header is True
    assert list(df.columns) == _HEADER
    assert df.iloc[0]["stock"] == "AAPL"


# ── _read_table: optional header ──────────────────────────────────────────────

def test_read_table_detects_header_row():
    content = _csv([_HEADER, ["US", "AAPL", "2024-01-16", "10", "buy", "150.00"]])
    df, had_header = import_service._read_table("portfolio.csv", content)
    assert had_header is True
    assert len(df) == 1
    assert df.iloc[0]["stock"] == "AAPL"


def test_read_table_detects_missing_header_and_uses_positional_columns():
    content = _csv([["US", "AAPL", "2024-01-16", "10", "buy", "150.00"]])  # no header row
    df, had_header = import_service._read_table("portfolio.csv", content)
    assert had_header is False
    assert list(df.columns) == import_service._DEFAULT_COLUMN_ORDER
    assert len(df) == 1  # the only row is data, not consumed as a header
    assert df.iloc[0]["ticker"] == "AAPL"


def test_read_table_header_aliases_still_detected():
    content = _csv([
        ["Market (US/IND)", "Stock (Ticker)", "Date", "Number", "Buy/Sell", "Price"],
        ["US", "AAPL", "2024-01-16", "10", "buy", "150.00"],
    ])
    _df, had_header = import_service._read_table("portfolio.csv", content)
    assert had_header is True


def test_read_table_headerless_xlsx():
    content = _xlsx_no_header([["US", "AAPL", "2024-01-16", "10", "buy", "150.00"]])
    df, had_header = import_service._read_table("portfolio.xlsx", content)
    assert had_header is False
    assert df.iloc[0]["ticker"] == "AAPL"


# ── _parse_date ──────────────────────────────────────────────────────────────

def test_parse_date_accepts_iso_format():
    iso, error = import_service._parse_date("2024-01-16")
    assert error is None
    assert iso == "2024-01-16"


def test_parse_date_accepts_us_slash_format():
    iso, error = import_service._parse_date("01/16/2024")
    assert error is None
    assert iso == "2024-01-16"


def test_parse_date_rejects_future_date():
    iso, error = import_service._parse_date(FUTURE)
    assert iso is None
    assert "future" in error


def test_parse_date_rejects_garbage():
    iso, error = import_service._parse_date("not a date")
    assert iso is None
    assert "invalid date" in error


def test_parse_date_rejects_empty():
    iso, error = import_service._parse_date("")
    assert iso is None
    assert "missing date" in error


# ── _parse_rows ──────────────────────────────────────────────────────────────

def test_parse_rows_missing_required_column_raises():
    df = pd.DataFrame([["US", "AAPL"]], columns=["market", "stock"])
    with pytest.raises(ValueError, match="Missing required column"):
        import_service._parse_rows(df, had_header=True)


# ── broker exports land on trading sessions ──────────────────────────────
#
# Statement and settlement dates routinely fall on weekends. A date with no
# price bar behind it breaks the performance chart silently, so the import
# moves it and says so rather than importing it as given.

def _one_row(day: str, market: str = "US", ticker: str = "AAPL") -> dict:
    df = pd.read_csv(io.BytesIO(_csv([
        _HEADER, [market, ticker, day, "10", "buy", "150.00"],
    ])), dtype=str, keep_default_na=False)
    return import_service._parse_rows(df, had_header=True)[0]


def test_a_weekend_row_is_moved_to_the_next_session():
    r = _one_row("2024-01-06")  # a Saturday
    assert r["date"] == "2024-01-08"
    assert r["original_date"] == "2024-01-06"
    assert r["valid"] is True  # moved, not rejected


def test_a_holiday_row_is_moved_to_the_next_session():
    r = _one_row("2024-01-15")  # Martin Luther King Jr. Day
    assert r["date"] == "2024-01-16"
    assert r["original_date"] == "2024-01-15"


def test_a_row_already_on_a_session_is_not_flagged_as_moved():
    r = _one_row("2024-01-16")
    assert r["date"] == "2024-01-16"
    assert r["original_date"] is None


def test_an_indian_row_is_moved_on_the_indian_calendar():
    r = _one_row("2026-01-26", market="IND", ticker="RELIANCE")  # Republic Day
    assert r["date"] == "2026-01-27"
    assert r["original_date"] == "2026-01-26"


def test_an_unparseable_date_is_still_an_error_not_a_move():
    r = _one_row("not-a-date")
    assert r["valid"] is False
    assert r["original_date"] is None


async def test_the_preview_reports_the_move_to_the_user(db_session, _mock_yfinance):
    content = _csv([_HEADER, ["US", "AAPL", "2024-01-06", "10", "buy", "150.00"]])
    result = await import_service.preview_import(db_session, USER_ID, "portfolio.csv", content)

    assert result.rows[0].date == "2024-01-08"
    assert result.rows[0].original_date == "2024-01-06"


def test_parse_rows_accepts_header_aliases_and_hint_text():
    df = pd.read_csv(io.BytesIO(_csv([
        ["Market (US/IND)", "Stock (Ticker)", "Date", "Number", "Buy/Sell", "Price"],
        ["US", "AAPL", "2024-01-16", "10", "buy", "150.00"],
    ])), dtype=str, keep_default_na=False)
    rows = import_service._parse_rows(df, had_header=True)
    assert len(rows) == 1
    r = rows[0]
    assert r["valid"] is True
    assert r["row_num"] == 2
    assert r["market_label"] == "US"
    assert r["ticker"] == "AAPL"
    assert r["date"] == "2024-01-16"
    assert r["action"] == "buy"
    assert r["shares"] == 10
    assert r["price"] == Decimal("150.00")
    assert r["duplicate"] is False


@pytest.mark.parametrize("market_cell,expected_ticker", [
    ("US", "AAPL"),
    ("USA", "AAPL"),
    ("IND", "AAPL.NS"),
    ("in", "AAPL.NS"),
    ("India", "AAPL.NS"),
])
def test_parse_rows_market_aliases(market_cell, expected_ticker):
    df = pd.DataFrame([[market_cell, "AAPL", TODAY, "10", "buy", "150"]], columns=_HEADER)
    rows = import_service._parse_rows(df, had_header=True)
    assert rows[0]["valid"] is True
    assert rows[0]["ticker"] == expected_ticker


def test_parse_rows_indian_ticker_with_explicit_suffix_is_unchanged():
    df = pd.DataFrame([["IND", "TCS.BO", TODAY, "10", "buy", "150"]], columns=_HEADER)
    rows = import_service._parse_rows(df, had_header=True)
    assert rows[0]["ticker"] == "TCS.BO"  # not "TCS.BO.NS"


@pytest.mark.parametrize("action_cell", ["buy", "Buy", "BUY", "b", "B"])
def test_parse_rows_buy_aliases(action_cell):
    df = pd.DataFrame([["US", "AAPL", TODAY, "10", action_cell, "150"]], columns=_HEADER)
    rows = import_service._parse_rows(df, had_header=True)
    assert rows[0]["valid"] is True
    assert rows[0]["action"] == "buy"


@pytest.mark.parametrize("action_cell", ["sell", "Sell", "SELL", "s", "S"])
def test_parse_rows_sell_aliases(action_cell):
    df = pd.DataFrame([["US", "AAPL", TODAY, "10", action_cell, "150"]], columns=_HEADER)
    rows = import_service._parse_rows(df, had_header=True)
    assert rows[0]["valid"] is True
    assert rows[0]["action"] == "sell"


def test_parse_rows_accepts_float_looking_whole_share_counts():
    df = pd.DataFrame([["US", "AAPL", TODAY, "100.0", "buy", "150"]], columns=_HEADER)
    rows = import_service._parse_rows(df, had_header=True)
    assert rows[0]["valid"] is True
    assert rows[0]["shares"] == 100


def test_parse_rows_skips_fully_blank_rows():
    df = pd.DataFrame([
        ["US", "AAPL", TODAY, "10", "buy", "150"],
        ["", "", "", "", "", ""],
    ], columns=_HEADER)
    rows = import_service._parse_rows(df, had_header=True)
    assert len(rows) == 1


def test_parse_rows_flags_bad_market_without_raising():
    df = pd.DataFrame([["UK", "AAPL", TODAY, "10", "buy", "150"]], columns=_HEADER)
    rows = import_service._parse_rows(df, had_header=True)
    assert rows[0]["valid"] is False
    assert rows[0]["row_num"] == 2
    assert "market" in rows[0]["error"]


def test_parse_rows_flags_bad_action_without_raising():
    df = pd.DataFrame([["US", "AAPL", TODAY, "10", "hold", "150"]], columns=_HEADER)
    rows = import_service._parse_rows(df, had_header=True)
    assert rows[0]["valid"] is False
    assert "buy/sell" in rows[0]["error"]


def test_parse_rows_flags_future_date():
    df = pd.DataFrame([["US", "AAPL", FUTURE, "10", "buy", "150"]], columns=_HEADER)
    rows = import_service._parse_rows(df, had_header=True)
    assert rows[0]["valid"] is False
    assert "future" in rows[0]["error"]


def test_parse_rows_flags_fractional_and_nonpositive_shares():
    df = pd.DataFrame([
        ["US", "AAPL", TODAY, "10.5", "buy", "150"],
        ["US", "MSFT", TODAY, "0", "buy", "150"],
        ["US", "NVDA", TODAY, "-5", "buy", "150"],
    ], columns=_HEADER)
    rows = import_service._parse_rows(df, had_header=True)
    assert all(r["valid"] is False for r in rows)
    assert all("share count" in r["error"] for r in rows)


def test_parse_rows_flags_bad_price():
    df = pd.DataFrame([["US", "AAPL", TODAY, "10", "buy", "n/a"]], columns=_HEADER)
    rows = import_service._parse_rows(df, had_header=True)
    assert rows[0]["valid"] is False
    assert "price" in rows[0]["error"]


def test_parse_rows_multiple_errors_on_one_row_are_combined():
    df = pd.DataFrame([["UK", "AAPL", "garbage", "-5", "hold", "n/a"]], columns=_HEADER)
    rows = import_service._parse_rows(df, had_header=True)
    assert rows[0]["error"].count(";") == 4  # 5 problems joined by "; "


def test_parse_rows_row_numbering_with_header_starts_at_two():
    df = pd.DataFrame([["US", "AAPL", TODAY, "10", "buy", "150"]], columns=_HEADER)
    rows = import_service._parse_rows(df, had_header=True)
    assert rows[0]["row_num"] == 2  # header occupies row 1


def test_parse_rows_row_numbering_without_header_starts_at_one():
    df = pd.DataFrame(
        [["US", "AAPL", TODAY, "10", "buy", "150"]],
        columns=import_service._DEFAULT_COLUMN_ORDER,
    )
    rows = import_service._parse_rows(df, had_header=False)
    assert rows[0]["row_num"] == 1  # no header row to occupy row 1


def test_parse_rows_missing_columns_without_header_gives_positional_hint():
    df = pd.DataFrame([["US", "AAPL"]], columns=["market", "ticker"])
    with pytest.raises(ValueError, match="no header row needs exactly six columns"):
        import_service._parse_rows(df, had_header=False)


# ── preview_import / _flag_duplicates (integration) ───────────────────────────

@pytest.fixture
def _mock_yfinance():
    with patch("services.portfolio_service._validate_and_fetch_name",
               new_callable=AsyncMock, return_value="Mock Co."):
        with patch("services.portfolio_service._current_price",
                   new_callable=AsyncMock, return_value=Decimal("100.0")):
            with patch("services.portfolio_service.asyncio.create_task"):
                yield


async def test_preview_flags_duplicate_within_same_file(db_session, _mock_yfinance):
    content = _csv([
        _HEADER,
        ["US", "AAPL", "2024-01-16", "10", "buy", "150.00"],
        ["US", "AAPL", "2024-01-16", "10", "buy", "150.00"],  # exact duplicate of row 2
    ])
    result = await import_service.preview_import(db_session, USER_ID, "portfolio.csv", content)

    assert result.rows[0].duplicate is False
    assert result.rows[1].duplicate is True
    assert "row 2" in result.rows[1].duplicate_reason


async def test_preview_does_not_flag_rows_that_differ_in_one_field(db_session, _mock_yfinance):
    content = _csv([
        _HEADER,
        ["US", "AAPL", "2024-01-16", "10", "buy", "150.00"],
        ["US", "AAPL", "2024-01-17", "10", "buy", "150.00"],  # different date
        ["US", "AAPL", "2024-01-16", "11", "buy", "150.00"],  # different shares
        ["US", "AAPL", "2024-01-16", "10", "buy", "150.01"],  # different price
        ["US", "AAPL", "2024-01-16", "10", "sell", "150.00"],  # different action
    ])
    result = await import_service.preview_import(db_session, USER_ID, "portfolio.csv", content)
    assert all(r.duplicate is False for r in result.rows)


async def test_preview_flags_duplicate_against_existing_transaction(db_session, _mock_yfinance):
    # First upload lands a real transaction...
    first = _csv([_HEADER, ["US", "AAPL", "2024-01-16", "10", "buy", "150.00"]])
    preview1 = await import_service.preview_import(db_session, USER_ID, "portfolio.csv", first)
    await import_service.apply_import(db_session, USER_ID, [
        ImportApplyRow(row=r.row, market=r.market, ticker=r.ticker, date=r.date,
                       action=r.action, shares=r.shares, price=r.price, include=True)
        for r in preview1.rows
    ])

    # ...a second upload with the exact same row should be flagged as a duplicate.
    second = _csv([_HEADER, ["US", "AAPL", "2024-01-16", "10", "buy", "150.00"]])
    preview2 = await import_service.preview_import(db_session, USER_ID, "portfolio.csv", second)
    assert preview2.rows[0].duplicate is True
    assert "already have" in preview2.rows[0].duplicate_reason


async def test_a_legacy_off_session_transaction_is_still_recognised_as_a_duplicate(
    db_session, pid, _mock_yfinance,
):
    """Transactions written before dates were snapped sit on the date the file
    gave. Comparing only the snapped date would miss them, and re-importing
    the same broker export would record every weekend trade twice."""
    holding = Holding(
        user_id=USER_ID, portfolio_id=pid, ticker="AAPL", company_name="Apple Inc.",
        market="US", shares=10, sold_shares=0, average_cost=Decimal("150.0"),
    )
    db_session.add(holding)
    await db_session.flush()
    db_session.add(Transaction(
        holding_id=holding.id, sale=False, date="2024-01-06",  # a Saturday, stored as-is
        shares=10, bought_at=Decimal("150.00"), shares_remaining=10,
    ))
    await db_session.commit()

    content = _csv([_HEADER, ["US", "AAPL", "2024-01-06", "10", "buy", "150.00"]])
    preview = await import_service.preview_import(db_session, USER_ID, "portfolio.csv", content)

    row = preview.rows[0]
    assert row.date == "2024-01-08"        # still snapped for the write
    assert row.original_date == "2024-01-06"
    assert row.duplicate is True
    assert "2024-01-06" in row.duplicate_reason


async def test_a_snapped_transaction_is_recognised_on_re_import(db_session, pid, _mock_yfinance):
    """The other direction: once a trade is stored on its snapped date, the
    same file must still match it."""
    holding = Holding(
        user_id=USER_ID, portfolio_id=pid, ticker="AAPL", company_name="Apple Inc.",
        market="US", shares=10, sold_shares=0, average_cost=Decimal("150.0"),
    )
    db_session.add(holding)
    await db_session.flush()
    db_session.add(Transaction(
        holding_id=holding.id, sale=False, date="2024-01-08",  # already snapped
        shares=10, bought_at=Decimal("150.00"), shares_remaining=10,
    ))
    await db_session.commit()

    content = _csv([_HEADER, ["US", "AAPL", "2024-01-06", "10", "buy", "150.00"]])
    preview = await import_service.preview_import(db_session, USER_ID, "portfolio.csv", content)

    assert preview.rows[0].duplicate is True


async def test_two_rows_on_different_closed_days_are_not_each_others_duplicate(
    db_session, _mock_yfinance,
):
    """A Saturday and a Sunday row snap to the same session but are two
    trades, so the in-file check compares what the file actually said."""
    content = _csv([
        _HEADER,
        ["US", "AAPL", "2024-01-06", "10", "buy", "150.00"],  # Saturday
        ["US", "AAPL", "2024-01-07", "10", "buy", "150.00"],  # Sunday
    ])
    preview = await import_service.preview_import(db_session, USER_ID, "portfolio.csv", content)

    assert [r.date for r in preview.rows] == ["2024-01-08", "2024-01-08"]
    assert all(r.duplicate is False for r in preview.rows)


async def test_preview_never_flags_invalid_rows_as_duplicate(db_session, _mock_yfinance):
    content = _csv([
        _HEADER,
        ["UK", "AAPL", "2024-01-16", "10", "buy", "150.00"],
        ["UK", "AAPL", "2024-01-16", "10", "buy", "150.00"],
    ])
    result = await import_service.preview_import(db_session, USER_ID, "portfolio.csv", content)
    assert all(r.valid is False for r in result.rows)
    assert all(r.duplicate is False for r in result.rows)


# ── apply_import (integration) ─────────────────────────────────────────────

async def test_apply_import_uses_the_given_date_not_today(db_session, _mock_yfinance, pid):
    rows = [ImportApplyRow(row=2, market="US", ticker="AAPL", date="2024-01-16",
                            action="buy", shares=10, price=Decimal("150.00"), include=True)]
    result = await import_service.apply_import(db_session, USER_ID, rows)

    assert result.imported_rows == 1
    holding = await import_service.portfolio_service.get_stock_holding(db_session, pid, "AAPL", price=Decimal("100"))
    assert holding.trade_history[0].date == "2024-01-16"


async def test_apply_import_skips_rows_with_include_false(db_session, _mock_yfinance, pid):
    rows = [
        ImportApplyRow(row=2, market="US", ticker="AAPL", date=TODAY,
                       action="buy", shares=10, price=Decimal("150.00"), include=True),
        ImportApplyRow(row=3, market="US", ticker="AAPL", date=TODAY,
                       action="buy", shares=5, price=Decimal("150.00"), include=False),
    ]
    result = await import_service.apply_import(db_session, USER_ID, rows)

    assert result.imported_rows == 1
    assert result.skipped_rows == 1
    assert result.failed_rows == 0
    skipped = next(r for r in result.rows if r.row == 3)
    assert skipped.status == "skipped"

    holding = await import_service.portfolio_service.get_stock_holding(db_session, pid, "AAPL", price=Decimal("100"))
    assert holding.shares == 10  # only the included row landed


async def test_apply_import_buy_then_sell_same_ticker(db_session, _mock_yfinance, pid):
    rows = [
        ImportApplyRow(row=2, market="US", ticker="AAPL", date="2024-01-01",
                       action="buy", shares=100, price=Decimal("150.00"), include=True),
        ImportApplyRow(row=3, market="US", ticker="AAPL", date="2024-02-01",
                       action="sell", shares=40, price=Decimal("200.00"), include=True),
    ]
    result = await import_service.apply_import(db_session, USER_ID, rows)

    assert result.imported_rows == 2
    holding = await import_service.portfolio_service.get_stock_holding(db_session, pid, "AAPL", price=Decimal("100"))
    assert holding.shares == 60
    assert holding.sold_shares == 40


async def test_apply_import_sell_without_existing_holding_fails_that_row_only(db_session, _mock_yfinance):
    rows = [
        ImportApplyRow(row=2, market="US", ticker="AAPL", date=TODAY,
                       action="buy", shares=10, price=Decimal("150.00"), include=True),
        ImportApplyRow(row=3, market="US", ticker="MSFT", date=TODAY,
                       action="sell", shares=5, price=Decimal("300.00"), include=True),
    ]
    result = await import_service.apply_import(db_session, USER_ID, rows)

    assert result.imported_rows == 1
    assert result.failed_rows == 1
    failed = next(r for r in result.rows if r.status == "failed")
    assert failed.ticker == "MSFT"
    assert "No holding found" in failed.error


async def test_apply_import_from_xlsx_preview(db_session, _mock_yfinance):
    content = _xlsx([_HEADER, ["US", "AAPL", TODAY, "10", "buy", "150.00"]])
    preview = await import_service.preview_import(db_session, USER_ID, "portfolio.xlsx", content)
    assert len(preview.rows) == 1
    assert preview.rows[0].valid is True

    result = await import_service.apply_import(db_session, USER_ID, [
        ImportApplyRow(row=r.row, market=r.market, ticker=r.ticker, date=r.date,
                       action=r.action, shares=r.shares, price=r.price, include=True)
        for r in preview.rows
    ])
    assert result.imported_rows == 1


async def test_preview_and_apply_work_with_no_header_row(db_session, _mock_yfinance):
    # Bare data, no header line at all — six columns in the fixed
    # market/stock/date/number/buy-sell/price order.
    content = _csv([
        ["US", "AAPL", "2024-01-16", "10", "buy", "150.00"],
        ["IND", "RELIANCE", "2024-02-01", "5", "buy", "2500.00"],
    ])
    preview = await import_service.preview_import(db_session, USER_ID, "portfolio.csv", content)

    assert len(preview.rows) == 2
    assert [r.row for r in preview.rows] == [1, 2]  # numbering starts at 1 — no header to occupy row 1
    assert preview.rows[0].ticker == "AAPL"
    assert preview.rows[1].ticker == "RELIANCE.NS"
    assert all(r.valid for r in preview.rows)

    result = await import_service.apply_import(db_session, USER_ID, [
        ImportApplyRow(row=r.row, market=r.market, ticker=r.ticker, date=r.date,
                       action=r.action, shares=r.shares, price=r.price, include=True)
        for r in preview.rows
    ])
    assert result.imported_rows == 2


# ── portfolio column ─────────────────────────────────────────────────────────
#
# Unlike every other kind of row error, a bad portfolio name blocks the whole
# import: a transaction that can't be filed in the portfolio the user named
# must not be quietly filed somewhere else. See import_service's docstring.

_HEADER_P = ["market", "stock", "date", "number", "buy/sell", "price", "portfolio"]


async def _make_portfolio(session, market: str, name: str):
    from services import portfolio_admin_service
    return await portfolio_admin_service.create(session, USER_ID, market, name)


async def test_no_portfolio_column_sends_everything_to_the_default(db_session, _mock_yfinance, pid):
    content = _csv([_HEADER, ["US", "AAPL", "2024-01-16", "10", "buy", "150.00"]])
    preview = await import_service.preview_import(db_session, USER_ID, "p.csv", content)

    assert preview.blocking_errors == []
    assert preview.rows[0].portfolio is None
    assert preview.rows[0].portfolio_id == pid


async def test_named_portfolio_routes_the_row_there(db_session, _mock_yfinance):
    zerodha = await _make_portfolio(db_session, "US", "Zerodha")
    content = _csv([_HEADER_P, ["US", "AAPL", "2024-01-16", "10", "buy", "150.00", "Zerodha"]])

    preview = await import_service.preview_import(db_session, USER_ID, "p.csv", content)
    assert preview.blocking_errors == []
    assert preview.rows[0].portfolio_id == zerodha.id

    result = await import_service.apply_import(db_session, USER_ID, [
        ImportApplyRow(row=r.row, market=r.market, ticker=r.ticker, date=r.date,
                       action=r.action, shares=r.shares, price=r.price,
                       portfolio=r.portfolio, include=True)
        for r in preview.rows
    ])
    assert result.imported_rows == 1
    holding = await import_service.portfolio_service.get_stock_holding(
        db_session, zerodha.id, "AAPL", price=Decimal("100"),
    )
    assert holding.shares == 10


async def test_portfolio_name_matching_ignores_case_and_padding(db_session, _mock_yfinance):
    zerodha = await _make_portfolio(db_session, "US", "Zerodha")
    content = _csv([_HEADER_P, ["US", "AAPL", "2024-01-16", "10", "buy", "150.00", "  zERODHA "]])

    preview = await import_service.preview_import(db_session, USER_ID, "p.csv", content)
    assert preview.blocking_errors == []
    assert preview.rows[0].portfolio_id == zerodha.id


async def test_unknown_portfolio_blocks_the_import(db_session, _mock_yfinance, pid):
    content = _csv([
        _HEADER_P,
        ["US", "AAPL", "2024-01-16", "10", "buy", "150.00", "Nope"],
        ["US", "MSFT", "2024-01-16", "5", "buy", "300.00", "Nope"],
    ])
    preview = await import_service.preview_import(db_session, USER_ID, "p.csv", content)

    assert [e.row for e in preview.blocking_errors] == [2, 3]
    assert "No portfolio named 'Nope'" in preview.blocking_errors[0].message


async def test_blank_portfolio_cell_among_named_rows_blocks_the_import(db_session, _mock_yfinance):
    await _make_portfolio(db_session, "US", "Zerodha")
    content = _csv([
        _HEADER_P,
        ["US", "AAPL", "2024-01-16", "10", "buy", "150.00", "Zerodha"],
        ["US", "MSFT", "2024-01-16", "5", "buy", "300.00", ""],
    ])
    preview = await import_service.preview_import(db_session, USER_ID, "p.csv", content)

    assert [e.row for e in preview.blocking_errors] == [3]
    assert "blank" in preview.blocking_errors[0].message


async def test_portfolio_from_the_other_market_says_so(db_session, _mock_yfinance):
    await _make_portfolio(db_session, "US", "Zerodha")
    content = _csv([_HEADER_P, ["IND", "RELIANCE", "2024-01-16", "5", "buy", "2500.00", "Zerodha"]])

    preview = await import_service.preview_import(db_session, USER_ID, "p.csv", content)
    assert len(preview.blocking_errors) == 1
    assert "is a US portfolio" in preview.blocking_errors[0].message


async def test_apply_rejects_a_portfolio_name_that_does_not_resolve(db_session, _mock_yfinance, pid):
    """The client's echo is never trusted — apply re-resolves names itself."""
    rows = [
        ImportApplyRow(row=2, market="US", ticker="AAPL", date=TODAY, action="buy",
                       shares=10, price=Decimal("150.00"), portfolio="Ghost", include=True),
    ]
    with pytest.raises(ValueError, match="No portfolio named 'Ghost'"):
        await import_service.apply_import(db_session, USER_ID, rows)


async def test_duplicate_detection_is_per_portfolio(db_session, _mock_yfinance, pid):
    """The same transaction in a different portfolio is not a duplicate."""
    zerodha = await _make_portfolio(db_session, "US", "Zerodha")
    await import_service.apply_import(db_session, USER_ID, [
        ImportApplyRow(row=2, market="US", ticker="AAPL", date="2024-01-16", action="buy",
                       shares=10, price=Decimal("150.00"), include=True),
    ])

    content = _csv([
        _HEADER_P,
        ["US", "AAPL", "2024-01-16", "10", "buy", "150.00", "main"],
        ["US", "AAPL", "2024-01-16", "10", "buy", "150.00", "Zerodha"],
    ])
    preview = await import_service.preview_import(db_session, USER_ID, "p.csv", content)

    assert preview.blocking_errors == []
    by_portfolio = {r.portfolio_id: r.duplicate for r in preview.rows}
    assert by_portfolio[pid] is True          # already in main
    assert by_portfolio[zerodha.id] is False  # a different portfolio entirely
