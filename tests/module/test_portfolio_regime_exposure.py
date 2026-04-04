"""Regime-aware portfolio weights, exposure cap, deterministic."""

from __future__ import annotations

from bist_core.portfolio.portfolio_engine import PortfolioEngine, _regime_weight_adjustment
from bist_core.risk.exposure_controller import ExposureController


def test_regime_weight_adjustment_values() -> None:
    assert _regime_weight_adjustment("trend") == 1.2
    assert _regime_weight_adjustment("range") == 0.8
    assert _regime_weight_adjustment("unknown") == 1.0


def test_allocate_with_regime_renormalizes() -> None:
    ranked = [
        {
            "symbol": "A",
            "rank_score": 1.0,
            "volatility": 1.0,
            "returns": 0.0,
            "score": 0.5,
            "decision": {"regime": "trend"},
        },
        {
            "symbol": "B",
            "rank_score": 0.9,
            "volatility": 2.0,
            "returns": 0.0,
            "score": 0.5,
            "decision": {"regime": "range"},
        },
    ]
    out = PortfolioEngine(top_n=2).allocate(ranked)
    assert len(out) == 2
    s = sum(p["weight"] for p in out)
    assert abs(s - 1.0) < 1e-9
    assert "regime" in out[0]


def test_exposure_controller_blocks_overfill() -> None:
    ec = ExposureController()
    assert ec.adjust(0.5, 0.6) == 0.0
    assert ec.adjust(0.5, 0.5) == 0.5
