"""Adaptive live controller — deterministic metrics (no network)."""

from __future__ import annotations

from bist_core.live.adaptive_live_controller import AdaptiveLiveController


def test_thresholds_in_bounds() -> None:
    a = AdaptiveLiveController(window=10)
    for _ in range(5):
        a.record_cycle(
            selected=2,
            portfolio_empty=False,
            actions=("enter",),
            confidences=(0.2,),
            portfolio_scores=(0.7, 0.3),
        )
    t = a.thresholds_for_next_cycle()
    assert 0.08 <= t["min_conf"] <= 0.25
    assert 0.001 <= t["min_pf"] <= 0.01


def test_build_report_stability_score() -> None:
    a = AdaptiveLiveController(window=50)
    for i in range(10):
        a.record_cycle(
            selected=3,
            portfolio_empty=False,
            actions=("enter", "hold", "exit"),
            confidences=(0.2 + i * 0.02, 0.3, 0.15),
            portfolio_scores=(0.4, 0.9),
        )
    r = a.build_report(total_cycles=10)
    assert "avg_selected" in r
    assert "stability_score" in r
    assert "hard_rules" in r
    assert "market_regime_distribution" in r
    assert "edge_scores" in r
    assert "portfolio_quality_avg" in r
    assert r["frozen_thresholds"]["min_conf"] >= 0.08
