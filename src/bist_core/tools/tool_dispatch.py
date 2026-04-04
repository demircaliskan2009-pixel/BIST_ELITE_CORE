from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bist_core.tools.debug_tools import inspect_comparison, inspect_ranking, inspect_symbol_state, validate_dataset

FAIL_CLOSED_OUTPUT = "INSUFFICIENT EVIDENCE"


def _fail_closed(reason: str) -> dict[str, Any]:
    return {
        "status": "rejected",
        "reason": reason or FAIL_CLOSED_OUTPUT,
        "output": FAIL_CLOSED_OUTPUT,
        "data": {},
    }


def _as_mapping(payload: Any) -> dict[str, Any]:
    return dict(payload) if isinstance(payload, Mapping) else {}


def _extract_symbols(payload: Mapping[str, Any]) -> list[str]:
    raw_symbols = payload.get("symbols")
    if isinstance(raw_symbols, Sequence) and not isinstance(raw_symbols, (str, bytes)):
        return [str(item or "").strip() for item in raw_symbols if str(item or "").strip()]
    symbol = str(payload.get("symbol") or "").strip()
    return [symbol] if symbol else []


def dispatch_tool(intent: Any, payload: Any) -> dict[str, Any]:
    route = str(intent or "").strip()
    data = _as_mapping(payload)
    if not route:
        return _fail_closed("INVALID TOOL INTENT")

    try:
        if route == "debug_symbol":
            result = inspect_symbol_state(data.get("symbol"))
        elif route == "debug_ranking":
            result = inspect_ranking(data.get("symbols"))
        elif route == "debug_comparison":
            result = inspect_comparison(data.get("symbols"))
        elif route == "debug_dataset":
            result = validate_dataset(data.get("symbol"))
        else:
            return _fail_closed("UNSUPPORTED TOOL INTENT")
    except Exception:
        return _fail_closed(FAIL_CLOSED_OUTPUT)

    if not isinstance(result, Mapping):
        return _fail_closed(FAIL_CLOSED_OUTPUT)

    normalized = dict(result)
    if str(normalized.get("status") or "").strip() != "ok":
        return {
            "status": "rejected",
            "reason": str(normalized.get("reason") or FAIL_CLOSED_OUTPUT),
            "output": FAIL_CLOSED_OUTPUT,
            "data": normalized,
        }

    symbols = _extract_symbols(data)
    return {
        "status": "ok",
        "reason": "",
        "output": FAIL_CLOSED_OUTPUT,
        "intent": route,
        "symbols": symbols,
        "data": normalized,
    }
