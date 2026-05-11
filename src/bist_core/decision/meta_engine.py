"""PRDV3 Meta-Portfolio Engine — regime-aware capital allocation.

Architecture:

    bars → V2 (edge detection + regime filter) → MetaDecisionEngine
         → (regime classify + capital_mult) → PortfolioDecisionEngine
         → (position caps + scoring + risk sizing) → BacktestEngine

The meta engine adds regime-based CAPITAL INTELLIGENCE to the V2 edge:

1. REGIME CLASSIFIER: classifies each bar into one of four regimes
   using only price, volatility, and trend structure (no lookahead).

2. CAPITAL ALLOCATOR: adjusts position size via regime confidence
   multiplier. Scales up in TRENDING_UP (1.2x), scales down in
   TRENDING_DOWN (0.6x) and HIGH_VOLATILITY (0.7x).

3. EDGE-REGIME PENALTY: reduces capital for known weak edge-regime
   combinations (e.g., trend_pullback in HIGH_VOL → 0.5x penalty).

The meta engine does NOT block edges or duplicate V2's regime logic.
V2 handles all edge detection and internal regime filtering.
All logic is deterministic. No ML, no randomness, no future data.
"""

from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional

from bist_core.decision.bist_edge_v2 import (
    _MIN_BARS,
    _SMA_LONG,
    _SMA_SHORT,
    _gap_fade_signal,
    _mean_reversion_signal,
    _momentum_continuation_signal,
    _relative_strength_signal,
    _sector_rotation_signal,
    _sma,
    _stddev_returns,
    _trend_pullback_signal,
    _vol_compression_breakout_signal,
)
from bist_core.decision.mtf_regime import mtf_confidence_mult
from bist_core.models.ohlcv import OHLCVBar

# ===================================================================
# STEP 2 — Regime Classification
# ===================================================================


