"""DeltaBuffer — bounded in-memory buffer for order-book deltas during recovery.

Purpose:
  During a reconnect/recovery window, incoming order-book delta events CANNOT
  be applied to the book immediately because the book state is undefined until
  the REST snapshot has been fetched and applied.

  DeltaBuffer accumulates those deltas in sequence order during the SNAPSHOTTING
  state so they can be replayed against the restored snapshot in REPLAYING state.

Fail-closed contract:
  - Buffer is bounded by MAX_DELTAS.
  - Overflow → OverflowError raised at push time (caller must fail recovery).
  - Sequence discontinuity within the buffer is detected at replay time.
  - Stale deltas (last_update_id <= snapshot.last_update_id) are silently
    discarded during replay (they are already covered by the snapshot).
  - Gap after snapshot (first buffered relevant delta is not contiguous with
    snapshot) → raises SequenceGapError at replay time.
  - Out-of-order buffered delta → raises SequenceGapError at replay time.

PRD reference: §4.5 Recovery Protocol — delta replay closure (Phase 7C).
"""

from __future__ import annotations

import logging
from collections import deque

from crypto_core.data.models.events import OrderBookEvent, OrderBookEventType

logger = logging.getLogger(__name__)

# Maximum number of delta events to hold in the buffer.
# Binance emits ~100ms depth updates; 500 events covers ~50s of data.
# Keeping it bounded prevents unbounded memory use during slow snapshot fetch.
MAX_DELTAS: int = 500


class SequenceGapError(Exception):
    """Raised when buffered deltas cannot be continuously replayed against snapshot."""

    def __init__(self, message: str, expected: int, got: int) -> None:
        super().__init__(message)
        self.expected = expected
        self.got = got


