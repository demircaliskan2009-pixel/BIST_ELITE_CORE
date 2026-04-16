"""Temporal scheduler engine — Phase 5G.

Deterministic, bounded-memory temporal state tracker.
Produces TemporalSnapshot → TemporalInput for NoTradeGuard NT-T rules.

Design contract:
  - No background threads. All state updates are explicit method calls.
  - Deterministic: same inputs → same outputs.
  - Fail-closed: malformed inputs raise immediately.
  - Bounded memory: event list is capped at _MAX_EVENTS.

Lifecycle of a pipeline cycle:
  1. Before guard stage:
       snap = scheduler.snapshot(current_ns=ts)
  2. Convert to TemporalInput for guard:
       temporal_input = scheduler.to_temporal_input(snap)
  3. After kill-switch stage:
       if ks_result.level >= ks_cooldown_threshold:
           scheduler.notify_ks_event(level=ks_result.level, current_ns=ts)

Startup warmup:
  - Set via set_engine_start(ns) or at construction.
  - Warmup phase is ACTIVE while (current_ns - engine_start_ns) < warmup_duration_ns.
  - engine_start_ns=0 keeps phase PENDING (warmup disabled).

KS cooldown:
  - Triggered by notify_ks_event(level, current_ns).
  - Cooldown duration scales with KS level (configured per-level durations).
  - Repeated triggers extend the cooldown from the NEW trigger time.

Event windows:
  - Added via add_event(ScheduledEvent).
  - Expired events are pruned lazily on snapshot() and explicitly via prune_expired().
  - Active event = start_ns <= current_ns < end_ns.

PRD reference: §1.21 NT-T01–NT-T03.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from crypto_core.guard.models import TemporalInput
from crypto_core.temporal.models import (
    ActiveEventWindow,
    CooldownPhase,
    KSCooldownSnapshot,
    ScheduledEvent,
    StartupWarmupSnapshot,
    TemporalSnapshot,
    WarmupPhase,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Maximum number of scheduled events retained (oldest are evicted on overflow).
_MAX_EVENTS: int = 256

#: Default warmup duration (5 minutes in nanoseconds).
_DEFAULT_WARMUP_NS: int = 5 * 60 * 1_000_000_000  # 5 min

#: Minimum KS level that triggers a cooldown.
_DEFAULT_KS_COOLDOWN_THRESHOLD: int = 2  # KS_LEVEL_BLOCK = 2

#: Default KS cooldown durations per level (ns).
#: Level 0/1 → no cooldown; 2 → 5 min; 3 → 15 min; 4 → 60 min.
_DEFAULT_KS_COOLDOWN_NS: dict[int, int] = {
    0: 0,
    1: 0,
    2: 5 * 60 * 1_000_000_000,  # 5 min
    3: 15 * 60 * 1_000_000_000,  # 15 min
    4: 60 * 60 * 1_000_000_000,  # 60 min
}


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class TemporalSchedulerError(ValueError):
    """Raised on invalid input to the temporal scheduler (fail-closed)."""


# ---------------------------------------------------------------------------
# Scheduler config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TemporalSchedulerConfig:
    """Configuration bundle for TemporalScheduler.

    All durations are nanoseconds.
    """

    #: Warmup duration after engine start (ns).
    warmup_duration_ns: int = _DEFAULT_WARMUP_NS

    #: Minimum KS level that triggers a post-KS cooldown.
    ks_cooldown_threshold: int = _DEFAULT_KS_COOLDOWN_THRESHOLD

    #: Per-level KS cooldown durations (ns). Must have keys 0–4.
    ks_cooldown_durations_ns: dict[int, int] = None  # type: ignore[assignment]

    #: Maximum event entries retained (bounded memory).
    max_events: int = _MAX_EVENTS

    def __post_init__(self) -> None:
        if self.ks_cooldown_durations_ns is None:
            object.__setattr__(self, "ks_cooldown_durations_ns", dict(_DEFAULT_KS_COOLDOWN_NS))
        if self.warmup_duration_ns < 0:
            raise TemporalSchedulerError(f"warmup_duration_ns must be >= 0, got {self.warmup_duration_ns}")
        if not (0 <= self.ks_cooldown_threshold <= 4):
            raise TemporalSchedulerError(f"ks_cooldown_threshold must be 0–4, got {self.ks_cooldown_threshold}")


# ---------------------------------------------------------------------------
# Temporal scheduler
# ---------------------------------------------------------------------------


class TemporalScheduler:
    """Deterministic temporal state manager.

    Maintains:
      - startup warmup state (set once, evolves with time)
      - KS cooldown state (updated on KS events)
      - scheduled event window list (bounded, sorted, pruned)

    Thread safety: NOT thread-safe. One instance per pipeline thread.

    Usage::

        sched = TemporalScheduler()
        sched.set_engine_start(engine_start_ns=time.time_ns())

        # Each pipeline cycle:
        snap = sched.snapshot(current_ns=ts)
        temporal_input = sched.to_temporal_input(snap)
        # ... pass temporal_input to guard ...
        # After KS computation:
        if ks_level >= sched.config.ks_cooldown_threshold:
            sched.notify_ks_event(level=ks_level, current_ns=ts)
    """

    def __init__(
        self,
        config: TemporalSchedulerConfig | None = None,
        engine_start_ns: int = 0,
    ) -> None:
        self._cfg = config or TemporalSchedulerConfig()
        # Startup warmup state
        self._engine_start_ns: int = engine_start_ns
        # KS cooldown state
        self._cooldown_until_ns: int = 0  # 0 = no active cooldown
        self._cooldown_triggered_level: int = 0  # KS level that set the cooldown
        self._cooldown_started_ns: int = 0  # when the current cooldown started
        # Event list: kept sorted by start_ns ascending
        self._events: list[ScheduledEvent] = []

    # -----------------------------------------------------------------------
    # Configuration accessors
    # -----------------------------------------------------------------------

    @property
    def config(self) -> TemporalSchedulerConfig:
        return self._cfg

    @property
    def engine_start_ns(self) -> int:
        return self._engine_start_ns

    # -----------------------------------------------------------------------
    # Engine start management
    # -----------------------------------------------------------------------

    def set_engine_start(self, engine_start_ns: int) -> None:
        """Record the engine start timestamp.

        Call once, immediately after the pipeline engine initialises.
        Calling again resets the warmup clock (for test isolation / restarts).

        Args:
            engine_start_ns: wall-clock timestamp in ns.

        Raises:
            TemporalSchedulerError: if engine_start_ns < 0.
        """
        if engine_start_ns < 0:
            raise TemporalSchedulerError(f"engine_start_ns must be >= 0, got {engine_start_ns}")
        self._engine_start_ns = engine_start_ns

    # -----------------------------------------------------------------------
    # KS cooldown management
    # -----------------------------------------------------------------------

    def notify_ks_event(self, level: int, current_ns: int) -> None:
        """Record a kill-switch event and refresh the cooldown window.

        Called AFTER the KS engine computes its level for this cycle.
        Repeated calls extend the cooldown from the current timestamp
        (not cumulative — always fresh N minutes from NOW).

        Args:
            level:      KS level (0–4).
            current_ns: current pipeline timestamp in ns.

        Raises:
            TemporalSchedulerError: if level out of range or current_ns < 0.
        """
        if not (0 <= level <= 4):
            raise TemporalSchedulerError(f"KS level must be 0–4, got {level}")
        if current_ns < 0:
            raise TemporalSchedulerError(f"current_ns must be >= 0, got {current_ns}")
        if level < self._cfg.ks_cooldown_threshold:
            # Level below threshold — no cooldown triggered, but do not error
            return
        duration_ns = self._cfg.ks_cooldown_durations_ns.get(level, 0)
        if duration_ns <= 0:
            return
        new_until = current_ns + duration_ns
        # Extend if already in cooldown (take the later deadline)
        if new_until > self._cooldown_until_ns:
            self._cooldown_until_ns = new_until
            self._cooldown_triggered_level = level
            self._cooldown_started_ns = current_ns

    def clear_cooldown(self) -> None:
        """Operator-level cooldown reset (emergency clear).

        Use during test setup or after manual system inspection.
        """
        self._cooldown_until_ns = 0
        self._cooldown_triggered_level = 0
        self._cooldown_started_ns = 0

    # -----------------------------------------------------------------------
    # Event management
    # -----------------------------------------------------------------------

    def add_event(self, event: ScheduledEvent) -> None:
        """Add a scheduled event window.

        Events with duplicate event_id are silently deduplicated (later add wins
        via remove then re-add — use remove_event first if an update is intended).

        Args:
            event: the event to register.

        Raises:
            TemporalSchedulerError: if event fields are invalid.
        """
        errors = _validate_event(event)
        if errors:
            raise TemporalSchedulerError("; ".join(errors))
        # Remove existing entry with same id (idempotent update)
        self._events = [e for e in self._events if e.event_id != event.event_id]
        self._events.append(event)
        # Keep sorted by start_ns ascending (deterministic ordering)
        self._events.sort(key=lambda e: (e.start_ns, e.event_id))
        # Enforce bounded memory: if over limit, drop oldest by start_ns
        if len(self._events) > self._cfg.max_events:
            self._events = self._events[-self._cfg.max_events :]

    def remove_event(self, event_id: str) -> None:
        """Remove a scheduled event by ID (no-op if not found)."""
        self._events = [e for e in self._events if e.event_id != event_id]

    def prune_expired(self, current_ns: int) -> int:
        """Remove all events whose end_ns <= current_ns.

        Returns the number of events removed.
        """
        before = len(self._events)
        self._events = [e for e in self._events if e.end_ns > current_ns]
        return before - len(self._events)

    @property
    def event_count(self) -> int:
        """Current number of scheduled events (active + future)."""
        return len(self._events)

    # -----------------------------------------------------------------------
    # Snapshot generation
    # -----------------------------------------------------------------------

    def snapshot(self, current_ns: int) -> TemporalSnapshot:
        """Compute an immutable temporal snapshot at the given timestamp.

        Lazily prunes expired events before building the snapshot.
        Does NOT mutate cooldown state.

        Args:
            current_ns: wall-clock timestamp in ns.

        Returns:
            TemporalSnapshot with warmup, cooldown, and active event state.
        """
        if current_ns < 0:
            raise TemporalSchedulerError(f"current_ns must be >= 0, got {current_ns}")
        # Prune expired events (lazy cleanup)
        self.prune_expired(current_ns)

        warmup_snap = self._compute_warmup_snapshot(current_ns)
        cooldown_snap = self._compute_cooldown_snapshot(current_ns)
        active_events = self._compute_active_events(current_ns)

        return TemporalSnapshot(
            warmup=warmup_snap,
            cooldown=cooldown_snap,
            active_events=tuple(active_events),
            event_count=len(self._events),
            snapshot_ns=current_ns,
        )

    def to_temporal_input(self, snap: TemporalSnapshot) -> TemporalInput:
        """Convert a TemporalSnapshot into a TemporalInput for NoTradeGuard.

        Maps:
          NT-T01: engine_start_ns (>0 when warmup is tracking)
          NT-T02: ks_cooldown_active (bool when cooldown tracked)
          NT-T03: high_impact_event_window_active (bool from active event list)

        Returns a TemporalInput with real values (not None) for all fields
        this scheduler can compute. Unknown fields remain None by convention.
        """
        # NT-T01: pass engine_start_ns so guard computes warmup age inline.
        # Guard uses: (current_ns - engine_start_ns) < warmup_ms to decide.
        # We pass the raw ns so the guard uses its own configured warmup_ms.
        engine_start_ns = self._engine_start_ns  # 0 = disabled

        # NT-T02: cooldown active is a real bool now (not None).
        ks_cooldown_active: bool | None = snap.ks_cooldown_active

        # NT-T03: event window active is a real bool now.
        high_impact_active: bool | None = snap.high_impact_event_window_active

        return TemporalInput(
            engine_start_ns=engine_start_ns,
            ks_cooldown_active=ks_cooldown_active,
            high_impact_event_window_active=high_impact_active,
        )

    # -----------------------------------------------------------------------
    # Reset
    # -----------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all state for test isolation.

        After reset:
          - engine_start_ns = 0 (warmup disabled)
          - no active cooldown
          - empty event list
        """
        self._engine_start_ns = 0
        self._cooldown_until_ns = 0
        self._cooldown_triggered_level = 0
        self._cooldown_started_ns = 0
        self._events.clear()

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _compute_warmup_snapshot(self, current_ns: int) -> StartupWarmupSnapshot:
        start = self._engine_start_ns
        if start <= 0:
            return StartupWarmupSnapshot(
                phase=WarmupPhase.PENDING,
                engine_start_ns=0,
                warmup_duration_ns=self._cfg.warmup_duration_ns,
                age_ns=0,
                remaining_ns=0,
                snapshot_ns=current_ns,
            )
        age_ns = max(0, current_ns - start)
        remaining_ns = max(0, self._cfg.warmup_duration_ns - age_ns)
        phase = WarmupPhase.ACTIVE if remaining_ns > 0 else WarmupPhase.COMPLETE
        return StartupWarmupSnapshot(
            phase=phase,
            engine_start_ns=start,
            warmup_duration_ns=self._cfg.warmup_duration_ns,
            age_ns=age_ns,
            remaining_ns=remaining_ns,
            snapshot_ns=current_ns,
        )

    def _compute_cooldown_snapshot(self, current_ns: int) -> KSCooldownSnapshot:
        if self._cooldown_until_ns <= 0 or current_ns >= self._cooldown_until_ns:
            return KSCooldownSnapshot(
                phase=CooldownPhase.INACTIVE,
                cooldown_until_ns=0,
                triggered_by_level=0,
                age_ns=0,
                remaining_ns=0,
                snapshot_ns=current_ns,
            )
        remaining = self._cooldown_until_ns - current_ns
        age = max(0, current_ns - self._cooldown_started_ns)
        return KSCooldownSnapshot(
            phase=CooldownPhase.ACTIVE,
            cooldown_until_ns=self._cooldown_until_ns,
            triggered_by_level=self._cooldown_triggered_level,
            age_ns=age,
            remaining_ns=remaining,
            snapshot_ns=current_ns,
        )

    def _compute_active_events(self, current_ns: int) -> list[ActiveEventWindow]:
        active: list[ActiveEventWindow] = []
        for e in self._events:
            if e.start_ns <= current_ns < e.end_ns:
                active.append(
                    ActiveEventWindow(
                        event_id=e.event_id,
                        event_type=e.event_type,
                        description=e.description,
                        remaining_ns=e.end_ns - current_ns,
                    )
                )
        return active


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_event(event: ScheduledEvent) -> list[str]:
    """Return list of validation error strings (empty = valid)."""
    errors: list[str] = []
    if not event.event_id:
        errors.append("event_id must not be empty")
    if event.start_ns < 0:
        errors.append(f"start_ns must be >= 0, got {event.start_ns}")
    if event.end_ns <= event.start_ns:
        errors.append(f"end_ns ({event.end_ns}) must be > start_ns ({event.start_ns})")
    return errors
