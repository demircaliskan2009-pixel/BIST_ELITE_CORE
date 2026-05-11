from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bist_core.services.advisor_chat_quality import build_advisor_chat_quality_metrics
from bist_core.services.advisor_chat_runtime import build_chat_result_via_advisor

_REQUEST_CORE_KEYS = {
    "text",
    "query",
    "message",
    "day",
    "date",
    "known_symbols",
    "symbols_universe",
    "scan_universe",
    "universe",
    "scan_symbols",
    "market_overview_text",
    "default_scan_n",
    "advisor_kwargs",
}


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
            if token and token not in out:
                out.append(token)
        return out
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _extract_advisor_kwargs(
    request: Mapping[str, Any] | None,
    explicit: Mapping[str, Any] | dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(request, Mapping):
        for key, value in request.items():
            if key not in _REQUEST_CORE_KEYS and value is not None:
                out[str(key)] = value
    if isinstance(explicit, Mapping):
        for key, value in explicit.items():
            if value is not None:
                out[str(key)] = value
    return out


def normalize_advisor_chat_request(
    request: Mapping[str, Any] | dict[str, Any] | None = None,
    *,
    text: str | None = None,
    day: Any = None,
    known_symbols: Sequence[str] | None = None,
    scan_universe: Sequence[str] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
    advisor_kwargs: Mapping[str, Any] | dict[str, Any] | None = None,
) -> dict[str, Any]:
    req = dict(request) if isinstance(request, Mapping) else {}

    query = _as_str(text if text is not None else req.get("text") or req.get("query") or req.get("message"))
    resolved_day = day if day is not None else req.get("day") or req.get("date")
    resolved_known = _as_symbol_list(
        known_symbols if known_symbols is not None else req.get("known_symbols") or req.get("symbols_universe")
    )
    resolved_universe = _as_symbol_list(
        scan_universe if scan_universe is not None else req.get("scan_universe") or req.get("universe") or req.get("scan_symbols")
    )
    market_text = _as_str(market_overview_text if market_overview_text is not None else req.get("market_overview_text"))
    scan_n = _as_int(req.get("default_scan_n") if "default_scan_n" in req else default_scan_n, default=default_scan_n)
    extra_kwargs = _extract_advisor_kwargs(req, advisor_kwargs if advisor_kwargs is not None else req.get("advisor_kwargs"))

    return {
        "text": query,
        "day": resolved_day,
        "known_symbols": resolved_known,
        "scan_universe": resolved_universe,
        "market_overview_text": market_text,
        "default_scan_n": scan_n,
        "advisor_kwargs": extra_kwargs,
    }


def build_advisor_chat_service_result(
    request: Mapping[str, Any] | dict[str, Any] | None = None,
    *,
    text: str | None = None,
    day: Any = None,
    known_symbols: Sequence[str] | None = None,
    scan_universe: Sequence[str] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
    advisor_kwargs: Mapping[str, Any] | dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_advisor_chat_request(
        request,
        text=text,
        day=day,
        known_symbols=known_symbols,
        scan_universe=scan_universe,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
        advisor_kwargs=advisor_kwargs,
    )

    response = build_chat_result_via_advisor(
        normalized["text"],
        normalized["day"],
        known_symbols=normalized["known_symbols"],
        scan_universe=normalized["scan_universe"],
        market_overview_text=normalized["market_overview_text"] or None,
        default_scan_n=normalized["default_scan_n"],
        **normalized["advisor_kwargs"],
    )

    result = {
        "ok": bool(response.get("ok")),
        "status": str(response.get("status") or ("ok" if response.get("ok") else "error")),
        "request": normalized,
        "response": response,
        "route": response.get("route"),
        "advisor_route": response.get("advisor_route"),
        "text": response.get("text"),
        "title": response.get("title"),
        "subtitle": response.get("subtitle"),
        "primary_symbol": response.get("primary_symbol"),
        "leader_symbol": response.get("leader_symbol"),
        "resolved_symbols": list(response.get("resolved_symbols") or []),
        "advisor_count": int(response.get("advisor_count") or 0),
        "advisor_errors": _as_dict(response.get("advisor_errors")),
        "advisor_error_count": int(response.get("advisor_error_count") or 0),
        "data_asof_mode": response.get("data_asof_mode"),
        "data_asof_requested_day": response.get("data_asof_requested_day"),
        "data_asof_effective_days": list(response.get("data_asof_effective_days") or []),
        "data_asof_symbols": list(response.get("data_asof_symbols") or []),
        "live_context_meta": _as_dict(response.get("live_context_meta")),
        "error": response.get("error"),
    }
    result["quality"] = build_advisor_chat_quality_metrics(result)
    return result


def render_advisor_chat_text(
    request: Mapping[str, Any] | dict[str, Any] | None = None,
    *,
    text: str | None = None,
    day: Any = None,
    known_symbols: Sequence[str] | None = None,
    scan_universe: Sequence[str] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
    advisor_kwargs: Mapping[str, Any] | dict[str, Any] | None = None,
) -> str:
    result = build_advisor_chat_service_result(
        request,
        text=text,
        day=day,
        known_symbols=known_symbols,
        scan_universe=scan_universe,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
        advisor_kwargs=advisor_kwargs,
    )
    return _as_str(result.get("text"))


def render_advisor_chat_markdown(
    request: Mapping[str, Any] | dict[str, Any] | None = None,
    *,
    text: str | None = None,
    day: Any = None,
    known_symbols: Sequence[str] | None = None,
    scan_universe: Sequence[str] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
    advisor_kwargs: Mapping[str, Any] | dict[str, Any] | None = None,
) -> str:
    result = build_advisor_chat_service_result(
        request,
        text=text,
        day=day,
        known_symbols=known_symbols,
        scan_universe=scan_universe,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
        advisor_kwargs=advisor_kwargs,
    )

    title = _as_str(result.get("title"))
    subtitle = _as_str(result.get("subtitle"))
    body = _as_str(result.get("text"))

    parts: list[str] = []
    if title:
        parts.append(f"## {title}")
    if subtitle:
        parts.append(subtitle)
    if body:
        parts.append(body)
    return "\n\n".join(parts).strip()
