from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bist_core.services.chat_response_builder import build_chat_response
from bist_core.services.market_overview_brief import build_market_overview_payload


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def build_chat_service_payload(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> dict[str, Any]:
    response = build_chat_response(
        text,
        known_symbols=known_symbols,
        results_by_symbol=results_by_symbol,
        scan_results=scan_results,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
    )

    route = str(response.get("route") or "unknown")
    ok = bool(response.get("ok"))
    response_text = str(response.get("text") or "").strip()
    error_code = response.get("error_code")
    intent_symbols = list(response.get("intent_symbols") or [])
    requested_symbols = intent_symbols or list(response.get("symbols") or [])
    payload = _as_dict(response.get("payload"))

    requested_symbol = None
    leader_symbol = None
    primary_symbol = None
    scan_count = 0
    comparison_count = 0

    if route == "single_symbol":
        requested_symbol = requested_symbols[0] if requested_symbols else payload.get("symbol")
        primary_symbol = requested_symbol
    elif route == "comparison":
        leader = _as_dict(payload.get("leader"))
        leader_symbol = leader.get("symbol")
        primary_symbol = leader_symbol
        comparison_count = int(payload.get("comparison_count") or 0)
    elif route == "scan":
        leader = _as_dict(payload.get("leader"))
        leader_symbol = leader.get("symbol")
        primary_symbol = leader_symbol
        scan_count = int(payload.get("count") or 0)
    elif route == "market_overview":
        market_payload = build_market_overview_payload(
            scan_results or [],
            top_n=min(max(int(default_scan_n), 1), 5),
        )
        leader = _as_dict(market_payload.get("leader"))
        leader_symbol = leader.get("symbol")
        primary_symbol = leader_symbol
        scan_count = int(market_payload.get("count") or 0)

    return {
        "ok": ok,
        "route": route,
        "text": response_text,
        "error_code": error_code,
        "requested_symbols": requested_symbols,
        "requested_symbol": requested_symbol,
        "leader_symbol": leader_symbol,
        "primary_symbol": primary_symbol,
        "top_n": response.get("top_n"),
        "scan_count": scan_count,
        "comparison_count": comparison_count,
        "has_text": bool(response_text),
        "payload": payload,
        "raw_response": response,
    }


def render_chat_service_text(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> str:
    payload = build_chat_service_payload(
        text,
        known_symbols=known_symbols,
        results_by_symbol=results_by_symbol,
        scan_results=scan_results,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
    )
    return str(payload.get("text") or "").strip()
