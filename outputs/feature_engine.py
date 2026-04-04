"""Feature engine — computes feature vectors from OHLCVBar sequences.

Uses the feature registry to resolve names and produces deterministic
output sorted by timestamp.  Fail-closed on unknown feature names.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.features.feature_registry import get_feature


class FeatureEngine:
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
