"""Temporal subsystem — public API.

Phase 5G: deterministic temporal scheduling for NT-T rule family.

Exports:
  TemporalEventType          — event category enum
  WarmupPhase                — warmup lifecycle enum
  CooldownPhase              — KS cooldown lifecycle enum
  ScheduledEvent             — immutable scheduled event window
  StartupWarmupSnapshot      — immutable warmup state snapshot
  KSCooldownSnapshot         — immutable KS cooldown state snapshot
  ActiveEventWindow          — one currently-active event window entry
  TemporalSnapshot           — aggregate temporal state for one cycle
  TemporalSchedulerConfig    — configuration for TemporalScheduler
  TemporalSchedulerError     — raised on malformed input (fail-closed)
  TemporalScheduler          — stateful deterministic temporal engine
"""

from crypto_core.temporal.models import (
    ActiveEventWindow,
    CooldownPhase,
    KSCooldownSnapshot,
    ScheduledEvent,
    StartupWarmupSnapshot,
    TemporalEventType,
    TemporalSnapshot,
    WarmupPhase,
)
from crypto_core.temporal.scheduler import TemporalScheduler, TemporalSchedulerConfig, TemporalSchedulerError

__all__ = [
    "TemporalEventType",
    "WarmupPhase",
    "CooldownPhase",
    "ScheduledEvent",
    "StartupWarmupSnapshot",
    "KSCooldownSnapshot",
    "ActiveEventWindow",
    "TemporalSnapshot",
    "TemporalSchedulerConfig",
    "TemporalSchedulerError",
    "TemporalScheduler",
]
