from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bist_core.services.chat_service import build_chat_service_payload


_ROUTE_TITLE = {
    "scan": "Tarama Sonucu",
    "comparison": "Sembol Karşılaştırma",
    "single_symbol": "Tek Hisse Özeti",
    "market_overview": "Piyasa Özeti",
    "unknown": "Chat Yanıtı",
}


def _first_line(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    return raw.splitlines()[0].strip()


def _build_title(route: str, payload: Mapping[str, Any]) -> str:
    route = str(route or "unknown")
    primary_symbol = payload.get("primary_symbol")
    top_n = payload.get("top_n")

    if route == "single_symbol" and primary_symbol:
        return f"{primary_symbol} Özeti"

    if route == "comparison":
        symbols = list(payload.get("requested_symbols") or [])
        if len(symbols) >= 2:
            return f"{symbols[0]} vs {symbols[1]}"

    if route == "scan" and top_n:
        return f"Top {top_n} Tarama"

    return _ROUTE_TITLE.get(route, "Chat Yanıtı")


def _build_subtitle(route: str, payload: Mapping[str, Any]) -> str:
    route = str(route or "unknown")
    leader_symbol = payload.get("leader_symbol")
    primary_symbol = payload.get("primary_symbol")
    scan_count = int(payload.get("scan_count") or 0)
    comparison_count = int(payload.get("comparison_count") or 0)

    if route == "single_symbol":
        if primary_symbol:
            return f"Canlı giriş özeti | sembol={primary_symbol}"
        return "Canlı giriş özeti"

    if route == "comparison":
        bits: list[str] = []
        if comparison_count > 0:
            bits.append(f"{comparison_count} sembol")
        if leader_symbol:
            bits.append(f"lider={leader_symbol}")
        return " | ".join(bits)

    if route == "scan":
        bits: list[str] = []
        if scan_count > 0:
            bits.append(f"{scan_count} aday")
        if leader_symbol:
            bits.append(f"lider={leader_symbol}")
        return " | ".join(bits)

    if route == "market_overview":
        bits: list[str] = []
        if scan_count > 0:
            bits.append(f"{scan_count} öne çıkan aday")
        if leader_symbol:
            bits.append(f"lider={leader_symbol}")
        return " | ".join(bits)

    return ""


def build_chat_facade_result(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> dict[str, Any]:
    service_payload = build_chat_service_payload(
        text,
        known_symbols=known_symbols,
        results_by_symbol=results_by_symbol,
        scan_results=scan_results,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
    )

    route = str(service_payload.get("route") or "unknown")
    response_text = str(service_payload.get("text") or "").strip()
    title = _build_title(route, service_payload)
    subtitle = _build_subtitle(route, service_payload)
    preview = _first_line(response_text)

    return {
        "ok": bool(service_payload.get("ok")),
        "route": route,
        "title": title,
        "subtitle": subtitle,
        "text": response_text,
        "preview": preview,
        "has_text": bool(response_text),
        "error_code": service_payload.get("error_code"),
        "primary_symbol": service_payload.get("primary_symbol"),
        "leader_symbol": service_payload.get("leader_symbol"),
        "requested_symbol": service_payload.get("requested_symbol"),
        "requested_symbols": list(service_payload.get("requested_symbols") or []),
        "top_n": service_payload.get("top_n"),
        "scan_count": int(service_payload.get("scan_count") or 0),
        "comparison_count": int(service_payload.get("comparison_count") or 0),
        "raw": service_payload,
    }


def render_chat_facade_text(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> str:
    result = build_chat_facade_result(
        text,
        known_symbols=known_symbols,
        results_by_symbol=results_by_symbol,
        scan_results=scan_results,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
    )
    return str(result.get("text") or "").strip()
