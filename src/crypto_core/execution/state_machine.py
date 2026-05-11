"""Execution order state machine — Phase 6D/6F lifecycle.

Defines the canonical order lifecycle states and transition rules.
All transitions are deterministic and fail-closed on illegal moves.

State graph:

    CREATED
      ├─► VALIDATED
      │     ├─► SUBMITTED
      │     │     ├─► PARTIALLY_FILLED ──► PARTIALLY_FILLED (accumulate)
      │     │     │         ├─► FILLED
      │     │     │         ├─► CANCELLED
      │     │     │         ├─► EXPIRED
      │     │     │         ├─► CANCEL_PENDING ──► CANCELLED / FILLED / STALE
      │     │     │         └─► REPLACE_PENDING ──► CANCELLED / STALE
      │     │     ├─► FILLED
      │     │     ├─► CANCELLED
      │     │     ├─► REJECTED
      │     │     ├─► EXPIRED
      │     │     ├─► CANCEL_PENDING ──► CANCELLED / FILLED / PARTIALLY_FILLED / STALE
      │     │     └─► REPLACE_PENDING ──► CANCELLED / STALE
      │     └─► REJECTED
      └─► REJECTED

Terminal states (lock all further transitions):
    FILLED, CANCELLED, REJECTED, EXPIRED, STALE

Phase 6F additions:
  - CANCEL_PENDING:  intermediate state while cancel is in-flight.
  - REPLACE_PENDING: intermediate state while cancel-for-replace is in-flight.
  - STALE:           fail-closed terminal state for orders that cannot be
                     reconciled after restart (paper: no exchange state).

PRD reference: §7 Execution Engine.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from crypto_core.execution.events import FillEvent, OrderEvent, OrderEventType
from crypto_core.execution.models import ExecutionMode, OrderIntent

# ---------------------------------------------------------------------------
# OrderState constants
# ---------------------------------------------------------------------------


class OrderState(str):
    """Lifecycle state of a single order."""


OrderState.CREATED = OrderState("CREATED")
OrderState.VALIDATED = OrderState("VALIDATED")
OrderState.SUBMITTED = OrderState("SUBMITTED")
OrderState.PARTIALLY_FILLED = OrderState("PARTIALLY_FILLED")
OrderState.FILLED = OrderState("FILLED")
OrderState.CANCELLED = OrderState("CANCELLED")
OrderState.REJECTED = OrderState("REJECTED")
OrderState.EXPIRED = OrderState("EXPIRED")
# Phase 6F additions
OrderState.CANCEL_PENDING = OrderState("CANCEL_PENDING")
OrderState.REPLACE_PENDING = OrderState("REPLACE_PENDING")
OrderState.STALE = OrderState("STALE")

_TERMINAL_STATES: frozenset[str] = frozenset(
    {
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
        OrderState.STALE,
    }
)

# Valid outbound transitions per state.
# Key absent → terminal (no outbound transitions allowed).
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    OrderState.CREATED: frozenset({OrderState.VALIDATED, OrderState.REJECTED}),
    OrderState.VALIDATED: frozenset({OrderState.SUBMITTED, OrderState.REJECTED}),
    OrderState.SUBMITTED: frozenset(
        {
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
            OrderState.EXPIRED,
            OrderState.CANCEL_PENDING,
            OrderState.REPLACE_PENDING,
            OrderState.STALE,
        }
    ),
    OrderState.PARTIALLY_FILLED: frozenset(
        {
            OrderState.PARTIALLY_FILLED,  # additional fill events
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.EXPIRED,
            OrderState.CANCEL_PENDING,
            OrderState.REPLACE_PENDING,
            OrderState.STALE,
        }
    ),
    # Phase 6F: cancel/replace pending states
    OrderState.CANCEL_PENDING: frozenset(
        {
            OrderState.CANCELLED,
            OrderState.FILLED,  # fill arrived before cancel ack
            OrderState.PARTIALLY_FILLED,  # partial fill arrived before cancel ack
            OrderState.EXPIRED,
            OrderState.STALE,  # fail-closed recovery
        }
    ),
    OrderState.REPLACE_PENDING: frozenset(
        {
            OrderState.CANCELLED,  # original cancelled for replace
            OrderState.FILLED,  # fill arrived before replace ack
            OrderState.PARTIALLY_FILLED,
            OrderState.EXPIRED,
            OrderState.STALE,  # fail-closed recovery
        }
    ),
}


# ---------------------------------------------------------------------------
# Illegal transition error
# ---------------------------------------------------------------------------


class IllegalOrderTransitionError(RuntimeError):
    """Raised when a state transition is not allowed by the lifecycle graph."""


# ---------------------------------------------------------------------------
# Order — mutable lifecycle object
# ---------------------------------------------------------------------------


@dataclass
class Order:
    """Mutable order object tracking lifecycle state and fill accumulation.

    This object is NOT frozen — it accumulates events and fill data
    as the order progresses through the lifecycle.  The event_history
    property exposes a frozen tuple for safe external inspection.

    Fields:
        order_id:           unique identifier (UUID string)
        symbol:             trading symbol (e.g. "BTCUSDT")
        exchange:           exchange identifier (e.g. "binance")
        intent:             BUY or SELL
        mode:               PAPER or DRY_RUN (LIVE blocked unless real adapter)
        requested_quantity: original base-currency quantity (> 0, immutable after creation)
        created_at_ns:      wall-clock timestamp of order creation (ns)

    Computed:
        remaining_quantity: requested_quantity − filled_quantity (≥ 0)
        average_fill_price: filled notional / filled_quantity (None if no fills)
        is_terminal:        True when in a terminal state (locks further transitions)
    """

    order_id: str
    symbol: str
    exchange: str
    intent: OrderIntent
    mode: ExecutionMode
    requested_quantity: float
    created_at_ns: int
    # Mutable lifecycle fields
    state: OrderState = field(default=OrderState.CREATED)  # type: ignore[assignment]
    remaining_quantity: float = field(init=False)
    filled_quantity: float = 0.0
    fill_price_sum: float = 0.0  # notional sum — used for VWAP fill price
    updated_at_ns: int = field(init=False)
    _event_history: list[OrderEvent] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        # Set derived init-time fields
        object.__setattr__(self, "state", OrderState.CREATED)
        self.remaining_quantity = self.requested_quantity
        self.updated_at_ns = self.created_at_ns

    # -----------------------------------------------------------------------
    # Read-only properties
    # -----------------------------------------------------------------------

    @property
    def event_history(self) -> tuple[OrderEvent, ...]:
        """Append-only event history as a frozen tuple."""
        return tuple(self._event_history)

    @property
    def average_fill_price(self) -> float | None:
        """Volume-weighted average fill price; None if not yet filled."""
        if self.filled_quantity <= 0.0:
            return None
        return self.fill_price_sum / self.filled_quantity

    @property
    def is_terminal(self) -> bool:
        """True when in a terminal state (FILLED/CANCELLED/REJECTED/EXPIRED)."""
        return str(self.state) in _TERMINAL_STATES

    @property
    def fill_ratio(self) -> float:
        """Fraction of requested quantity that has been filled [0.0, 1.0]."""
        if self.requested_quantity <= 0.0:
            return 0.0
        return self.filled_quantity / self.requested_quantity

    # -----------------------------------------------------------------------
    # State transitions
    # -----------------------------------------------------------------------

    def transition(self, to_state: OrderState, event: OrderEvent) -> None:
        """Apply a deterministic state transition.

        Appends the event to the audit history and updates state.
        Fails closed (raises IllegalOrderTransitionError) on:
          - attempt to leave a terminal state
          - transition not in the allowed set for the current state

        Args:
            to_state: target OrderState.
            event:    pre-built OrderEvent carrying the audit payload.
        """
        allowed = _ALLOWED_TRANSITIONS.get(str(self.state))
        if allowed is None:
            raise IllegalOrderTransitionError(
                f"Order {self.order_id} is in terminal state {self.state!r} — no further transitions allowed"
            )
        if str(to_state) not in allowed:
            raise IllegalOrderTransitionError(
                f"Order {self.order_id}: transition {self.state!r} → {to_state!r} is not in allowed set {sorted(allowed)}"
            )
        self.state = to_state
        self.updated_at_ns = event.timestamp_ns
        self._event_history.append(event)

    def apply_fill(self, fill_event: FillEvent) -> None:
        """Accumulate a fill event into quantity / notional tracking.

        Must be called BEFORE the corresponding transition event.
        Does NOT change state — caller must call transition() after.
        """
        self.filled_quantity += fill_event.filled_quantity
        self.fill_price_sum += fill_event.filled_quantity * fill_event.fill_price
        self.remaining_quantity = max(0.0, self.requested_quantity - self.filled_quantity)

    # -----------------------------------------------------------------------
    # Factory
    # -----------------------------------------------------------------------

    @staticmethod
    def create(
        symbol: str,
        exchange: str,
        intent: OrderIntent,
        mode: ExecutionMode,
        quantity: float,
        timestamp_ns: int,
        order_id: str | None = None,
    ) -> Order:
        """Create a new Order in CREATED state with an initial CREATED event."""
        oid = order_id or str(uuid.uuid4())
        order = Order(
            order_id=oid,
            symbol=symbol,
            exchange=exchange,
            intent=intent,
            mode=mode,
            requested_quantity=quantity,
            created_at_ns=timestamp_ns,
        )
        created_event = OrderEvent(
            order_id=oid,
            event_type=OrderEventType.CREATED,
            from_state=str(OrderState.CREATED),
            to_state=str(OrderState.CREATED),
            timestamp_ns=timestamp_ns,
            evidence={"symbol": symbol, "exchange": exchange, "intent": str(intent), "quantity": quantity},
        )
        order._event_history.append(created_event)
        return order
