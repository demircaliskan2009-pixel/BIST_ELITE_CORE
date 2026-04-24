"""FAZ72: place_orders/cancel/get_fills schemas + StubBrokerAdapter. Stage 14: low-level BrokerAdapter + PaperBrokerAdapter."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional, Protocol

from bist_core.execution.order_state_machine import Order, OrderState
from bist_core.providers.base import FailClosedError

if TYPE_CHECKING:
    from bist_core.execution.execution_engine import ExecutionEngine

# --- Strict schemas (required keys + types) ---

PLACE_ORDERS_INPUT_KEYS = frozenset({"day", "actions"})
PLACE_ORDERS_OUTPUT_KEYS = frozenset({"ok", "order_ids", "fills", "errors"})
CANCEL_INPUT_KEYS = frozenset({"order_id"})
CANCEL_OUTPUT_KEYS = frozenset({"ok", "cancelled", "errors"})
GET_FILLS_INPUT_KEYS = frozenset({"day", "order_id"})  # both optional for query
GET_FILLS_OUTPUT_KEYS = frozenset({"ok", "fills", "errors"})
FILL_RECORD_KEYS = frozenset({"order_id", "symbol", "side", "qty", "price", "notional"})


def _validate_place_orders_input(data: Any) -> Optional[str]:
    """Validate place_orders input. Returns None if valid, else error string."""
    if not isinstance(data, dict):
        return "place_orders_input_not_dict"
    if "day" not in data:
        return "place_orders_input_missing_day"
    if "actions" not in data:
        return "place_orders_input_missing_actions"
    if not isinstance(data["day"], str):
        return "place_orders_input_day_not_str"
    if not isinstance(data["actions"], list):
        return "place_orders_input_actions_not_list"
    return None


def _validate_place_orders_output(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return "place_orders_output_not_dict"
    for k in PLACE_ORDERS_OUTPUT_KEYS:
        if k not in data:
            return f"place_orders_output_missing_{k}"
    if not isinstance(data["ok"], bool):
        return "place_orders_output_ok_not_bool"
    if not isinstance(data["order_ids"], list):
        return "place_orders_output_order_ids_not_list"
    if not isinstance(data["fills"], list):
        return "place_orders_output_fills_not_list"
    if not isinstance(data["errors"], list):
        return "place_orders_output_errors_not_list"
    for f in data["fills"]:
        err = _validate_fill_record(f)
        if err:
            return err
    return None


def _validate_cancel_input(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return "cancel_input_not_dict"
    if "order_id" not in data:
        return "cancel_input_missing_order_id"
    if data["order_id"] is not None and not isinstance(data["order_id"], str):
        return "cancel_input_order_id_not_str_or_none"
    return None


def _validate_cancel_output(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return "cancel_output_not_dict"
    for k in CANCEL_OUTPUT_KEYS:
        if k not in data:
            return f"cancel_output_missing_{k}"
    if not isinstance(data["ok"], bool):
        return "cancel_output_ok_not_bool"
    if not isinstance(data["cancelled"], list):
        return "cancel_output_cancelled_not_list"
    if not isinstance(data["errors"], list):
        return "cancel_output_errors_not_list"
    return None


def _validate_get_fills_input(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return "get_fills_input_not_dict"
    if "day" in data and data["day"] is not None and not isinstance(data["day"], str):
        return "get_fills_input_day_not_str_or_none"
    if "order_id" in data and data["order_id"] is not None and not isinstance(data["order_id"], str):
        return "get_fills_input_order_id_not_str_or_none"
    return None


def _validate_get_fills_output(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return "get_fills_output_not_dict"
    for k in GET_FILLS_OUTPUT_KEYS:
        if k not in data:
            return f"get_fills_output_missing_{k}"
    if not isinstance(data["ok"], bool):
        return "get_fills_output_ok_not_bool"
    if not isinstance(data["fills"], list):
        return "get_fills_output_fills_not_list"
    if not isinstance(data["errors"], list):
        return "get_fills_output_errors_not_list"
    for f in data["fills"]:
        err = _validate_fill_record(f)
        if err:
            return err
    return None


def _validate_fill_record(f: Any) -> Optional[str]:
    if not isinstance(f, dict):
        return "fill_record_not_dict"
    for k in FILL_RECORD_KEYS:
        if k not in f:
            return f"fill_record_missing_{k}"
    if not isinstance(f["order_id"], str):
        return "fill_record_order_id_not_str"
    if not isinstance(f["symbol"], str):
        return "fill_record_symbol_not_str"
    if not isinstance(f["side"], str):
        return "fill_record_side_not_str"
    if not isinstance(f["qty"], (int, float)):
        return "fill_record_qty_not_number"
    if not isinstance(f["price"], (int, float)):
        return "fill_record_price_not_number"
    if not isinstance(f["notional"], (int, float)):
        return "fill_record_notional_not_number"
    return None


class BrokerPlacementProtocol(Protocol):
    """High-level broker: place_orders, cancel, get_fills with strict schemas (FAZ72)."""

    def place_orders(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Place orders. Input: {day, actions}. Output: {ok, order_ids, fills, errors}."""
        ...

    def cancel(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel order(s). Input: {order_id} (null = cancel all). Output: {ok, cancelled, errors}."""
        ...

    def get_fills(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get fills. Input: {day?, order_id?}. Output: {ok, fills, errors}."""
        ...


OrderSide = Literal["buy", "sell"]


class OrderStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class BrokerResponse:
    order_id: str
    status: OrderStatus
    filled_quantity: int
    avg_price: float
    timestamp: int
    reason: str | None = None


def _fail_closed(message: str) -> None:
    raise FailClosedError(message)


def _validate_order_id(order_id: Any) -> str:
    if not isinstance(order_id, str):
        _fail_closed("invalid_order_id:type")
    normalized = order_id.strip()
    if not normalized:
        _fail_closed("invalid_order_id:empty")
    return normalized


def _validate_order_for_broker(order: Any) -> Order:
    if not isinstance(order, Order):
        _fail_closed("invalid_order:type")
    if not str(order.symbol or "").strip():
        _fail_closed("invalid_symbol")
    _validate_order_id(order.order_id)
    if isinstance(order.quantity, bool) or not isinstance(order.quantity, int) or order.quantity <= 0:
        _fail_closed("invalid_quantity")
    if isinstance(order.filled_quantity, bool) or not isinstance(order.filled_quantity, int) or order.filled_quantity < 0:
        _fail_closed("invalid_filled_quantity")
    if order.filled_quantity > order.quantity:
        _fail_closed("filled_quantity_exceeds_quantity")
    if float(order.price) <= 0.0:
        _fail_closed("invalid_price")
    if order.state not in {OrderState.VALIDATED, OrderState.SENT}:
        _fail_closed("invalid_state")
    if order.filled_quantity != 0:
        _fail_closed("invalid_filled_quantity")
    return order


class BrokerAdapter(ABC):
    """Low-level execution bridge (paper / live). No network in base class."""

    @abstractmethod
    def send_order(self, order: Order) -> BrokerResponse: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> BrokerResponse: ...

    @abstractmethod
    def get_order_status(self, order_id: str) -> BrokerResponse: ...


class DummyBrokerAdapter(BrokerAdapter):
    """Strict in-memory adapter: accepts validated orders, never guesses fills."""

    def __init__(self) -> None:
        self._responses: dict[str, BrokerResponse] = {}
        self._clock = 0

    def _next_timestamp(self) -> int:
        self._clock += 1
        return self._clock

    def send_order(self, order: Order) -> BrokerResponse:
        validated_order = _validate_order_for_broker(order)
        order_id = _validate_order_id(validated_order.order_id)
        if order_id in self._responses:
            _fail_closed("duplicate_order_id")
        response = BrokerResponse(
            order_id=order_id,
            status=OrderStatus.ACCEPTED,
            filled_quantity=0,
            avg_price=0.0,
            timestamp=self._next_timestamp(),
            reason=None,
        )
        self._responses[order_id] = response
        return response

    def cancel_order(self, order_id: str) -> BrokerResponse:
        normalized_order_id = _validate_order_id(order_id)
        previous = self._responses.get(normalized_order_id)
        if previous is None:
            _fail_closed("unknown_order_id")
        if previous.status is not OrderStatus.ACCEPTED:
            _fail_closed("invalid_state")
        response = BrokerResponse(
            order_id=normalized_order_id,
            status=OrderStatus.CANCELLED,
            filled_quantity=previous.filled_quantity,
            avg_price=previous.avg_price,
            timestamp=self._next_timestamp(),
            reason=None,
        )
        self._responses[normalized_order_id] = response
        return response

    def get_order_status(self, order_id: str) -> BrokerResponse:
        normalized_order_id = _validate_order_id(order_id)
        response = self._responses.get(normalized_order_id)
        if response is None:
            _fail_closed("unknown_order_id")
        return response


class StubBrokerAdapter:
    """
    Stub broker adapter that reads fixture JSON responses for place_orders, cancel, get_fills.
    Config: dict with optional "fixture_dir" (path) or paths "place_orders_response", "cancel_response", "get_fills_response".
    If fixture path missing, returns default ok=True empty response.
    """

    def __init__(self, config: Dict[str, Any] | Path | str) -> None:
        self._config: Dict[str, Any] = {}
        if isinstance(config, (Path, str)):
            path = Path(config)
            if path.is_file():
                self._config = json.loads(path.read_text(encoding="utf-8"))
            elif path.is_dir():
                self._config = {"fixture_dir": str(path)}
        else:
            self._config = dict(config) if config else {}
        self._fixture_dir: Optional[Path] = None
        if self._config.get("fixture_dir"):
            self._fixture_dir = Path(self._config["fixture_dir"])

    def _read_fixture(self, key: str, default: Dict[str, Any]) -> Dict[str, Any]:
        path = self._config.get(key)
        if path and Path(path).is_file():
            out = json.loads(Path(path).read_text(encoding="utf-8"))
            return out if isinstance(out, dict) else default
        if self._fixture_dir:
            # Conventional filenames: place_orders_response.json, cancel_response.json, get_fills_response.json
            name = {
                "place_orders_response": "place_orders_response.json",
                "cancel_response": "cancel_response.json",
                "get_fills_response": "get_fills_response.json",
            }.get(key, f"{key}.json")
            p = self._fixture_dir / name
            if p.is_file():
                out = json.loads(p.read_text(encoding="utf-8"))
                return out if isinstance(out, dict) else default
        return default

    def place_orders(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        err = _validate_place_orders_input(payload)
        if err:
            return {"ok": False, "order_ids": [], "fills": [], "errors": [err]}
        default = {"ok": True, "order_ids": [], "fills": [], "errors": []}
        out = self._read_fixture("place_orders_response", default)
        if _validate_place_orders_output(out):
            return default
        return out

    def cancel(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        err = _validate_cancel_input(payload)
        if err:
            return {"ok": False, "cancelled": [], "errors": [err]}
        default = {"ok": True, "cancelled": [], "errors": []}
        out = self._read_fixture("cancel_response", default)
        if _validate_cancel_output(out):
            return default
        return out

    def get_fills(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        err = _validate_get_fills_input(payload)
        if err:
            return {"ok": False, "fills": [], "errors": [err]}
        default = {"ok": True, "fills": [], "errors": []}
        out = self._read_fixture("get_fills_response", default)
        if _validate_get_fills_output(out):
            return default
        return out


class PaperBrokerAdapter(BrokerAdapter):
    """Paper path: create order on engine, immediate fill attempt at ``market_price``."""

    def __init__(self, execution_engine: "ExecutionEngine") -> None:
        self.engine = execution_engine

    def send_order(
        self,
        symbol: str,
        side: OrderSide,
        price: float,
        size: int,
        *,
        market_price: float | None = None,
    ) -> str:
        mp = float(market_price) if market_price is not None else float(price)
        order = self.engine.create_order(symbol, side, float(price), int(size))
        self.engine.process_fill(order, mp)
        return str(order.id)

    def cancel_order(self, order_id: str) -> bool:
        return self.engine.cancel_order(order_id)

    def get_order_status(self, order_id: str) -> Optional[str]:
        o = self.engine.orders.get(order_id)
        if o is None:
            return None
        return str(o.status)


__all__ = [
    "BrokerResponse",
    "BrokerAdapter",
    "BrokerPlacementProtocol",
    "DummyBrokerAdapter",
    "OrderStatus",
    "PaperBrokerAdapter",
    "StubBrokerAdapter",
    "PLACE_ORDERS_INPUT_KEYS",
    "PLACE_ORDERS_OUTPUT_KEYS",
    "CANCEL_INPUT_KEYS",
    "CANCEL_OUTPUT_KEYS",
    "GET_FILLS_INPUT_KEYS",
    "GET_FILLS_OUTPUT_KEYS",
    "FILL_RECORD_KEYS",
    "_validate_place_orders_input",
    "_validate_place_orders_output",
    "_validate_cancel_input",
    "_validate_cancel_output",
    "_validate_get_fills_input",
    "_validate_get_fills_output",
    "_validate_fill_record",
]
