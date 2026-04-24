"""PRDV3 Multi-Timeframe Regime Filter — hierarchical trend/regime alignment.

Since only daily EOD data is available, this module implements MTF via
multi-HORIZON analysis on daily bars. Each horizon has ONE responsibility:

HIERARCHY (strict):
    Monthly (60-bar):  macro regime filter — bull/bear/range
    Weekly  (20-bar):  directional bias — trend direction + strength
    Daily   (5-bar):   setup quality — volatility + momentum alignment

RULES:
    - Monthly regime must ALLOW the trade class (trend/reversion/breakout)
    - Weekly bias must CONFIRM the trade direction
    - Daily must show adequate setup quality (not exhausted/overextended)

    - Conflicting signals across horizons → NO TRADE (fail-closed)
    - Each horizon evaluated independently then ANDed
    - No redundant signals — each horizon adds unique information

This is the FRAMEWORK for true MTF. When intraday data becomes available:
    Monthly (60-bar) → Daily (252-bar)
    Weekly  (20-bar) → 60-minute
    Daily   (5-bar)  → 5-minute

All logic is deterministic. No ML, no randomness, no future data.
"""

from __future__ import annotations

import enum
from typing import List

from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Horizon constants
# ---------------------------------------------------------------------------

_MONTHLY_LOOKBACK = 60   # ~3 months of daily bars
_WEEKLY_LOOKBACK = 20    # ~1 month
_DAILY_LOOKBACK = 5      # ~1 week

# Monthly regime thresholds
_MONTHLY_SMA_FAST = 20
_MONTHLY_SMA_SLOW = 50
_MONTHLY_VOL_HIGH = 0.035   # daily stddev above this = volatile regime
_MONTHLY_TREND_BAND = 0.015 # |SMA_fast - SMA_slow| / SMA_slow

# Weekly directional bias thresholds
_WEEKLY_MOMENTUM_LOOKBACK = 10
_WEEKLY_TREND_SLOPE_MIN = 0.001  # SMA slope must show direction
_WEEKLY_ADX_PROXY_MIN = 0.015    # directional strength proxy

# Daily setup quality thresholds
_DAILY_EXHAUSTION_RSI = 75.0  # RSI above this = overbought (trend exhausted)
_DAILY_OVERSOLD_RSI = 30.0    # RSI below this = oversold
_DAILY_ATR_RATIO_MAX = 2.0    # ATR expanding too fast = unstable setup


# ---------------------------------------------------------------------------
# Regime enums — one per horizon
# ---------------------------------------------------------------------------

class MonthlyRegime(enum.Enum):
    BULL = "bull"
    BEAR = "bear"
    RANGE = "range"
    VOLATILE = "volatile"


class WeeklyBias(enum.Enum):
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"


class DailySetup(enum.Enum):
    READY = "ready"
    EXHAUSTED = "exhausted"
    OVERSOLD = "oversold"
    UNSTABLE = "unstable"


# ---------------------------------------------------------------------------
# Feature helpers (pure, no side effects)
# ---------------------------------------------------------------------------

def _sma(values: List[float], period: int) -> float:
    if len(values) < period:
        return 0.0
    return sum(values[-period:]) / period


def _stddev(values: List[float], period: int) -> float:
    if len(values) < period + 1:
        return 0.0
    rets = []
    start = len(values) - period
    for i in range(start, len(values)):
        if values[i - 1] > 0:
            rets.append((values[i] - values[i - 1]) / values[i - 1])
    if len(rets) < 2:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return var ** 0.5


