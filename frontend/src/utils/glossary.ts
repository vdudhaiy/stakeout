/**
 * Plain-language explanations for every statistic in the app, shown via the
 * (?) InfoTip next to each stat. Each entry answers three questions:
 * what it is, what it means, and how to read it. Kept deliberately short —
 * these are captions, not a textbook.
 */

export const GLOSSARY: Record<string, { title: string; body: string }> = {
  xirr: {
    title: 'Money-weighted return (XIRR)',
    body: 'What your money actually earned, per year, counting when each amount went in. Adding a lot right before a rally lifts this; adding right before a fall drags it down. This is the honest answer to "how did I do?".',
  },
  twr: {
    title: 'Time-weighted return',
    body: "What your holdings earned, with the timing of deposits stripped out. It's the only fair way to compare against an index, because an index never has money paid into it.",
  },
  cagr: {
    title: 'Annualized return (CAGR)',
    body: 'The time-weighted return expressed as a steady yearly rate. Hidden for periods under a month — annualizing a couple of weeks produces a huge number that means nothing.',
  },
  benchmark_equivalent: {
    title: 'If you had bought the index',
    body: 'The same money, on the same days, put into the benchmark index instead. Comparing against this rather than the index’s headline return is what makes the comparison fair when your contributions were irregular.',
  },
  value_added: {
    title: 'Value added',
    body: 'Your portfolio today minus what the index path would be worth. Positive means your picks and timing beat simply buying the index; negative means they did not.',
  },
  max_drawdown: {
    title: 'Maximum drawdown',
    body: 'The largest peak-to-trough fall over the period, measured on returns rather than on balance — so withdrawing money never counts as a loss. A rough gauge of the worst stretch you sat through.',
  },
  volatility: {
    title: 'Volatility',
    body: 'How much daily returns swing around, annualized. Higher means a bumpier ride for the same destination. Hidden below 20 trading days, where it is noise rather than a statistic.',
  },
  beta: {
    title: 'Beta',
    body: 'How sharply your portfolio moves with the index. 1.0 means it moves in step; above 1.0 means it amplifies the index; below means it is steadier.',
  },
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
    body: 'The full picture: unrealized return on what you hold, plus realized gains from what you sold, plus dividend income received.',
  },
  dividends: {
    title: 'Dividends',
    body: 'Cash income received while holding shares, independent of price moves. Auto-fetched from Yahoo Finance where available (shares held × amount per share on each ex-dividend date); you can add, edit, or delete entries by hand too.',
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
