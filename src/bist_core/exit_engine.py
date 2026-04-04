"""Exit engine v1 — deterministic, fail-closed exit signals (edge / time / vol / TP)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExitDecision:
    action: str  # "hold" | "exit_partial" | "exit_full"
    reason: str
    size_fraction: float


def compute_exit_decision(
    entry_edge: float,
    current_edge: float,
    bars_held: int,
    volatility_norm: float,
    unrealized_pnl: float,
) -> ExitDecision:
    # --- FAIL CLOSED ---
    if entry_edge <= 0:
        return ExitDecision("exit_full", "invalid_entry_edge", 1.0)

    safe_entry_edge = max(entry_edge, 1e-6)
    edge_decay = current_edge / safe_entry_edge

    # --- VOLATILITY SPIKE (HIGHEST PRIORITY) ---
    if volatility_norm > 2.5:
        return ExitDecision("exit_full", "vol_spike", 1.0)

    # --- EDGE DECAY EXIT ---
    if edge_decay < 0.6:
        return ExitDecision("exit_full", "edge_decay", 1.0)

    # --- TIME DECAY ---
    if bars_held > 120:
        return ExitDecision("exit_partial", "time_decay", 0.5)

    # --- PARTIAL TAKE PROFIT ---
    if unrealized_pnl > 0.02:
        return ExitDecision("exit_partial", "tp_partial", 0.4)

    return ExitDecision("hold", "no_exit", 0.0)
