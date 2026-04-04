from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any

from bist_core.services.chat_application_service import build_chat_application_service_result
from bist_core.services.live_price_sanity import sanitize_live_payload_for_chat


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        out = asdict(value)
        try:
            extra = dict(vars(value))
        except TypeError:
            extra = {}
        for key, raw in extra.items():
            out[key] = raw
        return out
    if hasattr(value, "__dict__"):
        try:
            return dict(vars(value))
        except TypeError:
            return {}
    return {}


def _clean_symbol(value: Any) -> str:
    return str(value or "").upper().strip()


def normalize_advice_like_result(value: Any) -> dict[str, Any]:
    raw = _as_dict(value)
    if not raw:
        return {}

    symbol = _clean_symbol(raw.get("symbol") or raw.get("ticker"))
    if not symbol:
        return {}

    out: dict[str, Any] = {"symbol": symbol}

    score = raw.get("score")
    if score is not None:
        out["score"] = score

    decision = raw.get("decision") or raw.get("action") or raw.get("signal")
    if decision is not None:
        out["decision"] = decision

    entry = raw.get("entry") or raw.get("entry_price") or raw.get("suggested_entry") or raw.get("buy_below")
    if entry is not None:
        out["entry"] = entry

    stop = raw.get("stop") or raw.get("stop_loss") or raw.get("invalidation") or raw.get("invalid_below")
    if stop is not None:
        out["stop"] = stop

    target = raw.get("target") or raw.get("hedef") or raw.get("take_profit") or raw.get("tp") or raw.get("first_target")
    if target is not None:
        out["target"] = target

    rationale = (
        raw.get("compact_rationale")
        or raw.get("rationale")
        or raw.get("summary")
        or raw.get("text")
    )
    if rationale is not None:
        out["rationale"] = str(rationale).strip()

    for key in (
        "entry_missed",
        "should_wait_pullback",
        "is_discount_to_entry",
        "live_gap_pct",
        "live_entry_status",
        "live_entry_text",
    ):
        if key in raw and raw[key] is not None:
            out[key] = raw[key]

    live_payload = raw.get("live_payload") or raw.get("live_bridge") or raw.get("bridge_row") or raw.get("current_bar")
    if isinstance(live_payload, Mapping):
        out["live_payload"] = dict(live_payload)

    return sanitize_live_payload_for_chat(out)


def build_results_by_symbol_from_advice_map(
    advice_map: Mapping[str, Any] | dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(advice_map, Mapping):
        return {}

    out: dict[str, dict[str, Any]] = {}
    for key, value in advice_map.items():
        normalized = normalize_advice_like_result(value)
        symbol = normalized.get("symbol") or _clean_symbol(key)
        if symbol:
            normalized["symbol"] = symbol
            out[str(symbol)] = normalized
    return out


def build_scan_results_from_advice_map(
    advice_map: Mapping[str, Any] | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    results_by_symbol = build_results_by_symbol_from_advice_map(advice_map)
    return list(results_by_symbol.values())


def build_chat_result_from_advice_map(
    text: str | None,
    *,
    advice_map: Mapping[str, Any] | dict[str, Any] | None = None,
    known_symbols: Sequence[str] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> dict[str, Any]:
    results_by_symbol = build_results_by_symbol_from_advice_map(advice_map)
    scan_results = build_scan_results_from_advice_map(advice_map)

    resolved_known = list(known_symbols) if known_symbols is not None else list(results_by_symbol.keys())

    return build_chat_application_service_result(
        text=text,
        known_symbols=resolved_known,
        results_by_symbol=results_by_symbol,
        scan_results=scan_results,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
    )

