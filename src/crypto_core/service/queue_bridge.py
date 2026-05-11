"""Thread-safe bounded event queue bridge — Phase 8A.

Provides the async-safe bridge between DataIngestor callback threads
(producers) and the single-threaded paper-live consumer loop.

Design rules:
- Thread-safe: multiple producer threads may call enqueue() concurrently.
- Single consumer: drain() / get() must be called from one thread only.
- Bounded: queue has a hard capacity limit.
- Fail-closed on overflow: events are dropped and counted; the service
  must detect overflow via queue_snapshot() and act accordingly.
- Deterministic replay: when used without real threads (test/replay mode),
  enqueue+drain produces the same ordered sequence.

PRD reference: §2 System Orchestration, §4.1 Data Layer.
"""

from __future__ import annotations

import logging
import queue
import threading
import time

from crypto_core.service.models import QueuePressure, QueueSnapshot, ServiceConfig

logger = logging.getLogger(__name__)


class EventQueueBridge:
    """Bounded event queue between feed callback threads and consumer loop.

    Usage::

        bridge = EventQueueBridge(config)
        # Producer side (feed callback threads):
        bridge.enqueue(event)
        # Consumer side (single processing thread):
        event = bridge.get(timeout=1.0)

    Thread safety:
        enqueue() is safe to call from any thread.
        get() / drain() must be called from the consumer thread only.
    """

    def __init__(self, config: ServiceConfig) -> None:
        self._config = config
        self._queue: queue.Queue[object] = queue.Queue(maxsize=config.queue_max_size)
        self._lock = threading.Lock()  # protects counters only

        # Counters (protected by _lock).
        self._total_enqueued: int = 0
        self._total_dropped: int = 0
        self._total_processed: int = 0
        self._last_enqueue_time_ns: int = 0
        self._last_dequeue_time_ns: int = 0

        # Overflow audit trail.
        self._overflow_count: int = 0
        self._last_overflow_time_ns: int = 0

    # ------------------------------------------------------------------
    # Producer side (thread-safe)
    # ------------------------------------------------------------------

    def enqueue(self, event: object) -> bool:
        """Enqueue an event from a producer thread.

        Returns True if the event was accepted, False if the queue is full
        (overflow). Overflow is counted and auditable.

        Thread-safe: may be called from any thread concurrently.
        """
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            with self._lock:
                self._total_dropped += 1
                self._overflow_count += 1
                self._last_overflow_time_ns = time.time_ns()
            logger.warning(
                "EventQueueBridge overflow — event dropped (total_dropped=%d, queue_size=%d)",
                self._total_dropped,
                self._config.queue_max_size,
            )
            return False

        with self._lock:
            self._total_enqueued += 1
            self._last_enqueue_time_ns = time.time_ns()
        return True

    # ------------------------------------------------------------------
    # Consumer side (single-threaded)
    # ------------------------------------------------------------------

    def get(self, timeout: float | None = None) -> object | None:
        """Get the next event from the queue.

        Returns None if the queue is empty after the timeout expires.
        Must be called from the consumer thread only.
        """
        effective_timeout = timeout if timeout is not None else self._config.consumer_poll_timeout_s
        try:
            event = self._queue.get(timeout=effective_timeout)
        except queue.Empty:
            return None

        with self._lock:
            self._total_processed += 1
            self._last_dequeue_time_ns = time.time_ns()
        return event

    def drain(self, max_events: int = 0) -> list[object]:
        """Drain events from the queue without blocking.

        Args:
            max_events: maximum events to drain (0 = drain all available).

        Returns:
            List of events in FIFO order.
        """
        events: list[object] = []
        limit = max_events if max_events > 0 else self._config.queue_max_size
        while len(events) < limit:
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                break
            events.append(event)

        if events:
            with self._lock:
                self._total_processed += len(events)
                self._last_dequeue_time_ns = time.time_ns()
        return events

    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------

    def queue_snapshot(self) -> QueueSnapshot:
        """Produce a snapshot of the queue state.

        Thread-safe: may be called from any thread.
        """
        depth = self._queue.qsize()
        max_size = self._config.queue_max_size
        pressure = self._compute_pressure(depth, max_size)

        with self._lock:
            return QueueSnapshot(
                current_depth=depth,
                max_size=max_size,
                pressure=pressure,
                total_enqueued=self._total_enqueued,
                total_dropped=self._total_dropped,
                total_processed=self._total_processed,
            )

    @property
    def depth(self) -> int:
        """Current number of events in the queue."""
        return self._queue.qsize()

    @property
    def total_dropped(self) -> int:
        """Total events dropped due to overflow."""
        with self._lock:
            return self._total_dropped

    @property
    def last_enqueue_time_ns(self) -> int:
        """Wall-clock ns of the last successful enqueue."""
        with self._lock:
            return self._last_enqueue_time_ns

    @property
    def last_dequeue_time_ns(self) -> int:
        """Wall-clock ns of the last successful dequeue."""
        with self._lock:
            return self._last_dequeue_time_ns

    def is_empty(self) -> bool:
        """True if the queue is currently empty."""
        return self._queue.empty()

    def clear(self) -> int:
        """Clear all events from the queue. Returns the count of cleared events."""
        count = 0
        while True:
            try:
                self._queue.get_nowait()
                count += 1
            except queue.Empty:
                break
        return count

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _compute_pressure(self, depth: int, max_size: int) -> QueuePressure:
        """Classify queue occupancy into a pressure zone."""
        if max_size <= 0:
            return QueuePressure.NORMAL

        pct = (depth / max_size) * 100.0

        if depth >= max_size:
            return QueuePressure.OVERFLOW
        if pct >= self._config.queue_critical_pct:
            return QueuePressure.CRITICAL
        if pct >= self._config.queue_warning_pct:
            return QueuePressure.WARNING
        return QueuePressure.NORMAL
