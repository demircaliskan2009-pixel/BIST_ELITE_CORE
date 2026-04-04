"""Exit engine v2 — adaptive trailing, edge-aware TP, nonlinear time pressure."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExitDecisionV2:
    action: str  # hold | exit_partial | exit_full
    reason: str
    size_fraction: float


def compute_exit_v2(
    entry_edge: float,
    peak_edge: float,
    current_edge: float,
    bars_held: int,
    unrealized_pnl: float,
) -> ExitDecisionV2:
    safe_peak = max(peak_edge, 1e-6)
    drawdown = (peak_edge - current_edge) / safe_peak

    if peak_edge > 0.75:
        if drawdown > 0.25:
            return ExitDecisionV2("exit_partial", "strong_pullback", 0.5)
    else:
        if drawdown > 0.4:
            return ExitDecisionV2("exit_full", "edge_trailing_stop", 1.0)

    # --- ADAPTIVE TAKE PROFIT ---
    if unrealized_pnl > 0:
        if entry_edge > 0.75:
            tp_threshold = 0.05
        elif entry_edge > 0.65:
            tp_threshold = 0.035
        else:
            tp_threshold = 0.02

        if unrealized_pnl > tp_threshold:
            return ExitDecisionV2("exit_partial", "adaptive_tp", 0.3)

    # --- TIME PRESSURE (NONLINEAR) ---
    if bars_held > 150:
        decay = min(1.0, (bars_held - 150) / 100)
        if decay > 0.5:
            return ExitDecisionV2("exit_partial", "time_pressure", 0.4)

    return ExitDecisionV2("hold", "no_exit", 0.0)
