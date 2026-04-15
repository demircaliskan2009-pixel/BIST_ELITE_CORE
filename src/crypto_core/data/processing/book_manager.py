"""OrderBookManager — applies snapshots/deltas, validates CRC32, detects stale.

Responsibilities:
1. Maintain a single OrderBook per (symbol, exchange).
2. Apply snapshot and delta events in their correct sequence.
3. Validate CRC32 checksums when provided (Bybit).
4. Detect and reject crossed books after any update.
5. Detect deltas arriving before initial snapshot.
6. Enforce sequence continuity: delta.first_update_id == book.last_update_id + 1.

Fail-closed:
- CRC32 mismatch → raise ValidationError (caller triggers re-snapshot).
- Crossed book → raise ValidationError.
- Delta before snapshot → raise ValidationError.
- Sequence gap in deltas → raise ValidationError.

State boundary: one OrderBookManager instance per (symbol, exchange).

PRD reference: §4.2 (order book management), §4.5 (CRC32 recovery trigger).
"""

from __future__ import annotations

import logging
import zlib
from typing import Callable

from crypto_core.data.models.events import OrderBookEvent, OrderBookEventType
from crypto_core.data.models.order_book import OrderBook
from crypto_core.data.validation.errors import ValidationError, ValidationErrorCode

logger = logging.getLogger(__name__)

# Downstream callback: receives a snapshot copy of the OrderBook after each update.
BookUpdateCallback = Callable[[OrderBook], None]


