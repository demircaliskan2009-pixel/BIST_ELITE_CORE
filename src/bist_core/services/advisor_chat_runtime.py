from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any

from bist_core.services import advisor as advisor_mod
from bist_core.services.advisor_chat_adapter import (
    build_chat_result_from_advice_map,
    build_scan_results_from_advice_map,
)
from bist_core.services.chat_intent import classify_chat_intent
from bist_core.services.scan_ranking import rank_scan_candidates
from bist_core.services.live_price_sanity import (
    sanitize_advice_payload_for_chat,
    sanitize_chat_result_live_text,
)


def _normalize_symbol_list(values: Sequence[str] | None) -> list[str]:
    if not values:
        return []
    out: list[str] = []
    for value in values:
        token = str(value or "").upper().strip()
        if token and token not in out:
            out.append(token)
    return out


def _resolve_runtime_symbols(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    scan_universe: Sequence[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    normalized_known = _normalize_symbol_list(known_symbols)
    normalized_universe = _normalize_symbol_list(scan_universe)
    intent = classify_chat_intent(text, known_symbols=(normalized_known or normalized_universe or None))
    route = str(intent.get("intent") or "unknown")
    intent_symbols = _normalize_symbol_list(intent.get("symbols") or [])

    if route in {"single_symbol", "comparison"} and intent_symbols:
        return intent, intent_symbols

    base = normalized_universe or normalized_known
    return intent, base


def _call_build_advice_for_symbol(
    symbol: str,
    day: Any,
    **kwargs: Any,
) -> Any:
    fn = advisor_mod.build_advice_for_symbol
    sig = inspect.signature(fn)

    accepted: dict[str, Any] = {}
    params = sig.parameters

    if "symbol" in params:
        accepted["symbol"] = symbol

    if "date" in params:
        accepted["date"] = day
    elif "day" in params:
        accepted["day"] = day

    for key, value in kwargs.items():
        if key in params and value is not None:
            accepted[key] = value

    return fn(**accepted)


def _error_summary(exc: Exception) -> str:
    return exc.__class__.__name__


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


def _coerce_day_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text[:10] if text else ""


def _extract_effective_day(advice: Any) -> str:
    raw = _as_dict(advice)
    for key in ("date", "day", "asof_date", "snapshot_date", "effective_date"):
        text = _coerce_day_text(raw.get(key))
        if text:
            return text
    return ""


def _collect_asof_metadata(
    advice_map: Mapping[str, Any] | dict[str, Any] | None,
    requested_day: Any,
) -> dict[str, Any]:
    requested_text = _coerce_day_text(requested_day)
    effective_by_symbol: dict[str, str] = {}
    stale_symbols: list[str] = []

    if isinstance(advice_map, Mapping):
        for symbol, advice in advice_map.items():
            effective_text = _extract_effective_day(advice)
            if effective_text:
                effective_by_symbol[str(symbol)] = effective_text
                if requested_text and effective_text != requested_text:
                    stale_symbols.append(str(symbol))

    return {
        "requested_day": requested_text,
        "effective_days": sorted(set(effective_by_symbol.values())),
        "effective_by_symbol": effective_by_symbol,
        "stale_symbols": stale_symbols,
        "is_fallback": bool(stale_symbols),
    }




def _append_live_context_note(
    result: Mapping[str, Any] | dict[str, Any],
    live_context_meta: Mapping[str, Any] | dict[str, Any] | None,
) -> dict[str, Any]:
    out = dict(result) if isinstance(result, Mapping) else {}
    meta = dict(live_context_meta) if isinstance(live_context_meta, Mapping) else {}

    if not bool(meta.get("suppressed")):
        return out

    reason = str(meta.get("suppression_reason") or "").strip()
    note = "Canlı veri ölçek tutarsızlığı nedeniyle canlı bağlam gizlendi."
    if reason and reason != "live_price_out_of_band":
        note = f"{note} Sebep: {reason}."

    body = str(out.get("text") or "").strip()
    base_note = "Canlı veri ölçek tutarsızlığı nedeniyle canlı bağlam gizlendi."
    if base_note not in body and note not in body:
        out["text"] = f"{body}\n\n{note}" if body else note

    if reason == "live_price_out_of_band" and "Sebep: suspicious_live_gap_text." in str(out.get("text") or ""):
        out["text"] = str(out.get("text") or "").replace(
            "\n\nCanlı veri ölçek tutarsızlığı nedeniyle canlı bağlam gizlendi. Sebep: suspicious_live_gap_text.",
            "",
        ).replace(
            "Canlı veri ölçek tutarsızlığı nedeniyle canlı bağlam gizlendi. Sebep: suspicious_live_gap_text.\n\n",
            "",
        )

    preview = str(out.get("preview") or "").strip()
    if preview and note not in preview:
        out["preview"] = f"{preview} [canlı bağlam gizlendi]"

    return out

def _append_asof_note(
    result: Mapping[str, Any] | dict[str, Any],
    meta: Mapping[str, Any] | dict[str, Any],
) -> dict[str, Any]:
    out = dict(result) if isinstance(result, Mapping) else {}

    requested_day = str(meta.get("requested_day") or "").strip()
    effective_days = list(meta.get("effective_days") or [])
    stale_symbols = list(meta.get("stale_symbols") or [])

    out["data_asof_requested_day"] = requested_day
    out["data_asof_effective_days"] = effective_days
    out["data_asof_symbols"] = stale_symbols

    if not requested_day or not effective_days:
        out["data_asof_mode"] = "unknown"
        return out

    if not stale_symbols:
        out["data_asof_mode"] = "exact"
        return out

    effective_text = ", ".join(effective_days)
    symbols_text = ", ".join(stale_symbols)
    note = f"Veri as-of: {effective_text} (istenen gün: {requested_day}; fallback semboller: {symbols_text})."

    body = str(out.get("text") or "").strip()
    if note not in body:
        out["text"] = f"{body}\n\n{note}" if body else note

    preview = str(out.get("preview") or "").strip()
    if preview and note not in preview:
        out["preview"] = f"{preview} [{effective_text} as-of]"

    subtitle = str(out.get("subtitle") or "").strip()
    if subtitle and "as-of=" not in subtitle:
        out["subtitle"] = f"{subtitle} | as-of={effective_text}"

    out["data_asof_mode"] = "fallback"
    return out


def _entry_from_advice(advice: Mapping[str, Any] | dict[str, Any] | None) -> float | None:
    """Extract entry price from advice (entry, entry_price, suggested_entry, buy_below)."""
    if not advice or not isinstance(advice, (Mapping, dict)):
        return None
    raw = dict(advice) if isinstance(advice, Mapping) else advice
    val = raw.get("entry") or raw.get("entry_price") or raw.get("suggested_entry") or raw.get("buy_below")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _live_payload_has_sane_prices(
    live_payload: Mapping[str, Any] | dict[str, Any] | None,
    entry: float | None = None,
) -> bool:
    """True if live_payload has current_price close to price/last_price (within 0.01) and in scale with entry (0.2 <= current/entry <= 5)."""
    if not live_payload or not isinstance(live_payload, (Mapping, dict)):
        return False
    if entry is None or entry <= 0:
        return False
    raw = dict(live_payload) if isinstance(live_payload, Mapping) else live_payload

    def _float(key: str) -> float | None:
        val = raw.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    current = _float("current_price")
    price = _float("price")
    last = _float("last_price")
    if current is None or current <= 0:
        return False
    price_close = (price is not None and abs(current - price) < 0.01) or (
        last is not None and abs(current - last) < 0.01
    )
    if not price_close:
        return False
    ratio = current / entry
    if ratio < 0.2 or ratio > 5:
        return False
    return True


def _enforce_live_context_suppression_no_trusted_feed(
    meta: Mapping[str, Any] | dict[str, Any] | None,
    *,
    has_sane_live_payload: bool = False,
) -> dict[str, Any]:
    """Fail-closed: suppress when no trusted feed; do not suppress when live_payload has sane prices."""
    if meta is None:
        return {}
    out = dict(meta) if isinstance(meta, Mapping) else {}
    if not out:
        return out
    if has_sane_live_payload:
        out["suppressed"] = False
    else:
        if out.get("suppressed") is False:
            out["suppressed"] = True
        if not str(out.get("suppression_reason") or "").strip():
            out["suppression_reason"] = "live_price_out_of_band"
    if out.get("suppressed") is True:
        reason = str(out.get("suppression_reason") or "").strip()
        existing_reasons = list(out.get("suppression_reasons") or [])
        if reason and not existing_reasons:
            out["suppression_reasons"] = [reason]
    return out


def _fill_suppressed_symbols_when_empty(
    meta: dict[str, Any],
    route: str,
    resolved_symbols: Sequence[str],
    ranked_first_two: Sequence[str] | None = None,
) -> None:
    """If suppressed is True and suppressed_symbols is empty, populate from route. For scan/market_overview use ranking result only."""
    if not meta or meta.get("suppressed") is not True:
        return
    existing = list(meta.get("suppressed_symbols") or [])
    if existing:
        return
    if route == "single_symbol":
        symbols = _normalize_symbol_list(resolved_symbols)
        if symbols:
            meta["suppressed_symbols"] = [symbols[0]]
    elif route == "comparison":
        symbols = _normalize_symbol_list(resolved_symbols)
        if symbols:
            meta["suppressed_symbols"] = [symbols[0]]
    elif route in ("scan", "market_overview"):
        symbols = _normalize_symbol_list(resolved_symbols)
        if symbols:
            meta["suppressed_symbols"] = symbols[:2]
        else:
            meta["suppressed_symbols"] = []
    else:
        symbols = _normalize_symbol_list(resolved_symbols)
        if symbols:
            meta["suppressed_symbols"] = [symbols[0]]


def _collect_live_context_meta(
    advice_map: Mapping[str, Any] | dict[str, Any] | None,
) -> dict[str, Any]:
    suppressed = False
    reasons: list[str] = []
    symbols: list[str] = []

    if isinstance(advice_map, Mapping):
        for symbol, advice in advice_map.items():
            raw = _as_dict(advice)
            meta = _as_dict(raw.get("live_context_meta"))
            if not bool(meta.get("suppressed")):
                continue

            suppressed = True
            sym = str(symbol).upper().strip()
            if sym and sym not in symbols:
                symbols.append(sym)

            reason = str(meta.get("suppression_reason") or "").strip()
            if reason and reason not in reasons:
                reasons.append(reason)

    return {
        "suppressed": suppressed,
        "suppression_reason": (reasons[0] if reasons else ""),
        "suppressed_symbols": symbols,
        "suppression_reasons": reasons,
    }


def build_advice_collection_via_advisor(
    symbols: Sequence[str] | None,
    day: Any,
    **advisor_kwargs: Any,
) -> dict[str, Any]:
    resolved = _normalize_symbol_list(symbols)
    advice_map: dict[str, Any] = {}
    raw_live_payloads: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}

    for symbol in resolved:
        try:
            advice = _call_build_advice_for_symbol(symbol, day, **advisor_kwargs)
        except Exception as exc:
            errors[symbol] = _error_summary(exc)
            continue

        if advice is not None:
            advice_like = _as_dict(advice) or advice
            raw = advice_like if isinstance(advice_like, (Mapping, dict)) else {}
            lp = raw.get("live_payload") or raw.get("live_bridge") or raw.get("bridge_row") or raw.get("current_bar")
            if isinstance(lp, (Mapping, dict)):
                raw_live_payloads[symbol] = dict(lp)
            advice_map[symbol] = sanitize_advice_payload_for_chat(advice_like)

    return {
        "advice_map": advice_map,
        "raw_live_payloads": raw_live_payloads,
        "errors": errors,
        "requested_symbols": resolved,
    }


def build_advice_map_via_advisor(
    symbols: Sequence[str] | None,
    day: Any,
    **advisor_kwargs: Any,
) -> dict[str, Any]:
    collection = build_advice_collection_via_advisor(symbols, day, **advisor_kwargs)
    return dict(collection.get("advice_map") or {})


def build_chat_result_via_advisor(
    text: str | None,
    day: Any,
    *,
    known_symbols: Sequence[str] | None = None,
    scan_universe: Sequence[str] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
    **advisor_kwargs: Any,
) -> dict[str, Any]:
    intent, resolved_symbols = _resolve_runtime_symbols(
        text,
        known_symbols=known_symbols,
        scan_universe=scan_universe,
    )

    collection = build_advice_collection_via_advisor(resolved_symbols, day, **advisor_kwargs)
    advice_map = dict(collection.get("advice_map") or {})
    raw_live_payloads = dict(collection.get("raw_live_payloads") or {})
    advisor_errors = dict(collection.get("errors") or {})

    has_sane_live_payload = any(
        _live_payload_has_sane_prices(
            raw_live_payloads[s],
            _entry_from_advice(advice_map.get(s)),
        )
        for s in raw_live_payloads
    )

    resolved_known = (
        _normalize_symbol_list(known_symbols)
        or _normalize_symbol_list(scan_universe)
        or list(advice_map.keys())
        or list(resolved_symbols)
    )

    result = build_chat_result_from_advice_map(
        text,
        advice_map=advice_map,
        known_symbols=resolved_known,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
    )
    result["live_context_meta"] = _enforce_live_context_suppression_no_trusted_feed(
        _collect_live_context_meta(advice_map),
        has_sane_live_payload=has_sane_live_payload,
    )
    route = str(intent.get("intent") or "unknown")
    ranked_first_two: list[str] = []
    if route == "scan" or route == "market_overview":
        scan_results = build_scan_results_from_advice_map(advice_map)
        scan_result = rank_scan_candidates(scan_results, top_n=default_scan_n)
        ranked = scan_result.get("ranked") or []
        ranked_first_two = [
            row.get("symbol")
            for row in ranked[:2]
            if row.get("symbol")
        ]
    _fill_suppressed_symbols_when_empty(
        result["live_context_meta"],
        route,
        resolved_symbols,
        ranked_first_two=ranked_first_two if ranked_first_two else None,
    )
    result = sanitize_chat_result_live_text(result)
    result = _append_live_context_note(result, result.get("live_context_meta"))

    asof_meta = _collect_asof_metadata(advice_map, day)
    result = _append_asof_note(result, asof_meta)

    return {
        **result,
        "advisor_route": intent.get("intent"),
        "resolved_symbols": resolved_symbols,
        "advisor_count": len(advice_map),
        "advisor_errors": advisor_errors,
        "advisor_error_count": len(advisor_errors),
        "data_asof_mode": result.get("data_asof_mode"),
        "data_asof_requested_day": result.get("data_asof_requested_day"),
        "data_asof_effective_days": list(result.get("data_asof_effective_days") or []),
        "data_asof_symbols": list(result.get("data_asof_symbols") or []),
        "live_context_meta": dict(result.get("live_context_meta") or {}),
    }




