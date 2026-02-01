"""FAZ72: Broker adapter interface (place_orders, cancel, get_fills) with strict input/output schemas. Stub reads fixture responses. No external libs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


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


class BrokerAdapter(Protocol):
    """Broker adapter interface: place_orders, cancel, get_fills with strict schemas."""

    def place_orders(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Place orders. Input: {day, actions}. Output: {ok, order_ids, fills, errors}."""
        ...

    def cancel(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel order(s). Input: {order_id} (null = cancel all). Output: {ok, cancelled, errors}."""
        ...

    def get_fills(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get fills. Input: {day?, order_id?}. Output: {ok, fills, errors}."""
        ...


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


__all__ = [
    "BrokerAdapter",
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