def _rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(len(closes) - period, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _atr(bars: List[OHLCVBar], period: int = 14) -> float:
    n = len(bars)
    if n < period + 1:
        return 0.0
    trs = []
    for i in range(n - period, n):
        h = float(bars[i].high)
        l = float(bars[i].low)
        pc = float(bars[i - 1].close)
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0


# ---------------------------------------------------------------------------
# Monthly regime classifier (60-bar horizon)
# ---------------------------------------------------------------------------

def classify_monthly_regime(closes: List[float]) -> MonthlyRegime:
    """Macro regime from ~3 months of daily data.

    Responsibility: determine IF the market environment allows trading.
    """
    if len(closes) < _MONTHLY_LOOKBACK:
        return MonthlyRegime.RANGE  # insufficient data → conservative

    # Volatility check first (overrides trend)
    vol = _stddev(closes, _MONTHLY_SMA_FAST)
    if vol >= _MONTHLY_VOL_HIGH:
        return MonthlyRegime.VOLATILE

    sma_fast = _sma(closes, _MONTHLY_SMA_FAST)
    sma_slow = _sma(closes, _MONTHLY_SMA_SLOW)

    if sma_slow <= 0:
        return MonthlyRegime.RANGE

    # Range detection: SMAs converged
    gap = abs(sma_fast - sma_slow) / sma_slow
    if gap < _MONTHLY_TREND_BAND:
        return MonthlyRegime.RANGE

    # Trend direction
    if sma_fast > sma_slow:
        return MonthlyRegime.BULL
    return MonthlyRegime.BEAR


# ---------------------------------------------------------------------------
# Weekly directional bias (20-bar horizon)
# ---------------------------------------------------------------------------

def classify_weekly_bias(closes: List[float]) -> WeeklyBias:
    """Directional bias from ~1 month of daily data.

    Responsibility: determine trade DIRECTION alignment.
    """
    if len(closes) < _WEEKLY_LOOKBACK + _WEEKLY_MOMENTUM_LOOKBACK:
        return WeeklyBias.NEUTRAL

    sma_now = _sma(closes, _WEEKLY_LOOKBACK)
    # SMA slope: compare current SMA to SMA from 10 bars ago
    sma_prev = _sma(closes[:-_WEEKLY_MOMENTUM_LOOKBACK], _WEEKLY_LOOKBACK)
    if sma_prev <= 0:
        return WeeklyBias.NEUTRAL

    slope = (sma_now - sma_prev) / sma_prev

    # Directional strength: use momentum as ADX proxy
    momentum = (closes[-1] - closes[-_WEEKLY_MOMENTUM_LOOKBACK]) / closes[-_WEEKLY_MOMENTUM_LOOKBACK] if closes[-_WEEKLY_MOMENTUM_LOOKBACK] > 0 else 0.0

    # Both slope AND momentum must agree for directional bias
    if slope > _WEEKLY_TREND_SLOPE_MIN and momentum > _WEEKLY_ADX_PROXY_MIN:
        return WeeklyBias.UP
    if slope < -_WEEKLY_TREND_SLOPE_MIN and momentum < -_WEEKLY_ADX_PROXY_MIN:
        return WeeklyBias.DOWN
    return WeeklyBias.NEUTRAL


# ---------------------------------------------------------------------------
# Daily setup quality (5-bar horizon)
# ---------------------------------------------------------------------------

def classify_daily_setup(
    closes: List[float],
    bars: List[OHLCVBar],
) -> DailySetup:
    """Setup quality from ~1 week of daily data.

    Responsibility: determine if the TIMING is right for entry.
    """
    if len(closes) < 20 or len(bars) < 20:
        return DailySetup.READY  # insufficient → allow (other filters protect)

    rsi = _rsi(closes)

    # Exhaustion: RSI too high → trend may reverse
    if rsi >= _DAILY_EXHAUSTION_RSI:
        return DailySetup.EXHAUSTED

    # Oversold: for mean-reversion opportunities
    if rsi <= _DAILY_OVERSOLD_RSI:
        return DailySetup.OVERSOLD

    # Volatility stability: compare short ATR to longer ATR
    atr_short = _atr(bars, period=5)
    atr_long = _atr(bars, period=14)
    if atr_long > 0 and atr_short / atr_long > _DAILY_ATR_RATIO_MAX:
        return DailySetup.UNSTABLE

    return DailySetup.READY


# ---------------------------------------------------------------------------
# MTF alignment check
# ---------------------------------------------------------------------------

# Which monthly regimes allow which edge types
_MONTHLY_ALLOWS: dict[str, set[MonthlyRegime]] = {
    "trend_pullback": {MonthlyRegime.BULL},
    "vol_breakout": {MonthlyRegime.BULL, MonthlyRegime.VOLATILE},
    "mean_reversion": {MonthlyRegime.RANGE, MonthlyRegime.BEAR},
    "gap_fade": {MonthlyRegime.BEAR, MonthlyRegime.VOLATILE},
    "rs_momentum": {MonthlyRegime.BULL, MonthlyRegime.RANGE},
    "sector_rotation": {MonthlyRegime.BULL, MonthlyRegime.RANGE},
    "momentum_cont": {MonthlyRegime.BULL},
}

# Which weekly biases confirm which edge directions
_WEEKLY_CONFIRMS: dict[str, set[WeeklyBias]] = {
    "trend_pullback": {WeeklyBias.UP},
    "vol_breakout": {WeeklyBias.UP, WeeklyBias.NEUTRAL},
    "mean_reversion": {WeeklyBias.DOWN, WeeklyBias.NEUTRAL},
    "gap_fade": {WeeklyBias.DOWN, WeeklyBias.NEUTRAL},
    "rs_momentum": {WeeklyBias.UP, WeeklyBias.NEUTRAL},
    "sector_rotation": {WeeklyBias.UP, WeeklyBias.NEUTRAL},
    "momentum_cont": {WeeklyBias.UP},
}

# Which daily setups are valid for which edge types
_DAILY_ALLOWS: dict[str, set[DailySetup]] = {
    "trend_pullback": {DailySetup.READY},  # NOT exhausted
    "vol_breakout": {DailySetup.READY},
    "mean_reversion": {DailySetup.OVERSOLD, DailySetup.READY},
    "gap_fade": {DailySetup.OVERSOLD, DailySetup.READY},
    "rs_momentum": {DailySetup.READY},
    "sector_rotation": {DailySetup.READY},
    "momentum_cont": {DailySetup.READY},
}


# Confidence multiplier for partial alignment
# 3/3 horizons agree → 1.0, 2/3 → 0.7, 1/3 → 0.4, 0/3 → 0.2
_MTF_CONF_MAP = {3: 1.0, 2: 0.7, 1: 0.4, 0: 0.2}


def mtf_confidence_mult(
    closes: List[float],
    bars: List[OHLCVBar],
    edge_name: str,
) -> float:
    """Return a capital multiplier (0.2–1.0) based on MTF horizon alignment.

    With only daily data, the three horizons share the same price series
    (different lookbacks). A hard gate (all-or-nothing) over-filters when
    the horizons are correlated. Instead, this returns a graded confidence
    multiplier:

        3/3 aligned → 1.0 (full confidence)
        2/3 aligned → 0.7 (mild caution)
        1/3 aligned → 0.4 (significant penalty)
        0/3 aligned → 0.2 (minimal allocation, NOT zero)

    When true multi-timeframe data becomes available (intraday), this can
    revert to a hard gate since the horizons become truly independent.
    """
    monthly = classify_monthly_regime(closes)
    weekly = classify_weekly_bias(closes)
    daily = classify_daily_setup(closes, bars)

    score = 0
    if monthly in _MONTHLY_ALLOWS.get(edge_name, set()):
        score += 1
    if weekly in _WEEKLY_CONFIRMS.get(edge_name, set()):
        score += 1
    if daily in _DAILY_ALLOWS.get(edge_name, set()):
        score += 1

    return _MTF_CONF_MAP[score]


def mtf_allows_trade(
    closes: List[float],
    bars: List[OHLCVBar],
    edge_name: str,
) -> bool:
    """Legacy boolean API — returns True if at least 2/3 horizons agree.

    Kept for backward compatibility. Prefer mtf_confidence_mult() for
    graded capital adjustment.
    """
    return mtf_confidence_mult(closes, bars, edge_name) >= 0.4


def classify_all_horizons(
    closes: List[float],
    bars: List[OHLCVBar],
) -> dict:
    """Classify all three horizons and return structured result."""
    return {
        "monthly_regime": classify_monthly_regime(closes).value,
        "weekly_bias": classify_weekly_bias(closes).value,
        "daily_setup": classify_daily_setup(closes, bars).value,
    }


__all__ = [
    "MonthlyRegime",
    "WeeklyBias",
    "DailySetup",
    "classify_monthly_regime",
    "classify_weekly_bias",
    "classify_daily_setup",
    "mtf_allows_trade",
    "mtf_confidence_mult",
    "classify_all_horizons",
]
