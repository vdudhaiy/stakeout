"""Excel export for the portfolio.

Covers every portfolio in the exported market. The "Transaction History"
sheet's market, stock, date, number, buy/sell, price and portfolio columns
are deliberately the exact columns import_service expects (see its module
docstring), so this file doubles as a ready-made backup: re-uploading it
through Import lands every transaction back in the portfolio it came from.
Company/Remaining/P&L are extra, informational-only columns the importer
ignores.

Sheet 1 leads with the combined figures across the market, followed by one
summary block per portfolio when there is more than one — mirroring the
combined bar and per-portfolio stats rows in the UI.
"""

import io
from datetime import date as dt_date

import xlsxwriter

from schemas.portfolio import PortfolioResponse, PortfolioStats, StockHolding, StockPurchaseHistory

# ── Layout constants (0-indexed rows) ─────────────────────────────────────────
_S1_TITLE_ROW   = 0
_S1_SUM_HDR_ROW = 2
_S1_FIRST_SUM   = 3   # Portfolio Value row
_S1_SUM_ROWS    = 6   # rows per summary block
_S1_MIN_TABLE_ROW = 10  # holdings table header row when there's one summary block

_S2_TITLE_ROW   = 0
_S2_TABLE_ROW   = 2   # Transactions table header row

_S1_LAST_COL = 11  # Dividends — 12 columns counting Portfolio
_S2_LAST_COL = 9   # P&L — 10 columns counting Portfolio


