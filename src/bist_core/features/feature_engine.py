"""Feature engines — registry-based series features + scalar extract for decisions."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from bist_core.features.feature_registry import get_feature
from bist_core.market.regime_engine import RegimeEngine
from bist_core.models.ohlcv import OHLCVBar


class RegistryFeatureEngine:
    """Compute features from bars using the global feature registry."""

    def compute_feature(
        self,
        bars: Sequence[OHLCVBar],
        feature_name: str,
    ) -> List[Optional[float]]:
        fn = get_feature(feature_name)
        return fn(bars)

    def compute_features(
        self,
        bars: Sequence[OHLCVBar],
        features: Sequence[str],
    ) -> Dict[str, List[Optional[float]]]:
        result: dict[str, list[float | None]] = {}
        for name in features:
            result[name] = self.compute_feature(bars, name)
        return result

    def compute_feature_frame(
        self,
        bars: Sequence[OHLCVBar],
        features: Sequence[str],
    ) -> List[Dict[str, Any]]:
        computed = self.compute_features(bars, features)
        rows: list[dict[str, Any]] = []
        for i, bar in enumerate(bars):
            row: dict[str, Any] = {"timestamp": bar.timestamp}
            for name in features:
                row[name] = computed[name][i]
            rows.append(row)
        rows.sort(key=lambda r: r["timestamp"])
        return rows


class FeatureEngine:
    """Scalar features for decision scoring (deterministic, no numpy)."""

    def __init__(self) -> None:
        self._regime_engine = RegimeEngine()

    def _extract_closes(self, bars: List[Any]) -> List[float]:
        out: List[float] = []
        for b in bars:
            try:
                c = getattr(b, "close", None)
                if isinstance(c, (int, float)) and c > 0:
                    out.append(float(c))
            except Exception:
                continue
        return out

    def window_closes(self, bars: List[Any], *, lookback: int = 20) -> List[float]:
        """Last ``lookback`` valid closes (or all if shorter), same rule as DecisionEngineV2."""
        closes = self._extract_closes(bars)
        lb = int(lookback) if lookback and int(lookback) >= 2 else 20
        if not closes:
            return []
        if len(closes) >= lb:
            return closes[-lb:]
        return closes

    def trend_strength(self, closes: List[float]) -> float:
        if not closes or len(closes) < 5:
            return 0.0
        start = float(closes[0])
        end = float(closes[-1])
        if start == 0:
            return 0.0
        return (end - start) / start

    def volatility(self, closes: List[float]) -> float:
        """Mean absolute bar-to-bar return — normalization denominator for momentum."""
        if len(closes) < 5:
            return 0.0
        returns: list[float] = []
        for i in range(1, len(closes)):
            prev = closes[i - 1]
            curr = closes[i]
            if prev != 0:
                returns.append((curr - prev) / prev)
        if not returns:
            return 0.0
        return sum(abs(r) for r in returns) / len(returns)

    def volatility_regime(self, vol: float) -> str:
        v = float(vol)
        if v < 0.001:
            return "low"
        if v < 0.005:
            return "normal"
        return "high"

    def momentum_acceleration(self, closes: List[float]) -> float:
        if len(closes) < 6:
            return 0.0
        m1 = float(closes[-1]) - float(closes[-2])
        m2 = float(closes[-2]) - float(closes[-3])
        return float(m1 - m2)

    def breakout_strength(self, closes: List[float]) -> float:
        if len(closes) < 10:
            return 0.0
        recent_max = max(closes[-10:-1])
        last = float(closes[-1])
        if recent_max == 0:
            return 0.0
        return (last - float(recent_max)) / float(recent_max)

    def extract_from_window(self, window: List[float]) -> Dict[str, float]:
        """Scalar features from a pre-built close window (same math as ``extract``)."""
        feats = self._scalar_features(window)
        closes = window
        feats["trend_strength"] = self.trend_strength(window)
        feats["volatility"] = self.volatility(window)
        feats["vol_regime"] = self.volatility_regime(feats.get("volatility", 0.0))
        feats["momentum_acceleration"] = self.momentum_acceleration(closes)
        feats["breakout"] = self.breakout_strength(closes)
        feats["regime_confidence"] = self._regime_engine.regime_confidence(closes)
        return feats

    def _scalar_features(self, window: List[float]) -> Dict[str, float]:
        if len(window) < 2:
            return {
                "returns": 0.0,
                "volatility": 0.0,
                "slope": 0.0,
                "mean": 0.0,
                "momentum": 0.0,
                "mean_reversion": 0.0,
            }
        first_c = float(window[0])
        last_c = float(window[-1])
        returns = (last_c / first_c - 1.0) if first_c > 0 else 0.0
        mean = float(sum(window) / len(window))
        var = sum((v - mean) ** 2 for v in window) / len(window)
        volatility = float(var**0.5)

        n = len(window)
        x_mean = (n - 1) / 2.0
        y_mean = sum(window) / n
        num = 0.0
        den = 0.0
        for i, v in enumerate(window):
            dx = i - x_mean
            dy = v - y_mean
            num += dx * dy
            den += dx * dx
        slope = float(num / den) if den != 0 else 0.0

        momentum = float(last_c - first_c)
        mean_price = float(sum(window) / len(window))
        mean_reversion = float((last_c - mean_price) / (mean_price + 1e-6))

        return {
            "returns": float(returns),
            "volatility": float(volatility),
            "slope": float(slope),
            "mean": float(mean),
            "momentum": float(momentum),
            "mean_reversion": float(mean_reversion),
        }

    def extract(self, bars: List[Any], *, lookback: int = 20) -> Dict[str, float]:
        """returns, vol, slope, mean(close), momentum (last-first), mean-reversion vs mean."""
        window = self.window_closes(bars, lookback=lookback)
        return self.extract_from_window(window)

    def multi_timeframe_momentum(self, bars: List[Any]) -> float:
        """Short + long window close-to-close change (hybrid timeframe signal)."""
        short = self.window_closes(bars, lookback=5)
        long = self.window_closes(bars, lookback=20)
        if not short or not long:
            return 0.0
        return float((short[-1] - short[0]) + (long[-1] - long[0]))


__all__ = [
    "FeatureEngine",
    "RegistryFeatureEngine",
]
