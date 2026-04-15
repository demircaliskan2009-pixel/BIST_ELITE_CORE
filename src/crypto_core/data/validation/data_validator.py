"""DataValidator — orchestrates all validation rules.

This is the single entry point for data validation.
All processors call DataValidator before accepting any event.

Fail-closed contract:
- Any rule violation raises ValidationError immediately.
- The caller (processor) catches the error, logs it, and discards the event.
- No partial acceptance. No auto-correction.

Stale detection:
- Checked per-feed via FeedState.is_stale().
- Called by DataIngestor before routing events downstream.

PRD reference: §4.2 (order book), §4.3 (trades), §4.4 (halt conditions NT-D01–NT-D05).
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Callable

from crypto_core.data.models.events import OrderBookEvent, TradeEvent
from crypto_core.data.validation.errors import ValidationError, ValidationErrorCode
from crypto_core.data.validation.rules import (
    validate_order_book_fields,
    validate_trade_clock,
    validate_trade_fields,
)
from crypto_core.data.validation.sequence_tracker import SequenceTracker

# Type alias for a wall-clock provider (injectable for deterministic tests).
WallClockProvider = Callable[[], int]  # returns nanoseconds since epoch

# Maximum number of trade IDs kept in the dedup window.
# 100 000 entries ≈ 8 MB worst-case, covers 30-60s of high-throughput trade streams.
_DEDUP_MAX_SIZE: int = 100_000


class DataValidator:
    """Orchestrates all validation rules for the data layer.

    Each DataValidator instance maintains its own SequenceTracker and
    a set of seen trade_ids for deduplication.

    Constructor args:
        wall_clock:          callable returning current time in nanoseconds (UTC).
                             Defaults to time.time_ns. Override in tests for determinism.
        clock_drift_threshold_ns: maximum acceptable |event_ts - wall_clock| before CLOCK_DRIFT.
        stale_threshold_ns:  maximum time since last event before STALE_DATA (default 10s).
        active_symbols:      optional whitelist of valid symbols; None = all symbols accepted.
    """

    def __init__(
        self,
        wall_clock: WallClockProvider | None = None,
        clock_drift_threshold_ns: int = 5_000_000_000,
        stale_threshold_ns: int = 10_000_000_000,
        active_symbols: set[str] | None = None,
        dedup_max_size: int = _DEDUP_MAX_SIZE,
    ) -> None:
        import time

        self._wall_clock: WallClockProvider = wall_clock or time.time_ns
        self._clock_drift_threshold_ns = clock_drift_threshold_ns
        self._stale_threshold_ns = stale_threshold_ns
        self._active_symbols = active_symbols
        self._sequence_tracker = SequenceTracker()
        self._dedup_max_size = dedup_max_size
        # OrderedDict used as an O(1) insertion-ordered set with FIFO eviction.
        self._seen_trade_ids: OrderedDict[str, None] = OrderedDict()

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    def validate_trade(self, event: TradeEvent) -> None:
        """Full validation for a TradeEvent.

        Checks (in order):
         1. Symbol whitelist (if configured)
         2. Field presence and value constraints
         3. Clock drift
         4. Trade-ID deduplication
         5. Stream sequence number

        Raises ValidationError on the first violation encountered.
        """
        self._check_symbol(event.symbol)
        validate_trade_fields(event)
        validate_trade_clock(event, self._wall_clock(), self._clock_drift_threshold_ns)
        self._check_trade_dedup(event)
        stream_key = self._trade_stream_key(event)
        self._sequence_tracker.advance(stream_key, event.sequence_no)

    def validate_order_book(self, event: OrderBookEvent) -> None:
        """Full validation for an OrderBookEvent.

        Checks (in order):
         1. Symbol whitelist (if configured)
         2. Field presence and value constraints

        Sequence for order book deltas is handled by OrderBookManager
        (which needs to compare against the last_update_id of the local book,
        not just the previous event — handled at the application layer).

        Raises ValidationError on the first violation encountered.
        """
        self._check_symbol(event.symbol)
        validate_order_book_fields(event)

    def check_stale(self, stream_key: str, last_event_ts_ns: int) -> None:
        """Check whether a stream is stale.

        Raises ValidationError(STALE_DATA) if the wall clock has advanced
        more than stale_threshold_ns since last_event_ts_ns.

        Called by DataIngestor on a periodic heartbeat, not per-event.
        """
        if last_event_ts_ns == 0:
            return  # never received data — not yet stale
        wall = self._wall_clock()
        delta = wall - last_event_ts_ns
        if delta > self._stale_threshold_ns:
            raise ValidationError(
                ValidationErrorCode.STALE_DATA,
                f"Stream '{stream_key}' stale: no event for {delta / 1e9:.1f}s "
                f"(threshold {self._stale_threshold_ns / 1e9:.1f}s)",
                {"stream_key": stream_key, "last_event_ts_ns": last_event_ts_ns, "wall_ns": wall, "delta_ns": delta},
            )

    def reset_sequence(self, stream_key: str) -> None:
        """Reset sequence tracker for a stream (called on reconnect)."""
        self._sequence_tracker.reset(stream_key)

    # ──────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────

    def _check_symbol(self, symbol: str) -> None:
        if self._active_symbols is not None and symbol not in self._active_symbols:
            raise ValidationError(
                ValidationErrorCode.INVALID_SYMBOL,
                f"Symbol '{symbol}' is not in the active universe",
                {"symbol": symbol},
            )

    def _check_trade_dedup(self, event: TradeEvent) -> None:
        dedup_key = f"{event.exchange.value}:{event.symbol}:{event.trade_id}"
        if dedup_key in self._seen_trade_ids:
            raise ValidationError(
                ValidationErrorCode.DUPLICATE_EVENT,
                f"Duplicate trade_id '{event.trade_id}' for {event.symbol} on {event.exchange}",
                {"trade_id": event.trade_id, "symbol": event.symbol, "exchange": str(event.exchange)},
            )
        self._seen_trade_ids[dedup_key] = None
        # FIFO eviction: drop oldest entries when window is exceeded.
        while len(self._seen_trade_ids) > self._dedup_max_size:
            self._seen_trade_ids.popitem(last=False)

    @staticmethod
    def _trade_stream_key(event: TradeEvent) -> str:
        return f"{event.exchange.value}:{event.symbol}:trade"