class DeltaBuffer:
    """Bounded FIFO buffer that accumulates order-book DELTA events during recovery.

    Usage lifecycle per recovery cycle:
      1. buffer.start_buffering()      → open the buffer (recovery begins)
      2. buffer.push(delta)            → store each incoming delta (≤ MAX_DELTAS)
      3. snapshot = fetcher.fetch()    → REST snapshot arrives
      4. deltas = buffer.drain_for_replay(snapshot.last_update_id)
                                       → returns only deltas newer than snapshot
      5. apply snapshot, then apply each delta in order via OrderBookManager
      6. buffer.clear()                → reset for next cycle (or on success)

    Thread safety:
      The buffer is NOT thread-safe by design.  It is always accessed from the
      DataIngestor's raw-callback thread (push) and the recovery/supervision
      thread (drain_for_replay / clear).  Callers are responsible for ensuring
      these never overlap; the DataIngestor achieves this by design:
        - push() is called only while recovery_state == SNAPSHOTTING
        - drain_for_replay() is called by the snapshot callback after the
          snapshot fetch completes (same callchain, no overlap possible).
    """

    def __init__(self, max_deltas: int = MAX_DELTAS) -> None:
        self._max = max_deltas
        self._buf: deque[OrderBookEvent] = deque()
        self._active: bool = False

    # ──────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────

    def start_buffering(self) -> None:
        """Open the buffer.  Previous contents are discarded (clean slate per cycle)."""
        self._buf.clear()
        self._active = True
        logger.debug("DeltaBuffer: buffering started (capacity=%d)", self._max)

    def is_active(self) -> bool:
        """True while the buffer is open for pushes."""
        return self._active

    def clear(self) -> None:
        """Discard all buffered events and close the buffer."""
        count = len(self._buf)
        self._buf.clear()
        self._active = False
        logger.debug("DeltaBuffer: cleared (%d events discarded)", count)

    # ──────────────────────────────────────────────────────────────
    # Write path
    # ──────────────────────────────────────────────────────────────

    def push(self, event: OrderBookEvent) -> None:
        """Buffer a DELTA event during recovery.

        Only DELTA events are accepted.  SNAPSHOT events are rejected with
        ValueError — the snapshot callback path handles those separately.

        Raises:
            ValueError:    if event is not a DELTA or buffer is not active.
            OverflowError: if buffer would exceed max_deltas (fail-closed).
        """
        if not self._active:
            raise ValueError("DeltaBuffer.push() called while buffer is not active")
        if event.event_type != OrderBookEventType.DELTA:
            raise ValueError(f"DeltaBuffer only accepts DELTA events, got {event.event_type}")
        if len(self._buf) >= self._max:
            raise OverflowError(
                f"DeltaBuffer overflow: max_deltas={self._max} reached for "
                f"{event.exchange}:{event.symbol}. Recovery must fail closed."
            )
        self._buf.append(event)
        logger.debug(
            "DeltaBuffer.push: buffered delta update_id=%d  buf_size=%d",
            event.last_update_id,
            len(self._buf),
        )

    # ──────────────────────────────────────────────────────────────
    # Read / replay path
    # ──────────────────────────────────────────────────────────────

    def drain_for_replay(
        self,
        snapshot_last_update_id: int,
        *,
        require_strict_contiguous: bool = True,
    ) -> list[OrderBookEvent]:
        """Return ordered list of deltas that must be replayed after the snapshot.

        Algorithm:
          1. Discard all deltas whose last_update_id <= snapshot_last_update_id
             (they are already covered by the snapshot).
          2. Verify the remaining deltas form a valid replay sequence:

             require_strict_contiguous=True  (Binance — strict +1 contiguity):
               - delta[0].first_update_id must equal snapshot_last_update_id + 1.
               - each successive delta[i].first_update_id must equal
                 delta[i-1].last_update_id + 1.

             require_strict_contiguous=False  (Bybit — monotonic ordering):
               - delta[0].first_update_id must be strictly greater than
                 snapshot_last_update_id (no +1 requirement; Bybit seq is a
                 global cross-symbol counter with legitimate gaps per symbol).
               - each successive delta[i].first_update_id must be strictly
                 greater than delta[i-1].last_update_id (monotonically
                 increasing, gaps are valid).

          3. If the sequence check fails → raise SequenceGapError (fail-closed).
          4. Return the validated list.

        Does NOT clear the buffer.  Call clear() after successful replay.

        Args:
            snapshot_last_update_id: The last_update_id of the REST snapshot.
            require_strict_contiguous: True (default) for Binance strict +1
                contiguity.  False for Bybit monotonic-only ordering.

        Raises:
            SequenceGapError: if the replay sequence is broken or gapped.
        """
        # Step 1: filter out deltas already covered by the snapshot.
        relevant = [d for d in self._buf if d.last_update_id > snapshot_last_update_id]

        if not relevant:
            logger.info(
                "DeltaBuffer.drain_for_replay: no deltas newer than snapshot update_id=%d (buffered=%d total)",
                snapshot_last_update_id,
                len(self._buf),
            )
            return []

        if require_strict_contiguous:
            # ── Binance path: strict +1 continuity ────────────────────────
            # Step 2a: verify first delta aligns immediately after snapshot.
            expected_first = snapshot_last_update_id + 1
            if relevant[0].first_update_id != expected_first:
                raise SequenceGapError(
                    f"Gap between snapshot and first replay delta: "
                    f"expected first_update_id={expected_first}, "
                    f"got {relevant[0].first_update_id} "
                    f"(symbol={relevant[0].symbol})",
                    expected=expected_first,
                    got=relevant[0].first_update_id,
                )

            # Step 3a: verify inter-delta strict +1 continuity.
            for i in range(1, len(relevant)):
                prev = relevant[i - 1]
                curr = relevant[i]
                expected = prev.last_update_id + 1
                if curr.first_update_id != expected:
                    raise SequenceGapError(
                        f"Delta replay sequence gap at position {i}: "
                        f"expected first_update_id={expected}, "
                        f"got {curr.first_update_id} "
                        f"(symbol={curr.symbol})",
                        expected=expected,
                        got=curr.first_update_id,
                    )
        else:
            # ── Bybit path: monotonic ordering only (no strict +1) ─────────
            # Step 2b: first delta must be strictly after the snapshot seq.
            if relevant[0].first_update_id <= snapshot_last_update_id:
                raise SequenceGapError(
                    f"First replay delta is not strictly after snapshot: "
                    f"snapshot_last={snapshot_last_update_id}, "
                    f"got first_update_id={relevant[0].first_update_id} "
                    f"(symbol={relevant[0].symbol})",
                    expected=snapshot_last_update_id + 1,
                    got=relevant[0].first_update_id,
                )

            # Step 3b: verify inter-delta strict monotonic ordering.
            for i in range(1, len(relevant)):
                prev = relevant[i - 1]
                curr = relevant[i]
                if curr.first_update_id <= prev.last_update_id:
                    raise SequenceGapError(
                        f"Non-monotonic delta at position {i}: "
                        f"prev last_update_id={prev.last_update_id}, "
                        f"got first_update_id={curr.first_update_id} "
                        f"(symbol={curr.symbol}) — out-of-order or duplicate",
                        expected=prev.last_update_id + 1,
                        got=curr.first_update_id,
                    )

        logger.info(
            "DeltaBuffer.drain_for_replay: %d deltas validated for replay "
            "(snapshot_update_id=%d, first=%d, last=%d, strict_contiguous=%s)",
            len(relevant),
            snapshot_last_update_id,
            relevant[0].first_update_id,
            relevant[-1].last_update_id,
            require_strict_contiguous,
        )
        return relevant

    # ──────────────────────────────────────────────────────────────
    # Inspection
    # ──────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._buf)

    def __repr__(self) -> str:
        return f"DeltaBuffer(active={self._active}, size={len(self._buf)}, max={self._max})"
