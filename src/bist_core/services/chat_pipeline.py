from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from bist_core.hooks.hook_engine import build_hook_context, run_post_hooks, run_pre_hooks
from bist_core.services.chat_facade import build_chat_facade_result
from bist_core.services.chat_intent import classify_chat_intent
from bist_core.tools.tool_dispatch import dispatch_tool

logger = logging.getLogger(__name__)

_DEBUG_ROUTES = {"debug_symbol", "debug_ranking", "debug_comparison", "debug_dataset"}


def _log_pipeline_rejection(reason: str) -> None:
    logger.error("chat_pipeline_rejected reason=%s", reason)


def _build_rejected_pipeline_result(reason: str, output: str = "INSUFFICIENT EVIDENCE") -> dict[str, Any]:
    _log_pipeline_rejection(reason)
    return {
        "ok": False,
        "status": "error",
        "route": "hook_rejected",
        "title": "Hook Rejected",
        "subtitle": reason,
        "preview": output,
        "body": output,
        "primary_symbol": None,
        "leader_symbol": None,
        "requested_symbol": None,
        "requested_symbols": [],
        "top_n": None,
        "scan_count": 0,
        "comparison_count": 0,
        "error_code": "hook_rejected",
        "ui_card": {
            "title": "Hook Rejected",
            "subtitle": reason,
            "preview": output,
            "body": output,
        },
        "hook_contract": {
            "sections": {
                "WHAT WAS ANALYZED": "hook runtime pre/post validation",
                "WHAT WAS FOUND": reason,
                "WHAT WAS FIXED": "fail_closed_rejection",
                "WHY IT WORKS": "runtime enforcement blocked unsafe output",
                "RISKS": reason,
            },
            "contains_hallucination": False,
            "missing_data_used": False,
        },
        "raw": {},
    }


