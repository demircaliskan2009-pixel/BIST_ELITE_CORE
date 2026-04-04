"""Tests for LiveEdgeBuffer — rich records, deterministic copies."""

from __future__ import annotations

from bist_core.edge.bucket_key import regime_from_feat
from bist_core.edge.live_edge_buffer import LiveEdgeBuffer


def _sample_feat() -> dict[str, float | int]:
    return {
        "vol": 0.02,
        "trend": 0.1,
        "breakout": 0,
        "vol_ratio": 1.0,
        "hour": 10,
    }


def test_add_stores_copy_of_features() -> None:
    buf = LiveEdgeBuffer()
    f = _sample_feat()
    buf.add(
        {
            "features": f,
            "return": 0.05,
            "holding_period": 3,
            "volatility": 0.03,
            "regime": regime_from_feat(f),
        }
    )
    f["vol"] = 99.0
    assert buf.data[0]["features"]["vol"] == 0.02
    assert buf.data[0]["return"] == 0.05
    assert buf.data[0]["holding_period"] == 3


def test_max_rows_truncates_oldest() -> None:
    buf = LiveEdgeBuffer(max_rows=3)
    f = _sample_feat()
    for i in range(5):
        buf.add(
            {
                "features": dict(f),
                "return": float(i),
                "holding_period": 1,
                "volatility": 0.02,
                "regime": "mv_up",
            }
        )
    assert len(buf.data) == 3
    assert buf.data[-1]["return"] == 4.0


def test_add_coerces_numeric_fields() -> None:
    buf = LiveEdgeBuffer()
    f = _sample_feat()
    buf.add(
        {
            "features": f,
            "return": 1,
            "holding_period": 2,
            "volatility": 0.02,
            "regime": "mv_up",
        }
    )
    assert buf.data[0]["return"] == 1.0
    assert isinstance(buf.data[0]["holding_period"], int)
