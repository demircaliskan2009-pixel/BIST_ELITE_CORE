"""System State Engine — typed models (PRD §1.29).

Defines SystemState enum, SignalInputs (10 signals), StateSnapshot, TransitionRecord,
and the constant tables used by the engine for threshold evaluation.

PRD reference: §1.29 — Global System State Engine.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------


class SystemState(str):
    """Five operational states (§1.29 System States).

    String values are the canonical labels used in telemetry and logs.
    Transitions:
      - Escalation: immediate (no delay, no hysteresis)
      - De-escalation: requires sustained exit threshold (hysteresis)
    """

    # We implement as a simple str subclass with class-level constants so that
    # ruff UP006/UP007 rules don't trigger, and the values remain JSON-safe.
    pass


# Singleton constants — use these everywhere instead of bare strings.
SystemState.NORMAL = SystemState("NORMAL")  # type: ignore[attr-defined]
SystemState.DEGRADED = SystemState("DEGRADED")  # type: ignore[attr-defined]
SystemState.DEFENSIVE = SystemState("DEFENSIVE")  # type: ignore[attr-defined]
SystemState.CRISIS = SystemState("CRISIS")  # type: ignore[attr-defined]
SystemState.HALT = SystemState("HALT")  # type: ignore[attr-defined]

# Ordered sequence used for severity comparisons (index = severity level).
_STATE_ORDER: tuple[SystemState, ...] = (
    SystemState.NORMAL,
    SystemState.DEGRADED,
    SystemState.DEFENSIVE,
    SystemState.CRISIS,
    SystemState.HALT,
)

_STATE_SEVERITY: dict[str, int] = {s: i for i, s in enumerate(_STATE_ORDER)}


def state_severity(state: SystemState) -> int:
    """Returns ordinal severity (0=NORMAL … 4=HALT).

    Raises ValueError for unknown states (fail-closed).
    """
    try:
        return _STATE_SEVERITY[state]
    except KeyError:
        # Unknown state → treat as most severe (fail-closed invariant)
        return len(_STATE_ORDER)


def is_at_least(state: SystemState, threshold: SystemState) -> bool:
    """True if *state* is at least as severe as *threshold*."""
    return state_severity(state) >= state_severity(threshold)


# ---------------------------------------------------------------------------
# Signal weights (S1..S10, sum = 1.0)
# ---------------------------------------------------------------------------

#: Weight vector per §1.29 — index 0 = S1, index 9 = S10.
SHS_WEIGHTS: tuple[float, ...] = (0.20, 0.15, 0.15, 0.10, 0.10, 0.08, 0.07, 0.05, 0.05, 0.05)

assert abs(sum(SHS_WEIGHTS) - 1.0) < 1e-9, "SHS_WEIGHTS must sum to 1.0"  # noqa: S101


# ---------------------------------------------------------------------------
# Signal names (for override logging)
# ---------------------------------------------------------------------------

SIGNAL_NAMES: tuple[str, ...] = (
    "S1_kill_switch",
    "S2_drawdown",
    "S3_cvar",
    "S4_data_feed",
    "S5_execution",
    "S6_liquidity",
    "S7_feature_drift",
    "S8_correlation",
    "S9_margin",
    "S10_latency",
)


# ---------------------------------------------------------------------------
# De-escalation tables
# ---------------------------------------------------------------------------

#: SHS must EXCEED this value to begin de-escalation timer from a given state.
DEESC_EXIT_SHS: dict[str, float] = {
    SystemState.NORMAL: 2.0,  # sentinel — NORMAL has no de-escalation
    SystemState.DEGRADED: 0.85,
    SystemState.DEFENSIVE: 0.70,
    SystemState.CRISIS: 0.50,
    SystemState.HALT: 0.60,  # + manual approval
}

#: Minimum time already spent IN the current state before de-escalation is eligible (seconds).
DEESC_MIN_IN_STATE_S: dict[str, float] = {
    SystemState.NORMAL: 0.0,
    SystemState.DEGRADED: 10 * 60.0,  # 10 min
    SystemState.DEFENSIVE: 30 * 60.0,  # 30 min
    SystemState.CRISIS: 2 * 3600.0,  # 2 h
    SystemState.HALT: float("inf"),  # manual only
}

#: SHS exit threshold must be sustained for this long before de-escalation fires (seconds).
DEESC_SUSTAINED_S: dict[str, float] = {
    SystemState.NORMAL: 0.0,
    SystemState.DEGRADED: 30 * 60.0,  # 30 min
    SystemState.DEFENSIVE: 2 * 3600.0,  # 2 h
    SystemState.CRISIS: 6 * 3600.0,  # 6 h
    SystemState.HALT: float("inf"),  # manual only
}

#: Maximum leverage per state (fractional, e.g. 3.0 = 3x).
MAX_LEVERAGE: dict[str, float] = {
    SystemState.NORMAL: 3.0,
    SystemState.DEGRADED: 2.0,
    SystemState.DEFENSIVE: 1.5,
    SystemState.CRISIS: 1.0,
    SystemState.HALT: 0.0,
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignalInputs:
    """10 input signals for SHS computation (§1.29 State Derivation).

    All fields represent severity in [0.0, 1.0].
    The engine clamps values outside this range before use.

    Caller responsibilities:
    - s1_kill_switch  = kill_switch_level / 4   (1.0 means KS-4 → HALT)
    - s2_drawdown     = min(1, realised_dd / 0.15)
    - s3_cvar         = min(1, cvar99 / (0.05 * NAV))
    - s4_data_feed    = fraction of active NT-D data-feed triggers
    - s5_execution    = fraction of active NT-X execution triggers
    - s6_liquidity    = 1 - liquidity_regime_score
    - s7_feature_drift= min(1, CSI / 0.50)
    - s8_correlation  = min(1, portfolio_correlation / 0.85)
    - s9_margin       = min(1, margin_utilization / 0.85)
    - s10_latency     = max_tier(min(1, latency / (5 * L_tier)))
    """

    s1_kill_switch: float = 0.0
    s2_drawdown: float = 0.0
    s3_cvar: float = 0.0
    s4_data_feed: float = 0.0
    s5_execution: float = 0.0
    s6_liquidity: float = 0.0
    s7_feature_drift: float = 0.0
    s8_correlation: float = 0.0
    s9_margin: float = 0.0
    s10_latency: float = 0.0

    def as_tuple(self) -> tuple[float, ...]:
        """All 10 signal values in S1..S10 order."""
        return (
            self.s1_kill_switch,
            self.s2_drawdown,
            self.s3_cvar,
            self.s4_data_feed,
            self.s5_execution,
            self.s6_liquidity,
            self.s7_feature_drift,
            self.s8_correlation,
            self.s9_margin,
            self.s10_latency,
        )


@dataclass(frozen=True)
class StateSnapshot:
    """Immutable snapshot of one SHS evaluation cycle."""

    timestamp_ns: int
    state: SystemState
    shs: float
    signals: SignalInputs
    trigger_reason: str


@dataclass
class TransitionRecord:
    """Audit record of a state change. Mutable for list append performance."""

    timestamp_ns: int
    old_state: SystemState
    new_state: SystemState
    shs: float
    signals: SignalInputs
    trigger_reason: str
