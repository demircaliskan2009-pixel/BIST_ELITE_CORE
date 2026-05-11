"""Edge health subsystem — public API.

Phase 5F: deterministic edge health tracking for NT-E rule family.

Exports:
  EdgeFSMState           — lifecycle FSM state enum (ACTIVE/DEGRADED/DISABLED)
  UtilizationBand        — capacity utilization band enum (SAFE/WARNING/RED)
  EdgeSignalRecord       — one signal observation stored in rolling history
  EdgeHealthSnapshot     — immutable per-(family, symbol, exchange) health state
  EdgeHealthTrackerSnapshot — aggregate tracker-level summary for telemetry
  EdgeSignalRecordError  — raised on malformed record (fail-closed)
  EdgeHealthTracker      — stateful deterministic edge health tracker engine
"""

from crypto_core.edge_health.models import (
    EdgeFSMState,
    EdgeHealthSnapshot,
    EdgeHealthTrackerSnapshot,
    EdgeSignalRecord,
    UtilizationBand,
)
from crypto_core.edge_health.tracker import EdgeHealthTracker, EdgeSignalRecordError

__all__ = [
    "EdgeFSMState",
    "EdgeHealthSnapshot",
    "EdgeHealthTrackerSnapshot",
    "EdgeSignalRecord",
    "UtilizationBand",
    "EdgeHealthTracker",
    "EdgeSignalRecordError",
]
