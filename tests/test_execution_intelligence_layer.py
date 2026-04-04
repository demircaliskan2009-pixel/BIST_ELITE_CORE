"""Execution intelligence: entry quality, slippage fraction, plan gating, partial exit."""

from __future__ import annotations

import pytest

from bist_core.live.execution_intelligence import (
    ExecutionIntelligenceLayer,
    classify_entry_quality,
    fill_probability,
    map_layer_action,
    slippage_extra_fraction,
)
from bist_core.live.execution_runtime import PaperExecution
from bist_core.live.state_store import LiveState
from bist_core.models.ohlcv import OHLCVBar


def test_classify_entry_quality_bands() -> None:
    assert classify_entry_quality(98.0, 100.0) == "excellent"
    assert classify_entry_quality(100.0, 100.0) == "good"
    assert classify_entry_quality(101.0, 100.0) == "good"
    assert classify_entry_quality(103.0, 100.0) == "late"
    assert classify_entry_quality(105.1, 100.0) == "chase"


def test_map_layer_action_chase_and_excellent() -> None:
    assert map_layer_action("enter", "chase") == "wait_pullback"
    assert map_layer_action("enter", "excellent") == "aggressive_enter"
    assert map_layer_action("enter", "good") == "enter"


def test_slippage_extra_fraction_deterministic() -> None:
    assert slippage_extra_fraction(0.02) == pytest.approx(0.002)
    assert slippage_extra_fraction(0.5) == pytest.approx(0.05)


def test_fill_probability_ordering() -> None:
    assert fill_probability(0.01, "excellent") > fill_probability(0.2, "chase")


def test_plan_delays_when_min_fill_prob_high(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIST_EXEC_MIN_FILL_PROB", "0.99")
    monkeypatch.setenv("BIST_EXEC_CHOPPY_DELAY", "0")
    layer = ExecutionIntelligenceLayer()
    bars = [
        OHLCVBar(
            timestamp=1,
            symbol="TEST",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1_000_000.0,
        ),
        OHLCVBar(
            timestamp=2,
            symbol="TEST",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1_000_000.0,
        ),
    ]
    p = layer.plan(
        "TEST",
        {"action": "enter", "entry": 100.0, "confidence": 0.5},
        current_price=100.0,
        volatility=0.02,
        buffer=bars,
        last_regime="MIXED",
    )
    assert p is not None
    assert p.delay_this_bar is True
    assert p.exec_action == "wait_pullback"


def test_paper_exit_partial_preserves_remaining_qty() -> None:
    st = LiveState()
    st.equity = 1.0
    st.daily_pnl = 0.0
    st.positions["X"] = [
        {"entry_price": 100.0, "size": 1, "qty": 1.0, "order_id": "a"},
    ]
    pe = PaperExecution(st)
    res = pe.execute(
        "X",
        "exit",
        100.0,
        volatility=0.02,
        volume_proxy=500_000.0,
        slippage_extra_frac=0.0,
        size_fraction=0.5,
    )
    assert res is not None
    assert res.get("ok") is True
    rest = st.positions.get("X", [])
    assert len(rest) == 1
    assert float(rest[0]["qty"]) == pytest.approx(0.5)
