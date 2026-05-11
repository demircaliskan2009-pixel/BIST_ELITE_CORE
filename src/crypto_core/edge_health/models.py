"""Edge health typed models — PRDV4-closer Phase 6C EHS contract.

The tracker now exposes a partial PRD-aligned Edge Health Score with explicit
component availability and a four-state lifecycle:

ACTIVE → WARNING → DISABLED → QUARANTINE

Unavailable realized-performance components are never fabricated. When the
tracker has to fall back to runtime proxies, that fact is carried explicitly in
the component metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EdgeFSMState(str, Enum):
    """Lifecycle states for one edge family on one symbol/exchange key."""

    ACTIVE = "ACTIVE"
    WARNING = "WARNING"
    DISABLED = "DISABLED"
    QUARANTINE = "QUARANTINE"


class UtilizationBand(str, Enum):
    """Categorical capacity utilization band."""

    SAFE = "safe"
    WARNING = "warning"
    RED = "red"


@dataclass(frozen=True)
class EdgeEHSComponent:
    """One scored EHS component with explicit availability metadata."""

    name: str
    weight: float
    score: float | None
    available: bool
    source: str
    evidence: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class EdgeSignalRecord:
    """One edge-stage observation stored in rolling health history."""

    family: str
    symbol: str
    exchange: str
    is_valid: bool
    confidence: float
    timestamp_ns: int
    utilization_pct: float | None = None
    score: float = 0.0


@dataclass(frozen=True)
class EdgeHealthSnapshot:
    """Immutable point-in-time health state for one edge key."""

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
    allocation_factor: float = 0.0
    component_availability_ratio: float = 0.0
    quarantine_until_ns: int | None = None
    ehs_components: tuple[EdgeEHSComponent, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EdgeHealthTrackerSnapshot:
    """Tracker-level aggregate summary across all tracked keys."""

    valid_edge_count: int | None
    disabled_edge_count: int
    active_edge_count: int
    min_ehs: float | None
    max_ehs: float | None
    capacity_red_count: int
    snapshot_ns: int
    warning_edge_count: int = 0
    quarantine_edge_count: int = 0
    family_snapshots: tuple[EdgeHealthSnapshot, ...] = field(default_factory=tuple)
