"""Edge accumulation — weighted bucketed expected returns (deterministic, fail-closed)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from bist_core.edge.bucket_key import edge_bucket_key, weighted_std

# Max weighted std of returns in a bucket; above → discard edge (fail-closed).
INSTABILITY_STD_MAX = 0.12


class EdgeEngineV2:
    def __init__(self) -> None:
        self.buckets: defaultdict[tuple[Any, ...], list[tuple[float, float]]] = defaultdict(list)

    def key(self, f: dict[str, Any], context: dict[str, Any] | None = None) -> tuple[Any, ...]:
        return edge_bucket_key(f, context)

    def ingest(
        self,
        feat: dict[str, Any],
        future_ret: float,
        context: dict[str, Any] | None = None,
    ) -> None:
        ctx = dict(context) if context else {}
        if "weight" not in ctx:
            ctx["weight"] = 1.0
        k = edge_bucket_key(feat, ctx)
        self.buckets[k].append((float(future_ret), float(ctx["weight"])))

    def compute(self) -> dict[tuple[Any, ...], dict[str, Any]]:
        edges: dict[tuple[Any, ...], dict[str, Any]] = {}

        for k, samples in self.buckets.items():
            n = len(samples)
            if n < 30:
                continue

            tw = sum(w for _, w in samples)
            if tw <= 0.0:
                continue

            wstd = weighted_std(samples)
            if wstd > INSTABILITY_STD_MAX:
                continue

            exp = sum(r * w for r, w in samples) / tw
            # Confidence: high when stable (low std); bounded to [0, 1].
            confidence = 1.0 / (1.0 + wstd * 5.0)
            confidence = max(0.0, min(1.0, float(confidence)))

            edges[k] = {
                "exp": float(exp),
                "count": int(n),
                "confidence": confidence,
            }

        return edges


__all__ = ["EdgeEngineV2", "INSTABILITY_STD_MAX"]
