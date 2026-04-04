"""Consensus fusion across timeframe edges — need ≥2 positive expectations."""

from __future__ import annotations

import math
from typing import Any, Optional


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


class EdgeFusion:
    def decide(self, edges: list[Optional[dict[str, Any]]]) -> Optional[dict[str, Any]]:
        valid = [e for e in edges if e is not None and float(e.get("exp", 0.0)) > 0.0]
        if len(valid) < 2:
            return None
        avg_exp = sum(float(e["exp"]) for e in valid) / len(valid)
        confs = [
            float(e.get("confidence", max(0.01, float(e.get("exp", 0.01)))))
            for e in valid
        ]
        avg_c = sum(confs) / len(confs)
        edge_amp = math.tanh((float(avg_exp) - 0.015) * 22.0)
        fused = 0.22 + 0.62 * (0.5 + 0.5 * edge_amp) * (0.35 + 0.65 * _clamp01(avg_c))
        fused = max(0.2, min(0.9, fused))
        return {
            "exp": float(avg_exp),
            "count": len(valid),
            "confidence": float(fused),
        }


__all__ = ["EdgeFusion"]