class OrderBookManager:
    """Manages L2 order book state for one (symbol, exchange).

    Initialise one per symbol per exchange:
        mgr = OrderBookManager("BTCUSDT", "binance", on_book_update=my_callback)

    Call apply(event) for every OrderBookEvent received from EventRouter.
    """

    def __init__(
        self,
        symbol: str,
        exchange: str,
        on_book_update: BookUpdateCallback | None = None,
        stale_threshold_ns: int = 10_000_000_000,
    ) -> None:
        self._symbol = symbol
        self._exchange = exchange
        self._on_book_update = on_book_update
        self._stale_threshold_ns = stale_threshold_ns
        self._book: OrderBook = OrderBook(symbol=symbol, exchange=exchange)
        self._has_snapshot: bool = False

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    def apply(self, event: OrderBookEvent) -> None:
        """Apply an order book event to the local book.

        Raises ValidationError for:
          - Delta before snapshot
          - Sequence gap
          - Crossed book after update
          - CRC32 mismatch (when checksum provided)

        On success: calls on_book_update with the updated book.
        """
        if event.event_type == OrderBookEventType.SNAPSHOT:
            self._apply_snapshot(event)
        else:
            self._apply_delta(event)

        if self._on_book_update is not None:
            self._on_book_update(self._book.snapshot())

    def book(self) -> OrderBook:
        """Returns a snapshot copy of the current book state (safe to read, do NOT mutate)."""
        return self._book.snapshot()

    def has_snapshot(self) -> bool:
        """Returns True if an initial snapshot has been applied."""
        return self._has_snapshot

    def reset(self) -> None:
        """Discard current book state and mark as requiring a new snapshot.

        Called by RecoveryManager on reconnect.
        """
        self._book = OrderBook(symbol=self._symbol, exchange=self._exchange)
        self._has_snapshot = False
        logger.info("OrderBookManager reset for %s:%s", self._exchange, self._symbol)

    def check_stale(self, wall_clock_ns: int) -> None:
        """Raise ValidationError(STALE_DATA) if the book hasn't been updated recently.

        Called by DataIngestor on its heartbeat timer.
        """
        if self._book.last_update_ts_ns == 0:
            return  # no update yet
        delta = wall_clock_ns - self._book.last_update_ts_ns
        if delta > self._stale_threshold_ns:
            raise ValidationError(
                ValidationErrorCode.STALE_DATA,
                f"Order book for {self._exchange}:{self._symbol} stale: "
                f"no update for {delta / 1e9:.1f}s (threshold {self._stale_threshold_ns / 1e9:.1f}s)",
                {"symbol": self._symbol, "exchange": self._exchange, "delta_ns": delta},
            )

    # ──────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────

    def _apply_snapshot(self, event: OrderBookEvent) -> None:
        """Replace the local book with a full snapshot."""
        self._book.bids.clear()
        self._book.asks.clear()
        for level in event.bids:
            if level.qty > 0.0:
                self._book.bids[level.price] = level.qty
        for level in event.asks:
            if level.qty > 0.0:
                self._book.asks[level.price] = level.qty
        self._book.last_update_id = event.last_update_id
        self._book.last_update_ts_ns = event.timestamp_ns
        self._book.snapshot_ts_ns = event.timestamp_ns
        self._has_snapshot = True
        self._validate_book_integrity(event)
        logger.debug(
            "OrderBook snapshot applied for %s:%s  update_id=%d  bids=%d  asks=%d",
            self._exchange,
            self._symbol,
            event.last_update_id,
            len(self._book.bids),
            len(self._book.asks),
        )

    def _apply_delta(self, event: OrderBookEvent) -> None:
        """Apply an incremental delta to the local book."""
        if not self._has_snapshot:
            raise ValidationError(
                ValidationErrorCode.BOOK_NO_SNAPSHOT,
                f"Delta received before initial snapshot for {self._exchange}:{self._symbol}",
                {"symbol": self._symbol, "exchange": self._exchange, "update_id": event.last_update_id},
            )

        # Sequence continuity check for deltas.
        # Binance: event.first_update_id must equal last_update_id + 1.
        expected_first = self._book.last_update_id + 1
        if event.first_update_id != expected_first:
            raise ValidationError(
                ValidationErrorCode.SEQ_GAP,
                f"OrderBook delta sequence gap for {self._exchange}:{self._symbol}: "
                f"expected first_update_id={expected_first}, got {event.first_update_id}",
                {
                    "symbol": self._symbol,
                    "expected_first": expected_first,
                    "got_first": event.first_update_id,
                    "last_update_id": self._book.last_update_id,
                },
            )

        # Apply bids
        for level in event.bids:
            if level.qty == 0.0:
                self._book.bids.pop(level.price, None)
            else:
                self._book.bids[level.price] = level.qty

        # Apply asks
        for level in event.asks:
            if level.qty == 0.0:
                self._book.asks.pop(level.price, None)
            else:
                self._book.asks[level.price] = level.qty

        self._book.last_update_id = event.last_update_id
        self._book.last_update_ts_ns = event.timestamp_ns

        self._validate_book_integrity(event)
        self._validate_checksum(event)

    def _validate_book_integrity(self, event: OrderBookEvent) -> None:
        """Raise ValidationError if the book is in a crossed state."""
        if self._book.is_crossed():
            bb = self._book.best_bid()
            ba = self._book.best_ask()
            raise ValidationError(
                ValidationErrorCode.BOOK_CROSSED,
                f"Order book crossed after update: best_bid={bb} >= best_ask={ba} for {self._exchange}:{self._symbol}",
                {
                    "symbol": self._symbol,
                    "exchange": self._exchange,
                    "best_bid": bb,
                    "best_ask": ba,
                    "update_id": event.last_update_id,
                },
            )

    def _validate_checksum(self, event: OrderBookEvent) -> None:
        """Validate CRC32 checksum if provided by the exchange (Bybit).

        CRC32 format: bid1_price:bid1_qty|bid2_price:bid2_qty|...|ask1_price:ask1_qty|...
        Bybit verifies against top-25 levels.
        """
        if event.checksum is None:
            return  # no checksum provided; skip

        top_bids = sorted(self._book.bids.keys(), reverse=True)[:25]
        top_asks = sorted(self._book.asks.keys())[:25]

        parts = []
        for p in top_bids:
            parts.append(f"{p}:{self._book.bids[p]}")
        for p in top_asks:
            parts.append(f"{p}:{self._book.asks[p]}")

        crc_input = "|".join(parts).encode("utf-8")
        computed = zlib.crc32(crc_input) & 0xFFFFFFFF

        if computed != (event.checksum & 0xFFFFFFFF):
            raise ValidationError(
                ValidationErrorCode.BOOK_CRC_MISMATCH,
                f"Order book CRC32 mismatch for {self._exchange}:{self._symbol}: "
                f"computed={computed}, expected={event.checksum}",
                {
                    "symbol": self._symbol,
                    "exchange": self._exchange,
                    "computed": computed,
                    "expected": event.checksum,
                },
            )
