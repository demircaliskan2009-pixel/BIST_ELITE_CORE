"""Real-time price intelligence vs model entry."""

from __future__ import annotations

from bist_core.decision.price_intelligence import (
    apply_realtime_price_intelligence,
    compute_entry_quality,
)


def test_entry_quality_bands() -> None:
    assert compute_entry_quality(100.0, 100.0) == "optimal"
    assert compute_entry_quality(100.5, 100.0) == "optimal"
    assert compute_entry_quality(103.0, 100.0) == "late"
    assert compute_entry_quality(97.0, 100.0) == "early"


def test_enter_wait_pullback_when_chased() -> None:
    d, adj = apply_realtime_price_intelligence(
        {
            "action": "enter",
            "confidence": 0.7,
            "reason": "x",
            "entry": 100.0,
            "institutional": True,
        },
        {
            "current_price": 103.0,
            "ideal_price": 100.0,
            "price_source": "matriks",
            "validation_diff": 0.03,
        },
        inst={"features": {"momentum": 1.0}},
    )
    assert d["action"] == "wait_pullback"
    assert adj is True
    assert d.get("price_intelligence_adjusted") is True


def test_aggressive_enter_when_discount() -> None:
    d, adj = apply_realtime_price_intelligence(
        {
            "action": "enter",
            "confidence": 0.5,
            "reason": "x",
            "entry": 100.0,
            "institutional": True,
        },
        {
            "current_price": 97.0,
            "ideal_price": 100.0,
            "price_source": "matriks",
            "validation_diff": 0.03,
        },
        inst={"features": {"momentum": 0.0}},
    )
    assert d["action"] == "aggressive_enter"
    assert adj is True
    assert d["confidence"] > 0.5


def test_exit_to_partial_when_momentum_positive() -> None:
    d, adj = apply_realtime_price_intelligence(
        {
            "action": "exit",
            "confidence": 0.5,
            "reason": "x",
            "entry": 100.0,
            "institutional": True,
        },
        {
            "current_price": 100.0,
            "ideal_price": 100.0,
            "price_source": "ideal",
            "validation_diff": 0.0,
        },
        inst={"features": {"momentum": 0.5}},
    )
    assert d["action"] == "partial_exit"
    assert adj is True


def test_anti_blind_late_low_conf() -> None:
    d, adj = apply_realtime_price_intelligence(
        {
            "action": "enter",
            "confidence": 0.5,
            "reason": "x",
            "entry": 100.0,
            "institutional": True,
        },
        {
            "current_price": 103.5,
            "ideal_price": 100.0,
            "price_source": "matriks",
            "validation_diff": 0.035,
        },
        inst={"features": {"momentum": 0.0}},
    )
    assert d["action"] == "wait_pullback"
    assert "anti_blind" in d.get("reason", "") or "entry_missed" in d.get("reason", "")


def test_non_institutional_no_mutations() -> None:
    d, adj = apply_realtime_price_intelligence(
        {"action": "hold", "confidence": 0.3, "reason": "y", "institutional": False},
        {"current_price": 100.0, "price_source": "ideal", "validation_diff": 0.0},
        None,
    )
    assert d["action"] == "hold"
    assert adj is False
