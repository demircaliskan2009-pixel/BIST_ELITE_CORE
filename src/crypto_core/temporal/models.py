"""Temporal scheduler typed models — Phase 5G.

All types in this module are frozen dataclasses or enums.
No mutation. No mutable defaults.

PRD reference: §1.21 NT-T temporal restrictions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TemporalEventType(str, Enum):
    """Category of a scheduled temporal event.

    Used to classify event windows for logging, telemetry, and routing.
    Values are plain lowercase strings for schema compatibility.
    """

    MACRO_NEWS = "macro_news"
    """High-impact macroeconomic announcement (e.g., FOMC, CPI)."""

    EXCHANGE_MAINTENANCE = "exchange_maintenance"
    """Planned exchange downtime or degraded-mode window."""

    FUNDING_SETTLEMENT = "funding_settlement"
    """Funding rate settlement window (typically ±N minutes around settlement)."""

    CUSTOM = "custom"
    """Operator-injected event with no specific category."""


class WarmupPhase(str, Enum):
    """Startup warmup lifecycle phase.

    PENDING  — warmup not yet started (engine_start_ns == 0).
    ACTIVE   — inside warmup window; NT-T01 blocks trading.
    COMPLETE — warmup window has elapsed; trading allowed.
    """

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETE = "complete"


class CooldownPhase(str, Enum):
    """Kill-switch cooldown lifecycle phase.

    INACTIVE  — no active cooldown.
    ACTIVE    — inside cooldown window; NT-T02 blocks trading.
    """

    INACTIVE = "inactive"
    ACTIVE = "active"


# ---------------------------------------------------------------------------
# Scheduled event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScheduledEvent:
    """A single time-bounded event that may block trading (NT-T03).

    All timestamps are nanoseconds.

    Fields:
        event_id        — unique identifier (operator-supplied or generated).
        event_type      — category enum.
        start_ns        — event window start (inclusive), ns.
        end_ns          — event window end (exclusive), ns.
        description     — optional human-readable label.

    Constraints:
        start_ns < end_ns — validated at creation by TemporalScheduler.
        Overlapping events are allowed; any active window blocks trading.
    """

    event_id: str
    event_type: TemporalEventType
    start_ns: int
    end_ns: int
    description: str = ""


# ---------------------------------------------------------------------------
# Snapshot types (immutable outputs)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StartupWarmupSnapshot:
    """Immutable state of the startup warmup window."""

    phase: WarmupPhase
    engine_start_ns: int  # 0 = never started / disabled
    warmup_duration_ns: int  # configured duration in ns
    age_ns: int  # current_ns - engine_start_ns; 0 if not started
    remaining_ns: int  # ns left in warmup; 0 if complete or not started
    snapshot_ns: int  # wall-clock of this snapshot


@dataclass(frozen=True)
class KSCooldownSnapshot:
    """Immutable state of the post-kill-switch cooldown window."""

    phase: CooldownPhase
    cooldown_until_ns: int  # absolute ns when cooldown expires; 0 = none
    triggered_by_level: int  # KS level that last triggered cooldown; 0 = none
    age_ns: int  # ns elapsed since cooldown started; 0 if inactive
    remaining_ns: int  # ns until cooldown expires; 0 if inactive
    snapshot_ns: int


@dataclass(frozen=True)
class ActiveEventWindow:
    """A single event window that is active at a given timestamp."""

    event_id: str
    event_type: TemporalEventType
    description: str
    remaining_ns: int  # ns until end of this window


@dataclass(frozen=True)
class TemporalSnapshot:
    """Aggregate temporal state snapshot produced by TemporalScheduler.

    This is the value passed to guard as `temporal=TemporalInput(...)`.

    Fields:
        warmup          — startup warmup state.
        cooldown        — KS cooldown state.
        active_events   — tuple of currently active event windows (NT-T03).
        event_count     — total scheduled events (active + future).
        snapshot_ns     — wall-clock when snapshot was taken.
    """

    warmup: StartupWarmupSnapshot
    cooldown: KSCooldownSnapshot
    active_events: tuple[ActiveEventWindow, ...]
    event_count: int  # total events in the scheduler (not just active)
    snapshot_ns: int

    @property
    def startup_warmup_active(self) -> bool:
        """True iff NT-T01 should block (warmup ACTIVE)."""
        return self.warmup.phase == WarmupPhase.ACTIVE

    @property
    def ks_cooldown_active(self) -> bool:
        """True iff NT-T02 should block (cooldown ACTIVE)."""
        return self.cooldown.phase == CooldownPhase.ACTIVE

    @property
    def high_impact_event_window_active(self) -> bool:
        """True iff NT-T03 should block (any active event window)."""
        return len(self.active_events) > 0