class Regime(enum.Enum):
    """Market regime — deterministic classification from price/vol/trend."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"


# Regime thresholds (structural, not optimized)
_VOL_THRESHOLD = 0.035  # daily return stddev above this → HIGH_VOL
_RANGE_BAND = 0.01  # |SMA20 - SMA50| / SMA50 < this → RANGING
_TREND_CONFIRM_BARS = 3  # SMA20 vs SMA50 must hold N bars for trend


def classify_regime(closes: List[float]) -> Regime:
    """Classify market regime from a close-price series.

    Decision tree (evaluated top-down, first match wins):
    1. HIGH_VOLATILITY: if 20-day return stddev > threshold
    2. RANGING: if |SMA20 - SMA50| / SMA50 < range_band
    3. TRENDING_UP: if SMA20 > SMA50 for N consecutive bars
    4. TRENDING_DOWN: else

    Uses only: price (closes), volatility (stddev_returns), trend (SMA).
    No future data. No external inputs.
    """
    n = len(closes)
    if n < _SMA_LONG + _TREND_CONFIRM_BARS:
        return Regime.RANGING  # insufficient data → conservative

    # 1. Volatility check first (overrides trend)
    vol = _stddev_returns(closes, _SMA_SHORT)
    if vol >= _VOL_THRESHOLD:
        return Regime.HIGH_VOLATILITY

    # 2. Range check — SMAs converged
    sma20 = _sma(closes, _SMA_SHORT)
    sma50 = _sma(closes, _SMA_LONG)
    if sma50 > 0 and abs(sma20 - sma50) / sma50 < _RANGE_BAND:
        return Regime.RANGING

    # 3. Trend confirmation — SMA20 vs SMA50 must hold for N bars
    consecutive_up = 0
    for i in range(n - _TREND_CONFIRM_BARS, n):
        window = closes[: i + 1]
        s20 = _sma(window, _SMA_SHORT)
        s50 = _sma(window, _SMA_LONG)
        if s20 > s50:
            consecutive_up += 1
        else:
            consecutive_up = 0

    if consecutive_up >= _TREND_CONFIRM_BARS:
        return Regime.TRENDING_UP

    return Regime.TRENDING_DOWN


# ===================================================================
# STEP 3 — Edge-Regime Map (empirical evidence)
# ===================================================================
#
# Evidence from meta_root_cause.py analysis:
#
# trend_pullback:
#   - 383 signals, avg next-bar return = -0.161%
#   - 78% fire in TRENDING_UP (correct), 18% in HIGH_VOL (wrong)
#   - CONCLUSION: allow ONLY in TRENDING_UP
#
# mean_reversion:
#   - 266 signals, avg next-bar return = +0.058%
#   - 35% in RANGING (correct), 30% in TRENDING_DOWN (reasonable)
#   - CONCLUSION: allow in RANGING and TRENDING_DOWN
#
# vol_breakout:
#   - 38 signals, avg next-bar return = +0.038%
#   - 34% in HIGH_VOL, 39% in TRENDING_UP
#   - CONCLUSION: allow in HIGH_VOL and TRENDING_UP
#

# Regime confidence multiplier for position sizing
# Higher confidence → larger allocation (0.5 to 1.5 range)
_REGIME_CAPITAL_MULT: dict[Regime, float] = {
    Regime.TRENDING_UP: 1.2,       # highest confidence — trend + pullback proven
    Regime.RANGING: 1.0,           # neutral — mean reversion works but lower freq
    Regime.HIGH_VOLATILITY: 0.7,   # caution — breakouts work but high variance
    Regime.TRENDING_DOWN: 0.6,     # lowest — only mean reversion, defensive
}

# Edge-regime PENALTY: reduce capital for known weak combinations.
# Evidence: trend_pullback in HIGH_VOL has -0.161% avg next-bar return.
# We don't BLOCK the signal (V2 already handles that), but we PENALIZE
# the allocation to reduce drawdown contribution.
_EDGE_REGIME_PENALTY: dict[str, set[Regime]] = {
    "trend_pullback": {Regime.HIGH_VOLATILITY, Regime.TRENDING_DOWN},
    "vol_breakout": {Regime.TRENDING_DOWN},
    "mean_reversion": set(),  # no penalty — works across multiple regimes
    "gap_fade": {Regime.TRENDING_UP},
    "rs_momentum": {Regime.TRENDING_DOWN},  # RS struggles in broad selloffs
    "sector_rotation": set(),  # sector momentum works across regimes
    "momentum_cont": {Regime.HIGH_VOLATILITY},  # momentum unreliable in high vol
}
_PENALTY_FACTOR = 0.5  # halve capital for penalized combos


# ===================================================================
# Edge identification (post-hoc, no side effects)
# ===================================================================

def _identify_edge(
    closes: List[float],
    volumes: List[float],
    bars_window: Optional[List[OHLCVBar]] = None,
    symbol: Optional[str] = None,
    universe_closes: Optional[dict[str, List[float]]] = None,
) -> str:
    """Identify which edge most likely fired. Best-effort, for logging."""
    if _trend_pullback_signal(closes, volumes):
        return "trend_pullback"
    if _vol_compression_breakout_signal(closes, volumes):
        return "vol_breakout"
    if _mean_reversion_signal(closes, volumes):
        return "mean_reversion"
    if bars_window is not None and _gap_fade_signal(bars_window, closes, volumes):
        return "gap_fade"
    if _momentum_continuation_signal(closes, volumes):
        return "momentum_cont"
    if symbol and universe_closes and _relative_strength_signal(symbol, closes, universe_closes):
        return "rs_momentum"
    if symbol and universe_closes and _sector_rotation_signal(symbol, closes, universe_closes):
        return "sector_rotation"
    return "unknown"


# ===================================================================
# STEP 4 — Meta Decision Engine
# ===================================================================


class MetaDecisionEngine:
    """Regime-aware capital allocator wrapping BistEdgeV2Decision.

    Callable matching DecisionFunction protocol:
        (symbol, bars, bar_index) -> Optional[Dict]

    Architecture:
    - V2 handles ALL edge detection and internal regime filtering.
      Its regime checks are tuned to its edges — don't override them.
    - Meta engine adds: regime classification + capital multiplier.
    - Portfolio wrapper adds: position caps, scoring, risk sizing.

    The meta engine does NOT block edges. It adjusts how much capital
    the portfolio wrapper allocates per trade based on regime confidence.
    This avoids the double-filtering problem where meta regime logic
    conflicts with V2's internal regime logic.
    """

    def __init__(self) -> None:
        from bist_core.decision.bist_edge_v2 import BistEdgeV2Decision
        self._edge = BistEdgeV2Decision()

    def __call__(
        self,
        symbol: str,
        bars: List[OHLCVBar],
        bar_index: int,
    ) -> Optional[Dict[str, Any]]:
        if bar_index < _MIN_BARS or not bars:
            return None

        # --- V2 handles everything: cooldown, regime, quality, edges ---
        decision = self._edge(symbol, bars, bar_index)
        if decision is None:
            return None

        # --- Classify regime for capital allocation ---
        window = bars[: bar_index + 1]
        closes = [float(b.close) for b in window]
        regime = classify_regime(closes)

        # --- Edge name comes directly from V2 decision ---
        edge_name = decision.get("edge", "")
        if not edge_name:
            # Fallback: post-hoc identification (shouldn't happen now)
            volumes = [float(b.volume) for b in window]
            universe_closes = getattr(self._edge, "_universe_closes", None)
            edge_name = _identify_edge(
                closes, volumes,
                bars_window=window,
                symbol=symbol,
                universe_closes=universe_closes,
            )

        # --- MTF confidence: graded capital adjustment by horizon alignment ---
        mtf_mult = mtf_confidence_mult(closes, list(window), edge_name)

        # --- Capital multiplier based on regime ---
        capital_mult = _REGIME_CAPITAL_MULT.get(regime, 1.0)

        # --- Edge-regime penalty: reduce capital for known weak combos ---
        if edge_name and regime in _EDGE_REGIME_PENALTY.get(edge_name, set()):
            capital_mult *= _PENALTY_FACTOR

        # Apply MTF confidence scaling
        capital_mult *= mtf_mult

        decision["regime"] = regime.value
        decision["edge"] = edge_name
        decision["capital_mult"] = capital_mult
        return decision


__all__ = [
    "MetaDecisionEngine",
    "Regime",
    "classify_regime",
]
