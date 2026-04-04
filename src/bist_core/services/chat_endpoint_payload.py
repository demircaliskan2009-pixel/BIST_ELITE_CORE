from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bist_core.services.chat_pipeline import build_chat_pipeline_result


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _build_primary_card(pipe: Mapping[str, Any]) -> dict[str, Any] | None:
    body = _clean_text(pipe.get("body"))
    if not body:
        return None

    return {
        "kind": "summary",
        "route": str(pipe.get("route") or "unknown"),
        "title": _clean_text(pipe.get("title")),
        "subtitle": _clean_text(pipe.get("subtitle")),
        "preview": _clean_text(pipe.get("preview")),
        "body": body,
    }


def build_chat_endpoint_payload(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> dict[str, Any]:
    pipe = build_chat_pipeline_result(
        text,
        known_symbols=known_symbols,
        results_by_symbol=results_by_symbol,
        scan_results=scan_results,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
    )

    primary_card = _build_primary_card(pipe)
    cards = [primary_card] if primary_card is not None else []

    error_code = pipe.get("error_code")
    error_obj = None
    if error_code:
        error_obj = {
            "code": str(error_code),
            "message": _clean_text(pipe.get("body")),
        }

    return {
        "ok": bool(pipe.get("ok")),
        "status": str(pipe.get("status") or ("ok" if pipe.get("ok") else "error")),
        "query": _clean_text(text),
        "route": str(pipe.get("route") or "unknown"),
        "answer_type": str(pipe.get("route") or "unknown"),
        "title": _clean_text(pipe.get("title")),
        "subtitle": _clean_text(pipe.get("subtitle")),
        "preview": _clean_text(pipe.get("preview")),
        "text": _clean_text(pipe.get("body")),
        "symbols": {
            "requested": list(pipe.get("requested_symbols") or []),
            "requested_symbol": pipe.get("requested_symbol"),
            "primary": pipe.get("primary_symbol"),
            "leader": pipe.get("leader_symbol"),
        },
        "metrics": {
            "top_n": pipe.get("top_n"),
            "scan_count": int(pipe.get("scan_count") or 0),
            "comparison_count": int(pipe.get("comparison_count") or 0),
        },
        "error": error_obj,
        "cards": cards,
        "ui": {
            "primary_card": primary_card,
            "has_cards": bool(cards),
        },
        "raw": pipe,
    }


def render_chat_endpoint_text(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> str:
    payload = build_chat_endpoint_payload(
        text,
        known_symbols=known_symbols,
        results_by_symbol=results_by_symbol,
        scan_results=scan_results,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
    )
    return _clean_text(payload.get("text"))


def render_chat_endpoint_markdown(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> str:
    payload = build_chat_endpoint_payload(
        text,
        known_symbols=known_symbols,
        results_by_symbol=results_by_symbol,
        scan_results=scan_results,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
    )

    title = _clean_text(payload.get("title"))
    subtitle = _clean_text(payload.get("subtitle"))
    body = _clean_text(payload.get("text"))

    parts: list[str] = []
    if title:
        parts.append(f"## {title}")
    if subtitle:
        parts.append(subtitle)
    if body:
        parts.append(body)
    return "\n\n".join(parts).strip()
