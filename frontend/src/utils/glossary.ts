/**
 * Plain-language explanations for every statistic in the app, shown via the
 * (?) InfoTip next to each stat. Each entry answers three questions:
 * what it is, what it means, and how to read it. Kept deliberately short —
 * these are captions, not a textbook.
 */

export const GLOSSARY: Record<string, { title: string; body: string }> = {
  open: {
    title: 'Open',
    body: "The first traded price of the session. A gap between today's open and yesterday's close usually reflects news that broke while the market was shut.",
  },
  high: {
    title: 'High',
    body: 'The highest price traded during the session. Repeated failures to push past a similar high can act as short-term resistance.',
  },
  low: {
    title: 'Low',
    body: 'The lowest price traded during the session. A low well below the close means buyers stepped in during the day.',
  },
  close: {
    title: 'Close',
    body: 'The final traded price of the session — the most-quoted "price" of a stock, and the anchor for daily change calculations.',
  },
  change: {
    title: 'Day change',
    body: "Today's close (or live price) minus the previous close, in money and percent. Green = up, red = down. Percent matters more than the raw number when comparing stocks.",
  },
  volume: {
    title: 'Volume',
    body: 'Number of shares traded in the session. Price moves on high volume carry more conviction than the same move on thin volume.',
  },
  sma: {
    title: 'Simple Moving Average (SMA)',
    body: 'The average close over the last N days, drawn as a smooth line. Price above a rising SMA suggests an uptrend; crosses of short vs. long SMAs are classic trend signals.',
  },
  ema: {
    title: 'Exponential Moving Average (EMA)',
    body: 'Like an SMA but weights recent days more, so it reacts faster to new prices. Traders often use it for shorter-term trend reads.',
  },
  bollinger: {
    title: 'Bollinger Bands',
    body: 'A 20-day average with bands ±2 standard deviations around it. Touching the upper band = stretched relative to recent volatility; band squeezes often precede big moves.',
  },
  rsi: {
    title: 'Relative Strength Index (RSI)',
    body: 'A 0–100 momentum gauge over 14 days. Above 70 is conventionally "overbought", below 30 "oversold" — a context clue, not a buy/sell signal on its own.',
  },
  macd: {
    title: 'MACD',
    body: 'The gap between a fast (12-day) and slow (26-day) EMA, plus a 9-day signal line. MACD crossing above its signal is read as bullish momentum; below, bearish.',
  },
  price_target: {
    title: 'Analyst price targets',
    body: 'Where professional analysts expect the price to be in ~12 months. The mean/median is the consensus; a wide low–high spread means analysts disagree — treat with skepticism.',
  },
  upside: {
    title: 'Upside',
    body: 'How far the mean analyst target sits above (or below) the current price, in percent. Positive upside means analysts on average expect gains — historically an optimistic crowd.',
  },
  recommendations: {
    title: 'Analyst recommendations',
    body: 'The count of analysts rating the stock Strong Buy → Strong Sell in recent months. Watch the direction of drift across periods more than the absolute mix.',
  },
  eps_estimate: {
    title: 'EPS estimates',
    body: "Analysts' forecast of earnings per share for upcoming quarters. The stock often reacts to results relative to this consensus, not to the raw numbers.",
  },
  revenue_estimate: {
    title: 'Revenue estimates',
    body: "Analysts' forecast of total sales for upcoming quarters. Growth vs. the year-ago quarter is the headline investors watch.",
  },
  earnings_surprise: {
    title: 'Earnings surprise',
    body: 'How much reported EPS beat (+) or missed (−) the consensus estimate, in percent. Consistent beats build credibility; misses often trigger sharp drops.',
  },
  portfolio_value: {
    title: 'Portfolio value',
    body: 'Current market value of every share you still hold: shares × latest price, summed across holdings in this market.',
  },
  total_invested: {
    title: 'Cost basis (invested)',
    body: 'What you actually paid for the shares you still hold, computed FIFO — oldest lots are treated as sold first. Sold shares drop out of this number.',
  },
  total_return: {
    title: 'Unrealized return',
    body: "Paper profit or loss on shares you still hold: portfolio value − cost basis. It isn't locked in until you sell.",
  },
  realized_gains: {
    title: 'Realized gains',
    body: 'Profit or loss actually locked in by selling: (sale price − FIFO purchase cost) × shares sold, summed over all sells.',
  },
  net_pl: {
    title: 'Net profit / loss',
    body: 'The full picture: unrealized return on what you hold plus realized gains from what you sold.',
  },
  return_pct: {
    title: 'Return %',
    body: 'Unrealized return as a percentage of cost basis. Useful for comparing performance across differently-sized positions.',
  },
  avg_cost: {
    title: 'Average cost',
    body: 'The weighted average price you paid per share still held. Compare with the current price to see your per-share cushion or shortfall.',
  },
  allocation: {
    title: 'Allocation',
    body: 'Each holding as a share of total portfolio value. A single position dominating the chart means concentrated risk — intentional or not.',
  },
  market_status: {
    title: 'Market status',
    body: 'Whether the exchange is currently in its regular trading session. Prices only update live while the market is open; otherwise you see the last close.',
  },
}

export type GlossaryKey = keyof typeof GLOSSARY
