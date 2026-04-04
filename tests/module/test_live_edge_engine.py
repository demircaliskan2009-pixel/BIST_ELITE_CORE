"""Tests for LiveEdgeEngine — deterministic rebuild from buffer."""

from __future__ import annotations

from bist_core.edge.bucket_key import regime_from_feat
from bist_core.edge.live_edge_buffer import LiveEdgeBuffer
from bist_core.edge.live_edge_engine import LiveEdgeEngine


def _feat() -> dict[str, float | int]:
    return {
        "vol": 0.02,
        "trend": 0.1,
        "breakout": 0,
        "vol_ratio": 1.0,
        "hour": 10,
    }


def _row(ret: float) -> dict[str, object]:
    f = _feat()
    return {
        "features": f,
        "return": ret,
        "holding_period": 1,
        "volatility": 0.02,
        "regime": regime_from_feat(f),
    }


def test_update_empty_buffer_returns_empty() -> None:
    eng = LiveEdgeEngine()
    buf = LiveEdgeBuffer()
    assert eng.update(buf) == {}


def test_update_emits_edges_after_thirty_same_bucket() -> None:
    eng = LiveEdgeEngine()
    buf = LiveEdgeBuffer()
    for _ in range(30):
        buf.add(_row(0.01))
    out = eng.update(buf)
    assert len(out) == 1
    k = next(iter(out))
    assert abs(out[k]["exp"] - 0.01) < 1e-9
    assert out[k]["count"] == 30
    assert "confidence" in out[k]


def test_update_twice_same_buffer_idempotent_not_double_count() -> None:
    """Second update rebuilds from same buffer rows (fresh engine each update)."""
    eng = LiveEdgeEngine()
    buf = LiveEdgeBuffer()
    for _ in range(30):
        buf.add(_row(0.02))
    a = eng.update(buf)
    b = eng.update(buf)
    assert a == b

