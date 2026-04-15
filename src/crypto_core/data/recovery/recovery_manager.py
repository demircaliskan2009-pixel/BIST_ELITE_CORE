"""RecoveryManager — reconnect, exponential backoff, snapshot protocol.

Manages the full lifecycle of a stream recovery after disconnect:
1. Detect disconnection (heartbeat timeout).
2. Reconnect with exponential backoff (1s, 2s, 4s, 8s … max 30s).
3. Request a full order book snapshot on reconnection.
4. Replay delta updates received between snapshot timestamp and WS catch-up.
5. Validate state consistency (CRC32 + sequence).
6. Transition FeedState to READY.

If recovery fails after max_recovery_seconds → escalate via on_recovery_failed.

Fail-closed:
- No events are emitted downstream while recovery_state != READY.
- Failed recovery raises / calls on_recovery_failed callback.

PRD reference: §4.5 Recovery Protocol.
  - ping every 5s, timeout at 15s
  - backoff: 1s, 2s, 4s, 8s, max 30s
  - failed after 120s → escalate to KS-3
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from crypto_core.data.models.feed_state import ConnectionState, FeedState, RecoveryState

logger = logging.getLogger(__name__)

# Backoff sequence per PRD §4.5 (seconds).
_BACKOFF_SEQUENCE = [1.0, 2.0, 4.0, 8.0, 16.0, 30.0]
_MAX_RECOVERY_SECONDS = 120.0

# Callback definitions.
# Called when recovery succeeded (feed is READY again).
RecoverySuccessCallback = Callable[[FeedState], None]
# Called when recovery is exhausted (120s limit or max retries).
RecoveryFailedCallback = Callable[[FeedState, str], None]
# Called when a new WebSocket connection must be established.
ConnectCallback = Callable[[], None]
# Called when a REST snapshot must be requested.
SnapshotRequestCallback = Callable[[str, str], None]  # (symbol, exchange)


class RecoveryManager:
    """Manages stream reconnect and recovery for one (symbol, exchange) feed.

    Constructor args:
        feed_state:           The FeedState object for the feed; mutated by this manager.
        on_connect:           Callback to re-establish the WebSocket connection.
        on_snapshot_request:  Callback to request a REST order book snapshot.
        on_recovery_success:  Optional callback when recovery completes.
        on_recovery_failed:   Optional callback when recovery is exhausted.
        sleep_fn:             Injectable sleep function (use a no-op in tests).
        max_recovery_seconds: Maximum wall-clock seconds before giving up (PRD §4.5: 120s).
    """

    def __init__(
        self,
        feed_state: FeedState,
        on_connect: ConnectCallback,
        on_snapshot_request: SnapshotRequestCallback,
        on_recovery_success: Optional[RecoverySuccessCallback] = None,
        on_recovery_failed: Optional[RecoveryFailedCallback] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        max_recovery_seconds: float = _MAX_RECOVERY_SECONDS,
    ) -> None:
        self._feed_state = feed_state
        self._on_connect = on_connect
        self._on_snapshot_request = on_snapshot_request
        self._on_recovery_success = on_recovery_success
        self._on_recovery_failed = on_recovery_failed
        self._sleep = sleep_fn or time.sleep
        self._max_recovery_seconds = max_recovery_seconds

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    def on_disconnect(self) -> None:
        """Trigger recovery on detected disconnection.

        Transitions FeedState:
          CONNECTED → RECONNECTING
          Runs the full reconnect + snapshot loop.
        """
        fs = self._feed_state
        fs.connection_state = ConnectionState.RECONNECTING
        fs.recovery_state = RecoveryState.IDLE
        logger.warning(
            "Feed %s:%s disconnected — starting recovery",
            fs.exchange,
            fs.symbol,
        )
        self._run_recovery_loop()

    def on_snapshot_received(self) -> None:
        """Called when the REST snapshot response has been applied by OrderBookManager.

        Transitions RecoveryState: SNAPSHOTTING → REPLAYING.
        """
        self._feed_state.recovery_state = RecoveryState.REPLAYING
        self._feed_state.snapshot_pending = False
        logger.info(
            "Snapshot received for %s:%s — replaying deltas",
            self._feed_state.exchange,
            self._feed_state.symbol,
        )

    def on_stream_caught_up(self) -> None:
        """Called when WS delta updates have caught up to the snapshot's update_id.

        Transitions RecoveryState: REPLAYING → VALIDATING.
        """
        self._feed_state.recovery_state = RecoveryState.VALIDATING
        logger.info(
            "WS caught up to snapshot for %s:%s — validating",
            self._feed_state.exchange,
            self._feed_state.symbol,
        )

    def on_validation_passed(self) -> None:
        """Called when CRC32 + sequence validation passes after re-snapshot.

        Transitions RecoveryState: VALIDATING → READY.
        """
        fs = self._feed_state
        fs.recovery_state = RecoveryState.READY
        fs.reconnect_attempt = 0
        logger.info("Recovery complete for %s:%s — feed is READY", fs.exchange, fs.symbol)
        if self._on_recovery_success is not None:
            self._on_recovery_success(fs)

    # ──────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────

    def _run_recovery_loop(self) -> None:
        """Execute the reconnect + snapshot loop with exponential backoff."""
        fs = self._feed_state
        start_time = time.monotonic()
        attempt = 0

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed >= self._max_recovery_seconds:
                reason = (
                    f"Recovery exhausted after {elapsed:.1f}s "
                    f"({attempt} attempts) for {fs.exchange}:{fs.symbol}"
                )
                logger.error(reason)
                fs.connection_state = ConnectionState.FAILED
                fs.recovery_state = RecoveryState.FAILED
                if self._on_recovery_failed is not None:
                    self._on_recovery_failed(fs, reason)
                return

            # Exponential backoff before reconnect attempt.
            backoff = _BACKOFF_SEQUENCE[min(attempt, len(_BACKOFF_SEQUENCE) - 1)]
            logger.info(
                "Recovery attempt %d for %s:%s — waiting %.1fs",
                attempt + 1,
                fs.exchange,
                fs.symbol,
                backoff,
            )
            self._sleep(backoff)

            fs.reconnect_attempt = attempt + 1
            fs.connection_state = ConnectionState.CONNECTING
            try:
                self._on_connect()
                fs.connection_state = ConnectionState.CONNECTED
            except Exception as connect_exc:
                logger.warning(
                    "Reconnect attempt %d failed for %s:%s: %s",
                    attempt + 1,
                    fs.exchange,
                    fs.symbol,
                    connect_exc,
                )
                attempt += 1
                continue

            # Request full snapshot on successful reconnect.
            fs.recovery_state = RecoveryState.SNAPSHOTTING
            fs.snapshot_pending = True
            try:
                self._on_snapshot_request(fs.symbol, fs.exchange)
                # Caller is responsible for calling on_snapshot_received() and
                # on_stream_caught_up() and on_validation_passed() in sequence.
                return
            except Exception as snap_exc:
                logger.warning(
                    "Snapshot request failed for %s:%s: %s",
                    fs.exchange,
                    fs.symbol,
                    snap_exc,
                )
                attempt += 1
