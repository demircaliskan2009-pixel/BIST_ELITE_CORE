"""
FAZ88: Orders intent schema v2 — define + validate.
Required: day (str), actions (list). Each action: symbol (str), side (str). Deterministic error codes.
"""

from __future__ import annotations

from typing import Any, List, Tuple

ORDERS_INTENT_SCHEMA_VERSION = 2


def validate_orders_intent_v2(data: Any) -> Tuple[bool, List[str]]:
    """
    Validate orders_intent for schema v2. Returns (ok, errors).
    Required: day (str), actions (list). Each action: symbol (str), side (str).
    errors are sorted stable codes: orders_intent_not_dict, orders_intent_missing_day, orders_intent_missing_actions,
    orders_intent_day_not_str, orders_intent_actions_not_list, orders_intent_action_missing_symbol, orders_intent_action_missing_side.
    """
    errors: List[str] = []
    if not isinstance(data, dict):
        return (False, ["orders_intent_not_dict"])
    if "day" not in data:
        errors.append("orders_intent_missing_day")
    elif not isinstance(data.get("day"), str):
        errors.append("orders_intent_day_not_str")
    if "actions" not in data:
        errors.append("orders_intent_missing_actions")
    elif not isinstance(data.get("actions"), list):
        errors.append("orders_intent_actions_not_list")
    else:
        for i, action in enumerate(data["actions"]):
            if not isinstance(action, dict):
                errors.append("orders_intent_action_not_dict")
                continue
            if not (action.get("symbol") or "").strip():
                errors.append("orders_intent_action_missing_symbol")
            if not (action.get("side") or "").strip():
                errors.append("orders_intent_action_missing_side")
    return (len(errors) == 0, sorted(set(errors)))


__all__ = ["ORDERS_INTENT_SCHEMA_VERSION", "validate_orders_intent_v2"]