def _finalize_pipeline_result(result: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    raw = dict(result) if isinstance(result, Mapping) else {}
    if not raw:
        return _build_rejected_pipeline_result("INSUFFICIENT EVIDENCE")

    post = run_post_hooks(raw)
    if post.status == "rejected":
        return _build_rejected_pipeline_result(post.reason)

    body = str(raw.get("body") or "").strip()
    route = str(raw.get("route") or "").strip()
    status = str(raw.get("status") or "").strip()
    if not body or not route or status not in {"ok", "error"}:
        return _build_rejected_pipeline_result("INSUFFICIENT EVIDENCE")

    return raw


def _build_hook_contract(
    *,
    text: str | None,
    route: str,
    body: str,
    ok: bool,
    error_code: Any,
    requested_symbols: Sequence[str],
) -> dict[str, Any]:
    query = str(text or "").strip() or "n/a"
    symbols_text = ", ".join(str(x) for x in requested_symbols) if requested_symbols else "n/a"
    found_text = body.strip() or (str(error_code).strip() if error_code else "n/a")
    return {
        "sections": {
            "WHAT WAS ANALYZED": f"route={route}; query={query}; symbols={symbols_text}",
            "WHAT WAS FOUND": found_text,
            "WHAT WAS FIXED": "response_generated" if ok else f"error={str(error_code or 'none')}",
            "WHY IT WORKS": "deterministic chat pipeline produced a structured response",
            "RISKS": "none" if ok else str(error_code or "response_error"),
        },
        "contains_hallucination": False,
        "missing_data_used": False,
    }


def _build_debug_payload(intent: Mapping[str, Any]) -> dict[str, Any]:
    symbols = [str(symbol).upper().strip() for symbol in (intent.get("symbols") or []) if str(symbol).strip()]
    first_symbol = symbols[0] if symbols else None
    return {
        "symbol": first_symbol,
        "symbols": symbols,
        "raw_text": str(intent.get("raw_text") or "").strip(),
    }


def _render_debug_body(route: str, data: Mapping[str, Any]) -> str:
    if route == "debug_symbol":
        context = dict(data.get("current_price_context") or {})
        return "\n".join(
            [
                f"What was analyzed: {data.get('symbol') or 'n/a'} score state on {data.get('day') or 'n/a'}.",
                f"What was found: entry_status={context.get('entry_status') or 'n/a'}, entry_gap_pct={context.get('entry_gap_pct') if context.get('entry_gap_pct') is not None else 'n/a'}, current_close={context.get('current_close') if context.get('current_close') is not None else 'n/a'}.",
                f"Why this score: {json.dumps(dict(data.get('score_breakdown') or {}), ensure_ascii=True, sort_keys=True)}",
                "Remaining risks: debug output reflects current deterministic advisor state only.",
            ]
        ).strip()

    if route == "debug_ranking":
        ranking = list(data.get("sorted_ranking") or [])
        leader = ranking[0].get("symbol") if ranking else "n/a"
        dispersion = dict(data.get("score_dispersion") or {})
        reasons = dict(data.get("ranking_reasons") or {})
        return "\n".join(
            [
                f"What was analyzed: ranking path for {len(ranking)} symbols on {data.get('day') or 'n/a'}.",
                f"What was found: leader={leader}, dispersion={json.dumps(dispersion, ensure_ascii=True, sort_keys=True)}.",
                f"Why this ranking: {json.dumps(reasons, ensure_ascii=True, sort_keys=True)}",
                "Remaining risks: ranking explanation is limited to the currently returned ranking payload.",
            ]
        ).strip()

    if route == "debug_comparison":
        leader_reason = dict(data.get("leader_selection_reason") or {})
        strengths = dict(data.get("strengths_weaknesses") or {})
        return "\n".join(
            [
                f"What was analyzed: comparison details on {data.get('day') or 'n/a'}.",
                f"What was found: leader={leader_reason.get('leader') or 'n/a'}, summary={leader_reason.get('summary') or 'n/a'}.",
                f"Compare details: {json.dumps(strengths, ensure_ascii=True, sort_keys=True)}",
                "Remaining risks: comparison detail is constrained to the normalized pairwise payload.",
            ]
        ).strip()

    if route == "debug_dataset":
        completeness = dict(data.get("data_completeness") or {})
        anomalies = list(data.get("anomalies") or [])
        missing = list(data.get("missing_fields") or [])
        return "\n".join(
            [
                f"What was analyzed: dataset integrity for {data.get('symbol') or 'n/a'} on {data.get('day') or 'n/a'}.",
                f"What was found: completeness={json.dumps(completeness, ensure_ascii=True, sort_keys=True)}.",
                f"Data validation details: missing_fields={json.dumps(missing, ensure_ascii=True)}, anomalies={json.dumps(anomalies, ensure_ascii=True)}",
                "Remaining risks: validation is snapshot-based and does not infer missing external context.",
            ]
        ).strip()

    return "INSUFFICIENT EVIDENCE"


def _build_debug_pipeline_result(text: str | None, intent: Mapping[str, Any]) -> dict[str, Any]:
    route = str(intent.get("intent") or "").strip()
    tool_result = dispatch_tool(route, _build_debug_payload(intent))
    if str(tool_result.get("status") or "").strip() != "ok":
        return _build_rejected_pipeline_result(str(tool_result.get("reason") or "INSUFFICIENT EVIDENCE"))

    data = dict(tool_result.get("data") or {})
    symbols = [str(symbol).upper().strip() for symbol in (tool_result.get("symbols") or []) if str(symbol).strip()]
    primary_symbol = symbols[0] if symbols else None
    title_map = {
        "debug_symbol": f"{primary_symbol or 'Sembol'} Debug",
        "debug_ranking": "Ranking Debug",
        "debug_comparison": "Comparison Debug",
        "debug_dataset": f"{primary_symbol or 'Veri'} Dataset Debug",
    }
    body = _render_debug_body(route, data)
    return {
        "ok": True,
        "status": "ok",
        "route": route,
        "title": title_map.get(route, "Debug"),
        "subtitle": f"debug route={route}",
        "preview": str((body.splitlines() or ["INSUFFICIENT EVIDENCE"])[0]).strip(),
        "body": body,
        "primary_symbol": primary_symbol,
        "leader_symbol": data.get("leader_selection_reason", {}).get("leader")
        if isinstance(data.get("leader_selection_reason"), Mapping)
        else None,
        "requested_symbol": primary_symbol,
        "requested_symbols": symbols,
        "top_n": intent.get("top_n"),
        "scan_count": len(list(data.get("sorted_ranking") or [])),
        "comparison_count": len(symbols) if route == "debug_comparison" else 0,
        "error_code": None,
        "ui_card": {
            "title": title_map.get(route, "Debug"),
            "subtitle": f"debug route={route}",
            "preview": str((body.splitlines() or ["INSUFFICIENT EVIDENCE"])[0]).strip(),
            "body": body,
        },
        "hook_contract": _build_hook_contract(
            text=text,
            route=route,
            body=body,
            ok=True,
            error_code=None,
            requested_symbols=symbols,
        ),
        "tool_output": data,
        "raw": {"intent": dict(intent), "tool_result": dict(tool_result)},
    }


def build_chat_pipeline_result(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> dict[str, Any]:
    try:
        intent = classify_chat_intent(text, known_symbols=known_symbols)
        pre = run_pre_hooks(
            build_hook_context(
                text,
                known_symbols=known_symbols,
                results_by_symbol=results_by_symbol,
                scan_results=scan_results,
                market_overview_text=market_overview_text,
            )
        )
        if pre.status == "rejected":
            return _finalize_pipeline_result(
                _build_rejected_pipeline_result(pre.reason, pre.output or "INSUFFICIENT EVIDENCE")
            )

        if isinstance(intent, Mapping) and str(intent.get("intent") or "").strip() in _DEBUG_ROUTES:
            return _finalize_pipeline_result(_build_debug_pipeline_result(text, intent))

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

        result = {
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
            "hook_contract": _build_hook_contract(
                text=text,
                route=route,
                body=body,
                ok=ok,
                error_code=facade.get("error_code"),
                requested_symbols=list(facade.get("requested_symbols") or []),
            ),
            "raw": facade,
        }
        return _finalize_pipeline_result(result)
    except Exception as exc:
        return _finalize_pipeline_result(_build_rejected_pipeline_result(exc.__class__.__name__))


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
