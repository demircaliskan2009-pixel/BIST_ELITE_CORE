"""Synthetic fill model and factory for paper / dry-run position tracking.

Only PAPER and DRY_RUN modes generate SyntheticFills.  LIVE fills are not
supported and will not be added here — they require a broker adapter layer.

PRD reference: §7 Execution Engine.
Phase 6A: SyntheticFillFactory.from_decision converts an approved ExecutionDecision
          into a SyntheticFill ready for PositionTracker.apply_fill().
Phase 6D: SyntheticFillFactory.from_fill_event converts a lifecycle FillEvent
          into a SyntheticFill — the preferred path for lifecycle-driven fills.
"""

from __future__ import annotations

from dataclasses import dataclass

from crypto_core.execution.models import ExecutionDecision, ExecutionMode, ExecutionRequest, OrderIntent


@dataclass(frozen=True)
class SyntheticFill:
    """Represents one paper / dry-run fill produced from an approved execution.

    Produced by SyntheticFillFactory from an allowed ExecutionDecision.
    Used as input to PositionTracker to update position state.

    Fields:
      symbol        — trading symbol (e.g. "BTCUSDT")
      exchange      — exchange identifier
      intent        — BUY (open long / close short) or SELL (open short / close long)
      quantity      — base-currency fill size (> 0)
      fill_price    — simulated fill price in USD
      leverage      — leverage at fill time [1.0, 3.0]; default 1.0 for paper
      mode          — PAPER or DRY_RUN
      order_id      — execution engine order_id (from ExecutionDecision)
      timestamp_ns  — fill wall-clock in ns
    """

    symbol: str
    exchange: str
    intent: OrderIntent
    quantity: float  # base-currency size, > 0
    fill_price: float  # USD
    leverage: float  # [1.0, 3.0]
    mode: ExecutionMode
    order_id: str
    timestamp_ns: int


class FillValidationError(Exception):
    """Raised by PositionTracker when a fill is rejected as malformed."""

    pass


class SyntheticFillFactory:
    """Convert an approved ExecutionDecision into a SyntheticFill.

    Rules:
      - Only call when decision.allowed is True.  Raises ValueError otherwise.
      - fill_price: uses decision.fill_price (paper realistic) when available,
        falls back to request.price_hint (dry-run / degraded paper mode).
      - Rejected decisions NEVER generate a fill.
      - leverage must be in (0.0, 3.0].

    Usage::

        if decision.allowed:
            fill = SyntheticFillFactory.from_decision(decision, request)
            tracker.apply_fill(fill)

    This is the only correct bridge between execution approval and portfolio
    state mutation.  Do not construct SyntheticFill directly from raw prices.
    """

    @staticmethod
    def from_decision(
        decision: ExecutionDecision,
        request: ExecutionRequest,
        leverage: float = 1.0,
    ) -> SyntheticFill:
        """Create a SyntheticFill from an allowed ExecutionDecision.

        Args:
            decision:  must have allowed=True (fail-closed check).
            request:   the original ExecutionRequest that produced the decision.
            leverage:  leverage at fill time [1.0, 3.0]; default 1.0 for paper.

        Returns:
            SyntheticFill ready for PositionTracker.apply_fill().

        Raises:
            ValueError: if decision.allowed is False, order_id is None,
                        fill_price is invalid, or leverage is out of range.
        """
        if not decision.allowed:
            raise ValueError(f"Cannot create fill from rejected decision: reason={decision.rejection_reason}")
        if decision.order_id is None:
            raise ValueError("ExecutionDecision.order_id is None — cannot create fill")
        if leverage <= 0.0 or leverage > 3.0:
            raise ValueError(f"leverage must be in (0, 3]; got {leverage}")

        # fill_price: realistic paper price if available, else price_hint fallback
        fill_price: float
        if decision.fill_price is not None:
            fill_price = decision.fill_price
        else:
            fill_price = request.price_hint

        if fill_price is None or fill_price <= 0.0:
            raise ValueError(f"Cannot create fill with invalid fill_price: {fill_price}")

        return SyntheticFill(
            symbol=request.symbol,
            exchange=request.exchange,
            intent=request.intent,
            quantity=request.size,
            fill_price=fill_price,
            leverage=leverage,
            mode=decision.mode,
            order_id=decision.order_id,
            timestamp_ns=decision.timestamp_ns,
        )

    @staticmethod
    def from_fill_event(
        fill_event: object,
        mode: ExecutionMode,
        leverage: float = 1.0,
    ) -> SyntheticFill:
        """Create a SyntheticFill from a lifecycle FillEvent (Phase 6D).

        This is the preferred path when using the ExecutionLifecycleEngine.
        The fill_event carries all pricing evidence from the lifecycle.

        Args:
            fill_event: FillEvent from ExecutionLifecycleResult.fill_events.
            mode:       ExecutionMode under which the fill was generated.
            leverage:   leverage at fill time [1.0, 3.0]; default 1.0 for paper.

        Returns:
            SyntheticFill ready for PositionTracker.apply_fill().

        Raises:
            ValueError: if fill quantities, price, or leverage are invalid.
        """
        # Import here to avoid circular import (fills ← models ← fills)
        from crypto_core.execution.events import FillEvent  # noqa: PLC0415

        if not isinstance(fill_event, FillEvent):
            raise ValueError(f"fill_event must be a FillEvent instance; got {type(fill_event)}")
        fe: FillEvent = fill_event
        if fe.filled_quantity <= 0.0:
            raise ValueError(f"FillEvent.filled_quantity must be > 0; got {fe.filled_quantity}")
        if fe.fill_price is None or fe.fill_price <= 0.0:
            raise ValueError(f"FillEvent.fill_price must be > 0; got {fe.fill_price}")
        if leverage <= 0.0 or leverage > 3.0:
            raise ValueError(f"leverage must be in (0, 3]; got {leverage}")
        return SyntheticFill(
            symbol=fe.symbol,
            exchange=fe.exchange,
            intent=fe.intent,
            quantity=fe.filled_quantity,
            fill_price=fe.fill_price,
            leverage=leverage,
            mode=mode,
            order_id=fe.order_id,
            timestamp_ns=fe.timestamp_ns,
        )
