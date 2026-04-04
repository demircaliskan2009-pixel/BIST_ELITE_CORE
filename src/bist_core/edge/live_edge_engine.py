"""Recompute bucketed edges from a :class:`LiveEdgeBuffer` (deterministic)."""

from __future__ import annotations

from typing import Any

from bist_core.edge.edge_engine_v2 import EdgeEngineV2
from bist_core.edge.live_edge_buffer import LiveEdgeBuffer


class LiveEdgeEngine:
    def __init__(self) -> None:
        self.engine = EdgeEngineV2()

    def update(self, buffer: LiveEdgeBuffer) -> dict[tuple[Any, ...], dict[str, Any]]:
        """Rebuild buckets from buffer; recent rows get higher weight via ``1/(1+age)``."""
        self.engine = EdgeEngineV2()
        n = len(buffer.data)
        for i, row in enumerate(buffer.data):
            age = n - 1 - i
            weight = 1.0 / (1.0 + float(age))
            feat = row["features"]
            ret = float(row["return"])
            ctx = {
                "holding_period_bars": int(row["holding_period"]),
                "volatility": float(row["volatility"]),
                "regime": str(row["regime"]),
                "weight": weight,
            }
            self.engine.ingest(feat, ret, ctx)
        return self.engine.compute()


__all__ = ["LiveEdgeEngine"]
