from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_RANKED_LINE_RE = re.compile(r"(?m)^\d+\)\s+[^\s]+")
_ENTRY_GAP_RE = re.compile(r"entry gap\s*([+-]?\d+(?:\.\d+)?)%", re.IGNORECASE)


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_int(value: Any, default: int = 0) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return default
    return out


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _extract_entry_gap_pct(text: str) -> float | None:
    match = _ENTRY_GAP_RE.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except (TypeError, ValueError):
        return None


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


def _extract_endpoint_payload(raw: Mapping[str, Any]) -> dict[str, Any]:
    response = _as_dict(raw.get("response"))
    if response.get("symbols") or response.get("metrics"):
        return response

    nested = _as_dict(response.get("response"))
    if nested.get("symbols") or nested.get("metrics"):
        return nested

    nested2 = _as_dict(nested.get("response"))
    if nested2.get("symbols") or nested2.get("metrics"):
        return nested2

    return {}


def _extract_symbols(raw: Mapping[str, Any]) -> tuple[list[str], str | None, str | None]:
    endpoint = _extract_endpoint_payload(raw)
    symbols = _as_dict(endpoint.get("symbols"))

    requested = _as_symbol_list(symbols.get("requested"))
    if not requested:
        requested = _as_symbol_list(raw.get("resolved_symbols"))

    primary = _as_str(raw.get("primary_symbol") or symbols.get("primary")) or None
    leader = _as_str(raw.get("leader_symbol") or symbols.get("leader")) or None
    return requested, primary, leader


def _extract_top_n(raw: Mapping[str, Any]) -> int:
    endpoint = _extract_endpoint_payload(raw)
    metrics = _as_dict(endpoint.get("metrics"))
    return _as_int(metrics.get("top_n"), default=0)


def build_advisor_chat_quality_metrics(
    result: Mapping[str, Any] | dict[str, Any] | None,
) -> dict[str, Any]:
    raw = _as_dict(result)
    route = _as_str(raw.get("route") or raw.get("advisor_route") or "unknown") or "unknown"
    text = _as_str(raw.get("text"))
    title = _as_str(raw.get("title"))
    subtitle = _as_str(raw.get("subtitle"))

    requested_symbols, primary_symbol, leader_symbol = _extract_symbols(raw)
    top_n = _extract_top_n(raw)
    advisor_count = _as_int(raw.get("advisor_count"), default=0)
    advisor_error_count = _as_int(raw.get("advisor_error_count"), default=0)
    data_asof_mode = _as_str(raw.get("data_asof_mode") or "")
    data_asof_requested_day = _as_str(raw.get("data_asof_requested_day") or "")
    data_asof_effective_days = _as_symbol_list(raw.get("data_asof_effective_days"))
    data_asof_symbols = _as_symbol_list(raw.get("data_asof_symbols"))
    live_context_meta = _as_dict(raw.get("live_context_meta"))
    has_live_context_suppressed = bool(live_context_meta.get("suppressed"))
    live_context_suppression_reason = _as_str(live_context_meta.get("suppression_reason") or "")
    has_asof_note = "Veri as-of:" in text
    has_asof_fallback = data_asof_mode == "fallback" or bool(data_asof_symbols) or has_asof_note

    ranked_line_count = len(_RANKED_LINE_RE.findall(text))
    has_title = bool(title)
    has_subtitle = bool(subtitle)
    has_text = bool(text)
    has_ranked_list = "Sıralama:" in text and ranked_line_count > 0
    mentions_leader = (" önde;" in text) or (" lider;" in text) or (" önde." in text) or (" lider." in text)
    has_live_context = any(
        token in text for token in ("Canlı fiyat", "giriş kaçmış", "geri çekilme", "indirimli")
    )
    has_levels = all(token in text for token in ("giriş=", "stop=", "hedef="))
    has_market_breadth = ("Öne çıkanlar:" in text) or ("Piyasada öne çıkan lider" in text)
    has_error_map = advisor_error_count > 0
    has_reasoning = any(
        token in text.lower()
        for token in ("momentum", "güçlü", "zayıf", "geri çekilme", "indirimli", "kaçmış")
    )
    has_core_summary = any(
        token in text for token in ("karar=", "score=", "giriş=", "stop=", "hedef=")
    )
    entry_gap_pct = _extract_entry_gap_pct(text)
    has_suspicious_live_gap = entry_gap_pct is not None and abs(entry_gap_pct) > 250.0
    has_live_scale_warning = "Canlı veri ölçek tutarsızlığı nedeniyle canlı bağlam gizlendi." in text

    if route == "single_symbol":
        route_quality_ok = bool(primary_symbol) and has_text and (
            has_levels or has_live_context or has_reasoning or has_core_summary
        )
    elif route == "comparison":
        route_quality_ok = len(requested_symbols) >= 2 and has_ranked_list and ranked_line_count >= 2 and mentions_leader
    elif route == "scan":
        min_lines = 2 if ((top_n >= 2) or (advisor_count >= 2)) else 1
        route_quality_ok = bool(leader_symbol) and has_ranked_list and ranked_line_count >= min_lines
    elif route == "market_overview":
        route_quality_ok = bool(leader_symbol) and has_market_breadth and has_text
    else:
        route_quality_ok = has_text

    if has_suspicious_live_gap and not has_live_scale_warning:
        route_quality_ok = False

    quality_summary = (
        f"route={route} | ok={route_quality_ok} | ranked={ranked_line_count} | "
        f"live={has_live_context} | levels={has_levels} | core={has_core_summary} | gap_bad={has_suspicious_live_gap} | live_suppressed={has_live_context_suppressed} | asof={data_asof_mode or '-'} | errors={advisor_error_count}"
    )

    return {
        "route": route,
        "title": title,
        "subtitle": subtitle,
        "requested_symbols": requested_symbols,
        "primary_symbol": primary_symbol,
        "leader_symbol": leader_symbol,
        "top_n": top_n,
        "advisor_count": advisor_count,
        "advisor_error_count": advisor_error_count,
        "data_asof_mode": data_asof_mode,
        "data_asof_requested_day": data_asof_requested_day,
        "data_asof_effective_days": data_asof_effective_days,
        "data_asof_symbols": data_asof_symbols,
        "has_live_context_suppressed": has_live_context_suppressed,
        "live_context_suppression_reason": live_context_suppression_reason,
        "has_asof_note": has_asof_note,
        "has_asof_fallback": has_asof_fallback,
        "ranked_line_count": ranked_line_count,
        "has_title": has_title,
        "has_subtitle": has_subtitle,
        "has_text": has_text,
        "has_ranked_list": has_ranked_list,
        "mentions_leader": mentions_leader,
        "has_live_context": has_live_context,
        "has_levels": has_levels,
        "has_market_breadth": has_market_breadth,
        "has_error_map": has_error_map,
        "has_reasoning": has_reasoning,
        "has_core_summary": has_core_summary,
        "entry_gap_pct": entry_gap_pct,
        "has_suspicious_live_gap": has_suspicious_live_gap,
        "has_live_scale_warning": has_live_scale_warning,
        "route_quality_ok": route_quality_ok,
        "quality_summary": quality_summary,
    }
