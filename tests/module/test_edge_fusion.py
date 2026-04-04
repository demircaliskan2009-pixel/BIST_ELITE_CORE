"""EdgeFusion consensus."""

from __future__ import annotations

from bist_core.edge.edge_fusion import EdgeFusion


def test_fusion_requires_two_positive() -> None:
    f = EdgeFusion()
    assert f.decide([None, {"exp": 0.01, "count": 10}]) is None
    assert f.decide([{"exp": 0.01, "count": 1}, {"exp": 0.02, "count": 2}]) is not None


def test_fusion_avg_exp() -> None:
    f = EdgeFusion()
    out = f.decide([{"exp": 0.10, "count": 1}, {"exp": 0.30, "count": 1}])
    assert out is not None
    assert out["exp"] == 0.2
    assert out["count"] == 2
    assert "confidence" in out
    assert 0.2 <= float(out["confidence"]) <= 0.9
