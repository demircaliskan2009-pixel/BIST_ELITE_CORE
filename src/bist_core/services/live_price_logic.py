from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_PRICE_KEYS = (
    "current_price",
    "live_price",
    "asof_price",
    "last_price",
    "current_close",
    "last_close",
    "close",
    "price",
)


def _as_float(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def pick_live_reference_price(payload_or_price: Mapping[str, Any] | float | int | None) -> float | None:
    if payload_or_price is None:
        return None
    if isinstance(payload_or_price, (int, float)):
        return _as_float(payload_or_price)
    if not isinstance(payload_or_price, Mapping):
        return None

    for key in _PRICE_KEYS:
        value = payload_or_price.get(key)
        price = _as_float(value)
        if price is not None:
            return price
    return None


def compute_entry_gap_pct(entry_price: float | int | None, payload_or_price: Mapping[str, Any] | float | int | None) -> float | None:
    entry = _as_float(entry_price, digits=4)
    live_price = pick_live_reference_price(payload_or_price)
    if entry is None or live_price is None or entry <= 0:
        return None
    return round(((live_price - entry) / entry) * 100.0, 4)


def classify_live_entry_status(
    entry_price: float | int | None,
    payload_or_price: Mapping[str, Any] | float | int | None,
    *,
    near_pct: float = 0.75,
    chase_pct: float = 1.50,
    favorable_pct: float = -0.75,
) -> dict[str, Any]:
    live_price = pick_live_reference_price(payload_or_price)
    entry = _as_float(entry_price)
    gap_pct = compute_entry_gap_pct(entry_price, payload_or_price)

    if live_price is None or entry is None or gap_pct is None:
        return {
            "entry_price": entry,
            "live_price": live_price,
            "gap_pct": gap_pct,
            "status": "unknown",
            "entry_missed": False,
            "should_wait_pullback": False,
            "is_discount_to_entry": False,
            "summary_code": "no_live_reference_price",
        }

    if gap_pct >= chase_pct:
        return {
            "entry_price": entry,
            "live_price": live_price,
            "gap_pct": gap_pct,
            "status": "extended_above_entry",
            "entry_missed": True,
            "should_wait_pullback": True,
            "is_discount_to_entry": False,
            "summary_code": "entry_missed_wait_pullback",
        }

    if gap_pct >= near_pct:
        return {
            "entry_price": entry,
            "live_price": live_price,
            "gap_pct": gap_pct,
            "status": "slightly_above_entry",
            "entry_missed": False,
            "should_wait_pullback": False,
            "is_discount_to_entry": False,
            "summary_code": "above_entry_not_extended",
        }

    if gap_pct <= favorable_pct:
        return {
            "entry_price": entry,
            "live_price": live_price,
            "gap_pct": gap_pct,
            "status": "below_entry_discount",
            "entry_missed": False,
            "should_wait_pullback": False,
            "is_discount_to_entry": True,
            "summary_code": "below_entry_discount",
        }

    return {
        "entry_price": entry,
        "live_price": live_price,
        "gap_pct": gap_pct,
        "status": "near_entry",
        "entry_missed": False,
        "should_wait_pullback": False,
        "is_discount_to_entry": False,
        "summary_code": "near_entry",
    }
