"""BIST Edge V1 — structural BIST-specific decision function (deterministic).

Combines two validated edges:
1. Trend Pullback: buy when price pulls back to SMA20 in a confirmed uptrend
   (SMA20 > SMA50, rising SMA20, adequate volume).
2. Volatility Compression Breakout: buy on 20-bar high breakout after volatility
   compression (10-bar stddev < 75% of 20-bar stddev) with volume expansion.

Both edges are structural, not indicator-soup. They exploit:
- BIST trend persistence in liquid mid/large caps
- BIST volatility clustering and expansion behavior after compression
- Volume confirmation to filter false signals

Risk model: 3% stop, 5% target, 10-bar max hold.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Constants — no randomness, no hidden parameters
# ---------------------------------------------------------------------------

_MIN_BARS_TREND = 50
_MIN_BARS_BREAKOUT = 30
_SMA_SHORT = 20
_SMA_LONG = 50
_SMA_SLOPE_LOOKBACK = 5
_PULLBACK_LOWER = -0.02
_PULLBACK_UPPER = 0.008
_VOLUME_FLOOR_RATIO = 0.7
_VOLUME_LOOKBACK = 10

_BREAKOUT_LOOKBACK = 20
_VOL_COMPRESS_THRESHOLD = 0.75
_BREAKOUT_VOLUME_RATIO = 1.1
_RETS_SHORT = 10
_RETS_LONG = 20

_STOP_PCT = 0.03
_TARGET_PCT = 0.05
_POSITION_SIZE = 10


# ---------------------------------------------------------------------------
# Feature extraction (pure, no side effects)
# ---------------------------------------------------------------------------

def _sma(closes: List[float], period: int) -> float:
    """Simple moving average over the last `period` closes."""
    if len(closes) < period:
        return 0.0
    return sum(closes[-period:]) / period


def _stddev_returns(closes: List[float], period: int) -> float:
    """Population standard deviation of returns over the last `period` closes."""
    if len(closes) < period + 1:
        return 0.0
    rets: list[float] = []
    start = len(closes) - period
    for j in range(start, len(closes)):
        prev = closes[j - 1]
        if prev <= 0:
            continue
        rets.append((closes[j] - prev) / prev)
    if len(rets) < 2:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return var ** 0.5


# ---------------------------------------------------------------------------
# Edge 1: Trend Pullback
# ---------------------------------------------------------------------------

def _trend_pullback_signal(
    closes: List[float],
    volumes: List[float],
) -> bool:
    """Uptrend pullback to SMA20 with volume confirmation."""
    n = len(closes)
    if n < _MIN_BARS_TREND:
        return False

    sma20 = _sma(closes, _SMA_SHORT)
    sma50 = _sma(closes, _SMA_LONG)

    # Uptrend: SMA20 > SMA50
    if sma20 <= sma50:
        return False

    # SMA20 must be rising (current vs 5 bars ago)
    if n < _SMA_SHORT + _SMA_SLOPE_LOOKBACK:
        return False
    sma20_prev = sum(closes[-(
        _SMA_SHORT + _SMA_SLOPE_LOOKBACK
    ): -_SMA_SLOPE_LOOKBACK]) / _SMA_SHORT
    if sma20 <= sma20_prev:
        return False

    # Price pulled back to SMA20 zone
    current = closes[-1]
    if sma20 <= 0:
        return False
    dist = (current - sma20) / sma20
    if not (_PULLBACK_LOWER <= dist <= _PULLBACK_UPPER):
        return False

    # Price above SMA50
    if current <= sma50:
        return False

    # Volume check
    if len(volumes) < _VOLUME_LOOKBACK:
        return False
    avg_vol = sum(volumes[-_VOLUME_LOOKBACK:]) / _VOLUME_LOOKBACK
    if avg_vol <= 0:
        return False
    if volumes[-1] < avg_vol * _VOLUME_FLOOR_RATIO:
        return False

    return True


# ---------------------------------------------------------------------------
# Edge 2: Volatility Compression Breakout
# ---------------------------------------------------------------------------

def _vol_compression_breakout_signal(
    closes: List[float],
    volumes: List[float],
) -> bool:
    """Breakout above 20-bar high after volatility compression with volume expansion."""
    n = len(closes)
    if n < _MIN_BARS_BREAKOUT:
        return False

    # 20-bar high breakout
    high20 = max(closes[-_BREAKOUT_LOOKBACK - 1: -1])
    if closes[-1] <= high20:
        return False

    # Volatility compression: recent < longer-term
    std_short = _stddev_returns(closes, _RETS_SHORT)
    std_long = _stddev_returns(closes, _RETS_LONG)
    if std_long <= 0:
        return False
    if std_short / std_long >= _VOL_COMPRESS_THRESHOLD:
        return False

    # Volume expansion on breakout
    if len(volumes) < _VOLUME_LOOKBACK:
        return False
    avg_vol = sum(volumes[-_VOLUME_LOOKBACK:]) / _VOLUME_LOOKBACK
    if avg_vol <= 0:
        return False
    if volumes[-1] < avg_vol * _BREAKOUT_VOLUME_RATIO:
        return False

    return True


# ---------------------------------------------------------------------------
# Combined decision function
# ---------------------------------------------------------------------------

def bist_edge_v1_decision(
    symbol: str,
    bars: List[OHLCVBar],
    bar_index: int,
) -> Optional[Dict[str, Any]]:
    """BIST Edge V1 decision function. Returns a decision dict or None."""
    if bar_index < _MIN_BARS_TREND or not bars:
        return None

    # Extract closes and volumes up to current bar (inclusive, no lookahead)
    window = bars[: bar_index + 1]
    closes = [float(b.close) for b in window]
    volumes = [float(b.volume) for b in window]

    if len(closes) < _MIN_BARS_TREND:
        return None

    signal = (
        _trend_pullback_signal(closes, volumes)
        or _vol_compression_breakout_signal(closes, volumes)
    )

    if not signal:
        return None

    entry = closes[-1]
    if entry <= 0:
        return None

    stop = round(entry * (1.0 - _STOP_PCT), 4)
    target = round(entry * (1.0 + _TARGET_PCT), 4)

    return {
        "symbol": symbol,
        "entry": entry,
        "stop": stop,
        "target": target,
        "position_size": _POSITION_SIZE,
    }


__all__ = ["bist_edge_v1_decision"]
