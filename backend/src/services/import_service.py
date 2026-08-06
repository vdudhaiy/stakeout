"""Bulk portfolio import from a CSV or Excel (.xlsx) file.

Expected columns (case-insensitive, any order, a few common synonyms
accepted — see _COLUMN_ALIASES):
  market    "US" | "IND" (also accepts "IN", "INDIA")
  stock     ticker symbol — bare ("RELIANCE") or already suffixed ("RELIANCE.NS")
  date      transaction date (any format pandas can parse; not in the future)
  number    share count (whole number)
  buy/sell  "buy" | "sell"
  price     price paid/received per share

The header row is optional. _read_table looks at the first row: if it reads
like column labels (see _looks_like_header), it's consumed as a header and
columns are matched by name (any order). Otherwise every row — including
the first — is treated as data, and columns are assigned by position in
_DEFAULT_COLUMN_ORDER, so a header-less file must list exactly those six
columns in that order.

For .xlsx specifically, a file can have multiple sheets — export_service's
own portfolio export does (a holdings summary before the transaction log) —
so _read_xlsx picks whichever sheet's first row best matches these column
headers, rather than assuming the data is on the first sheet. This is what
makes an exported file re-importable as-is: download it from Export, upload
the same file back through Import, and every transaction lands again.

An "IND" row with a bare ticker defaults to NSE (".NS") — the same default
used everywhere else a bare Indian ticker shows up, since NSE vs BSE isn't a
choice the user makes anywhere in the app; a ticker that already carries a
.NS/.BO suffix is left as-is (apply_exchange is idempotent). Unlike the
add/buy flows, import doesn't probe BSE as a fallback for a bare ticker —
preview has no network access — so a BSE-only stock must be entered with an
explicit ".BO" suffix in the file.

Two-phase flow, so the caller (the frontend) can resolve duplicates with the
user before anything is written:
  1. preview_import() parses + validates every row and flags any that
     exactly match (ticker, date, action, shares, price) either an existing
     transaction already in the portfolio, or an earlier row in the same
     file — without writing anything.
  2. apply_import() takes the previewed rows back, each with a user-decided
     include/skip flag, and actually applies the included ones.

Rows are grouped by ticker and applied as buys-then-sells (by original row
order within each), reusing add_stock_purchases_bulk / sell_stock_shares_bulk
— so a buy and a same-file sell of those same shares resolves correctly (the
buy lands and commits before the sell is attempted). Each ticker group is
atomic (that's already those functions' contract), but the import as a whole
is best-effort across tickers: one bad row (typo, oversell, insufficient
shares) fails only the rows for that ticker/action, not the rest of the file.
"""

import datetime
import io
import logging
from decimal import Decimal, InvalidOperation

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from markets import apply_exchange
from schemas.portfolio import (
    BulkPurchaseLot, BulkSaleLot, ImportApplyRow, ImportPreviewResult, ImportPreviewRow, ImportRowResult,
    PortfolioImportResult,
)
from . import portfolio_service

logger = logging.getLogger(__name__)

_MARKET_TO_EXCHANGE = {"US": "US", "USA": "US", "IND": "IN", "IN": "IN", "INDIA": "IN"}
_ACTION_ALIASES = {"BUY": "buy", "B": "buy", "SELL": "sell", "S": "sell"}

# Header cell -> the field it maps to. Matched after normalization (lowercased,
# stripped, anything from "(" onward dropped) so "Market (US/IND)" and
# "market" both resolve to "market".
_COLUMN_ALIASES = {
    "market": "market",
    "stock": "ticker", "ticker": "ticker", "symbol": "ticker",
    "date": "date", "txn date": "date", "transaction date": "date", "trade date": "date",
    "number": "shares", "shares": "shares", "qty": "shares", "quantity": "shares",
    "buy/sell": "action", "action": "action", "type": "action", "side": "action",
    "price": "price", "rate": "price",
}
_REQUIRED_FIELDS = {"market", "ticker", "date", "shares", "action", "price"}
# Positional fallback when the file has no header row — our internal field
# names double as their own aliases (see _COLUMN_ALIASES), so naming the
# columns this way lets _parse_rows' existing name-based lookup handle both
# cases identically.
_DEFAULT_COLUMN_ORDER = ["market", "ticker", "date", "shares", "action", "price"]


