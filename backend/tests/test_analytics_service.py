"""Tests for analytics_service — pure computation feeding the AI Explanation Layer."""

import pandas as pd
import pytest

from services.analytics_service import (
    classify_bollinger,
    classify_macd,
    classify_rsi,
    confidence,
    rsi_recovery_stats,
    sma_trend,
    volume_vs_average,
)


# ── classify_rsi ──────────────────────────────────────────────────────────────

def test_classify_rsi_overbought():
    assert classify_rsi(70) == "overbought"
    assert classify_rsi(85) == "overbought"


def test_classify_rsi_oversold():
    assert classify_rsi(30) == "oversold"
    assert classify_rsi(10) == "oversold"


def test_classify_rsi_neutral():
    assert classify_rsi(50) == "neutral"
    assert classify_rsi(69.9) == "neutral"
    assert classify_rsi(30.1) == "neutral"


def test_classify_rsi_none():
    assert classify_rsi(None) is None


# ── classify_bollinger ────────────────────────────────────────────────────────

def test_classify_bollinger_above_upper():
    assert classify_bollinger(110, upper=105, middle=100, lower=95) == "above_upper"


def test_classify_bollinger_below_lower():
    assert classify_bollinger(90, upper=105, middle=100, lower=95) == "below_lower"


def test_classify_bollinger_upper_half():
    assert classify_bollinger(102, upper=105, middle=100, lower=95) == "upper_half"


def test_classify_bollinger_lower_half():
    assert classify_bollinger(98, upper=105, middle=100, lower=95) == "lower_half"


def test_classify_bollinger_missing_value():
    assert classify_bollinger(100, upper=None, middle=100, lower=95) is None


# ── classify_macd ─────────────────────────────────────────────────────────────

def test_classify_macd_bullish_cross():
    recent = [{"macd": -1, "signal": 0}, {"macd": 1, "signal": 0}]
    assert classify_macd(recent) == "bullish_cross"


def test_classify_macd_bearish_cross():
    recent = [{"macd": 1, "signal": 0}, {"macd": -1, "signal": 0}]
    assert classify_macd(recent) == "bearish_cross"


def test_classify_macd_above_signal_no_cross():
    recent = [{"macd": 2, "signal": 1}, {"macd": 3, "signal": 1}]
    assert classify_macd(recent) == "above_signal"


def test_classify_macd_below_signal_no_cross():
    recent = [{"macd": -2, "signal": -1}, {"macd": -3, "signal": -1}]
    assert classify_macd(recent) == "below_signal"


def test_classify_macd_empty():
    assert classify_macd([]) is None


def test_classify_macd_all_none():
    assert classify_macd([{"macd": None, "signal": None}]) is None


# ── sma_trend ─────────────────────────────────────────────────────────────────

def test_sma_trend_above_both():
    assert sma_trend(110, sma50=100, sma200=90) == "above_both"


def test_sma_trend_below_both():
    assert sma_trend(80, sma50=100, sma200=90) == "below_both"


def test_sma_trend_mixed():
    assert sma_trend(95, sma50=100, sma200=90) == "mixed"


def test_sma_trend_missing_value():
    assert sma_trend(100, sma50=None, sma200=90) is None


# ── volume_vs_average ─────────────────────────────────────────────────────────

def test_volume_vs_average_insufficient_history():
    df = pd.DataFrame({"volume": [100, 100, 100, 100, 100]})
    assert volume_vs_average(df, window=20) is None


def test_volume_vs_average_computed():
    df = pd.DataFrame({"volume": [100, 100, 100, 100, 200]})
    # trailing 3-day average (indices 1,2,3) = 100; latest (index 4) = 200
    assert volume_vs_average(df, window=3) == pytest.approx(100.0)


# ── rsi_recovery_stats ────────────────────────────────────────────────────────

def _series_with_crossings(length: int, crossings: dict[int, tuple[float, float]]) -> tuple[list, list]:
    """Build (closes, rsi_values) of `length` with an RSI oversold crossing at
    each key of `crossings` (prev-day, curr-day values), flat elsewhere."""
    closes = [100.0] * length
    rsi_values: list[float | None] = [50.0] * length
    for idx, (prev, curr) in crossings.items():
        rsi_values[idx - 1] = prev
        rsi_values[idx] = curr
    return closes, rsi_values


def test_rsi_recovery_stats_none_below_min_occurrences():
    closes, rsi_values = _series_with_crossings(20, {2: (40, 25), 8: (40, 20)})
    assert rsi_recovery_stats(closes, rsi_values, horizon_days=2) is None


def test_rsi_recovery_stats_computed_with_enough_occurrences():
    closes = [100.0] * 20
    _, rsi_values = _series_with_crossings(20, {2: (40, 25), 8: (40, 20), 14: (42, 28)})
    # Occurrence 1 (entry idx 2 -> exit idx 4): recovers
    closes[4] = 110.0
    # Occurrence 2 (entry idx 8 -> exit idx 10): does not recover
    closes[10] = 90.0
    # Occurrence 3 (entry idx 14 -> exit idx 16): recovers
    closes[16] = 120.0

    result = rsi_recovery_stats(closes, rsi_values, horizon_days=2)

    assert result is not None
    assert result["occurrences"] == 3
    assert result["horizon_days"] == 2
    assert result["recovered_pct"] == pytest.approx(66.7, abs=0.1)
    assert result["avg_return_pct"] == pytest.approx(6.7, abs=0.1)


# ── confidence ────────────────────────────────────────────────────────────────

def test_confidence_high_with_news():
    assert confidence(history_days=250, recovery_occurrences=5, has_news=True) == "high"


def test_confidence_downgraded_without_news():
    assert confidence(history_days=250, recovery_occurrences=5, has_news=False) == "medium"


def test_confidence_medium_with_moderate_history():
    assert confidence(history_days=100, recovery_occurrences=0, has_news=True) == "medium"


def test_confidence_low_with_short_history():
    assert confidence(history_days=30, recovery_occurrences=0, has_news=True) == "low"