def build_portfolio_xlsx(portfolio: PortfolioResponse) -> bytes:
    output = io.BytesIO()
    wb = xlsxwriter.Workbook(output, {'in_memory': True})

    # ── Shared formats ─────────────────────────────────────────────────────────
    money    = wb.add_format({'num_format': '$#,##0.00'})
    pct_fmt  = wb.add_format({'num_format': '0.00%'})
    int_fmt  = wb.add_format({'num_format': '#,##0'})

    title_fmt = wb.add_format({
        'bold': True, 'font_size': 13, 'font_color': '#0f172a',
        'bg_color': '#e0e7ff', 'bottom': 2, 'border_color': '#6366f1',
        'valign': 'vcenter',
    })
    section_fmt = wb.add_format({
        'bold': True, 'font_size': 8, 'font_color': '#6366f1', 'italic': True,
    })
    lbl_fmt = wb.add_format({
        'bold': True, 'font_color': '#64748b', 'font_size': 9, 'align': 'right',
    })
    sum_neu = wb.add_format({
        'num_format': '$#,##0.00', 'bold': True, 'font_size': 10,
        'font_color': '#1e293b', 'left': 1, 'left_color': '#6366f1',
    })
    sum_pos = wb.add_format({
        'num_format': '$#,##0.00', 'bold': True, 'font_size': 10,
        'font_color': '#059669', 'left': 1, 'left_color': '#6366f1',
    })
    sum_neg = wb.add_format({
        'num_format': '$#,##0.00', 'bold': True, 'font_size': 10,
        'font_color': '#dc2626', 'left': 1, 'left_color': '#6366f1',
    })

    # Conditional-format-only formats (font_color only — num_format comes from column format)
    cf_pos  = wb.add_format({'font_color': '#059669'})
    cf_neg  = wb.add_format({'font_color': '#dc2626'})
    cf_buy  = wb.add_format({
        'font_color': '#059669', 'bold': True, 'bg_color': '#d1fae5', 'align': 'center',
    })
    cf_sell = wb.add_format({
        'font_color': '#dc2626', 'bold': True, 'bg_color': '#fee2e2', 'align': 'center',
    })

    def _sum_fmt(v):
        return sum_pos if v > 0 else (sum_neg if v < 0 else sum_neu)

    # ── Sheet 1: Portfolio ─────────────────────────────────────────────────────
    ws1 = wb.add_worksheet('Portfolio')
    ws1.set_zoom(90)
    ws1.hide_gridlines(2)
    ws1.set_row(_S1_TITLE_ROW, 24)

    ws1.set_column('A:A', 16)   # Portfolio
    ws1.set_column('B:B', 10)   # Ticker
    ws1.set_column('C:C', 26)   # Company
    ws1.set_column('D:D', 10)   # Shares
    ws1.set_column('E:E', 13)   # Avg Cost
    ws1.set_column('F:F', 14)   # Current Price
    ws1.set_column('G:G', 15)   # Market Value
    ws1.set_column('H:H', 15)   # Cost Basis
    ws1.set_column('I:I', 15)   # Unrealized P&L
    ws1.set_column('J:J', 12)   # % Gain/Loss
    ws1.set_column('K:K', 15)   # Realized Gains
    ws1.set_column('L:L', 14)   # Dividends

    ws1.merge_range(0, 0, 0, _S1_LAST_COL, f'Portfolio Snapshot — {dt_date.today().isoformat()}', title_fmt)

    def _write_summary(row: int, heading: str, stats) -> int:
        """Writes one heading + six figures. Returns the next free row."""
        ws1.write(row, 0, heading, section_fmt)
        rows = [
            ('Portfolio Value', stats.portfolio_value, False),
            ('Total Invested',  stats.total_invested,  False),
            ('Unrealized P&L',  stats.total_return,    True),
            ('Realized Gains',  stats.realized_gains,  True),
            ('Dividends',       stats.total_dividends, True),
            ('Net P&L',         stats.net_profit_loss, True),
        ]
        for i, (lbl, val, signed) in enumerate(rows):
            val = float(val)   # xlsxwriter doesn't accept Decimal cell values
            ws1.write(row + 1 + i, 0, lbl, lbl_fmt)
            ws1.write(row + 1 + i, 1, val, _sum_fmt(val) if signed else sum_neu)
        return row + 1 + len(rows)

    breakdown: list[PortfolioStats] = portfolio.portfolios
    multiple = len(breakdown) > 1

    row = _write_summary(
        _S1_SUM_HDR_ROW,
        'ALL PORTFOLIOS' if multiple else 'PORTFOLIO SUMMARY',
        portfolio,
    )
    if multiple:
        for stats in breakdown:
            row += 1  # blank spacer between blocks
            row = _write_summary(row, stats.name.upper(), stats)

    # One blank row between the last summary and the table — the same gap a
    # single-portfolio export has always had.
    T1 = max(row + 1, _S1_MIN_TABLE_ROW)

    # Holdings table
    names = {p.id: p.name for p in breakdown}
    holdings = portfolio.holdings
    n = len(holdings)

    h_cols = [
        {'header': 'Portfolio'},
        {'header': 'Ticker'},
        {'header': 'Company'},
        {'header': 'Shares',         'format': int_fmt},
        {'header': 'Avg Cost',       'format': money},
        {'header': 'Current Price',  'format': money},
        {'header': 'Market Value',   'format': money},
        {'header': 'Cost Basis',     'format': money},
        {'header': 'Unrealized P&L', 'format': money},
        {'header': '% Gain/Loss',    'format': pct_fmt},
        {'header': 'Realized Gains', 'format': money},
        {'header': 'Dividends',      'format': money},
    ]

    data1 = []
    for i, h in enumerate(holdings):
        xl = T1 + 2 + i          # 1-indexed Excel row for this data row
        # current_price is None when the live quote couldn't be fetched. Writing
        # 'N/A' text (rather than a formula referencing a blank cell, which Excel
        # would silently treat as 0) keeps that failure visible instead of
        # reporting a fabricated $0 market value / -100% loss.
        priced = h.current_price is not None
        data1.append([
            names.get(h.portfolio_id, ''),
            h.ticker,
            h.company_name,
            h.shares,
            float(h.average_cost),
            float(h.current_price) if priced else 'N/A',
            f'=D{xl}*F{xl}' if priced else 'N/A',              # Market Value
            float(h.total_invested),                             # Cost Basis (FIFO, snapshot)
            f'=G{xl}-H{xl}' if priced else 'N/A',               # Unrealized P&L
            f'=IF(H{xl}>0,(G{xl}-H{xl})/H{xl},0)' if priced else 'N/A',  # % Gain/Loss
            float(h.total_earned),                               # Realized Gains
            float(h.total_dividends),                            # Dividends
        ])

    ws1.add_table(T1, 0, T1 + n, _S1_LAST_COL, {
        'name': 'Holdings',
        'style': 'Table Style Medium 2',
        'columns': h_cols,
        'data': data1,
    })

    if n > 0:
        for col_idx in (8, 10):    # Unrealized P&L, Realized Gains
            ws1.conditional_format(T1 + 1, col_idx, T1 + n, col_idx,
                {'type': 'cell', 'criteria': '>', 'value': 0, 'format': cf_pos})
            ws1.conditional_format(T1 + 1, col_idx, T1 + n, col_idx,
                {'type': 'cell', 'criteria': '<', 'value': 0, 'format': cf_neg})
        ws1.conditional_format(T1 + 1, 9, T1 + n, 9,   # % Gain/Loss
            {'type': 'cell', 'criteria': '>', 'value': 0, 'format': cf_pos})
        ws1.conditional_format(T1 + 1, 9, T1 + n, 9,
            {'type': 'cell', 'criteria': '<', 'value': 0, 'format': cf_neg})

    ws1.freeze_panes(T1 + 1, 0)

    # ── Sheet 2: Transaction History ───────────────────────────────────────────
    ws2 = wb.add_worksheet('Transaction History')
    ws2.set_zoom(90)
    ws2.hide_gridlines(2)
    ws2.set_row(_S2_TITLE_ROW, 24)

    ws2.set_column('A:A', 16)   # Portfolio
    ws2.set_column('B:B', 9)    # Market
    ws2.set_column('C:C', 10)   # Stock
    ws2.set_column('D:D', 13)   # Date
    ws2.set_column('E:E', 10)   # Number
    ws2.set_column('F:F', 9)    # Buy/Sell
    ws2.set_column('G:G', 13)   # Price
    ws2.set_column('H:H', 26)   # Company
    ws2.set_column('I:I', 13)   # Remaining
    ws2.set_column('J:J', 15)   # P&L

    ws2.merge_range(0, 0, 0, _S2_LAST_COL, f'Transaction History — {dt_date.today().isoformat()}', title_fmt)

    # Header text matches import_service's recognized column aliases exactly
    # (Portfolio/Market/Stock/Date/Number/Buy-Sell/Price) — Company/Remaining/
    # P&L don't, so a re-import just ignores those three as harmless extras.
    # The importer matches by header name, not position, so Portfolio leading
    # the table doesn't affect round-tripping.
    t_cols = [
        {'header': 'Portfolio'},
        {'header': 'Market'},
        {'header': 'Stock'},
        {'header': 'Date'},
        {'header': 'Number',    'format': int_fmt},
        {'header': 'Buy/Sell'},
        {'header': 'Price',     'format': money},
        {'header': 'Company'},
        {'header': 'Remaining', 'format': int_fmt},
        {'header': 'P&L',       'format': money},
    ]

    all_txns: list[tuple[StockHolding, StockPurchaseHistory]] = []
    for h in portfolio.holdings:
        for txn in h.trade_history:
            all_txns.append((h, txn))
    all_txns.sort(key=lambda x: x[1].date, reverse=True)

    T2 = _S2_TABLE_ROW
    data2 = []
    for holding, txn in all_txns:
        # market+stock (bare, no exchange suffix) — same convention a user
        # would type into an import file, not "RELIANCE.NS" redundantly
        # alongside a market column that already says IN.
        stock = txn.ticker.removesuffix('.NS').removesuffix('.BO')
        price = txn.sold_at if txn.sale else txn.bought_at
        pnl = (txn.sold_at - txn.bought_at) * txn.shares if txn.sale else None
        data2.append([
            names.get(holding.portfolio_id, ''),
            holding.market,
            stock,
            txn.date,
            txn.shares,
            'SELL' if txn.sale else 'BUY',
            float(price),
            holding.company_name,
            txn.shares_remaining if not txn.sale else None,
            float(pnl) if pnl is not None else None,
        ])

    nt = len(data2)
    ws2.add_table(T2, 0, T2 + nt, _S2_LAST_COL, {
        'name': 'Transactions',
        'style': 'Table Style Medium 2',
        'columns': t_cols,
        'data': data2,
    })

    if nt > 0:
        ws2.conditional_format(T2 + 1, 5, T2 + nt, 5,   # Buy/Sell
            {'type': 'text', 'criteria': 'containing', 'value': 'BUY', 'format': cf_buy})
        ws2.conditional_format(T2 + 1, 5, T2 + nt, 5,
            {'type': 'text', 'criteria': 'containing', 'value': 'SELL', 'format': cf_sell})
        ws2.conditional_format(T2 + 1, 9, T2 + nt, 9,   # P&L
            {'type': 'cell', 'criteria': '>', 'value': 0, 'format': cf_pos})
        ws2.conditional_format(T2 + 1, 9, T2 + nt, 9,
            {'type': 'cell', 'criteria': '<', 'value': 0, 'format': cf_neg})

    ws2.freeze_panes(T2 + 1, 0)

    wb.close()
    return output.getvalue()