def _normalize_header(h: object) -> str:
    h = str(h).strip().lower()
    return h.split("(", 1)[0].strip() if "(" in h else h


def _header_match_count(cells) -> int:
    return sum(1 for cell in cells if _COLUMN_ALIASES.get(_normalize_header(cell)) is not None)


def _looks_like_header(cells) -> bool:
    """True if a row's cells read like column-name labels (e.g. "market",
    "Stock (Ticker)") rather than actual data. A genuine header matches most
    or all of the 6 expected fields; a real data row — tickers, dates,
    numbers, "buy"/"sell" — essentially never matches any, so a low
    threshold safely tells them apart.
    """
    return _header_match_count(cells) >= 2


# How many leading rows of an xlsx sheet to consider when hunting for a
# header. More than 1: our own portfolio export has a title row above each
# sheet's real column headers (see export_service), so checking only row 0
# would never find it.
_HEADER_SCAN_ROWS = 15


def _find_header_row(df: pd.DataFrame) -> tuple[int, int]:
    """Best-scoring row among the first _HEADER_SCAN_ROWS rows of `df`, as
    (row index, score). With no match at all, returns (0, 0)."""
    best_idx, best_score = 0, -1
    for i in range(min(_HEADER_SCAN_ROWS, len(df))):
        score = _header_match_count(df.iloc[i])
        if score > best_score:
            best_idx, best_score = i, score
    return best_idx, best_score


def _read_xlsx(buf: io.BytesIO) -> pd.DataFrame:
    """An .xlsx can have multiple sheets, and — like our own portfolio
    export — a title row before the real header on any given sheet (see
    export_service). Reads every sheet, finds each one's best header-row
    candidate via _find_header_row, and returns the sheet that scored
    highest overall, trimmed to start at that row. So re-uploading an export
    finds the transaction sheet (and skips its title row) automatically,
    rather than reading whatever happens to be listed first. Falls back to
    the first sheet, untrimmed, if nothing looks like a match anywhere — so
    a plain single-sheet file, headered or not, still works exactly as
    before (_find_header_row on an all-data sheet returns index 0).
    """
    sheets = pd.read_excel(buf, dtype=str, engine="openpyxl", header=None, sheet_name=None)
    best_df, best_idx, best_score = None, 0, -1
    for df in sheets.values():
        if df.empty:
            continue
        idx, score = _find_header_row(df)
        if score > best_score:
            best_df, best_idx, best_score = df, idx, score
    if best_df is None:
        return next(iter(sheets.values()))
    return best_df.iloc[best_idx:].reset_index(drop=True)


