"""Edge health typed models — Phase 5F.

Provides evidence-aware edge health snapshots consumed by:
  - NoTradeGuard (EdgeHealthInput producer for NT-E01–NT-E04)
  - orchestrator telemetry
  - future edge activation matrix work (Phase 5G+)

Design invariants:
  - All unavailable fields are explicitly None, never fabricated.
  - Enums used instead of magic strings.
  - All dataclasses are frozen (immutable, deterministic).
  - No hidden mutable state — all rolling state lives in the tracker engine.

V1 scope:
  - EHS proxy = mean(confidence) over rolling window of last N signals.
  - No fake Sharpe / hit-rate / drawdown — those require trade outcome data.
  - Clean extension path toward full PRD EHS decomposition.

PRD reference: §1.6 EHS lifecycle, §1.21 NT-E family.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EdgeFSMState(str, Enum):
    """Edge lifecycle finite-state-machine states.

    ACTIVE    — EHS >= _DEGRADED_THRESHOLD; edge may produce valid signals.
    DEGRADED  — EHS between _DISABLE_THRESHOLD and _DEGRADED_THRESHOLD;
                edge still active but in watch zone.
    DISABLED  — EHS < _DISABLE_THRESHOLD or explicitly disabled by operator;
                NT-E02 will block new entries for this edge.
    """

    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"


class UtilizationBand(str, Enum):
    """Categorical capacity utilization band.

    SAFE    — utilization_pct < 50%  — edge has headroom.
    WARNING — 50% <= pct < 80%       — approaching capacity limit.
    RED     — pct >= 80%             — NT-E03 blocking zone.

    Boundaries intentionally match NoTradeConfig.edge_utilization_red_threshold
    defaults, but are separate from the guard thresholds so the tracker can
    detect band transitions even when the guard does not fire.
    """

    SAFE = "safe"
    WARNING = "warning"
    RED = "red"


@dataclass(frozen=True)
class EdgeSignalRecord:
    """One edge signal observation stored in rolling health history.

    Mandatory fields (always required):
      family         — edge family identifier string.
      symbol         — market symbol (e.g. "BTCUSDT").
      exchange       — exchange identifier string.
      is_valid       — whether the signal was valid at emission time.
      confidence     — signal confidence [0.0, 1.0]; 0.0 for invalid signals.
      timestamp_ns   — nanoseconds since epoch (UTC).

    Optional:
      utilization_pct — edge-specific capacity utilization at signal time;
                        None = unavailable (not yet supplied by upstream).
    """

    family: str
    symbol: str
    exchange: str
    is_valid: bool
    confidence: float
    timestamp_ns: int
    utilization_pct: float | None = None


@dataclass(frozen=True)
class EdgeHealthSnapshot:
    """Immutable point-in-time health state for one (family, symbol, exchange) key.

    ehs_score         — V1 proxy score = mean(confidence) in rolling window.
                        [0.0, 1.0]; None = insufficient history (< min_observations).
    fsm_state         — lifecycle FSM state (ACTIVE / DEGRADED / DISABLED).
    utilization_pct   — last observed utilization from signal records; None = unavailable.
    utilization_band  — categorical band derived from utilization_pct; None if pct unavailable.
    observation_count — number of records currently in the rolling window.
    is_valid_edge     — True iff ehs_score >= _EHS_VALID_THRESHOLD and state != DISABLED.
    snapshot_ns       — wall-clock when this snapshot was produced.
    """

    family: str
    symbol: str
    exchange: str
    ehs_score: float | None
    fsm_state: EdgeFSMState
    utilization_pct: float | None
    utilization_band: UtilizationBand | None
    observation_count: int
    is_valid_edge: bool
    snapshot_ns: int


@dataclass(frozen=True)
class EdgeHealthTrackerSnapshot:
    """Tracker-level aggregate summary across all tracked (family, symbol, exchange) keys.

    Produced by EdgeHealthTracker.tracker_snapshot() for telemetry and audit.

    Fields:
      valid_edge_count   — families where EHS >= threshold and state != DISABLED;
                           None if no family has sufficient history yet.
      disabled_edge_count — count of families in DISABLED state.
      active_edge_count  — count of families in ACTIVE or DEGRADED state.
      min_ehs            — minimum EHS across families with history; None if no history.
      max_ehs            — maximum EHS; None if no history.
      capacity_red_count — count of edges in RED utilization band.
      snapshot_ns        — wall-clock for this snapshot.
      family_snapshots   — immutable tuple of per-key snapshots for telemetry.
    """

    valid_edge_count: int | None
    disabled_edge_count: int
    active_edge_count: int
    min_ehs: float | None
    max_ehs: float | None
    capacity_red_count: int
    snapshot_ns: int
    family_snapshots: tuple[EdgeHealthSnapshot, ...] = field(default_factory=tuple)
