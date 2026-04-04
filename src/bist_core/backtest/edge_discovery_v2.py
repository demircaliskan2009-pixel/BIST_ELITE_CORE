"""Walk-forward edge discovery from OHLCV bars — fail-closed."""

from __future__ import annotations

from bist_core.edge.bucket_key import regime_from_feat
from bist_core.edge.edge_engine_v2 import EdgeEngineV2
from bist_core.features.edge_features_v2 import FeatureEngineV2
from bist_core.models.ohlcv import OHLCVBar


def discover_edges(bars: list[OHLCVBar]) -> dict:
    fe = FeatureEngineV2()
    ee = EdgeEngineV2()
    last_i = len(bars) - 6

    for i in range(30, len(bars) - 5):
        window = bars[i - 30 : i]
        future = bars[i + 5].close

        feat = fe.extract(window)

        ret = (future - window[-1].close) / window[-1].close
        age = max(0, last_i - i)
        weight = 1.0 / (1.0 + float(age))
        ctx = {
            "holding_period_bars": 5,
            "volatility": float(feat["vol"]),
            "regime": regime_from_feat(feat),
            "weight": weight,
        }
        ee.ingest(feat, ret, ctx)

    out = ee.compute()
    return out if out else {}


__all__ = ["discover_edges"]
