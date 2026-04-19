"""Service-level typed models — Phase 8A.

Models for the managed paper-live service: service mode, queue pressure
zones, watchdog status, per-symbol health, and the top-level operator
status snapshot.

All status structures are frozen dataclasses for thread-safe snapshots.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crypto_core.runtime.models import RuntimeStatus


# ---------------------------------------------------------------------------
# Service lifecycle
# ---------------------------------------------------------------------------


class ServiceMode(str, Enum):
    """Top-level managed service lifecycle states.

    CREATED      → start() → STARTING
    STARTING     → feeds registered + consumer launched → RUNNING
    RUNNING      → stop() → STOPPING → STOPPED
    RUNNING      → pause() → PAUSED
    RUNNING      → fatal error → FAILED
    PAUSED       → resume() → RUNNING
    FAILED       → restart() → STARTING
    STOPPED      → (terminal)
    """

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Queue pressure zones
# ---------------------------------------------------------------------------


class QueuePressure(str, Enum):
    """Queue occupancy zones for backpressure policy.

    NORMAL:   < 50% capacity — proceed normally.
    WARNING:  50-80% capacity — log warning, continue processing.
    CRITICAL: > 80% capacity — fail-closed, block trading cycles.
    OVERFLOW: queue full — events rejected, service moves to FAILED.
    """

    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    OVERFLOW = "overflow"


# ---------------------------------------------------------------------------
# Watchdog status
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WatchdogStatus:
    """Snapshot of service health supervision state.

    consumer_alive:       True if consumer thread is running.
    last_event_time_ns:   wall-clock ns of the last event enqueued.
    last_cycle_time_ns:   wall-clock ns of the last session cycle fired.
    seconds_since_event:  seconds since last event (0.0 if no events yet).
    seconds_since_cycle:  seconds since last cycle (0.0 if no cycles yet).
    stall_detected:       True if consumer appears stalled.
    stall_threshold_s:    configured stall detection threshold.
    """

    consumer_alive: bool
    last_event_time_ns: int
    last_cycle_time_ns: int
    seconds_since_event: float
    seconds_since_cycle: float
    stall_detected: bool
    stall_threshold_s: float


# ---------------------------------------------------------------------------
# Per-symbol health
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SymbolHealth:
    """Per-symbol health snapshot within the managed service.

    symbol:              symbol name (e.g. "BTCUSDT").
    exchange:            exchange name (e.g. "binance").
    feed_connected:      True if feed connection state is connected.
    feed_ready:          True if feed recovery state is ready.
    feed_key:            DataIngestor feed key (e.g. "binance:BTCUSDT").
    last_event_time_ns:  most recent event timestamp for this symbol.
    blocked:             True if this symbol path is locally blocked.
    block_reason:        reason string if blocked, None otherwise.
    """

    symbol: str
    exchange: str
    feed_connected: bool
    feed_ready: bool
    feed_key: str
    last_event_time_ns: int
    blocked: bool
    block_reason: str | None


# ---------------------------------------------------------------------------
# Service configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceConfig:
    """Configuration for the managed paper-live service.

    queue_max_size:      bounded queue capacity.
    queue_warning_pct:   queue occupancy % threshold for WARNING zone.
    queue_critical_pct:  queue occupancy % threshold for CRITICAL zone.
    stall_threshold_s:   seconds without a processed cycle before stall detected.
    consumer_poll_timeout_s: consumer loop queue.get() timeout in seconds.
    """

    queue_max_size: int = 10_000
    queue_warning_pct: float = 50.0
    queue_critical_pct: float = 80.0
    stall_threshold_s: float = 60.0
    consumer_poll_timeout_s: float = 1.0


# ---------------------------------------------------------------------------
# Queue snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QueueSnapshot:
    """Snapshot of the event queue state.

    current_depth:    number of events currently in the queue.
    max_size:         configured queue capacity.
    pressure:         current QueuePressure zone.
    total_enqueued:   total events successfully enqueued since start.
    total_dropped:    total events dropped due to overflow since start.
    total_processed:  total events consumed from queue since start.
    """

    current_depth: int
    max_size: int
    pressure: QueuePressure
    total_enqueued: int
    total_dropped: int
    total_processed: int


# ---------------------------------------------------------------------------
# Top-level operator status snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceStatus:
    """Operator-facing managed service status snapshot.

    Frozen — the service creates a new instance on every status() call.
    """

    service_mode: str
    runtime_status: RuntimeStatus | None
    queue: QueueSnapshot
    watchdog: WatchdogStatus
    symbol_health: tuple[SymbolHealth, ...]
    symbol_count: int
    trading_enabled: bool
    blocked_reason: str | None
    last_error: str | None
    total_service_restarts: int = 0
    execution_intelligence: ExecutionIntelligenceStatus | None = None


# ---------------------------------------------------------------------------
# Execution intelligence policy — Phase 9E
# ---------------------------------------------------------------------------


class ExecutionIntelligenceMode(str, Enum):
    """Policy for whether execution intelligence is required at startup.

    STRICT:   router + TCA loop MUST be present; startup fails if missing.
    OPTIONAL: bootstrap attempts to build them; degrades gracefully if missing.
    DISABLED: execution intelligence is intentionally off; no degradation.
    """

    STRICT = "strict"
    OPTIONAL = "optional"
    DISABLED = "disabled"


@dataclass(frozen=True)
class ExecutionIntelligenceConfig:
    """Configuration for execution intelligence bootstrap.

    mode:              policy for enforcement (STRICT / OPTIONAL / DISABLED).
    tca_store_path:    filesystem path for TCA persistence; None = no persistence.
    tca_horizons:      markout observation horizons in seconds.
    auto_persist_tca:  persist TCA records when markout completes.
    """

    mode: ExecutionIntelligenceMode = ExecutionIntelligenceMode.OPTIONAL
    tca_store_path: str | None = None
    tca_horizons: tuple[int, ...] = (1, 5, 15)
    auto_persist_tca: bool = True


@dataclass(frozen=True)
class ExecutionIntelligenceStatus:
    """Operator-facing snapshot of execution intelligence subsystem.

    Frozen — rebuilt on every status() call.
    """

    mode: str
    route_binding_enabled: bool
    tca_loop_enabled: bool
    tca_store_available: bool
    replay_dedup_bootstrapped: bool
    degraded: bool
    degraded_reasons: tuple[str, ...] = ()
