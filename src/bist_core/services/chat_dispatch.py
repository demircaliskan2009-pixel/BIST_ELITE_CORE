from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bist_core.services.chat_intent import classify_chat_intent
from bist_core.services.scan_ranking import rank_scan_candidates, render_scan_ranking_text
from bist_core.services.single_symbol_brief import build_single_symbol_brief
from bist_core.services.symbol_comparison import compare_symbol_results, render_comparison_text


def _normalize_results_by_symbol(
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(results_by_symbol, Mapping):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, value in results_by_symbol.items():
        if not isinstance(value, Mapping):
            continue
        symbol = str(value.get("symbol") or key).upper().strip()
        if symbol:
            out[symbol] = dict(value)
    return out


def build_chat_dispatch_plan(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    default_scan_n: int = 5,
) -> dict[str, Any]:
    intent = classify_chat_intent(text, known_symbols=known_symbols)
    symbols = list(intent.get("symbols") or [])
    top_n = intent.get("top_n")
    route = intent.get("intent") or "unknown"
    error_code = None

    if route == "scan" and not top_n:
        top_n = default_scan_n

    if route == "comparison" and len(symbols) < 2:
        error_code = "insufficient_comparison_symbols"
    elif route == "single_symbol" and len(symbols) != 1:
        error_code = "single_symbol_resolution_failed"

    return {
        **intent,
        "route": route,
        "top_n": top_n,
        "error_code": error_code,
        "requires_symbols": route in {"comparison", "single_symbol"},
        "requires_scan_results": route == "scan",
    }


def dispatch_chat_request(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    default_scan_n: int = 5,
) -> dict[str, Any]:
    plan = build_chat_dispatch_plan(text, known_symbols=known_symbols, default_scan_n=default_scan_n)
    normalized_results = _normalize_results_by_symbol(results_by_symbol)
    route = plan["route"]
    intent_symbols = list(plan.get("symbols") or [])

    if plan.get("error_code"):
        return {
            "route": route,
            "ok": False,
            "error_code": plan["error_code"],
            "text": "",
            "symbols": plan.get("symbols", []),
        "intent_symbols": intent_symbols,
            "top_n": plan.get("top_n"),
            "payload": {},
        }

    if route == "comparison":
        requested = [s for s in plan.get("symbols", []) if s in normalized_results]
        compared_results = [normalized_results[s] for s in requested]
        compared = compare_symbol_results(compared_results)
        ok = compared.get("comparison_count", 0) >= 2
        return {
            "route": route,
            "ok": ok,
            "error_code": None if ok else "insufficient_comparison_results",
            "symbols": requested,
            "intent_symbols": intent_symbols,
            "top_n": None,
            "payload": compared,
            "text": render_comparison_text(compared_results) if ok else "",
        }

    if route == "scan":
        ranked = rank_scan_candidates(scan_results or [], top_n=plan.get("top_n"))
        ok = ranked.get("count", 0) > 0
        return {
            "route": route,
            "ok": ok,
            "error_code": None if ok else "empty_scan_results",
            "symbols": ranked.get("symbols", []),
            "intent_symbols": intent_symbols,
            "top_n": plan.get("top_n"),
            "payload": ranked,
            "text": render_scan_ranking_text(scan_results or [], top_n=plan.get("top_n")) if ok else "",
        }

    if route == "single_symbol":
        symbol = next(iter(plan.get("symbols", [])), None)
        selected = normalized_results.get(symbol) if symbol else None
        return {
            "route": route,
            "ok": selected is not None,
            "error_code": None if selected is not None else "missing_single_symbol_result",
            "symbols": [symbol] if symbol else [],
            "intent_symbols": intent_symbols,
            "top_n": None,
            "payload": selected if selected is not None else {},
            "text": build_single_symbol_brief(selected) if selected is not None else "",
        }

    if route == "market_overview":
        return {
            "route": route,
            "ok": True,
            "error_code": None,
            "symbols": [],
            "intent_symbols": intent_symbols,
            "top_n": None,
            "payload": {},
            "text": "",
        }

    return {
        "route": route,
        "ok": False,
        "error_code": "unknown_route",
        "symbols": plan.get("symbols", []),
        "intent_symbols": intent_symbols,
        "top_n": plan.get("top_n"),
        "payload": {},
        "text": "",
    }
