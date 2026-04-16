"""Abstract venue adapter contract — Phase 6D/6E paper/live bridge.

VenueAdapter is the single abstraction separating the execution lifecycle
engine from the venue-specific order submission mechanics.

Paper mode uses PaperVenueAdapter (deterministic fill simulation).
Future live adapters (Binance, Bybit) must implement this interface.

Phase 6E additions (live adapter foundation):
  - poll_open_orders():           enumerate known non-terminal order IDs
  - ingest_fill_event():          process an async fill notification from the venue
  - ingest_position_snapshot():   process an account/position state snapshot

Invariants for all adapter implementations:
  - Never raise — return events with explicit reason codes on failure.
  - Never mutate the Order directly — return events; caller applies them.
  - Be deterministic for the same inputs (paper mode must replay identically).
  - LIVE mode must block unless explicitly implemented by the adapter.
  - All events carry a timestamp_ns and an evidence payload.

PRD reference: §7 Execution Engine, §7.8 Adversarial Execution.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from crypto_core.execution.events import FillEvent, OrderEvent
from crypto_core.execution.models import BookContext, ExecutionMode, SlippageResult
from crypto_core.execution.state_machine import Order


class VenueAdapter(ABC):
    """Abstract contract for venue-specific order lifecycle operations.

    This interface represents the boundary between the generic execution
    lifecycle engine and the exchange-specific plumbing.

    Paper adapter: implements synchronous fill simulation.
    Live adapter (future): wraps exchange REST/WebSocket clients.

    Method contracts:
        submit_order:    transitions VALIDATED → SUBMITTED, may also produce
                         immediate fill events (paper adapter completes in one
                         call; live adapter returns SUBMITTED and expects
                         async fill event ingestion).
        request_cancel:  transitions in-flight order → CANCEL_REQUESTED;
                         returns the acknowledgement event.
        request_replace: cancel + replace in one atomic operation;
                         returns events for both legs.
    """

    # -----------------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------------

    @property
    @abstractmethod
    def mode(self) -> ExecutionMode:
        """The execution mode this adapter represents."""

    @property
    @abstractmethod
    def live_capable(self) -> bool:
        """True only for adapters that can submit real exchange orders.

        Paper / dry-run adapters MUST return False.
        All False adapters block if mode == LIVE is requested.
        """

    # -----------------------------------------------------------------------
    # Core operations
    # -----------------------------------------------------------------------

    @abstractmethod
    def submit_order(
        self,
        order: Order,
        book: BookContext | None,
        pricing: SlippageResult | None,
    ) -> list[OrderEvent]:
        """Submit the order to the venue and return the resulting events.

        The returned events must include:
          - A SUBMITTED event (always).
          - One or more PARTIALLY_FILLED / FILLED events (paper: immediate fill
            or partial fill based on available depth).
          - A REJECTED event instead of SUBMITTED if submission fails.
          - For partial fills: the method may add a final CANCELLED event
            to dispose of the residual quantity (paper: no order queue).

        Args:
            order:   the Order in VALIDATED state.
            book:    top-of-book context (may be None if feed unavailable).
            pricing: pre-computed SlippageResult (may be None — adapter
                     may re-compute or reject).

        Returns:
            Ordered list of OrderEvent objects representing the submission
            outcome.  Never empty.
        """

    @abstractmethod
    def request_cancel(self, order: Order, reason: str, timestamp_ns: int) -> OrderEvent:
        """Request cancellation of a live (non-terminal) order.

        Returns:
            A CANCELLED event (paper: immediate acknowledgement).
            A REJECTED event if cancellation is not allowed (e.g. already terminal).

        The returned event carries:
          - reason: the caller-supplied cancellation reason code
          - evidence: any adapter-specific diagnostics
        """

    @abstractmethod
    def request_replace(
        self,
        order: Order,
        new_quantity: float,
        book: BookContext | None,
        pricing: SlippageResult | None,
        timestamp_ns: int,
    ) -> list[OrderEvent]:
        """Cancel the existing order and submit a replacement with new_quantity.

        Returns events for both legs:
          [cancel_event, submit_events...]

        Args:
            order:        existing Order (must not be terminal).
            new_quantity: replacement quantity (base currency, > 0).
            book:         current top-of-book (may be None).
            pricing:      pre-computed replacement fill pricing (may be None).
            timestamp_ns: wall-clock for all returned events.
        """

    # -----------------------------------------------------------------------
    # Live adapter operations — Phase 6E
    # -----------------------------------------------------------------------

    @abstractmethod
    def poll_open_orders(self) -> list[str]:
        """Return a list of known non-terminal order IDs for this adapter.

        Used during recovery bootstrap to enumerate orders that may need
        reconciliation after a restart.

        Paper adapter: always returns [] (fills are synchronous, no open queue).
        Live adapter: returns exchange-reported open order IDs.

        Returns:
            List of order_id strings.  Empty list if none.
        """

    @abstractmethod
    def ingest_fill_event(
        self,
        fill: FillEvent,
        timestamp_ns: int,
    ) -> list[OrderEvent]:
        """Process an async fill notification received from the venue.

        Live adapters receive fill events asynchronously via WebSocket.
        This method converts an incoming venue fill notification into typed
        OrderEvent objects for the lifecycle engine to apply.

        Paper adapter: always returns [] (no async fills in paper mode).

        Args:
            fill:         the incoming fill notification from the venue.
            timestamp_ns: receipt timestamp (wall clock, nanoseconds).

        Returns:
            Ordered list of OrderEvent objects (empty if not actionable).
        """

    @abstractmethod
    def ingest_position_snapshot(
        self,
        snapshot: dict[str, object],
        timestamp_ns: int,
    ) -> None:
        """Process an account / position state snapshot from the venue.

        Used for reconciliation: compare exchange-reported positions against
        local tracker state and emit discrepancy evidence for audit.

        Paper adapter: no-op (no external account state to reconcile).

        Args:
            snapshot:     venue-specific position dict (exchange format).
            timestamp_ns: receipt timestamp (wall clock, nanoseconds).
        """
