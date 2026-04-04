"""Multi-timeframe feature extraction — deterministic, fail-closed per TF."""

from __future__ import annotations

from typing import Any

from bist_core.features.edge_features_v2 import FeatureEngineV2


class MultiTFFeatures:
    """Extract :class:`FeatureEngineV2` scalars per timeframe (≥30 bars only)."""

    def __init__(self) -> None:
        self.fe = FeatureEngineV2()

    def extract(self, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for tf in sorted(data.keys()):
            bars = data.get(tf)
            if not isinstance(bars, list) or len(bars) < 30:
                continue
            out[str(tf)] = self.fe.extract(bars)
        return out


__all__ = ["MultiTFFeatures"]
