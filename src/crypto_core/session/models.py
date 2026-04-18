"""Paper-live session typed models — Phase 7E.

Operator-facing status model, session configuration, and cycle result.
All session-state models are here; engine logic is in engine.py.

Design rules:
  - CycleResult is frozen (immutable audit record per cycle).
  - PaperSessionStatus is frozen (snapshot — engine creates a new one each call).
  - PaperSessionConfig is frozen (set once at construction time).
  - SessionMode is a string enum for JSON serialisation.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


class SessionMode(str, Enum):
    """Paper-live session lifecycle states.

    INITIALIZING → start() → RECOVERING | RUNNING
    RECOVERING   → success → RUNNING | BLOCKED
    RUNNING      → stop()  → STOPPED
    RUNNING      → pause() → PAUSED
    RUNNING      → error   → FAILED
    PAUSED       → resume() → RUNNING
    BLOCKED      → restart() → INITIALIZING
    FAILED       → restart() → INITIALIZING
    """

    INITIALIZING = "initializing"
    RECOVERING = "recovering"
    RUNNING = "running"
    PAUSED = "paused"
    BLOCKED = "blocked"
    STOPPED = "stopped"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperSessionConfig:
    """Configuration for a paper-live trading session.

    session_id:        unique identifier for this session run.
    initial_nav_usd:   starting equity when no persisted state exists.
    persist_every_fill: persist portfolio state after every fill event.
    persist_on_stop:   persist portfolio state on graceful stop.
    max_cycles:        optional upper limit on cycle count (0 = unlimited).
    """

    session_id: str = "paper-live-default"
    initial_nav_usd: float = 10_000.0
    persist_every_fill: bool = True
    persist_on_stop: bool = True
    max_cycles: int = 0
    cycle_history_size: int = 100


# ---------------------------------------------------------------------------
# Cycle result (one per process_event call)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CycleResult:
    """Immutable result of one session processing cycle.

    cycle_number:       1-based cycle counter for this session.
    timestamp_ns:       market data timestamp of this cycle.
    pipeline_result:    full PipelineResult from the orchestrator; None on error.
    fills_applied:      number of fills applied to the position tracker this cycle.
    portfolio_persisted: True if portfolio state was written to store this cycle.
    error:              non-None only when an exception occurred during processing.
    """

    cycle_number: int
    timestamp_ns: int
    pipeline_result: object | None  # PipelineResult (avoid circular import)
    fills_applied: int
    portfolio_persisted: bool
    error: str | None


# ---------------------------------------------------------------------------
# Operator-facing status snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperSessionStatus:
    """Operator-facing session status snapshot — produced by status().

    Frozen: the engine creates a new instance on every status() call.
    No mutable containers — tuples instead of lists/dicts.

    Fields:
      session_id:             configured session identifier.
      mode:                   current SessionMode value (string).
      start_time_ns:          session start wall-clock (ns); 0 if not started.
      current_cycle_time_ns:  timestamp of the most recent cycle; 0 if none.
      total_cycles:           cycles processed so far.
      total_fills:            total fill events applied across all cycles.
      approved_cycles:        cycles where the pipeline approved a trade.
      blocked_cycles:         cycles rejected because session not RUNNING.
      failed_cycles:          cycles that raised an internal exception.
      recovery_status:        "none" | "clean_start" | "recovered" | "failed:<reason>".
      unresolved_order_count: orders from recovery that could not be reconciled.
      open_positions_count:   number of open positions in the portfolio.
      nav_usd:                current NAV in USD; None if tracker unavailable.
      gross_exposure_pct:     gross exposure as % of NAV; None if unavailable.
      net_exposure_pct:       net directional exposure as % of NAV; None if unavailable.
      last_cycle_approved:    whether the last pipeline cycle approved a trade; None if no cycles.
      last_error:             most recent error string; None if no errors.
      trading_blocked:        True when session is not in RUNNING mode.
      block_reasons:          tuple of reasons why session is blocked (empty when running).
      cycle_history:          bounded tuple of recent CycleResult records for auditability.
    """

    session_id: str
    mode: str
    start_time_ns: int
    current_cycle_time_ns: int
    total_cycles: int
    total_fills: int
    approved_cycles: int
    blocked_cycles: int
    failed_cycles: int
    recovery_status: str
    unresolved_order_count: int
    open_positions_count: int
    nav_usd: float | None
    gross_exposure_pct: float | None
    net_exposure_pct: float | None
    last_cycle_approved: bool | None
    last_error: str | None
    trading_blocked: bool
    block_reasons: tuple[str, ...] = field(default_factory=tuple)
    cycle_history: tuple[CycleResult, ...] = field(default_factory=tuple)
