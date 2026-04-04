from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bist_core.services.chat_facade import build_chat_facade_result


def build_chat_pipeline_result(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> dict[str, Any]:
    facade = build_chat_facade_result(
        text,
        known_symbols=known_symbols,
        results_by_symbol=results_by_symbol,
        scan_results=scan_results,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
    )

    title = str(facade.get("title") or "").strip()
    subtitle = str(facade.get("subtitle") or "").strip()
    preview = str(facade.get("preview") or "").strip()
    body = str(facade.get("text") or "").strip()
    route = str(facade.get("route") or "unknown")
    ok = bool(facade.get("ok"))

    return {
        "ok": ok,
        "status": "ok" if ok else "error",
        "route": route,
        "title": title,
        "subtitle": subtitle,
        "preview": preview,
        "body": body,
        "primary_symbol": facade.get("primary_symbol"),
        "leader_symbol": facade.get("leader_symbol"),
        "requested_symbol": facade.get("requested_symbol"),
        "requested_symbols": list(facade.get("requested_symbols") or []),
        "top_n": facade.get("top_n"),
        "scan_count": int(facade.get("scan_count") or 0),
        "comparison_count": int(facade.get("comparison_count") or 0),
        "error_code": facade.get("error_code"),
        "ui_card": {
            "title": title,
            "subtitle": subtitle,
            "preview": preview,
            "body": body,
        },
        "raw": facade,
    }


def render_chat_pipeline_text(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> str:
    result = build_chat_pipeline_result(
        text,
        known_symbols=known_symbols,
        results_by_symbol=results_by_symbol,
        scan_results=scan_results,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
    )
    return str(result.get("body") or "").strip()


def render_chat_pipeline_markdown(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> str:
    result = build_chat_pipeline_result(
        text,
        known_symbols=known_symbols,
        results_by_symbol=results_by_symbol,
        scan_results=scan_results,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
    )

    title = str(result.get("title") or "").strip()
    subtitle = str(result.get("subtitle") or "").strip()
    body = str(result.get("body") or "").strip()

    parts: list[str] = []
    if title:
        parts.append(f"## {title}")
    if subtitle:
        parts.append(subtitle)
    if body:
        parts.append(body)
    return "\n\n".join(parts).strip()
