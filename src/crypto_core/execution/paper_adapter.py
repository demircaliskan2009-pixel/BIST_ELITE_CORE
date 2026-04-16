"""Paper venue adapter — deterministic fill simulation.

PaperVenueAdapter implements VenueAdapter using the existing FillPricer
for realistic fill pricing.  All behavior is deterministic.

Fill model:
  - Full fill: when book is available and participation is within limit.
  - Partial fill: when depth covers only part of the order → fills available
    depth, then CANCELS the residual (no queue management in paper mode).
  - No fill (rejected): book invalid / crossed / excessive spread.
  - No book available: if config allows, fill at price_hint (degraded mode).

Invariants:
  - live_capable = False — will never issue real exchange orders.
  - No randomness — identical inputs → identical output.
  - Never raises — returns events with explicit reason codes.

PRD reference: §7.1–§7.8 Execution Engine.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from crypto_core.execution.adapter import VenueAdapter
from crypto_core.execution.events import FillEvent, OrderEvent, OrderEventType
from crypto_core.execution.fill_pricer import FillPricer, FillPricerConfig
from crypto_core.execution.models import (
    BookContext,
    ExecutionMode,
    OrderIntent,
    RejectionReason,
    SlippageResult,
)
from crypto_core.execution.state_machine import Order, OrderState


@dataclass
class PaperAdapterConfig:
    """Configuration for the paper venue adapter.

    fill_pricer:  fill pricer configuration (spread, slippage, liquidity gates).
    allow_degraded_fill: if True and book is None, fill at price_hint with no
                         slippage (degraded paper mode).  If False, reject
                         with BOOK_UNAVAILABLE.
    """

    fill_pricer: FillPricerConfig = None  # type: ignore[assignment]
    allow_degraded_fill: bool = True

    def __post_init__(self) -> None:
        if self.fill_pricer is None:
            self.fill_pricer = FillPricerConfig()


class PaperVenueAdapter(VenueAdapter):
    """Deterministic paper venue adapter.

    Simulates order submission, fill pricing, partial fills, cancels, and
    cancel/replace using the deterministic FillPricer and top-of-book data.

    Paper fill rules:
      1. Book absent and degraded allowed → fill 100% at price_hint.
      2. Book absent and degraded not allowed → REJECTED (BOOK_UNAVAILABLE).
      3. Book present → run fill pricer:
         a. Pricer returns RejectionReason → REJECTED.
         b. Pricer returns SlippageResult:
            - If depth available and order fills within depth → FILLED.
            - If depth available and order exceeds depth → PARTIALLY_FILLED
              then CANCELLED for residual.
            - If depth unavailable → FILLED (full quantity, no depth check).
    """

    def __init__(self, config: PaperAdapterConfig | None = None) -> None:
        self._cfg = config or PaperAdapterConfig()
        self._pricer = FillPricer(self._cfg.fill_pricer)

    # -----------------------------------------------------------------------
    # VenueAdapter interface
    # -----------------------------------------------------------------------

    @property
    def mode(self) -> ExecutionMode:
        return ExecutionMode.PAPER

    @property
    def live_capable(self) -> bool:
        return False

    def submit_order(
        self,
        order: Order,
        book: BookContext | None,
        pricing: SlippageResult | None,
    ) -> list[OrderEvent]:
        """Simulate synchronous paper submission and fill."""
        ts = time.time_ns()
        events: list[OrderEvent] = []

        # ── No book context ────────────────────────────────────────────
        if book is None:
            if not self._cfg.allow_degraded_fill:
                return [
                    _reject_event(
                        order,
                        reason=str(RejectionReason.BOOK_UNAVAILABLE),
                        timestamp_ns=ts,
                        evidence={"book": None, "allow_degraded_fill": False},
                    )
                ]
            # Degraded path: no slippage, fill at price_hint from request evidence.
            # We need price_hint — extract from order evidence if available.
            price_hint = _extract_price_hint(order)
            if price_hint is None or price_hint <= 0.0:
                return [
                    _reject_event(
                        order,
                        reason=str(RejectionReason.BOOK_UNAVAILABLE),
                        timestamp_ns=ts,
                        evidence={"book": None, "price_hint": price_hint, "reason": "no_valid_price_hint"},
                    )
                ]

            submitted_event = _submitted_event(order, timestamp_ns=ts, evidence={"fill_mode": "degraded_price_hint"})
            events.append(submitted_event)

            fill_event = FillEvent(
                order_id=order.order_id,
                symbol=order.symbol,
                exchange=order.exchange,
                intent=order.intent,
                filled_quantity=order.requested_quantity,
                fill_price=price_hint,
                timestamp_ns=ts,
                evidence={"fill_mode": "degraded_price_hint", "price_hint": price_hint},
            )
            filled_event = _filled_event(order, fill_event, from_state=str(OrderState.SUBMITTED), timestamp_ns=ts)
            events.append(filled_event)
            return events

        # ── Use pre-computed pricing or run pricer ─────────────────────
        if pricing is None:
            pricing_result = self._pricer.price_fill(
                intent=order.intent,
                size=order.requested_quantity,
                book=book,
            )
        else:
            pricing_result = pricing

        if isinstance(pricing_result, RejectionReason):
            return [
                _reject_event(
                    order,
                    reason=str(pricing_result),
                    timestamp_ns=ts,
                    evidence={"pricing_rejection": str(pricing_result)},
                )
            ]

        assert isinstance(pricing_result, SlippageResult)

        submitted_event = _submitted_event(
            order,
            timestamp_ns=ts,
            evidence={
                "fill_mode": "paper_realistic",
                "fill_price": pricing_result.fill_price,
                "spread_bps": pricing_result.spread_bps,
                "slippage_bps": pricing_result.slippage_bps,
            },
        )
        events.append(submitted_event)

        # ── Determine fill quantity based on available depth ───────────
        side_depth = _side_depth(order.intent, book)

        if side_depth is not None and order.requested_quantity > side_depth:
            # Partial fill: depth covers less than the full order
            partial_qty = side_depth
            partial_fill = FillEvent(
                order_id=order.order_id,
                symbol=order.symbol,
                exchange=order.exchange,
                intent=order.intent,
                filled_quantity=partial_qty,
                fill_price=pricing_result.fill_price,
                timestamp_ns=ts,
                slippage_bps=pricing_result.slippage_bps,
                spread_bps=pricing_result.spread_bps,
                participation_pct=pricing_result.participation_pct,
                evidence={**pricing_result.evidence, "fill_type": "partial"},
            )
            partial_event = _partial_filled_event(
                order, partial_fill, from_state=str(OrderState.SUBMITTED), timestamp_ns=ts
            )
            events.append(partial_event)

            # Cancel residual — no queue management in paper mode
            residual = order.requested_quantity - partial_qty
            cancel_event = _cancelled_event(
                order,
                reason="residual_no_queue",
                from_state=str(OrderState.PARTIALLY_FILLED),
                timestamp_ns=ts,
                evidence={"residual_quantity": residual, "fill_type": "partial_cancel_residual"},
            )
            events.append(cancel_event)
        else:
            # Full fill
            full_fill = FillEvent(
                order_id=order.order_id,
                symbol=order.symbol,
                exchange=order.exchange,
                intent=order.intent,
                filled_quantity=order.requested_quantity,
                fill_price=pricing_result.fill_price,
                timestamp_ns=ts,
                slippage_bps=pricing_result.slippage_bps,
                spread_bps=pricing_result.spread_bps,
                participation_pct=pricing_result.participation_pct,
                evidence={**pricing_result.evidence, "fill_type": "full"},
            )
            filled_event = _filled_event(order, full_fill, from_state=str(OrderState.SUBMITTED), timestamp_ns=ts)
            events.append(filled_event)

        return events

    def request_cancel(self, order: Order, reason: str, timestamp_ns: int) -> OrderEvent:
        """Cancel a non-terminal order (paper: immediate acknowledgement)."""
        if order.is_terminal:
            # Cannot cancel an already-terminal order — return a no-op REJECTED
            return OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.REJECTED,
                from_state=str(order.state),
                to_state=str(order.state),
                timestamp_ns=timestamp_ns,
                reason="cancel_rejected_already_terminal",
                evidence={"current_state": str(order.state), "cancel_reason": reason},
            )
        from_state = str(order.state)
        return _cancelled_event(
            order,
            reason=reason,
            from_state=from_state,
            timestamp_ns=timestamp_ns,
            evidence={"cancel_reason": reason},
        )

    def request_replace(
        self,
        order: Order,
        new_quantity: float,
        book: BookContext | None,
        pricing: SlippageResult | None,
        timestamp_ns: int,
    ) -> list[OrderEvent]:
        """Cancel existing order and issue a replacement.

        Paper mode: cancels the original order then runs a new submission
        against the new quantity.  The replacement is treated as a new
        virtual order (same order_id, new events).
        """
        if order.is_terminal:
            return [
                OrderEvent(
                    order_id=order.order_id,
                    event_type=OrderEventType.REJECTED,
                    from_state=str(order.state),
                    to_state=str(order.state),
                    timestamp_ns=timestamp_ns,
                    reason="replace_rejected_already_terminal",
                    evidence={"current_state": str(order.state), "new_quantity": new_quantity},
                )
            ]

        from_state = str(order.state)
        cancel_event = _cancelled_event(
            order,
            reason="cancel_for_replace",
            from_state=from_state,
            timestamp_ns=timestamp_ns,
            evidence={"replace_new_quantity": new_quantity},
        )

        # Build a temporary replacement order to simulate the new submission.
        # The events reference the same order_id so the audit trail is continuous.
        from crypto_core.execution.state_machine import Order as _Order

        replacement = _Order.create(
            symbol=order.symbol,
            exchange=order.exchange,
            intent=order.intent,
            mode=order.mode,
            quantity=new_quantity,
            timestamp_ns=timestamp_ns,
            order_id=order.order_id,
        )
        # Validate the replacement (CREATED → VALIDATED)
        validated_event = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.VALIDATED,
            from_state=str(OrderState.CREATED),
            to_state=str(OrderState.VALIDATED),
            timestamp_ns=timestamp_ns,
            evidence={"replace_validation": "ok", "new_quantity": new_quantity},
        )
        replacement.transition(OrderState.VALIDATED, validated_event)

        # Submit the replacement
        submit_events = self.submit_order(replacement, book, pricing)

        return [cancel_event, *submit_events]


# ---------------------------------------------------------------------------
# Event builder helpers (module-private)
# ---------------------------------------------------------------------------


def _submitted_event(order: Order, timestamp_ns: int, evidence: dict) -> OrderEvent:
    return OrderEvent(
        order_id=order.order_id,
        event_type=OrderEventType.SUBMITTED,
        from_state=str(OrderState.VALIDATED),
        to_state=str(OrderState.SUBMITTED),
        timestamp_ns=timestamp_ns,
        evidence={**evidence, "order_id": order.order_id},
    )


def _filled_event(order: Order, fill_event: FillEvent, from_state: str, timestamp_ns: int) -> OrderEvent:
    return OrderEvent(
        order_id=order.order_id,
        event_type=OrderEventType.FILLED,
        from_state=from_state,
        to_state=str(OrderState.FILLED),
        timestamp_ns=timestamp_ns,
        fill_event=fill_event,
        evidence={
            "filled_quantity": fill_event.filled_quantity,
            "fill_price": fill_event.fill_price,
        },
    )


def _partial_filled_event(order: Order, fill_event: FillEvent, from_state: str, timestamp_ns: int) -> OrderEvent:
    return OrderEvent(
        order_id=order.order_id,
        event_type=OrderEventType.PARTIALLY_FILLED,
        from_state=from_state,
        to_state=str(OrderState.PARTIALLY_FILLED),
        timestamp_ns=timestamp_ns,
        fill_event=fill_event,
        evidence={
            "filled_quantity": fill_event.filled_quantity,
            "fill_price": fill_event.fill_price,
        },
    )


def _cancelled_event(
    order: Order,
    reason: str,
    from_state: str,
    timestamp_ns: int,
    evidence: dict | None = None,
) -> OrderEvent:
    return OrderEvent(
        order_id=order.order_id,
        event_type=OrderEventType.CANCELLED,
        from_state=from_state,
        to_state=str(OrderState.CANCELLED),
        timestamp_ns=timestamp_ns,
        reason=reason,
        evidence=evidence or {},
    )


def _reject_event(order: Order, reason: str, timestamp_ns: int, evidence: dict) -> OrderEvent:
    # Determine the correct from_state based on what events have occurred.
    from_state = str(OrderState.VALIDATED)
    return OrderEvent(
        order_id=order.order_id,
        event_type=OrderEventType.REJECTED,
        from_state=from_state,
        to_state=str(OrderState.REJECTED),
        timestamp_ns=timestamp_ns,
        reason=reason,
        evidence=evidence,
    )


def _side_depth(intent: OrderIntent, book: BookContext) -> float | None:
    """Return the relevant depth for the given intent."""
    if intent == OrderIntent.BUY:
        return book.ask_size
    return book.bid_size


def _extract_price_hint(order: Order) -> float | None:
    """Try to recover price_hint from the CREATED event's evidence."""
    for event in order._event_history:
        if event.event_type == OrderEventType.CREATED:
            val = event.evidence.get("price_hint")
            if val is not None:
                return float(val)
    return None
