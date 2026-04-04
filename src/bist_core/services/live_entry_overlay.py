from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bist_core.services.live_entry_text import build_live_entry_context


_ENTRY_KEYS = (
    "entry",
    "entry_price",
    "suggested_entry",
    "entry_level",
    "buy_below",
    "plan_entry",
)


def _as_float(value: Any, digits: int = 4) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def pick_result_entry_price(result: Mapping[str, Any] | dict[str, Any] | None) -> float | None:
    if not isinstance(result, Mapping):
        return None

    for key in _ENTRY_KEYS:
        value = result.get(key)
        price = _as_float(value)
        if price is not None and price > 0:
            return price
    return None


def pick_live_payload(
    result: Mapping[str, Any] | dict[str, Any] | None,
    explicit_live_payload: Mapping[str, Any] | dict[str, Any] | None = None,
) -> Mapping[str, Any] | dict[str, Any] | None:
    if isinstance(explicit_live_payload, Mapping):
        return explicit_live_payload
    if not isinstance(result, Mapping):
        return None

    for key in ("live_payload", "live_bridge", "bridge_row", "current_bar", "live_row"):
        candidate = result.get(key)
        if isinstance(candidate, Mapping):
            return candidate
    return None


def augment_result_with_live_entry_context(
    result: Mapping[str, Any] | dict[str, Any] | None,
    live_payload: Mapping[str, Any] | dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(result) if isinstance(result, Mapping) else {}
    resolved_live_payload = pick_live_payload(out, live_payload)
    entry_price = pick_result_entry_price(out)

    if entry_price is None or resolved_live_payload is None:
        return out

    ctx = build_live_entry_context(entry_price, resolved_live_payload)
    out["live_entry_price"] = ctx.get("entry_price")
    out["live_current_price"] = ctx.get("live_price")
    out["live_gap_pct"] = ctx.get("gap_pct")
    out["live_gap_text"] = ctx.get("gap_text")
    out["live_entry_status"] = ctx.get("status")
    out["live_entry_summary_code"] = ctx.get("summary_code")
    out["entry_missed"] = bool(ctx.get("entry_missed"))
    out["should_wait_pullback"] = bool(ctx.get("should_wait_pullback"))
    out["is_discount_to_entry"] = bool(ctx.get("is_discount_to_entry"))

    text = (ctx.get("text") or "").strip()
    if text:
        out["live_entry_text"] = text

    return out
