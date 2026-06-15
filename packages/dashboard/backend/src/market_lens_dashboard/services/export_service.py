"""Excel export for the portfolio."""

import io
from datetime import date as dt_date

import xlsxwriter

from ..schemas.portfolio import PortfolioResponse

# ── Layout constants (0-indexed rows) ─────────────────────────────────────────
_S1_TITLE_ROW   = 0
_S1_SUM_HDR_ROW = 2
_S1_FIRST_SUM   = 3   # Portfolio Value row
_S1_TABLE_ROW   = 9   # Holdings table header row

_S2_TITLE_ROW   = 0
_S2_TABLE_ROW   = 2   # Transactions table header row


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

    ws1.set_column('A:A', 10)   # Ticker
    ws1.set_column('B:B', 26)   # Company
    ws1.set_column('C:C', 10)   # Shares
    ws1.set_column('D:D', 13)   # Avg Cost
    ws1.set_column('E:E', 14)   # Current Price
    ws1.set_column('F:F', 15)   # Market Value
    ws1.set_column('G:G', 15)   # Cost Basis
    ws1.set_column('H:H', 15)   # Unrealized P&L
    ws1.set_column('I:I', 12)   # % Gain/Loss
    ws1.set_column('J:J', 15)   # Realized Gains

    ws1.merge_range(0, 0, 0, 9, f'Portfolio Snapshot — {dt_date.today().isoformat()}', title_fmt)
    ws1.write(_S1_SUM_HDR_ROW, 0, 'PORTFOLIO SUMMARY', section_fmt)

    summary_rows = [
        ('Portfolio Value', portfolio.portfolio_value, False),
        ('Total Invested',  portfolio.total_invested,  False),
        ('Unrealized P&L',  portfolio.total_return,    True),
        ('Realized Gains',  portfolio.realized_gains,  True),
        ('Net P&L',         portfolio.net_profit_loss, True),
    ]
    for i, (lbl, val, signed) in enumerate(summary_rows):
        row = _S1_FIRST_SUM + i
        ws1.write(row, 0, lbl, lbl_fmt)
        ws1.write(row, 1, val, _sum_fmt(val) if signed else sum_neu)

    # Holdings table
    holdings = portfolio.holdings
    n = len(holdings)
    T1 = _S1_TABLE_ROW

    h_cols = [
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
    ]

    data1 = []
    for i, h in enumerate(holdings):
        xl = T1 + 2 + i          # 1-indexed Excel row for this data row
        data1.append([
            h.ticker,
            h.company_name,
            h.shares,
            h.average_cost,
            h.current_price,
            f'=C{xl}*E{xl}',                                   # Market Value
            h.total_invested,                                    # Cost Basis (FIFO, snapshot)
            f'=F{xl}-G{xl}',                                    # Unrealized P&L
            f'=IF(G{xl}>0,(F{xl}-G{xl})/G{xl},0)',             # % Gain/Loss
            h.total_earned,                                      # Realized Gains
        ])

    ws1.add_table(T1, 0, T1 + n, 9, {
        'name': 'Holdings',
        'style': 'Table Style Medium 2',
        'columns': h_cols,
        'data': data1,
    })

    if n > 0:
        for col_idx in (7, 9):    # Unrealized P&L, Realized Gains
            ws1.conditional_format(T1 + 1, col_idx, T1 + n, col_idx,
                {'type': 'cell', 'criteria': '>', 'value': 0, 'format': cf_pos})
            ws1.conditional_format(T1 + 1, col_idx, T1 + n, col_idx,
                {'type': 'cell', 'criteria': '<', 'value': 0, 'format': cf_neg})
        ws1.conditional_format(T1 + 1, 8, T1 + n, 8,   # % Gain/Loss
            {'type': 'cell', 'criteria': '>', 'value': 0, 'format': cf_pos})
        ws1.conditional_format(T1 + 1, 8, T1 + n, 8,
            {'type': 'cell', 'criteria': '<', 'value': 0, 'format': cf_neg})

    ws1.freeze_panes(T1 + 1, 0)

    # ── Sheet 2: Transaction History ───────────────────────────────────────────
    ws2 = wb.add_worksheet('Transaction History')
    ws2.set_zoom(90)
    ws2.hide_gridlines(2)
    ws2.set_row(_S2_TITLE_ROW, 24)

    ws2.set_column('A:A', 13)   # Date
    ws2.set_column('B:B', 10)   # Ticker
    ws2.set_column('C:C', 26)   # Company
    ws2.set_column('D:D', 9)    # Type
    ws2.set_column('E:E', 10)   # Shares
    ws2.set_column('F:F', 13)   # Bought @
    ws2.set_column('G:G', 13)   # Sold @
    ws2.set_column('H:H', 13)   # Remaining
    ws2.set_column('I:I', 15)   # P&L

    ws2.merge_range(0, 0, 0, 8, f'Transaction History — {dt_date.today().isoformat()}', title_fmt)

    t_cols = [
        {'header': 'Date'},
        {'header': 'Ticker'},
        {'header': 'Company'},
        {'header': 'Type'},
        {'header': 'Shares',    'format': int_fmt},
        {'header': 'Bought @',  'format': money},
        {'header': 'Sold @',    'format': money},
        {'header': 'Remaining', 'format': int_fmt},
        {'header': 'P&L',       'format': money},
    ]

    all_txns: list[tuple[str, object]] = []
    for h in portfolio.holdings:
        for txn in h.trade_history:
            all_txns.append((h.company_name, txn))
    all_txns.sort(key=lambda x: x[1].date, reverse=True)

    T2 = _S2_TABLE_ROW
    data2 = []
    for j, (company, txn) in enumerate(all_txns):
        xl = T2 + 2 + j          # 1-indexed Excel row
        data2.append([
            txn.date,
            txn.ticker,
            company,
            'SELL' if txn.sale else 'BUY',
            txn.shares,
            txn.bought_at,
            txn.sold_at if txn.sale else None,
            txn.shares_remaining if not txn.sale else None,
            f'=E{xl}*(G{xl}-F{xl})' if txn.sale else None,    # P&L = shares × (sold - cost)
        ])

    nt = len(data2)
    ws2.add_table(T2, 0, T2 + nt, 8, {
        'name': 'Transactions',
        'style': 'Table Style Medium 2',
        'columns': t_cols,
        'data': data2,
    })

    if nt > 0:
        ws2.conditional_format(T2 + 1, 3, T2 + nt, 3,
            {'type': 'text', 'criteria': 'containing', 'value': 'BUY', 'format': cf_buy})
        ws2.conditional_format(T2 + 1, 3, T2 + nt, 3,
            {'type': 'text', 'criteria': 'containing', 'value': 'SELL', 'format': cf_sell})
        ws2.conditional_format(T2 + 1, 8, T2 + nt, 8,
            {'type': 'cell', 'criteria': '>', 'value': 0, 'format': cf_pos})
        ws2.conditional_format(T2 + 1, 8, T2 + nt, 8,
            {'type': 'cell', 'criteria': '<', 'value': 0, 'format': cf_neg})

    ws2.freeze_panes(T2 + 1, 0)

    wb.close()
    return output.getvalue()
