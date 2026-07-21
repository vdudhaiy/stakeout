'''
Service layer for computing technical indicators.
'''

import pandas as pd
from . import market_data_service
from ..schemas.indicators import (
    SMAPoint, SMAResponse,
    EMAPoint, EMAResponse,
    RSIPoint, RSIResponse,
    MACDPoint, MACDResponse,
    BollingerPoint, BollingerResponse,
    IndicatorsResponse,
)


# ── Data loading ──────────────────────────────────────────────────────────────

async def _load_ticker_df(ticker: str, days: int) -> pd.DataFrame:
   '''
   Load the archived OHLCV data for `ticker` from the market_data table and
   return a DataFrame trimmed to the last `days` rows, sorted ascending by date.

   Steps:
   1. Query market_data_service.get_ohlcv, which already returns rows sorted
      ascending by date. days <= 0 requests the full history — some indicators
      (RSI, MACD) need more lookback than the user-facing window to "warm up"
      the calculation; see the note in each compute_* function.
   2. Raise ValueError with a descriptive message if no rows exist,
      so the router can convert it to a 404.
   '''
   records = await market_data_service.get_ohlcv(ticker, days)

   if not records:
       raise ValueError(f"Data for ticker '{ticker}' not found.")

   return pd.DataFrame(records)


def _df_to_date_strings(df: pd.DataFrame) -> list[str]:
   '''
   Return the 'date' column as a list of "YYYY-MM-DD" strings.
   The date column is kept as a regular column (not the index) after _load_ticker_df.
   '''
   return pd.to_datetime(df['date']).dt.strftime("%Y-%m-%d").tolist()


def _nan_to_none(value) -> float | None:
   '''
   Convert a numpy NaN or pandas NA to Python None so that Pydantic serialises
   it as JSON null rather than raising a validation error.

   Use this on every individual indicator value before constructing a data-point
   model instance.
   '''
   if pd.isna(value):
      return None
   else:
      return float(value)  # ensure it's a plain Python float, not a numpy type


# ── SMA ───────────────────────────────────────────────────────────────────────

def compute_sma(df: pd.DataFrame, period: int) -> list[SMAPoint]:
   '''
   Compute Simple Moving Average over the 'close' column.

   Steps:
   1. Use df['close'].rolling(window=period).mean() to get the rolling mean series.
   2. Zip the date strings (from _df_to_date_strings) with the values.
   3. For each (date, value) pair, call _nan_to_none on the value, then construct
      and append an SMAPoint.
   4. Return the list — it will be the same length as the DataFrame.

   Note: the first (period - 1) entries will be NaN → None.
   '''
   sma = df['close'].rolling(window=period).mean()
   dates = _df_to_date_strings(df)
   points = []
   for date, value in zip(dates, sma):
      points.append(SMAPoint(date=date, value=_nan_to_none(value)))
   return points


# ── EMA ───────────────────────────────────────────────────────────────────────

def compute_ema(df: pd.DataFrame, period: int) -> list[EMAPoint]:
   '''
   Compute Exponential Moving Average over the 'close' column.

   Steps:
   1. Use df['close'].ewm(span=period, adjust=False).mean() to get the EMA series.
      `adjust=False` uses the recursive definition: EMA_t = alpha*price_t + (1-alpha)*EMA_{t-1}
      where alpha = 2/(period+1).  This matches how TradingView and most charting
      libraries compute EMA.
   2. Same zip-and-construct pattern as compute_sma.

   Note: pandas ewm with adjust=False initialises from the first data point, so
   unlike SMA there are no leading NaN values — but the earliest values are less
   meaningful because the exponential smoothing hasn't had time to "warm up".
   '''
   ema = df['close'].ewm(span=period, adjust=False).mean()
   dates = _df_to_date_strings(df)
   points = []
   for date, value in zip(dates, ema):
      points.append(EMAPoint(date=date, value=_nan_to_none(value)))
   return points


# ── RSI ───────────────────────────────────────────────────────────────────────

def compute_rsi(df: pd.DataFrame, period: int = 14) -> list[RSIPoint]:
   '''
   Compute the Relative Strength Index over the 'close' column using Wilder's
   smoothing method (which is an EMA with alpha = 1/period).

   Steps:
   1. Compute the daily price change: delta = df['close'].diff()
   2. Separate gains and losses:
      gains  = delta.clip(lower=0)        # negative changes become 0
      losses = (-delta).clip(lower=0)     # positive changes become 0
   3. Compute the initial average gain and average loss using Wilder's smoothing:
      avg_gain = gains.ewm(alpha=1/period, adjust=False).mean()
      avg_loss = losses.ewm(alpha=1/period, adjust=False).mean()
   4. Compute RS = avg_gain / avg_loss  (handle the divide-by-zero case where
      avg_loss == 0 → RS is infinite → RSI = 100)
   5. Compute RSI = 100 - (100 / (1 + RS))
   6. The first row of delta will be NaN (diff has no predecessor) — use
      _nan_to_none to keep those as None in the output.
   7. Zip dates and RSI values into RSIPoint objects and return the list.
   '''
   delta = df['close'].diff()
   gains = delta.clip(lower=0)
   losses = (-delta).clip(lower=0)
   avg_gain = gains.ewm(alpha=1/period, adjust=False).mean()
   avg_loss = losses.ewm(alpha=1/period, adjust=False).mean()
   rs = avg_gain / avg_loss.replace(0, float('nan'))
   rsi = 100 - (100 / (1 + rs))
   rsi = rsi.fillna(100.0)  # avg_loss == 0 means no down days → RSI is defined as 100
   dates = _df_to_date_strings(df)
   points = []
   for date, value in zip(dates, rsi):
      points.append(RSIPoint(date=date, value=_nan_to_none(value)))
   return points


