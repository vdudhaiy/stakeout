'''
Schema for Portfolio data in the Market Lens Dashboard.
'''

from pydantic import BaseModel


class StockPurchaseHistory(BaseModel):
    id: int
    sale: bool = False          # False = buy, True = sell
    ticker: str
    date: str
    shares: int
    bought_at: float = 0.0     # price per share on a buy; FIFO avg cost on sells
    sold_at: float = 0.0       # price per share on a sell; 0 on buys
    shares_remaining: int = 0  # unsold shares from this buy lot; always 0 for sells


class StockHolding(BaseModel):
    ticker: str
    market: str = "US"                   # "US" | "IN" — exchange the asset trades on
    currency: str = "USD"                # native currency of all monetary fields below
    company_name: str = ""               # display name; empty string if lookup failed
    shares: int                          # shares currently held
    sold_shares: int                     # total shares ever sold
    average_cost: float                  # weighted avg cost of held shares
    current_price: float                 # live price from yfinance
    stock_value: float                   # shares * current_price
    total_earned: float                  # proceeds from all sell transactions
    total_invested: float                # total amount invested (bought_at * shares for all buy transactions)
    profit_loss: float                   # stock_value - total_invested
    profit_loss_percentage: float        # (stock_value - total_invested) / total_invested * 100
    trade_history: list[StockPurchaseHistory]        # all buy + sell transactions, oldest first


class PortfolioResponse(BaseModel):
    market: str | None = None   # market filter applied ("US"/"IN"), or None for all
    currency: str = "USD"       # native currency of the aggregate figures below
    portfolio_value: float      # current total value of all holdings (sum of stock_value across all holdings)
    realized_gains: float     # proceeds from all sell transactions (sum of sold_shares * sold_at across all sell transactions)
    total_shares: int           # number of shares across all holdings
    total_invested: float       # sum of (shares * average_cost) across all holdings
    total_return: float         # portfolio_value - total_invested
    return_percentage: float     # (portfolio_value - total_invested) / total_invested * 100
    net_profit_loss: float      # total_return + realized_gains
    holdings: list[StockHolding] # list of all holdings with detailed info
