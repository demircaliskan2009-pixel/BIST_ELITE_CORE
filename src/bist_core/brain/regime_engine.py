"""Deterministic regime engine for normalized BIST OHLCV bars.

Priority order is explicit and fail-closed:
1. LOW_LIQUIDITY
2. TREND_UP / TREND_DOWN
3. VOLATILE
4. RANGE
5. NO_REGIME

Transition rules are also explicit. If a previous regime is provided, the
engine applies relaxed hold thresholds before allowing a switch, which reduces
state flicker on marginal bars.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Dict, Sequence

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.features.indicator_library import atr as compute_atr
from bist_core.features.indicator_library import sma as compute_sma
from bist_core.models.ohlcv import normalize_timestamp

TREND_UP = "TREND_UP"
TREND_DOWN = "TREND_DOWN"
RANGE = "RANGE"
VOLATILE = "VOLATILE"
LOW_LIQUIDITY = "LOW_LIQUIDITY"
NO_REGIME = "NO_REGIME"


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _round_metric(value: float) -> float:
    return round(float(value), 6)


@dataclass(frozen=True)
class RegimeMetrics:
    sma_fast: float
    sma_slow: float
    sma_slow_slope: float
    trend_gap: float
    atr_ratio: float
    return_std: float
    directional_consistency: float
    efficiency_ratio: float
    range_width_ratio: float
    recent_volume_ratio: float
    zero_volume_share: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "sma_fast": self.sma_fast,
            "sma_slow": self.sma_slow,
            "sma_slow_slope": self.sma_slow_slope,
            "trend_gap": self.trend_gap,
            "atr_ratio": self.atr_ratio,
            "return_std": self.return_std,
            "directional_consistency": self.directional_consistency,
            "efficiency_ratio": self.efficiency_ratio,
            "range_width_ratio": self.range_width_ratio,
            "recent_volume_ratio": self.recent_volume_ratio,
            "zero_volume_share": self.zero_volume_share,
        }


@dataclass(frozen=True)
class MarketRegime:
    regime: str
    confidence: float
    explanation: str
    timestamp: int
    metrics: RegimeMetrics

    @property
    def strength(self) -> float:
        return self.confidence

    @property
    def sma_fast(self) -> float:
        return self.metrics.sma_fast

    @property
    def sma_slow(self) -> float:
        return self.metrics.sma_slow

    def to_dict(self) -> Dict[str, Any]:
        metrics = self.metrics.to_dict()
        return {
            "regime": self.regime,
            "confidence": self.confidence,
            "strength": self.confidence,
            "explanation": self.explanation,
            "timestamp": self.timestamp,
            **metrics,
        }


class RegimeEngine:
    """Detect deterministic BIST market regimes from OHLCV only."""

    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 30,
        atr_period: int = 14,
        volume_window: int = 10,
        slope_window: int = 5,
    ) -> None:
        if fast_period < 2:
            raise ValueError("fast_period must be >= 2")
        if slow_period <= fast_period:
            raise ValueError("slow_period must be > fast_period")
        if atr_period < 2:
            raise ValueError("atr_period must be >= 2")
        if volume_window < 2:
            raise ValueError("volume_window must be >= 2")
        if slope_window < 1:
            raise ValueError("slope_window must be >= 1")

        self._fast = fast_period
        self._slow = slow_period
        self._atr = atr_period
        self._volume_window = volume_window
        self._slope_window = slope_window

    @property
    def fast_period(self) -> int:
        return self._fast

    @property
    def slow_period(self) -> int:
        return self._slow

    def detect_regime(
        self,
        bars: Sequence[OHLCVBar],
        previous_regime: MarketRegime | None = None,
    ) -> MarketRegime:
        timestamp = normalize_timestamp(bars[-1].timestamp) if bars else 0
        validation_error = self._validate_bars(bars)
        if validation_error is not None:
            return self._no_regime(timestamp, validation_error)

        metrics = self._compute_metrics(bars)
        if metrics is None:
            return self._no_regime(timestamp, "insufficient_history")

        raw_regime, raw_confidence, base_explanation = self._classify(metrics)
        final_regime, final_confidence, transition_note = self._apply_transition_rules(
            raw_regime,
            raw_confidence,
            previous_regime,
            metrics,
        )

        if final_regime == NO_REGIME:
            explanation = f"NO_REGIME: {base_explanation}; transition={transition_note}"
        else:
            explanation = f"{final_regime}: {base_explanation}; transition={transition_note}"

        return MarketRegime(
            regime=final_regime,
            confidence=round(final_confidence, 4),
            explanation=explanation,
            timestamp=timestamp,
            metrics=metrics,
        )

    def _validate_bars(self, bars: Sequence[OHLCVBar]) -> str | None:
        min_bars = max(self._slow + self._slope_window, self._atr + 1, self._volume_window)
        if len(bars) < min_bars:
            return "insufficient_bars"

        for bar in bars:
            if bar.close <= 0 or bar.open <= 0 or bar.high <= 0 or bar.low <= 0:
                return "non_positive_price"
            if bar.high < bar.low:
                return "high_below_low"
            if bar.volume < 0:
                return "negative_volume"
        return None

    def _compute_metrics(self, bars: Sequence[OHLCVBar]) -> RegimeMetrics | None:
        sma_fast_vals = compute_sma(bars, self._fast)
        sma_slow_vals = compute_sma(bars, self._slow)
        atr_vals = compute_atr(bars, self._atr)

        fast = sma_fast_vals[-1]
        slow = sma_slow_vals[-1]
        slow_prev = sma_slow_vals[-1 - self._slope_window]
        atr_value = atr_vals[-1]
        close = float(bars[-1].close)

        if fast is None or slow is None or slow_prev is None or atr_value is None or close <= 0:
            return None

        tail = bars[-self._slow :]
        returns = []
        path = 0.0
        direction_sum = 0
        for idx in range(1, len(tail)):
            prev_close = float(tail[idx - 1].close)
            curr_close = float(tail[idx].close)
            if prev_close <= 0:
                return None
            diff = curr_close - prev_close
            returns.append(diff / prev_close)
            path += abs(diff)
            if diff > 0:
                direction_sum += 1
            elif diff < 0:
                direction_sum -= 1

        if not returns or path <= 0:
            return None

        highs = [float(bar.high) for bar in tail]
        lows = [float(bar.low) for bar in tail]
        recent_volumes = [float(bar.volume) for bar in tail[-self._volume_window :]]
        baseline_volumes = [float(bar.volume) for bar in tail]
        baseline_volume = sum(baseline_volumes) / len(baseline_volumes)
        recent_volume = sum(recent_volumes) / len(recent_volumes)
        zero_volume_share = sum(1 for volume in recent_volumes if volume <= 0) / len(recent_volumes)

        trend_gap = (float(fast) - float(slow)) / float(slow)
        slow_slope = (float(slow) - float(slow_prev)) / float(slow_prev)
        atr_ratio = float(atr_value) / close
        return_std = statistics.pstdev(returns)
        directional_consistency = abs(direction_sum) / len(returns)
        efficiency_ratio = abs(float(tail[-1].close) - float(tail[0].close)) / path
        range_width_ratio = (max(highs) - min(lows)) / close
        recent_volume_ratio = recent_volume / baseline_volume if baseline_volume > 0 else 0.0

        return RegimeMetrics(
            sma_fast=_round_metric(fast),
            sma_slow=_round_metric(slow),
            sma_slow_slope=_round_metric(slow_slope),
            trend_gap=_round_metric(trend_gap),
            atr_ratio=_round_metric(atr_ratio),
            return_std=_round_metric(return_std),
            directional_consistency=_round_metric(directional_consistency),
            efficiency_ratio=_round_metric(efficiency_ratio),
            range_width_ratio=_round_metric(range_width_ratio),
            recent_volume_ratio=_round_metric(recent_volume_ratio),
            zero_volume_share=_round_metric(zero_volume_share),
        )

    def _classify(self, metrics: RegimeMetrics) -> tuple[str, float, str]:
        if self._is_low_liquidity(metrics, hold=False):
            confidence = self._low_liquidity_confidence(metrics)
            explanation = (
                "recent volume is materially below baseline"
                f" (recent_volume_ratio={metrics.recent_volume_ratio:.4f},"
                f" zero_volume_share={metrics.zero_volume_share:.4f})"
            )
            return LOW_LIQUIDITY, confidence, explanation

        if self._is_trend_up(metrics, hold=False):
            confidence = self._trend_confidence(metrics)
            explanation = (
                "fast SMA is above slow SMA with positive slope and directional persistence"
                f" (trend_gap={metrics.trend_gap:.4f},"
                f" slow_slope={metrics.sma_slow_slope:.4f},"
                f" efficiency={metrics.efficiency_ratio:.4f},"
                f" atr_ratio={metrics.atr_ratio:.4f})"
            )
            return TREND_UP, confidence, explanation

        if self._is_trend_down(metrics, hold=False):
            confidence = self._trend_confidence(metrics)
            explanation = (
                "fast SMA is below slow SMA with negative slope and directional persistence"
                f" (trend_gap={metrics.trend_gap:.4f},"
                f" slow_slope={metrics.sma_slow_slope:.4f},"
                f" efficiency={metrics.efficiency_ratio:.4f},"
                f" atr_ratio={metrics.atr_ratio:.4f})"
            )
            return TREND_DOWN, confidence, explanation

        if self._is_volatile(metrics, hold=False):
            confidence = self._volatile_confidence(metrics)
            explanation = (
                "realized volatility is elevated without a clear directional trend"
                f" (atr_ratio={metrics.atr_ratio:.4f},"
                f" return_std={metrics.return_std:.4f},"
                f" range_width_ratio={metrics.range_width_ratio:.4f})"
            )
            return VOLATILE, confidence, explanation

        if self._is_range(metrics, hold=False):
            confidence = self._range_confidence(metrics)
            explanation = (
                "trend gap, slope, and volatility are compressed"
                f" (trend_gap={metrics.trend_gap:.4f},"
                f" slow_slope={metrics.sma_slow_slope:.4f},"
                f" atr_ratio={metrics.atr_ratio:.4f},"
                f" efficiency={metrics.efficiency_ratio:.4f})"
            )
            return RANGE, confidence, explanation

        return NO_REGIME, 0.0, "no regime met explicit entry thresholds"

    def _apply_transition_rules(
        self,
        raw_regime: str,
        raw_confidence: float,
        previous_regime: MarketRegime | None,
        metrics: RegimeMetrics,
    ) -> tuple[str, float, str]:
        if previous_regime is None or previous_regime.regime == NO_REGIME:
            if raw_regime == NO_REGIME:
                return NO_REGIME, 0.0, "fresh_fail_closed"
            return raw_regime, raw_confidence, "fresh_classification"

        previous_label = previous_regime.regime
        if previous_label == raw_regime:
            return raw_regime, max(raw_confidence, previous_regime.confidence), "state_persisted"

        previous_holds = self._matches_regime(previous_label, metrics, hold=True)
        if previous_holds and raw_regime == NO_REGIME:
            held_confidence = max(min(previous_regime.confidence, 0.67), 0.5)
            return previous_label, held_confidence, "hysteresis_hold_no_candidate"

        if previous_holds and raw_confidence < 0.68:
            held_confidence = max(min(previous_regime.confidence, 0.67), raw_confidence)
            return previous_label, held_confidence, "hysteresis_hold_marginal_switch"

        if raw_regime == NO_REGIME:
            return NO_REGIME, 0.0, "fail_closed_no_clear_switch"

        if raw_confidence < 0.55:
            return NO_REGIME, 0.0, "fail_closed_low_switch_confidence"

        return raw_regime, raw_confidence, f"switched_from_{previous_label}"

    def _matches_regime(self, label: str, metrics: RegimeMetrics, hold: bool) -> bool:
        if label == TREND_UP:
            return self._is_trend_up(metrics, hold=hold)
        if label == TREND_DOWN:
            return self._is_trend_down(metrics, hold=hold)
        if label == RANGE:
            return self._is_range(metrics, hold=hold)
        if label == VOLATILE:
            return self._is_volatile(metrics, hold=hold)
        if label == LOW_LIQUIDITY:
            return self._is_low_liquidity(metrics, hold=hold)
        return False

    def _is_low_liquidity(self, metrics: RegimeMetrics, hold: bool) -> bool:
        volume_ratio_limit = 0.55 if not hold else 0.65
        zero_share_limit = 0.30 if not hold else 0.20
        return (
            metrics.recent_volume_ratio <= volume_ratio_limit
            or metrics.zero_volume_share >= zero_share_limit
        )

    def _is_trend_up(self, metrics: RegimeMetrics, hold: bool) -> bool:
        gap_min = 0.010 if not hold else 0.006
        slope_min = 0.0020 if not hold else 0.0010
        consistency_min = 0.58 if not hold else 0.50
        efficiency_min = 0.65 if not hold else 0.48
        volatility_max = 0.035 if not hold else 0.040
        return (
            metrics.trend_gap >= gap_min
            and metrics.sma_slow_slope >= slope_min
            and metrics.directional_consistency >= consistency_min
            and metrics.efficiency_ratio >= efficiency_min
            and metrics.atr_ratio <= volatility_max
            and metrics.recent_volume_ratio >= 0.65
        )

    def _is_trend_down(self, metrics: RegimeMetrics, hold: bool) -> bool:
        gap_max = -0.010 if not hold else -0.006
        slope_max = -0.0020 if not hold else -0.0010
        consistency_min = 0.58 if not hold else 0.50
        efficiency_min = 0.65 if not hold else 0.48
        volatility_max = 0.035 if not hold else 0.040
        return (
            metrics.trend_gap <= gap_max
            and metrics.sma_slow_slope <= slope_max
            and metrics.directional_consistency >= consistency_min
            and metrics.efficiency_ratio >= efficiency_min
            and metrics.atr_ratio <= volatility_max
            and metrics.recent_volume_ratio >= 0.65
        )

    def _is_volatile(self, metrics: RegimeMetrics, hold: bool) -> bool:
        atr_min = 0.030 if not hold else 0.026
        std_min = 0.020 if not hold else 0.017
        width_min = 0.100 if not hold else 0.085
        trend_gap_cap = 0.012 if not hold else 0.015
        efficiency_cap = 0.60 if not hold else 0.68
        return (
            metrics.recent_volume_ratio >= 0.65
            and abs(metrics.trend_gap) <= trend_gap_cap
            and metrics.efficiency_ratio <= efficiency_cap
            and (
                metrics.atr_ratio >= atr_min
                or metrics.return_std >= std_min
                or metrics.range_width_ratio >= width_min
            )
        )

    def _is_range(self, metrics: RegimeMetrics, hold: bool) -> bool:
        gap_cap = 0.004 if not hold else 0.006
        slope_cap = 0.0015 if not hold else 0.0025
        atr_cap = 0.018 if not hold else 0.022
        consistency_cap = 0.55 if not hold else 0.60
        efficiency_cap = 0.35 if not hold else 0.48
        width_cap = 0.070 if not hold else 0.090
        return (
            metrics.recent_volume_ratio >= 0.65
            and abs(metrics.trend_gap) <= gap_cap
            and abs(metrics.sma_slow_slope) <= slope_cap
            and metrics.atr_ratio <= atr_cap
            and metrics.directional_consistency <= consistency_cap
            and metrics.efficiency_ratio <= efficiency_cap
            and metrics.range_width_ratio <= width_cap
        )

    def _trend_confidence(self, metrics: RegimeMetrics) -> float:
        return round(
            (
                _clamp01(abs(metrics.trend_gap) / 0.03)
                + _clamp01(abs(metrics.sma_slow_slope) / 0.01)
                + metrics.directional_consistency
                + metrics.efficiency_ratio
                + _clamp01(metrics.recent_volume_ratio / 1.2)
            )
            / 5.0,
            4,
        )

    def _range_confidence(self, metrics: RegimeMetrics) -> float:
        return round(
            (
                _clamp01((0.008 - abs(metrics.trend_gap)) / 0.008)
                + _clamp01((0.003 - abs(metrics.sma_slow_slope)) / 0.003)
                + _clamp01((0.020 - metrics.atr_ratio) / 0.020)
                + _clamp01((0.50 - metrics.directional_consistency) / 0.50)
                + _clamp01((0.45 - metrics.efficiency_ratio) / 0.45)
            )
            / 5.0,
            4,
        )

    def _volatile_confidence(self, metrics: RegimeMetrics) -> float:
        return round(
            (
                _clamp01(metrics.atr_ratio / 0.06)
                + _clamp01(metrics.return_std / 0.04)
                + _clamp01(metrics.range_width_ratio / 0.16)
                + _clamp01((0.70 - metrics.efficiency_ratio) / 0.70)
            )
            / 4.0,
            4,
        )

    def _low_liquidity_confidence(self, metrics: RegimeMetrics) -> float:
        return round(
            (
                _clamp01((0.70 - metrics.recent_volume_ratio) / 0.70)
                + _clamp01(metrics.zero_volume_share / 0.50)
            )
            / 2.0,
            4,
        )

    def _no_regime(self, timestamp: int, reason: str) -> MarketRegime:
        metrics = RegimeMetrics(
            sma_fast=0.0,
            sma_slow=0.0,
            sma_slow_slope=0.0,
            trend_gap=0.0,
            atr_ratio=0.0,
            return_std=0.0,
            directional_consistency=0.0,
            efficiency_ratio=0.0,
            range_width_ratio=0.0,
            recent_volume_ratio=0.0,
            zero_volume_share=0.0,
        )
        return MarketRegime(
            regime=NO_REGIME,
            confidence=0.0,
            explanation=f"NO_REGIME: {reason}",
            timestamp=timestamp,
            metrics=metrics,
        )


__all__ = [
    "LOW_LIQUIDITY",
    "MarketRegime",
    "NO_REGIME",
    "RANGE",
    "RegimeEngine",
    "TREND_DOWN",
    "TREND_UP",
    "VOLATILE",
]
