"""Feed connection and recovery state models.

FeedState: single source of truth for the lifecycle of one (symbol, exchange, stream_type) feed.
All state transitions are explicit — no implicit state changes.

PRD reference: §4.5 Recovery Protocol, §8 System State Engine (SHS).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConnectionState(str, Enum):
    """WebSocket connection lifecycle states.

    Transitions:
      DISCONNECTED → CONNECTING (on connect attempt)
      CONNECTING   → CONNECTED  (on WS handshake complete)
      CONNECTED    → RECONNECTING (on disconnect detected)
      RECONNECTING → CONNECTING  (on retry)
      RECONNECTING → FAILED      (retries exhausted)
    """

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"  # all retries exhausted; escalates to KS-3


class RecoveryState(str, Enum):
    """Data recovery lifecycle after reconnect.

    Transitions:
      IDLE         → SNAPSHOTTING (on reconnect)
      SNAPSHOTTING → REPLAYING    (on snapshot received)
      REPLAYING    → VALIDATING   (on WS stream caught up to snapshot)
      VALIDATING   → READY        (on CRC32 + sequence validation pass)
      ANY          → FAILED       (on validation failure)
    """

    IDLE = "idle"
    SNAPSHOTTING = "snapshotting"
    REPLAYING = "replaying"
    VALIDATING = "validating"
    READY = "ready"
    FAILED = "failed"  # recovery failed; feed is in UNSAFE state


@dataclass
class FeedState:
    """Per-stream connection and recovery state.

    Single source of truth per (symbol, exchange, stream_type) tuple.
    No data is emitted downstream while recovery_state != READY.

    reconnect_attempt: monotonically increasing retry counter; reset to 0 on CONNECTED.
    snapshot_pending: True when a REST snapshot has been requested but not yet applied.
    """

    symbol: str
    exchange: str
    stream_type: str
    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    recovery_state: RecoveryState = RecoveryState.IDLE
    last_event_ts_ns: int = 0
    last_sequence_no: int = -1  # -1 = no event seen yet
    reconnect_attempt: int = 0
    snapshot_pending: bool = False

    def is_live(self) -> bool:
        """Returns True only when feed is connected and data is validated."""
        return (
            self.connection_state == ConnectionState.CONNECTED
            and self.recovery_state == RecoveryState.READY
        )

    def is_stale(self, wall_clock_ns: int, stale_threshold_ns: int = 10_000_000_000) -> bool:
        """Returns True if no event has been received within stale_threshold_ns.

        Default threshold: 10 seconds (PRD §4.2 NT-D02).
        """
        if self.last_event_ts_ns == 0:
            return False  # no event yet; staleness not applicable
        return (wall_clock_ns - self.last_event_ts_ns) > stale_threshold_ns
