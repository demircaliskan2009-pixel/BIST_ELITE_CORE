"""Execution order state machine — PRD Phase D §10.

Converts advisor decision objects into executable orders, enforces an
8-state lifecycle, applies risk controls, and manages stop/target exits
via PaperExecutionEngine.  Pure stdlib, deterministic, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Sequence

from bist_core.providers.base import FailClosedError
from bist_core.execution.paper_engine import (
    OrderSide,
    PaperExecutionEngine,
    PaperTrade,
    SlippageModel,
)


class OrderState(str, Enum):
    NEW = "NEW"
    VALIDATED = "VALIDATED"
    SENT = "SENT"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


_ORDER_STATE_TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    OrderState.NEW: frozenset({
        OrderState.VALIDATED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
    }),
    OrderState.VALIDATED: frozenset({
        OrderState.SENT,
        OrderState.CANCELLED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
    }),
    OrderState.SENT: frozenset({
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
    }),
    OrderState.PARTIALLY_FILLED: frozenset({
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.EXPIRED,
    }),
    OrderState.FILLED: frozenset(),
    OrderState.CANCELLED: frozenset(),
    OrderState.REJECTED: frozenset(),
    OrderState.EXPIRED: frozenset(),
}


@dataclass
class Order:
    order_id: str
    symbol: str
    side: OrderSide | str
    quantity: int
    filled_quantity: int = 0
    price: float = 0.0
    state: OrderState = OrderState.NEW
    timestamp: int = 0
    last_update: int = 0


def _raise_fail_closed(message: str) -> None:
    raise FailClosedError(message)


def _validate_non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _raise_fail_closed(f"invalid_{field_name}:expected_int")
    if value < 0:
        _raise_fail_closed(f"invalid_{field_name}:negative")
    return value


def _validate_positive_int(value: Any, field_name: str) -> int:
    normalized = _validate_non_negative_int(value, field_name)
    if normalized == 0:
        _raise_fail_closed(f"invalid_{field_name}:zero")
    return normalized


def _validate_positive_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        _raise_fail_closed(f"invalid_{field_name}:expected_number")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise FailClosedError(f"invalid_{field_name}:expected_number") from exc
    if normalized <= 0.0:
        _raise_fail_closed(f"invalid_{field_name}:non_positive")
    return normalized


def _normalize_side(side: OrderSide | str) -> OrderSide:
    if isinstance(side, OrderSide):
        return side
    try:
        return OrderSide(str(side).strip().upper())
    except ValueError as exc:
        raise FailClosedError("invalid_side") from exc


def _ensure_order_consistency(order: Order) -> None:
    if not str(order.order_id or "").strip():
        _raise_fail_closed("invalid_order_id")
    if not str(order.symbol or "").strip():
        _raise_fail_closed("invalid_symbol")
    order.side = _normalize_side(order.side)
    order.quantity = _validate_positive_int(order.quantity, "quantity")
    order.filled_quantity = _validate_non_negative_int(order.filled_quantity, "filled_quantity")
    order.timestamp = _validate_non_negative_int(order.timestamp, "timestamp")
    order.last_update = _validate_non_negative_int(order.last_update, "last_update")
    order.price = _validate_positive_float(order.price, "price")
    if not isinstance(order.state, OrderState):
        _raise_fail_closed("invalid_state")
    if order.filled_quantity > order.quantity:
        _raise_fail_closed("filled_quantity_exceeds_quantity")
    if order.state in {OrderState.NEW, OrderState.VALIDATED, OrderState.SENT} and order.filled_quantity != 0:
        _raise_fail_closed("premature_filled_quantity")
    if order.state == OrderState.PARTIALLY_FILLED and not (0 < order.filled_quantity < order.quantity):
        _raise_fail_closed("invalid_partial_fill_state")
    if order.state == OrderState.FILLED and order.filled_quantity != order.quantity:
        _raise_fail_closed("invalid_filled_state")


def _advance_last_update(order: Order) -> None:
    order.last_update = max(order.last_update, order.timestamp) + 1


def _transition(order: Order, target_state: OrderState) -> Order:
    allowed_states = _ORDER_STATE_TRANSITIONS.get(order.state, frozenset())
    if target_state not in allowed_states:
        _raise_fail_closed(f"invalid_transition:{order.state.value}->{target_state.value}")
    order.state = target_state
    _advance_last_update(order)
    return order


class OrderStateMachine:
    def validate(self, order: Order) -> Order:
        _ensure_order_consistency(order)
        return _transition(order, OrderState.VALIDATED)

    def send(self, order: Order) -> Order:
        _ensure_order_consistency(order)
        return _transition(order, OrderState.SENT)

    def on_fill(self, order: Order, fill_qty: int) -> Order:
        _ensure_order_consistency(order)
        fill_quantity = _validate_positive_int(fill_qty, "fill_qty")
        if order.state not in {OrderState.SENT, OrderState.PARTIALLY_FILLED}:
            _raise_fail_closed(f"invalid_transition:{order.state.value}->PARTIALLY_FILLED")
        remaining_quantity = order.quantity - order.filled_quantity
        if remaining_quantity <= 0:
            _raise_fail_closed("order_has_no_remaining_quantity")
        if fill_quantity > remaining_quantity:
            _raise_fail_closed("filled_quantity_exceeds_quantity")
        order.filled_quantity += fill_quantity
        target_state = OrderState.FILLED if order.filled_quantity == order.quantity else OrderState.PARTIALLY_FILLED
        return _transition(order, target_state)

    def cancel(self, order: Order) -> Order:
        _ensure_order_consistency(order)
        return _transition(order, OrderState.CANCELLED)

    def reject(self, order: Order) -> Order:
        _ensure_order_consistency(order)
        return _transition(order, OrderState.REJECTED)

    def expire(self, order: Order) -> Order:
        _ensure_order_consistency(order)
        return _transition(order, OrderState.EXPIRED)


# ---------------------------------------------------------------------------
# Extended order lifecycle (8 states)
# ---------------------------------------------------------------------------

class ExecutionOrderStatus(str, Enum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


_TRANSITIONS: dict[ExecutionOrderStatus, frozenset[ExecutionOrderStatus]] = {
    ExecutionOrderStatus.CREATED: frozenset({
        ExecutionOrderStatus.SUBMITTED,
        ExecutionOrderStatus.REJECTED,
        ExecutionOrderStatus.CANCELLED,
        ExecutionOrderStatus.EXPIRED,
    }),
    ExecutionOrderStatus.SUBMITTED: frozenset({
        ExecutionOrderStatus.ACCEPTED,
        ExecutionOrderStatus.REJECTED,
        ExecutionOrderStatus.CANCELLED,
    }),
    ExecutionOrderStatus.ACCEPTED: frozenset({
        ExecutionOrderStatus.PARTIALLY_FILLED,
        ExecutionOrderStatus.FILLED,
        ExecutionOrderStatus.CANCELLED,
        ExecutionOrderStatus.EXPIRED,
    }),
    ExecutionOrderStatus.PARTIALLY_FILLED: frozenset({
        ExecutionOrderStatus.PARTIALLY_FILLED,
        ExecutionOrderStatus.FILLED,
        ExecutionOrderStatus.CANCELLED,
    }),
    ExecutionOrderStatus.FILLED: frozenset(),
    ExecutionOrderStatus.CANCELLED: frozenset(),
    ExecutionOrderStatus.EXPIRED: frozenset(),
    ExecutionOrderStatus.REJECTED: frozenset(),
}


class ExecutionStateMachine:
    """Enforce valid 8-state order lifecycle transitions."""

    __slots__ = ("_status", "_history")

    def __init__(self) -> None:
        self._status = ExecutionOrderStatus.CREATED
        self._history: list[ExecutionOrderStatus] = [ExecutionOrderStatus.CREATED]

    @property
    def status(self) -> ExecutionOrderStatus:
        return self._status

    @property
    def history(self) -> list[ExecutionOrderStatus]:
        return list(self._history)

    @property
    def is_terminal(self) -> bool:
        return self._status in (
            ExecutionOrderStatus.FILLED,
            ExecutionOrderStatus.CANCELLED,
            ExecutionOrderStatus.EXPIRED,
            ExecutionOrderStatus.REJECTED,
        )

    def transition(self, target: ExecutionOrderStatus) -> None:
        allowed = _TRANSITIONS.get(self._status, frozenset())
        if target not in allowed:
            raise ValueError(
                f"Invalid transition: {self._status.value} -> {target.value}"
            )
        self._status = target
        self._history.append(target)


# ---------------------------------------------------------------------------
# Order types
# ---------------------------------------------------------------------------

class ExecutionOrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


# ---------------------------------------------------------------------------
# Risk controls
# ---------------------------------------------------------------------------

@dataclass
class RiskLimits:
    max_position_size: int = 10_000
    min_position_size: int = 1
    min_stop_distance_pct: float = 0.5
    max_risk_per_trade_pct: float = 2.0

    def validate(
        self,
        entry: float,
        stop: float,
        target: float,
        position_size: int,
        capital: float | None = None,
    ) -> list[str]:
        errors: list[str] = []
        if position_size < self.min_position_size:
            errors.append(f"position_size {position_size} < min {self.min_position_size}")
        if position_size > self.max_position_size:
            errors.append(f"position_size {position_size} > max {self.max_position_size}")
        if entry <= 0:
            errors.append("entry must be > 0")
        if stop <= 0:
            errors.append("stop must be > 0")
        if target <= 0:
            errors.append("target must be > 0")
        if entry > 0 and stop > 0:
            stop_distance_pct = abs(entry - stop) / entry * 100.0
            if stop_distance_pct < self.min_stop_distance_pct:
                errors.append(
                    f"stop distance {stop_distance_pct:.2f}% < min {self.min_stop_distance_pct:.2f}%"
                )
        if capital is not None and capital > 0 and entry > 0 and stop > 0:
            risk_amount = abs(entry - stop) * position_size
            risk_pct = (risk_amount / capital) * 100.0
            if risk_pct > self.max_risk_per_trade_pct:
                errors.append(
                    f"risk {risk_pct:.2f}% > max {self.max_risk_per_trade_pct:.2f}%"
                )
        return errors


_DEFAULT_RISK = RiskLimits()


# ---------------------------------------------------------------------------
# Managed order
# ---------------------------------------------------------------------------

@dataclass
class ManagedOrder:
    order_id: str
    symbol: str
    order_type: ExecutionOrderType
    entry: float
    stop: float
    target: float
    position_size: int
    sm: ExecutionStateMachine = field(default_factory=ExecutionStateMachine)
    trade: Optional[PaperTrade] = None
    rejection_reasons: list[str] = field(default_factory=list)
    exit_reason: Optional[str] = None
    edge: str = ""
    source: str = "technical"
    event_kind: str = ""
    event_multiplier: float = 1.0

    @property
    def status(self) -> ExecutionOrderStatus:
        return self.sm.status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "order_type": self.order_type.value,
            "entry": self.entry,
            "stop": self.stop,
            "target": self.target,
            "position_size": self.position_size,
            "status": self.sm.status.value,
            "history": [s.value for s in self.sm.history],
            "rejection_reasons": list(self.rejection_reasons),
            "exit_reason": self.exit_reason,
            "trade": self.trade.to_dict() if self.trade is not None else None,
            "source": self.source,
            "event_kind": self.event_kind,
            "event_multiplier": self.event_multiplier,
        }


# ---------------------------------------------------------------------------
# Order state machine controller
# ---------------------------------------------------------------------------

_ORDER_COUNTER = 0


def _next_order_id() -> str:
    global _ORDER_COUNTER
    _ORDER_COUNTER += 1
    return f"OSM-{_ORDER_COUNTER:06d}"


def reset_order_counter() -> None:
    global _ORDER_COUNTER
    _ORDER_COUNTER = 0


class OrderStateMachineController:
    """Bridges advisor decision objects to PaperExecutionEngine with risk controls."""

    def __init__(
        self,
        engine: PaperExecutionEngine | None = None,
        risk_limits: RiskLimits | None = None,
        capital: float | None = None,
    ) -> None:
        self._engine = engine or PaperExecutionEngine(
            slippage=SlippageModel(base_slippage_bps=0.0),
            fee_bps=10.0,
        )
        self._risk = risk_limits or _DEFAULT_RISK
        self._capital = capital
        self._orders: list[ManagedOrder] = []

    @property
    def orders(self) -> list[ManagedOrder]:
        return list(self._orders)

    @property
    def engine(self) -> PaperExecutionEngine:
        return self._engine

    # -- Decision -> Order ------------------------------------------------

    def create_order_from_decision(
        self,
        decision: Dict[str, Any],
        *,
        order_type: ExecutionOrderType = ExecutionOrderType.MARKET,
    ) -> ManagedOrder:
        symbol = str(decision.get("symbol") or "").upper().strip()
        entry = _safe_float(decision.get("entry")) or 0.0
        stop = _safe_float(decision.get("stop")) or 0.0
        target = _safe_float(decision.get("target")) or 0.0
        position_size = _safe_int(decision.get("position_size")) or 0

        edge = str(decision.get("edge") or "")
        source = str(decision.get("source") or "technical")
        event_kind = str(decision.get("event_kind") or "")
        event_multiplier = float(decision.get("event_multiplier") or 1.0)

        order = ManagedOrder(
            order_id=_next_order_id(),
            symbol=symbol,
            order_type=order_type,
            entry=entry,
            stop=stop,
            target=target,
            position_size=position_size,
            edge=edge,
            source=source,
            event_kind=event_kind,
            event_multiplier=event_multiplier,
        )
        self._orders.append(order)

        risk_errors = self._risk.validate(
            entry, stop, target, position_size, self._capital,
        )
        if not symbol:
            risk_errors.append("symbol is empty")

        if risk_errors:
            order.rejection_reasons = risk_errors
            order.sm.transition(ExecutionOrderStatus.REJECTED)
            return order

        return order

    # -- Submit -----------------------------------------------------------

    def submit_order(
        self,
        order: ManagedOrder,
        market_price: float,
        entry_time: str,
    ) -> ManagedOrder:
        if order.sm.is_terminal:
            return order

        if order.sm.status == ExecutionOrderStatus.CREATED:
            order.sm.transition(ExecutionOrderStatus.SUBMITTED)

        order.sm.transition(ExecutionOrderStatus.ACCEPTED)

        trade = self._engine.execute_decision(
            symbol=order.symbol,
            entry=order.entry,
            stop=order.stop,
            target=order.target,
            position_size=order.position_size,
            market_price=market_price,
            entry_time=entry_time,
            edge=order.edge,
            source=order.source,
            event_kind=order.event_kind,
            event_multiplier=order.event_multiplier,
        )

        if trade is None:
            order.rejection_reasons.append("engine_fill_failed")
            order.sm.transition(ExecutionOrderStatus.CANCELLED)
            return order

        order.trade = trade
        order.sm.transition(ExecutionOrderStatus.FILLED)
        return order

    # -- Stop / target triggers -------------------------------------------

    def check_stop_target(
        self,
        order: ManagedOrder,
        current_price: float,
        current_time: str,
    ) -> Optional[str]:
        if order.trade is None or order.trade.status != "OPEN":
            return None

        if current_price <= order.stop:
            self._engine.simulate_exit(order.trade, current_price, current_time)
            order.exit_reason = "stop_triggered"
            return "stop_triggered"

        if current_price >= order.target:
            self._engine.simulate_exit(order.trade, current_price, current_time)
            order.exit_reason = "target_triggered"
            return "target_triggered"

        return None

    # -- Manual actions ---------------------------------------------------

    def cancel_order(self, order: ManagedOrder) -> None:
        if order.sm.is_terminal:
            return
        order.sm.transition(ExecutionOrderStatus.CANCELLED)
        order.exit_reason = "manual_cancel"

    def expire_order(self, order: ManagedOrder) -> None:
        if order.sm.is_terminal:
            return
        order.sm.transition(ExecutionOrderStatus.EXPIRED)
        order.exit_reason = "expired"

    # -- Batch from advisor -----------------------------------------------

    def execute_decisions(
        self,
        decisions: Sequence[Dict[str, Any]],
        market_prices: Dict[str, float],
        entry_time: str,
    ) -> list[ManagedOrder]:
        results: list[ManagedOrder] = []
        for decision in decisions:
            order = self.create_order_from_decision(decision)
            if order.sm.is_terminal:
                results.append(order)
                continue
            symbol = order.symbol
            price = market_prices.get(symbol, 0.0)
            if price <= 0:
                order.rejection_reasons.append(f"no market price for {symbol}")
                order.sm.transition(ExecutionOrderStatus.REJECTED)
                results.append(order)
                continue
            self.submit_order(order, price, entry_time)
            results.append(order)
        return results

    # -- Price tick (batch stop/target) ------------------------------------

    def tick(
        self,
        prices: Dict[str, float],
        current_time: str,
    ) -> list[str]:
        events: list[str] = []
        for order in self._orders:
            if order.trade is None or order.trade.status != "OPEN":
                continue
            price = prices.get(order.symbol, 0.0)
            if price <= 0:
                continue
            result = self.check_stop_target(order, price, current_time)
            if result is not None:
                events.append(f"{order.symbol}:{result}")
        return events


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "ExecutionOrderStatus",
    "ExecutionOrderType",
    "ExecutionStateMachine",
    "ManagedOrder",
    "Order",
    "OrderState",
    "OrderStateMachine",
    "OrderStateMachineController",
    "RiskLimits",
    "reset_order_counter",
]
