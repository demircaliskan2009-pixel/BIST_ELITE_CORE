"""Deterministic technical indicator library — pure Python, no numpy/pandas.

All functions accept ``list[OHLCVBar]`` and return ``list[float | None]``
of the **same length** as the input.  Positions where the indicator cannot
be computed are ``None``.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from bist_core.backtest.backtest_engine import OHLCVBar


def sma(bars: Sequence[OHLCVBar], period: int) -> List[Optional[float]]:
    """Simple Moving Average of close prices over *period* bars."""
    n = len(bars)
    if period < 1:
        return [None] * n
    result: list[float | None] = [None] * n
    window_sum = 0.0
    for i in range(n):
        window_sum += bars[i].close
        if i >= period:
            window_sum -= bars[i - period].close
        if i >= period - 1:
            result[i] = round(window_sum / period, 6)
    return result


def ema(bars: Sequence[OHLCVBar], period: int) -> List[Optional[float]]:
    """Exponential Moving Average of close prices."""
    n = len(bars)
    if period < 1:
        return [None] * n
    result: list[float | None] = [None] * n
    if n < period:
        return result
    k = 2.0 / (period + 1)
    seed = sum(b.close for b in bars[:period]) / period
    result[period - 1] = round(seed, 6)
    prev = seed
    for i in range(period, n):
        val = bars[i].close * k + prev * (1.0 - k)
        result[i] = round(val, 6)
        prev = val
    return result


def rsi(bars: Sequence[OHLCVBar], period: int = 14) -> List[Optional[float]]:
    """Relative Strength Index (Wilder smoothing)."""
    n = len(bars)
    if period < 1 or n < period + 1:
        return [None] * n
    result: list[float | None] = [None] * n

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, n):
        diff = bars[i].close - bars[i - 1].close
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = round(100.0 - (100.0 / (1.0 + rs)), 6)

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        idx = i + 1
        if idx >= n:
            break
        if avg_loss == 0:
            result[idx] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[idx] = round(100.0 - (100.0 / (1.0 + rs)), 6)

    return result


def atr(bars: Sequence[OHLCVBar], period: int = 14) -> List[Optional[float]]:
    """Average True Range (Wilder smoothing)."""
    n = len(bars)
    if period < 1 or n < 2:
        return [None] * n
    result: list[float | None] = [None] * n

    tr_values: list[float] = [0.0]
    for i in range(1, n):
        hl = bars[i].high - bars[i].low
        hc = abs(bars[i].high - bars[i - 1].close)
        lc = abs(bars[i].low - bars[i - 1].close)
        tr_values.append(max(hl, hc, lc))

    if n < period + 1:
        return result

    first_atr = sum(tr_values[1 : period + 1]) / period
    result[period] = round(first_atr, 6)
    prev = first_atr

    for i in range(period + 1, n):
        val = (prev * (period - 1) + tr_values[i]) / period
        result[i] = round(val, 6)
        prev = val

    return result


def momentum_20(bars: Sequence[OHLCVBar]) -> List[Optional[float]]:
    """20-bar momentum: (close[N] - close[N-20]) / close[N-20] as decimal."""
    result: list[float | None] = []
    closes = [b.close for b in bars]
    for i in range(len(closes)):
        if i < 20:
            result.append(None)
        else:
            prev = closes[i - 20]
            if prev <= 0:
                result.append(None)
            else:
                result.append((closes[i] - prev) / prev)
    return result


def returns(bars: Sequence[OHLCVBar]) -> List[Optional[float]]:
    """Percentage returns: ``(close[i] - close[i-1]) / close[i-1] * 100``."""
    n = len(bars)
    result: list[float | None] = [None] * n
    for i in range(1, n):
        prev_close = bars[i - 1].close
        if prev_close != 0:
            result[i] = round((bars[i].close - prev_close) / prev_close * 100.0, 6)
    return result
