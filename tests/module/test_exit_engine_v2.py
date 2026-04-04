"""Exit engine v2 — trailing, adaptive TP, time pressure."""

from __future__ import annotations

from bist_core.exit_engine_v2 import ExitDecisionV2, compute_exit_v2


def test_edge_trailing_stop_full_exit() -> None:
    """Large edge drawdown vs peak triggers full exit (peak not in strong-trade band)."""
    d = compute_exit_v2(
        entry_edge=0.5,
        peak_edge=0.74,
        current_edge=0.3,
        bars_held=10,
        unrealized_pnl=0.0,
    )
    assert d == ExitDecisionV2("exit_full", "edge_trailing_stop", 1.0)


def test_strong_trade_partial_on_pullback() -> None:
    """High peak: moderate drawdown -> strong_pullback partial (before full trailing)."""
    d = compute_exit_v2(
        entry_edge=0.5,
        peak_edge=0.80,
        current_edge=0.59,
        bars_held=10,
        unrealized_pnl=0.0,
    )
    assert d.action == "exit_partial"
    assert d.reason == "strong_pullback"
    assert d.size_fraction == 0.5


def test_adaptive_tp_high_entry_stricter_threshold() -> None:
    d = compute_exit_v2(
        entry_edge=0.80,
        peak_edge=0.80,
        current_edge=0.80,
        bars_held=10,
        unrealized_pnl=0.06,
    )
    assert d == ExitDecisionV2("exit_partial", "adaptive_tp", 0.3)


def test_adaptive_tp_mid_entry() -> None:
    d = compute_exit_v2(
        entry_edge=0.70,
        peak_edge=0.70,
        current_edge=0.70,
        bars_held=10,
        unrealized_pnl=0.04,
    )
    assert d.reason == "adaptive_tp"


def test_adaptive_tp_low_entry() -> None:
    d = compute_exit_v2(
        entry_edge=0.50,
        peak_edge=0.50,
        current_edge=0.50,
        bars_held=10,
        unrealized_pnl=0.025,
    )
    assert d == ExitDecisionV2("exit_partial", "adaptive_tp", 0.3)


def test_time_pressure_partial() -> None:
    d = compute_exit_v2(
        entry_edge=0.8,
        peak_edge=0.8,
        current_edge=0.8,
        bars_held=201,
        unrealized_pnl=0.0,
    )
    assert d == ExitDecisionV2("exit_partial", "time_pressure", 0.4)


def test_time_pressure_not_at_boundary() -> None:
    """decay = 0.5 is not > 0.5."""
    d = compute_exit_v2(
        entry_edge=0.8,
        peak_edge=0.8,
        current_edge=0.8,
        bars_held=200,
        unrealized_pnl=0.0,
    )
    assert d.action == "hold"


def test_hold_clean() -> None:
    d = compute_exit_v2(
        entry_edge=0.5,
        peak_edge=0.55,
        current_edge=0.52,
        bars_held=50,
        unrealized_pnl=0.005,
    )
    assert d == ExitDecisionV2("hold", "no_exit", 0.0)