# ── MACD ──────────────────────────────────────────────────────────────────────

def compute_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> list[MACDPoint]:
   '''
   Compute MACD line, signal line, and histogram over the 'close' column.

   Steps:
   1. Compute the fast EMA: ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
   2. Compute the slow EMA: ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
   3. MACD line:  macd_line   = ema_fast - ema_slow
   4. Signal line: signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
   5. Histogram:   histogram   = macd_line - signal_line
   6. Zip dates with (macd_line, signal_line, histogram) — apply _nan_to_none to
      each value individually and construct MACDPoint objects.

   Note: because the slow EMA spans `slow` periods, the MACD line is only
   meaningful after roughly `slow + signal_period` data points.  The early values
   will not be NaN (ewm doesn't produce NaN with adjust=False), but they should be
   treated as warm-up artefacts.  The frontend should handle this gracefully.

   Caller responsibility: if the user requests a short `days` window (e.g. 7D),
   load extra history before trimming — see fetch_indicators for how to do this.
   '''
   ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
   ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
   macd_line = ema_fast - ema_slow
   signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
   histogram = macd_line - signal_line
   dates = _df_to_date_strings(df)
   points = []
   for date, macd_val, signal_val, hist_val in zip(dates, macd_line, signal_line, histogram):
      points.append(MACDPoint(
         date=date,
         macd=_nan_to_none(macd_val),
         signal=_nan_to_none(signal_val),
         histogram=_nan_to_none(hist_val),
      ))
   return points


# ── Bollinger Bands ───────────────────────────────────────────────────────────

def compute_bollinger(
    df: pd.DataFrame,
    period: int = 20,
    std_dev: float = 2.0,
) -> list[BollingerPoint]:
   '''
   Compute Bollinger Bands (upper, middle, lower) over the 'close' column.

   Steps:
   1. Middle band: rolling_mean = df['close'].rolling(window=period).mean()
   2. Rolling standard deviation: rolling_std = df['close'].rolling(window=period).std()
      pandas .std() uses ddof=1 (sample std) by default — this matches most
      charting platforms including TradingView.
   3. Upper band: rolling_mean + (std_dev * rolling_std)
   4. Lower band: rolling_mean - (std_dev * rolling_std)
   5. The first (period - 1) rows will be NaN for all three bands — apply
      _nan_to_none and construct BollingerPoint objects.
   6. Return the list.
   '''
   rolling_mean = df['close'].rolling(window=period).mean()
   rolling_std = df['close'].rolling(window=period).std()
   upper_band = rolling_mean + (std_dev * rolling_std)
   lower_band = rolling_mean - (std_dev * rolling_std)
   dates = _df_to_date_strings(df)
   points = []
   for date, upper, middle, lower in zip(dates, upper_band, rolling_mean, lower_band):
      points.append(BollingerPoint(
         date=date,
         upper=_nan_to_none(upper),
         middle=_nan_to_none(middle),
         lower=_nan_to_none(lower),
      ))
   return points


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def fetch_indicators(
    ticker: str,
    days: int,
    sma_periods: list[int] | None = None,
    ema_periods: list[int] | None = None,
    rsi_period: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    bb_period: int = 20,
    bb_std: float = 2.0,
) -> IndicatorsResponse:
   '''
   Load data and compute all indicators for a single ticker.

   sma_periods / ema_periods: lists of MA periods to compute (default covers
   the full standard set — 10/20/50/100/200 SMA, 9/12/20/26/50/200 EMA).
   All series are always returned; the frontend decides which to display.

   Warm-up buffer is the maximum of all requested periods plus the MACD
   slow+signal window, so the first visible candle always has a valid value
   for every indicator where mathematically possible.
   '''
   if sma_periods is None:
      sma_periods = [10, 20, 50, 100, 200]
   if ema_periods is None:
      ema_periods = [9, 12, 20, 26, 50, 200]
   max_ma_period = max(max(sma_periods), max(ema_periods), bb_period)
   warmup_buffer = max(macd_slow + macd_signal, rsi_period + 1, max_ma_period)
   df = await _load_ticker_df(ticker, days + warmup_buffer)
   sma_list = [
      SMAResponse(ticker=ticker, period=p, values=compute_sma(df, p)[-days:])
      for p in sma_periods
   ]
   ema_list = [
      EMAResponse(ticker=ticker, period=p, values=compute_ema(df, p)[-days:])
      for p in ema_periods
   ]
   rsi_points = compute_rsi(df, rsi_period)[-days:]
   macd_points = compute_macd(df, macd_fast, macd_slow, macd_signal)[-days:]
   bollinger_points = compute_bollinger(df, bb_period, bb_std)[-days:]
   return IndicatorsResponse(
      ticker=ticker,
      days=days,
      sma=sma_list,
      ema=ema_list,
      rsi=RSIResponse(ticker=ticker, period=rsi_period, values=rsi_points),
      macd=MACDResponse(ticker=ticker, fast=macd_fast, slow=macd_slow, signal_period=macd_signal, values=macd_points),
      bollinger=BollingerResponse(ticker=ticker, period=bb_period, std_dev=bb_std, values=bollinger_points),
   )
