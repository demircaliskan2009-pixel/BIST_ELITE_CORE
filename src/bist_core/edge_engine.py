"""Edge scoring with volatility, orderflow, and session adjustments."""

from __future__ import annotations

from typing import Any

from bist_core.decision import edge_engine as _decision_edge_engine
from bist_core.features.orderflow import (
    detect_breakout_vs_exhaustion,
    orderflow_edge_adjust,
    volume_zscore,
)
from bist_core.features.session_edges import (
    closing_pressure_edge,
    opening_drift_edge,
)
from bist_core.features.volatility import (
    classify_vol_regime,
    compute_realized_vol,
    volatility_edge_adjust,
)


class _EdgeLearningHost:
    """Run-persistent buffer for ``compute_edge`` (process lifetime; no external I/O)."""

    __slots__ = ("edge_history",)

    def __init__(self) -> None:
        self.edge_history: list[dict[str, Any]] = []


_EDGE_LEARNING_SELF = _EdgeLearningHost()


def _bar_to_ohlcv_dict(b: Any) -> dict[str, float]:
    if isinstance(b, dict):
        return {
            "open": float(b["open"]),
            "high": float(b["high"]),
            "low": float(b["low"]),
            "close": float(b["close"]),
            "volume": float(b["volume"]),
        }
    return {
        "open": float(getattr(b, "open")),
        "high": float(getattr(b, "high")),
        "low": float(getattr(b, "low")),
        "close": float(getattr(b, "close")),
        "volume": float(getattr(b, "volume")),
    }


def _bars_for_market_adjustments(bars: list[Any]) -> list[dict[str, float]]:
    return [_bar_to_ohlcv_dict(x) for x in bars]


def compute_edge(features: dict[str, Any], regime: str, bars: list[Any]) -> float:
    edge = float(_decision_edge_engine.compute_edge(features, regime))

    adj_bars = _bars_for_market_adjustments(bars)

    # VOLATILITY
    vol = compute_realized_vol(adj_bars[-50:])
    regime = classify_vol_regime(vol, [vol])
    edge = volatility_edge_adjust(edge, regime)

    # ORDERFLOW
    volumes = [b["volume"] for b in adj_bars[-30:]]
    vol_z = volume_zscore(volumes)

    signal = detect_breakout_vs_exhaustion(adj_bars[-1], vol_z)
    print(
        {
            "EDGE_COMPONENTS": {
                "vol_regime": regime,
                "vol_adjusted": edge,
                "orderflow_signal": signal,
            }
        },
        flush=True,
    )
    edge = orderflow_edge_adjust(edge, signal)

    # SESSION
    edge += 0.1 * opening_drift_edge(adj_bars)
    edge += 0.1 * closing_pressure_edge(adj_bars)

    # FINAL CLAMP
    edge = max(0.0, min(1.0, edge))

    symbol = features.get("symbol") or features.get("ticker") or "UNKNOWN"

    print(
        {
            "EDGE_FINAL_DEBUG": {
                "edge": edge,
                "symbol": symbol,
            }
        },
        flush=True,
    )

    self = _EDGE_LEARNING_SELF
    # EDGE LEARNING BUFFER
    self.edge_history = getattr(self, "edge_history", [])

    self.edge_history.append(
        {
            "edge": edge,
            "symbol": symbol,
        }
    )

    # LIMIT SIZE
    if len(self.edge_history) > 1000:
        self.edge_history = self.edge_history[-1000:]

    print(
        {
            "EDGE_HISTORY_SAMPLE": self.edge_history[-5:],
        },
        flush=True,
    )

    return float(edge)


__all__ = ["compute_edge"]
