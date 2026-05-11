"""Execution order event models — Phase 6D execution state machine.

All events are immutable (frozen dataclasses).
The event sequence is the authoritative audit trail for every order.
Deterministic replay: same event sequence → same final order state.

PRD reference: §7 Execution Engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from crypto_core.execution.models import OrderIntent

# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------


class OrderEventType(str):
    """Lifecycle event type tags — appended to order history."""


OrderEventType.CREATED = OrderEventType("CREATED")
OrderEventType.VALIDATED = OrderEventType("VALIDATED")
OrderEventType.SUBMITTED = OrderEventType("SUBMITTED")
OrderEventType.PARTIALLY_FILLED = OrderEventType("PARTIALLY_FILLED")
OrderEventType.FILLED = OrderEventType("FILLED")
OrderEventType.CANCELLED = OrderEventType("CANCELLED")
OrderEventType.REJECTED = OrderEventType("REJECTED")
OrderEventType.EXPIRED = OrderEventType("EXPIRED")
OrderEventType.CANCEL_REQUESTED = OrderEventType("CANCEL_REQUESTED")
OrderEventType.REPLACE_REQUESTED = OrderEventType("REPLACE_REQUESTED")
OrderEventType.STALE = OrderEventType("STALE")


# ---------------------------------------------------------------------------
# FillEvent — one atomic fill from the venue (or paper simulator)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FillEvent:
    """One atomic fill on an order.

    filled_quantity: base-currency amount filled in this event (> 0).
    fill_price:      USD price at which this fill was executed.
    slippage_bps:    fill cost from mid in bps (None when not computable).
    spread_bps:      full book bid-ask spread at fill time (None if no book).
    participation_pct: size / side_depth × 100; None when depth unavailable.
    evidence:        full audit dictionary from the fill pricer.
    """

    order_id: str
    symbol: str
    exchange: str
    intent: OrderIntent
    filled_quantity: float  # base-currency, > 0
    fill_price: float  # USD
    timestamp_ns: int
    slippage_bps: float | None = None
    spread_bps: float | None = None
    participation_pct: float | None = None
    evidence: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# OrderEvent — one lifecycle state transition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderEvent:
    """One lifecycle event for an order — records a state transition.

    from_state: state before this event.
    to_state:   state after this event.
    reason:     human-readable reason code for REJECTED / CANCELLED / EXPIRED.
    fill_event: present for PARTIALLY_FILLED and FILLED transitions.
    evidence:   full audit payload for this transition.
    """

    order_id: str
    event_type: OrderEventType
    from_state: str  # OrderState value
    to_state: str  # OrderState value
    timestamp_ns: int
    reason: str | None = None
    fill_event: FillEvent | None = None
    evidence: dict[str, object] = field(default_factory=dict)
