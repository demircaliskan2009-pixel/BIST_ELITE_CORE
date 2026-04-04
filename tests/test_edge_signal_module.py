"""edge_signal mapping — deterministic labels."""

from __future__ import annotations

from bist_core.decision.edge_signal import compute_edge_signal


def test_enter_strong_buy_when_high_conf_and_positive_score() -> None:
    s = compute_edge_signal(confidence=0.8, score=0.2, action="enter", edge_exp_boost=0.05)
    assert s == "STRONG_BUY"


def test_hold_neutral_near_zero_score() -> None:
    assert compute_edge_signal(confidence=0.5, score=0.0, action="hold") == "NEUTRAL"


def test_exit_maps_to_sell_side() -> None:
    assert compute_edge_signal(confidence=0.6, score=0.0, action="exit") in (
        "SELL",
        "STRONG_SELL",
    )
