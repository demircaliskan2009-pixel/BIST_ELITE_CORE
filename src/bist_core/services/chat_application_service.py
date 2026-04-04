from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bist_core.services.chat_endpoint_payload import (
    build_chat_endpoint_payload,
    render_chat_endpoint_markdown,
    render_chat_endpoint_text,
)


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_int(value: Any, default: int = 5) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return default
    return out if out > 0 else default


def _as_symbol_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [x.strip().upper() for x in value.replace(",", " ").split()]
        return [x for x in parts if x]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        out: list[str] = []
        for item in value:
            token = _as_str(item).upper()
            if token:
                out.append(token)
        return out
    return []


def _as_results_map(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, item in value.items():
        if not isinstance(item, Mapping):
            continue
        symbol = _as_str(item.get("symbol") if isinstance(item, Mapping) else None).upper() or _as_str(key).upper()
        if symbol:
            out[symbol] = dict(item)
    return out


def _as_result_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            out.append(dict(item))
    return out


def normalize_chat_application_request(
    request: Mapping[str, Any] | dict[str, Any] | None = None,
    *,
    text: str | None = None,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> dict[str, Any]:
    req = dict(request) if isinstance(request, Mapping) else {}

    query = _as_str(text if text is not None else req.get("text") or req.get("query") or req.get("message"))
    symbols = _as_symbol_list(
        known_symbols if known_symbols is not None else req.get("known_symbols") or req.get("symbols_universe")
    )
    results_map = _as_results_map(
        results_by_symbol if results_by_symbol is not None else req.get("results_by_symbol") or req.get("symbol_results")
    )
    scan_list = _as_result_list(
        scan_results if scan_results is not None else req.get("scan_results") or req.get("ranked_candidates")
    )
    market_text = _as_str(market_overview_text if market_overview_text is not None else req.get("market_overview_text"))
    scan_n = _as_int(req.get("default_scan_n") if "default_scan_n" in req else default_scan_n, default=default_scan_n)

    return {
        "text": query,
        "known_symbols": symbols,
        "results_by_symbol": results_map,
        "scan_results": scan_list,
        "market_overview_text": market_text,
        "default_scan_n": scan_n,
    }


def build_chat_application_service_result(
    request: Mapping[str, Any] | dict[str, Any] | None = None,
    *,
    text: str | None = None,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> dict[str, Any]:
    normalized = normalize_chat_application_request(
        request,
        text=text,
        known_symbols=known_symbols,
        results_by_symbol=results_by_symbol,
        scan_results=scan_results,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
    )

    endpoint = build_chat_endpoint_payload(
        normalized["text"],
        known_symbols=normalized["known_symbols"],
        results_by_symbol=normalized["results_by_symbol"],
        scan_results=normalized["scan_results"],
        market_overview_text=normalized["market_overview_text"] or None,
        default_scan_n=normalized["default_scan_n"],
    )

    return {
        "ok": bool(endpoint.get("ok")),
        "status": str(endpoint.get("status") or ("ok" if endpoint.get("ok") else "error")),
        "request": normalized,
        "response": endpoint,
        "route": endpoint.get("route"),
        "text": endpoint.get("text"),
        "title": endpoint.get("title"),
        "subtitle": endpoint.get("subtitle"),
        "primary_symbol": endpoint.get("symbols", {}).get("primary") if isinstance(endpoint.get("symbols"), Mapping) else None,
        "leader_symbol": endpoint.get("symbols", {}).get("leader") if isinstance(endpoint.get("symbols"), Mapping) else None,
        "error": endpoint.get("error"),
    }


def render_chat_application_text(
    request: Mapping[str, Any] | dict[str, Any] | None = None,
    *,
    text: str | None = None,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> str:
    normalized = normalize_chat_application_request(
        request,
        text=text,
        known_symbols=known_symbols,
        results_by_symbol=results_by_symbol,
        scan_results=scan_results,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
    )
    return render_chat_endpoint_text(
        normalized["text"],
        known_symbols=normalized["known_symbols"],
        results_by_symbol=normalized["results_by_symbol"],
        scan_results=normalized["scan_results"],
        market_overview_text=normalized["market_overview_text"] or None,
        default_scan_n=normalized["default_scan_n"],
    )


def render_chat_application_markdown(
    request: Mapping[str, Any] | dict[str, Any] | None = None,
    *,
    text: str | None = None,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> str:
    normalized = normalize_chat_application_request(
        request,
        text=text,
        known_symbols=known_symbols,
        results_by_symbol=results_by_symbol,
        scan_results=scan_results,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
    )
    return render_chat_endpoint_markdown(
        normalized["text"],
        known_symbols=normalized["known_symbols"],
        results_by_symbol=normalized["results_by_symbol"],
        scan_results=normalized["scan_results"],
        market_overview_text=normalized["market_overview_text"] or None,
        default_scan_n=normalized["default_scan_n"],
    )