def _read_table(filename: str, content: bytes) -> tuple[pd.DataFrame, bool]:
    """Returns (dataframe, had_header) with columns named after our internal
    fields — see the module docstring for the header-detection rule."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("csv", "xlsx"):
        raise ValueError(f"Unsupported file type '.{ext}' — upload a .csv or .xlsx file.")

    buf = io.BytesIO(content)
    try:
        if ext == "csv":
            df = pd.read_csv(buf, dtype=str, keep_default_na=False, header=None)
        else:
            df = _read_xlsx(buf)
    except Exception as e:  # noqa: BLE001
        # pandas.errors.EmptyDataError (an empty file) is itself a ValueError
        # subclass — catching Exception broadly here, rather than special-
        # casing ValueError, is what keeps that message consistent instead
        # of leaking pandas' raw wording straight through.
        raise ValueError(f"Could not read '{filename}' — is it a valid .csv or .xlsx file? ({e})")

    if df.empty:
        raise ValueError(f"'{filename}' has no rows.")

    had_header = _looks_like_header(df.iloc[0])
    if had_header:
        df.columns = [str(c) for c in df.iloc[0]]
        df = df.iloc[1:].reset_index(drop=True)
    else:
        n = len(df.columns)
        labels = _DEFAULT_COLUMN_ORDER[:n]
        labels += [f"extra_{i}" for i in range(n - len(labels))]
        df.columns = labels
    return df, had_header


def _parse_date(raw: str) -> tuple[str | None, str | None]:
    """Returns (iso_date, error) — exactly one of the two is None."""
    raw = raw.strip()
    if not raw:
        return None, "missing date"
    try:
        ts = pd.to_datetime(raw)
    except (ValueError, TypeError):
        return None, f"invalid date '{raw}'"
    if pd.isna(ts):
        return None, f"invalid date '{raw}'"
    if ts.date() > datetime.date.today():
        return None, f"date '{ts.date().isoformat()}' is in the future"
    return ts.strftime("%Y-%m-%d"), None


def _parse_rows(df: pd.DataFrame, had_header: bool) -> list[dict]:
    """Maps and validates every data row. Returns one dict per row (both
    valid and invalid), in file order — duplicate flags are added later by
    _flag_duplicates."""
    column_for: dict[str, str] = {}
    for col in df.columns:
        field = _COLUMN_ALIASES.get(_normalize_header(col))
        if field and field not in column_for:  # first match wins on duplicate synonyms
            column_for[field] = col

    missing = _REQUIRED_FIELDS - column_for.keys()
    if missing:
        if had_header:
            raise ValueError(
                f"Missing required column(s): {', '.join(sorted(missing))}. "
                "Expected: market, stock, date, number, buy/sell, price."
            )
        raise ValueError(
            "Could not find enough columns. A file with no header row needs exactly six "
            "columns in this order: market, stock, date, number, buy/sell, price."
        )

    rows: list[dict] = []
    row_offset = 2 if had_header else 1  # header is row 1, so data starts at row 2 — or row 1 with none
    for i, raw in df.iterrows():
        row_num = int(i) + row_offset
        market_raw = str(raw[column_for["market"]]).strip()
        ticker_raw = str(raw[column_for["ticker"]]).strip().upper()
        date_raw = str(raw[column_for["date"]]).strip()
        action_raw = str(raw[column_for["action"]]).strip().upper()
        shares_raw = str(raw[column_for["shares"]]).strip()
        price_raw = str(raw[column_for["price"]]).strip()

        if not any((market_raw, ticker_raw, date_raw, action_raw, shares_raw, price_raw)):
            continue  # a fully blank row (e.g. a trailing line) — not a data row at all

        errors: list[str] = []

        exchange = _MARKET_TO_EXCHANGE.get(market_raw.upper())
        if exchange is None:
            errors.append(f"unrecognized market '{market_raw}' (expected US or IND)")

        if not ticker_raw:
            errors.append("missing ticker")

        date, date_error = _parse_date(date_raw)
        if date_error:
            errors.append(date_error)

        action = _ACTION_ALIASES.get(action_raw)
        if action is None:
            errors.append(f"unrecognized buy/sell value '{action_raw}'")

        shares = 0
        try:
            shares_f = float(shares_raw)
            if shares_f <= 0 or shares_f != int(shares_f):
                errors.append(f"share count must be a positive whole number, got '{shares_raw}'")
            else:
                shares = int(shares_f)
        except ValueError:
            errors.append(f"invalid share count '{shares_raw}'")

        price = Decimal(0)
        try:
            price = Decimal(price_raw)
            if price <= 0:
                errors.append(f"price must be positive, got '{price_raw}'")
        except InvalidOperation:
            errors.append(f"invalid price '{price_raw}'")

        rows.append({
            "row_num": row_num,
            "market_label": market_raw,
            "ticker": apply_exchange(ticker_raw, exchange) if ticker_raw else ticker_raw,
            "action": action or "",
            "shares": shares,
            "price": price,
            "date": date,
            "valid": not errors,
            "error": "; ".join(errors) if errors else None,
            "duplicate": False,
            "duplicate_reason": None,
        })
    return rows


async def _flag_duplicates(session: AsyncSession, user_id: str, rows: list[dict]) -> None:
    """Mutates each valid row in place: sets duplicate/duplicate_reason for
    anything that exactly matches (date, action, shares, price) against
    either an existing transaction already recorded for that ticker, or an
    earlier row for the same ticker in this same file.
    """
    valid_rows = [r for r in rows if r["valid"]]
    tickers = sorted({r["ticker"] for r in valid_rows})

    existing_by_ticker: dict[str, set[tuple]] = {}
    for ticker in tickers:
        txns = await portfolio_service.get_holding_transactions(session, user_id, ticker)
        existing_by_ticker[ticker] = {
            (t.date, "sell" if t.sale else "buy", t.shares, Decimal(t.sold_at if t.sale else t.bought_at))
            for t in txns
        }

    seen_in_file: dict[str, dict[tuple, int]] = {}  # ticker -> {signature: first row_num it appeared on}
    for r in valid_rows:
        ticker = r["ticker"]
        sig = (r["date"], r["action"], r["shares"], r["price"])

        if sig in existing_by_ticker.get(ticker, ()):
            r["duplicate"] = True
            r["duplicate_reason"] = (
                f"Matches a transaction you already have — {r['action']} {r['shares']} {ticker} "
                f"@ {r['price']} on {r['date']}."
            )
            continue

        file_sigs = seen_in_file.setdefault(ticker, {})
        if sig in file_sigs:
            r["duplicate"] = True
            r["duplicate_reason"] = f"Duplicate of row {file_sigs[sig]} in this file."
        else:
            file_sigs[sig] = r["row_num"]


def _to_preview_row(r: dict) -> ImportPreviewRow:
    return ImportPreviewRow(
        row=r["row_num"], market=r["market_label"], ticker=r["ticker"], date=r["date"],
        action=r["action"], shares=r["shares"], price=r["price"], valid=r["valid"],
        error=r["error"], duplicate=r["duplicate"], duplicate_reason=r["duplicate_reason"],
    )


async def preview_import(
    session: AsyncSession, user_id: str, filename: str, content: bytes,
) -> ImportPreviewResult:
    df, had_header = _read_table(filename, content)
    rows = _parse_rows(df, had_header)
    await _flag_duplicates(session, user_id, rows)
    return ImportPreviewResult(
        total_rows=len(rows),
        rows=[_to_preview_row(r) for r in rows],
    )


async def _apply_rows(session: AsyncSession, user_id: str, rows: list[dict]) -> list[ImportRowResult]:
    by_ticker: dict[str, list[dict]] = {}
    for r in rows:
        by_ticker.setdefault(r["ticker"], []).append(r)

    def _result(r: dict, status: str, error: str | None = None) -> ImportRowResult:
        return ImportRowResult(
            row=r["row_num"], market=r["market_label"], ticker=r["ticker"], date=r["date"], action=r["action"],
            shares=r["shares"], price=r["price"], status=status, error=error,
        )

    results: list[ImportRowResult] = []
    for ticker, ticker_rows in by_ticker.items():
        buys = [r for r in ticker_rows if r["action"] == "buy"]
        sells = [r for r in ticker_rows if r["action"] == "sell"]

        if buys:
            try:
                await portfolio_service.add_stock_purchases_bulk(
                    session, user_id, ticker,
                    [BulkPurchaseLot(shares=r["shares"], bought_at=r["price"], date=r["date"]) for r in buys],
                )
                results.extend(_result(r, "imported") for r in buys)
            except Exception as e:  # noqa: BLE001
                logger.warning("Import: buy failed for %s: %r", ticker, e)
                results.extend(_result(r, "failed", str(e)) for r in buys)

        if sells:
            try:
                await portfolio_service.sell_stock_shares_bulk(
                    session, user_id, ticker,
                    [BulkSaleLot(shares=r["shares"], sold_at=r["price"], date=r["date"]) for r in sells],
                )
                results.extend(_result(r, "imported") for r in sells)
            except Exception as e:  # noqa: BLE001
                logger.warning("Import: sell failed for %s: %r", ticker, e)
                results.extend(_result(r, "failed", str(e)) for r in sells)

    return results


async def apply_import(
    session: AsyncSession, user_id: str, apply_rows: list[ImportApplyRow],
) -> PortfolioImportResult:
    included = [
        {
            "row_num": r.row, "market_label": r.market, "ticker": r.ticker,
            "action": r.action, "shares": r.shares, "price": r.price, "date": r.date,
        }
        for r in apply_rows if r.include
    ]
    applied = await _apply_rows(session, user_id, included)
    skipped = [
        ImportRowResult(
            row=r.row, market=r.market, ticker=r.ticker, date=r.date, action=r.action,
            shares=r.shares, price=r.price, status="skipped",
        )
        for r in apply_rows if not r.include
    ]

    all_rows = sorted(applied + skipped, key=lambda r: r.row)
    imported = sum(1 for r in all_rows if r.status == "imported")
    failed = sum(1 for r in all_rows if r.status == "failed")
    skipped_n = sum(1 for r in all_rows if r.status == "skipped")
    return PortfolioImportResult(
        total_rows=len(all_rows), imported_rows=imported, failed_rows=failed,
        skipped_rows=skipped_n, rows=all_rows,
    )
