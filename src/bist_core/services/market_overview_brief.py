from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bist_core.services.scan_ranking import rank_scan_candidates


def _as_float(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _entry_status_label(item: Mapping[str, Any]) -> str:
    if item.get("entry_missed"):
        return "giriş kaçmış"
    if item.get("is_discount_to_entry"):
        return "girişe göre indirimli"
    if item.get("should_wait_pullback"):
        return "geri çekilme beklenmeli"
    return "giriş durumu nötr"


def build_market_overview_brief(
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None,
    top_n: int = 5,
) -> str:
    ranked = rank_scan_candidates(scan_results or [], top_n=top_n)
    items = list(ranked.get("ranked") or [])
    if not items:
        return ""

    leader = items[0]
    leader_symbol = str(leader.get("symbol") or "").strip()
    leader_score = _as_float(leader.get("score"))
    summary_parts: list[str] = []

    if leader_symbol:
        if leader_score is not None:
            summary_parts.append(f"Piyasada öne çıkan lider {leader_symbol} (score={leader_score:.2f}).")
        else:
            summary_parts.append(f"Piyasada öne çıkan lider {leader_symbol}.")

    if len(items) >= 2:
        runner_up = items[1]
        runner_symbol = str(runner_up.get("symbol") or "").strip()
        runner_score = _as_float(runner_up.get("score"))
        if runner_symbol:
            if leader_score is not None and runner_score is not None:
                summary_parts.append(f"En yakın rakip {runner_symbol}; fark {(leader_score - runner_score):+.2f}.")
            else:
                summary_parts.append(f"En yakın rakip {runner_symbol}.")

    status_bits: list[str] = []
    entry_label = _entry_status_label(leader)
    if entry_label != "giriş durumu nötr":
        status_bits.append(entry_label)
    decision = leader.get("decision")
    if decision is not None:
        status_bits.append(f"karar={decision}")
    if status_bits:
        summary_parts.append("Lider görünüm: " + ", ".join(status_bits) + ".")

    symbols = [str(x.get("symbol") or "").strip() for x in items if str(x.get("symbol") or "").strip()]
    if symbols:
        summary_parts.append("Öne çıkanlar: " + ", ".join(symbols) + ".")

    leader_reason = str(leader.get("reason") or "").strip()
    if leader_reason:
        summary_parts.append(f"Lider tema: {leader_reason}")

    return " ".join(summary_parts).strip()


def build_market_overview_payload(
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None,
    top_n: int = 5,
) -> dict[str, Any]:
    ranked = rank_scan_candidates(scan_results or [], top_n=top_n)
    text = build_market_overview_brief(scan_results, top_n=top_n)
    return {
        "text": text,
        "leader": ranked.get("leader"),
        "symbols": list(ranked.get("symbols") or []),
        "count": int(ranked.get("count") or 0),
    }
