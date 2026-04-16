"""Execution lifecycle engine — Phase 6D.

Separates validation from order lifecycle management.

The lifecycle engine:
  1. Validates the execution request (all same gates as ExecutionEngine).
  2. Creates an Order object (CREATED state).
  3. Applies VALIDATED transition if all gates pass.
  4. Calls the VenueAdapter to submit and receive events.
  5. Applies each returned event to the Order state machine.
  6. Returns ExecutionLifecycleResult with the final Order + fill events.

This engine does NOT directly mutate portfolio state.  The caller is
responsible for passing FillEvent objects to SyntheticFillFactory and then
to PositionTracker.

LIVE mode guard:
  If the adapter is not live_capable, any request with ExecutionMode.LIVE
  is rejected fail-closed with LIVE_NOT_ENABLED.  A real Binance/Bybit
  adapter sets live_capable=True and handles the execution natively.

Paper mode:
  PaperVenueAdapter simulates synchronous fill.  The full lifecycle
  (CREATED → VALIDATED → SUBMITTED → FILLED) completes in one call.

PRD reference: §7.1–§7.8 Execution Engine.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from crypto_core.execution.adapter import VenueAdapter
from crypto_core.execution.events import FillEvent, OrderEvent, OrderEventType
from crypto_core.execution.fill_pricer import FillPricer, FillPricerConfig
from crypto_core.execution.models import (
    BookContext,
    ExecutionDecision,
    ExecutionMode,
    ExecutionRequest,
    RejectionReason,
    SlippageResult,
)
from crypto_core.execution.paper_adapter import PaperAdapterConfig, PaperVenueAdapter
from crypto_core.execution.state_machine import IllegalOrderTransitionError, Order, OrderState
from crypto_core.state.models import SystemState, is_at_least

logger = logging.getLogger(__name__)

#: Supported symbols (mirrors ExecutionEngine for gate parity)
_SUPPORTED_SYMBOLS: frozenset[str] = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"})


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionLifecycleResult:
    """Immutable result of one order's complete lifecycle run.

    order:                 the final Order object with full event history.
    fill_events:           all FillEvents accumulated during the lifecycle
                           (ordered chronologically).
    final_state:           terminal or current state of the order.
    total_filled_quantity: sum of all fill quantities (0.0 if not filled).
    average_fill_price:    VWAP of all fills (None if no fills).
    rejection_reason:      present when the order was rejected at validation.
    evidence:              top-level audit dict (validation gates + adapter).
    timestamp_ns:          wall-clock at lifecycle completion.
    """

    order: Order
    fill_events: tuple[FillEvent, ...]
    final_state: str  # OrderState value
    total_filled_quantity: float
    average_fill_price: float | None
    rejection_reason: RejectionReason | None
    evidence: dict[str, object]
    timestamp_ns: int

    @property
    def approved(self) -> bool:
        """True when the order was accepted through the validation gates.

        PAPER mode: requires at least one fill event to be considered approved.
        DRY_RUN mode: gates passing (no rejection) is sufficient — there are
                      intentionally no fills in dry-run.
        """
        if self.order.mode == ExecutionMode.PAPER:
            return self.total_filled_quantity > 0.0
        # DRY_RUN: approved when no rejection occurred
        return self.rejection_reason is None and str(self.order.state) != str(OrderState.REJECTED)

    @property
    def order_id(self) -> str:
        return self.order.order_id

    def to_execution_decision(self) -> ExecutionDecision:
        """Produce a backward-compatible ExecutionDecision from this result.

        Allows callers that still expect the legacy ExecutionDecision interface
        to work without code changes.
        """
        allowed = self.approved
        fill_price = self.average_fill_price

        return ExecutionDecision(
            allowed=allowed,
            rejection_reason=self.rejection_reason if not allowed else None,
            mode=self.order.mode,
            order_id=self.order.order_id if allowed else None,
            evidence=self.evidence,
            timestamp_ns=self.timestamp_ns,
            fill_price=fill_price,
            fill_generated=allowed and self.total_filled_quantity > 0.0,
        )


# ---------------------------------------------------------------------------
# Lifecycle engine config
# ---------------------------------------------------------------------------


@dataclass
class ExecutionLifecycleConfig:
    """Configuration for the execution lifecycle engine.

    mode:               ExecutionMode.PAPER or ExecutionMode.DRY_RUN.
    supported_symbols:  symbol whitelist.
    paper_adapter:      paper adapter config (used when mode=PAPER).
    fill_pricer:        fill pricer config for pre-computing pricing before
                        passing to the adapter.  None = use defaults.
    """

    mode: ExecutionMode = None  # type: ignore[assignment]
    supported_symbols: frozenset[str] = None  # type: ignore[assignment]
    paper_adapter: PaperAdapterConfig = None  # type: ignore[assignment]
    fill_pricer: FillPricerConfig | None = None

    def __post_init__(self) -> None:
        if self.mode is None:
            self.mode = ExecutionMode.DRY_RUN
        if self.supported_symbols is None:
            self.supported_symbols = _SUPPORTED_SYMBOLS
        if self.paper_adapter is None:
            self.paper_adapter = PaperAdapterConfig()


# ---------------------------------------------------------------------------
# Lifecycle engine
# ---------------------------------------------------------------------------


class ExecutionLifecycleEngine:
    """Execution lifecycle engine — manages full order state machine.

    Combines:
      - Validation gates (from ExecutionEngine, unchanged semantics)
      - Order state machine (CREATED → ... → terminal)
      - VenueAdapter bridge (paper adapter by default; pluggable for live)
      - Partial fill tracking and residual cancellation
      - Append-only audit trail via OrderEvent history

    Usage (paper mode)::

        cfg = ExecutionLifecycleConfig(mode=ExecutionMode.PAPER)
        engine = ExecutionLifecycleEngine(cfg)
        result = engine.process(request)
        for fill in result.fill_events:
            synthetic = SyntheticFillFactory.from_fill_event(fill, request.size, mode)
            tracker.apply_fill(synthetic)

    For cancel::

        engine.cancel(order_id, "manual_cancel")

    For cancel/replace::

        new_result = engine.replace(order_id, new_quantity=0.005)
    """

    def __init__(
        self,
        config: ExecutionLifecycleConfig | None = None,
        adapter: VenueAdapter | None = None,
    ) -> None:
        self._cfg = config or ExecutionLifecycleConfig()
        self._adapter = adapter or self._build_default_adapter()
        # Pre-compute pricing before handing to adapter (paper path).
        pricer_cfg = self._cfg.fill_pricer if self._cfg.fill_pricer is not None else FillPricerConfig()
        self._fill_pricer = FillPricer(pricer_cfg)
        # In-flight order registry (order_id → Order).  Paper mode orders
        # complete synchronously so this will usually be empty after each call.
        self._orders: dict[str, Order] = {}

    # -----------------------------------------------------------------------
    # Primary interface
    # -----------------------------------------------------------------------

    def process(self, request: ExecutionRequest) -> ExecutionLifecycleResult:
        """Execute the full order lifecycle for one request.

        Returns ExecutionLifecycleResult.  Never raises.
        """
        try:
            return self._do_process(request)
        except Exception:
            logger.exception("ExecutionLifecycleEngine.process raised — fail-closed")
            ts = time.time_ns()
            dummy_order = Order.create(
                symbol=request.symbol,
                exchange=request.exchange,
                intent=request.intent,
                mode=self._cfg.mode,
                quantity=request.size,
                timestamp_ns=ts,
            )
            return ExecutionLifecycleResult(
                order=dummy_order,
                fill_events=(),
                final_state=str(dummy_order.state),
                total_filled_quantity=0.0,
                average_fill_price=None,
                rejection_reason=RejectionReason.EXCEPTION_FAIL_CLOSED,
                evidence={"error": "exception_fail_closed"},
                timestamp_ns=ts,
            )

    def cancel(self, order_id: str, reason: str) -> OrderEvent | None:
        """Cancel an in-flight order by ID.

        Returns the cancel event, or None if the order is unknown.
        """
        order = self._orders.get(order_id)
        if order is None:
            return None
        ts = time.time_ns()
        cancel_event = self._adapter.request_cancel(order, reason, timestamp_ns=ts)
        if cancel_event.event_type == OrderEventType.CANCELLED:
            try:
                order.transition(OrderState.CANCELLED, cancel_event)
            except IllegalOrderTransitionError:
                logger.warning("Cancel transition failed for order %s — already terminal?", order_id)
        return cancel_event

    def replace(
        self,
        order_id: str,
        new_quantity: float,
        book: BookContext | None = None,
    ) -> list[OrderEvent]:
        """Cancel and replace an in-flight order with a new quantity.

        Returns the list of resulting events (cancel + new fill events).
        Returns empty list if order_id is unknown.
        """
        order = self._orders.get(order_id)
        if order is None:
            return []
        ts = time.time_ns()
        # Pre-compute pricing for the replacement
        pricing: SlippageResult | RejectionReason | None = None
        if book is not None:
            pricing_result = self._fill_pricer.price_fill(
                intent=order.intent,
                size=new_quantity,
                book=book,
            )
            pricing = pricing_result if isinstance(pricing_result, SlippageResult) else None

        events = self._adapter.request_replace(order, new_quantity, book, pricing, ts)
        self._apply_events(order, events)
        return events

    # -----------------------------------------------------------------------
    # Internal lifecycle
    # -----------------------------------------------------------------------

    def _do_process(self, req: ExecutionRequest) -> ExecutionLifecycleResult:
        ts = req.timestamp_ns
        cfg = self._cfg

        # ── Gate 0: LIVE not implemented ───────────────────────────────
        if cfg.mode not in (ExecutionMode.DRY_RUN, ExecutionMode.PAPER):
            return self._rejected_result(req, RejectionReason.LIVE_NOT_ENABLED, ts, {"mode": str(cfg.mode)})

        # ── Gate 1: symbol ─────────────────────────────────────────────
        if req.symbol not in cfg.supported_symbols:
            return self._rejected_result(
                req,
                RejectionReason.INVALID_SYMBOL,
                ts,
                {"symbol": req.symbol, "supported": sorted(cfg.supported_symbols)},
            )

        # ── Gate 2: size ───────────────────────────────────────────────
        if req.size <= 0.0:
            return self._rejected_result(req, RejectionReason.ZERO_SIZE, ts, {"size": req.size})

        # ── Gate 3: risk approved ──────────────────────────────────────
        if not req.risk_evaluation.approved:
            return self._rejected_result(
                req,
                RejectionReason.RISK_NOT_APPROVED,
                ts,
                {"risk_reason": str(req.risk_evaluation.block_reason)},
            )

        # ── Gate 4: system state ───────────────────────────────────────
        sys_state = req.risk_evaluation.system_state
        if is_at_least(sys_state, SystemState.DEFENSIVE):
            return self._rejected_result(
                req,
                RejectionReason.SYSTEM_STATE_DEFENSIVE,
                ts,
                {"system_state": str(sys_state)},
            )

        # ── DRY_RUN: no full lifecycle, abstract approval ──────────────
        if cfg.mode == ExecutionMode.DRY_RUN:
            return self._dry_run_result(req, ts)

        # ── PAPER: full lifecycle ──────────────────────────────────────
        return self._paper_lifecycle(req, ts)

    def _dry_run_result(self, req: ExecutionRequest, ts: int) -> ExecutionLifecycleResult:
        """DRY_RUN: create order and complete VALIDATED immediately (no fill)."""
        order = Order.create(
            symbol=req.symbol,
            exchange=req.exchange,
            intent=req.intent,
            mode=ExecutionMode.DRY_RUN,
            quantity=req.size,
            timestamp_ns=ts,
        )
        validated_event = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.VALIDATED,
            from_state=str(OrderState.CREATED),
            to_state=str(OrderState.VALIDATED),
            timestamp_ns=ts,
            evidence={"mode": "dry_run", "symbol": req.symbol, "size": req.size},
        )
        order.transition(OrderState.VALIDATED, validated_event)
        # DRY_RUN: we conceptually "fill" at price_hint for telemetry but do
        # not produce a real FillEvent that the PositionTracker should act on.
        # Leave order in VALIDATED state — no submission to adapter.
        logger.info(
            "[DRY_RUN] order lifecycle: %s %s %s @ ~%.2f  id=%s",
            req.symbol,
            str(req.intent).upper(),
            req.size,
            req.price_hint,
            order.order_id,
        )
        self._orders[order.order_id] = order
        return ExecutionLifecycleResult(
            order=order,
            fill_events=(),
            final_state=str(order.state),
            total_filled_quantity=0.0,
            average_fill_price=None,
            rejection_reason=None,
            evidence={
                "mode": "dry_run",
                "symbol": req.symbol,
                "exchange": req.exchange,
                "intent": str(req.intent),
                "size": req.size,
                "price_hint": req.price_hint,
                "order_id": order.order_id,
            },
            timestamp_ns=ts,
        )

    def _paper_lifecycle(self, req: ExecutionRequest, ts: int) -> ExecutionLifecycleResult:
        """PAPER: run full order lifecycle through state machine + adapter."""
        # Pre-compute pricing for the adapter
        pricing: SlippageResult | None = None
        if req.book is not None:
            pricing_result = self._fill_pricer.price_fill(
                intent=req.intent,
                size=req.size,
                book=req.book,
            )
            if isinstance(pricing_result, RejectionReason):
                # Return a lifecycle-level rejection before creating the order
                order = Order.create(
                    symbol=req.symbol,
                    exchange=req.exchange,
                    intent=req.intent,
                    mode=ExecutionMode.PAPER,
                    quantity=req.size,
                    timestamp_ns=ts,
                )
                # Reject straight from CREATED state
                reject_event = OrderEvent(
                    order_id=order.order_id,
                    event_type=OrderEventType.REJECTED,
                    from_state=str(OrderState.CREATED),
                    to_state=str(OrderState.REJECTED),
                    timestamp_ns=ts,
                    reason=str(pricing_result),
                    evidence={"pricing_rejection": str(pricing_result)},
                )
                # CREATED → REJECTED requires going through VALIDATED first in normal
                # flow, but pre-validation rejection short-circuits via a direct CREATED→REJECTED.
                # We bypass the FSM here and manually append + set state for this case.
                order._event_history.append(reject_event)
                order.state = OrderState.REJECTED
                order.updated_at_ns = ts
                return ExecutionLifecycleResult(
                    order=order,
                    fill_events=(),
                    final_state=str(OrderState.REJECTED),
                    total_filled_quantity=0.0,
                    average_fill_price=None,
                    rejection_reason=RejectionReason(str(pricing_result)),
                    evidence={"pricing_rejection": str(pricing_result)},
                    timestamp_ns=ts,
                )
            pricing = pricing_result

        # ── Create order ───────────────────────────────────────────────
        order = Order.create(
            symbol=req.symbol,
            exchange=req.exchange,
            intent=req.intent,
            mode=ExecutionMode.PAPER,
            quantity=req.size,
            timestamp_ns=ts,
            order_id=None,  # generate fresh UUID
        )
        # Embed price_hint in CREATED evidence so paper adapter can recover it
        order._event_history[-1] = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.CREATED,
            from_state=str(OrderState.CREATED),
            to_state=str(OrderState.CREATED),
            timestamp_ns=ts,
            evidence={
                "symbol": req.symbol,
                "exchange": req.exchange,
                "intent": str(req.intent),
                "quantity": req.size,
                "price_hint": req.price_hint,
            },
        )

        # ── CREATED → VALIDATED ────────────────────────────────────────
        validated_event = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.VALIDATED,
            from_state=str(OrderState.CREATED),
            to_state=str(OrderState.VALIDATED),
            timestamp_ns=ts,
            evidence={
                "symbol": req.symbol,
                "exchange": req.exchange,
                "intent": str(req.intent),
                "size": req.size,
                "risk_approved": True,
            },
        )
        order.transition(OrderState.VALIDATED, validated_event)

        # ── Submit via adapter → collect events ────────────────────────
        adapter_events = self._adapter.submit_order(order, req.book, pricing)

        # ── Apply events to state machine ──────────────────────────────
        fill_events: list[FillEvent] = []
        for event in adapter_events:
            try:
                self._apply_single_event(order, event, fill_events)
            except IllegalOrderTransitionError:
                logger.exception("Illegal state transition for order %s — fail-closed", order.order_id)
                # Treat as rejection
                order.state = OrderState.REJECTED
                order.updated_at_ns = ts
                break

        self._orders[order.order_id] = order

        evidence: dict[str, object] = {
            "mode": "paper",
            "symbol": req.symbol,
            "exchange": req.exchange,
            "intent": str(req.intent),
            "size": req.size,
            "order_id": order.order_id,
            "final_state": str(order.state),
            "event_count": len(order.event_history),
            "fill_count": len(fill_events),
        }
        if fill_events:
            evidence["fill_price"] = fill_events[-1].fill_price
            evidence["total_filled_quantity"] = order.filled_quantity
        if pricing is not None:
            evidence["spread_bps"] = pricing.spread_bps
            evidence["slippage_bps"] = pricing.slippage_bps

        return ExecutionLifecycleResult(
            order=order,
            fill_events=tuple(fill_events),
            final_state=str(order.state),
            total_filled_quantity=order.filled_quantity,
            average_fill_price=order.average_fill_price,
            rejection_reason=None,
            evidence=evidence,
            timestamp_ns=ts,
        )

    def _apply_events(self, order: Order, events: list[OrderEvent]) -> None:
        """Apply a sequence of adapter events to an existing order."""
        fill_events: list[FillEvent] = []
        for event in events:
            try:
                self._apply_single_event(order, event, fill_events)
            except IllegalOrderTransitionError:
                logger.exception("Illegal transition in _apply_events for order %s", order.order_id)
                break

    def _apply_single_event(
        self,
        order: Order,
        event: OrderEvent,
        fill_accumulator: list[FillEvent],
    ) -> None:
        """Apply one event to the order state machine."""
        etype = event.event_type

        if etype == OrderEventType.SUBMITTED:
            order.transition(OrderState.SUBMITTED, event)

        elif etype == OrderEventType.PARTIALLY_FILLED:
            if event.fill_event is not None:
                order.apply_fill(event.fill_event)
                fill_accumulator.append(event.fill_event)
            order.transition(OrderState.PARTIALLY_FILLED, event)

        elif etype == OrderEventType.FILLED:
            if event.fill_event is not None:
                order.apply_fill(event.fill_event)
                fill_accumulator.append(event.fill_event)
            order.transition(OrderState.FILLED, event)

        elif etype == OrderEventType.CANCELLED:
            order.transition(OrderState.CANCELLED, event)

        elif etype == OrderEventType.REJECTED:
            # REJECTED from VALIDATED state
            if str(order.state) == str(OrderState.VALIDATED):
                order.transition(OrderState.REJECTED, event)
            # REJECTED from SUBMITTED is also allowed (the FSM allows it)
            elif str(order.state) == str(OrderState.SUBMITTED):
                order.transition(OrderState.REJECTED, event)
            else:
                logger.warning(
                    "REJECTED event for order %s in unexpected state %s — skipping",
                    order.order_id,
                    order.state,
                )

        elif etype == OrderEventType.EXPIRED:
            order.transition(OrderState.EXPIRED, event)

    def _rejected_result(
        self,
        req: ExecutionRequest,
        reason: RejectionReason,
        ts: int,
        extra_evidence: dict,
    ) -> ExecutionLifecycleResult:
        """Build a fully-rejected lifecycle result (never entered adapter)."""
        order = Order.create(
            symbol=req.symbol,
            exchange=req.exchange,
            intent=req.intent,
            mode=self._cfg.mode,
            quantity=req.size,
            timestamp_ns=ts,
        )
        reject_event = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.REJECTED,
            from_state=str(OrderState.CREATED),
            to_state=str(OrderState.REJECTED),
            timestamp_ns=ts,
            reason=str(reason),
            evidence={**extra_evidence, "rejection_reason": str(reason)},
        )
        order._event_history.append(reject_event)
        order.state = OrderState.REJECTED
        order.updated_at_ns = ts

        evidence: dict[str, object] = {
            "mode": str(self._cfg.mode),
            "symbol": req.symbol,
            "rejection_reason": str(reason),
            **extra_evidence,
        }
        return ExecutionLifecycleResult(
            order=order,
            fill_events=(),
            final_state=str(OrderState.REJECTED),
            total_filled_quantity=0.0,
            average_fill_price=None,
            rejection_reason=reason,
            evidence=evidence,
            timestamp_ns=ts,
        )

    def _build_default_adapter(self) -> VenueAdapter:
        """Build the default adapter for the configured mode."""
        if self._cfg.mode == ExecutionMode.PAPER:
            return PaperVenueAdapter(self._cfg.paper_adapter)
        # DRY_RUN: use paper adapter in degraded (price_hint) mode
        cfg = PaperAdapterConfig(
            fill_pricer=FillPricerConfig(),
            allow_degraded_fill=True,
        )
        return PaperVenueAdapter(cfg)
