"""Exit engine v1 — deterministic rules."""

from __future__ import annotations

from bist_core.exit_engine import ExitDecision, compute_exit_decision


def test_invalid_entry_edge() -> None:
    d = compute_exit_decision(0.0, 0.5, 10, 1.0, 0.0)
    assert d == ExitDecision("exit_full", "invalid_entry_edge", 1.0)


def test_edge_decay_full_exit() -> None:
    d = compute_exit_decision(1.0, 0.59, 10, 1.0, 0.0)
    assert d.action == "exit_full"
    assert d.reason == "edge_decay"


def test_time_decay_partial() -> None:
    d = compute_exit_decision(1.0, 0.8, 121, 1.0, 0.0)
    assert d == ExitDecision("exit_partial", "time_decay", 0.5)


def test_vol_spike_full() -> None:
    d = compute_exit_decision(1.0, 0.8, 10, 2.6, 0.0)
    assert d == ExitDecision("exit_full", "vol_spike", 1.0)


def test_take_profit_partial() -> None:
    d = compute_exit_decision(1.0, 0.8, 10, 1.0, 0.03)
    assert d == ExitDecision("exit_partial", "tp_partial", 0.4)


def test_hold() -> None:
    d = compute_exit_decision(1.0, 0.8, 10, 1.0, 0.01)
    assert d == ExitDecision("hold", "no_exit", 0.0)


def test_vol_spike_overrides_time_decay() -> None:
    d = compute_exit_decision(1.0, 0.8, 121, 3.0, 0.0)
    assert d.reason == "vol_spike"
