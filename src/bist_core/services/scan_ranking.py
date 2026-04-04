from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


_DECISION_WEIGHT = {
    "strong_buy": 5,
    "buy": 4,
    "accumulate": 4,
    "watch": 3,
    "hold": 2,
    "reduce": 1,
    "avoid": 0,
    "sell": 0,
}


_SCORE_KEYS = (
    "score",
    "rank_score",
    "composite_score",
    "normalized_score",
    "final_score",
)


_DECISION_KEYS = (
    "decision",
    "action",
    "signal",
    "verdict",
)


_REASON_KEYS = (
    "live_entry_text",
    "compact_rationale",
    "rationale",
    "summary",
    "text",
)


def _as_float(value: Any, digits: int = 4) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "evet"}
    return bool(value)


def _pick_first(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _decision_weight(value: Any) -> int:
    if value is None:
        return -1
    token = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return _DECISION_WEIGHT.get(token, -1)


def _entry_status_label(item: Mapping[str, Any]) -> str:
    if item.get("entry_missed"):
        return "giriş kaçmış"
    if item.get("is_discount_to_entry"):
        return "girişe göre indirimli"
    if item.get("should_wait_pullback"):
        return "geri çekilme beklenmeli"
    return "giriş durumu nötr"


def _entry_status_rank(item: Mapping[str, Any]) -> int:
    if item.get("entry_missed"):
        return 0
    if item.get("should_wait_pullback"):
        return 1
    if item.get("is_discount_to_entry"):
        return 3
    return 2


def _format_optional_pct(value: Any) -> str:
    num = _as_float(value, digits=2)
    if num is None:
        return "n/a"
    return f"{num:+.2f}%"


def normalize_scan_candidate(result: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    symbol = str(result.get("symbol") or result.get("ticker") or "").upper().strip()
    score = _as_float(_pick_first(result, _SCORE_KEYS))
    decision = _pick_first(result, _DECISION_KEYS)
    entry_missed = _as_bool(result.get("entry_missed"))
    should_wait_pullback = _as_bool(result.get("should_wait_pullback"))
    is_discount_to_entry = _as_bool(result.get("is_discount_to_entry"))
    live_gap_pct = _as_float(result.get("live_gap_pct"))
    reason = _pick_first(result, _REASON_KEYS)

    row: dict[str, Any] = {
        "symbol": symbol,
        "score": score if score is not None else -999999.0,
        "raw_score": score,
        "decision": decision,
        "decision_weight": _decision_weight(decision),
        "entry_missed": entry_missed,
        "should_wait_pullback": should_wait_pullback,
        "is_discount_to_entry": is_discount_to_entry,
        "live_gap_pct": live_gap_pct,
        "reason": str(reason).strip() if reason is not None else "",
        "source": dict(result),
    }
    current_close = result.get("current_close") or result.get("close")
    if current_close is not None:
        row["current_close"] = current_close
        if "current_close_source" not in row:
            row["current_close_source"] = "snapshot"
    return row


def _scan_sort_key(item: Mapping[str, Any]) -> tuple[float, int, int, int, float, str]:
    gap = item.get("live_gap_pct")
    gap_for_sort = float(gap) if gap is not None else 0.0
    return (
        float(item["score"]),
        int(item["decision_weight"]),
        1 if not item["entry_missed"] else 0,
        1 if item["is_discount_to_entry"] else 0,
        -abs(gap_for_sort),
        str(item["symbol"]),
    )


def _build_scan_breakdown(leader: Mapping[str, Any], runner_up: Mapping[str, Any]) -> dict[str, Any]:
    leader_symbol = str(leader["symbol"])
    runner_symbol = str(runner_up["symbol"])

    leader_score = float(leader["score"])
    runner_score = float(runner_up["score"])
    lead_gap = round(leader_score - runner_score, 4)

    leader_reasons: list[str] = []
    runner_reasons: list[str] = []
    factor_rows: list[str] = [
        f"skor | {leader_symbol}={leader_score:.2f} | {runner_symbol}={runner_score:.2f} | fark={lead_gap:+.2f}"
    ]

    if leader_score > runner_score:
        leader_reasons.append(f"skor üstün ({leader_score:.2f} > {runner_score:.2f})")
        runner_reasons.append(f"skor geride ({runner_score:.2f} < {leader_score:.2f})")

    leader_decision = str(leader["decision"]).strip() if leader.get("decision") is not None else "n/a"
    runner_decision = str(runner_up["decision"]).strip() if runner_up.get("decision") is not None else "n/a"
    factor_rows.append(f"karar | {leader_symbol}={leader_decision} | {runner_symbol}={runner_decision}")

    leader_dw = int(leader["decision_weight"])
    runner_dw = int(runner_up["decision_weight"])
    if leader_dw > runner_dw:
        leader_reasons.append(f"karar katmanı daha güçlü ({leader_decision} > {runner_decision})")
        runner_reasons.append(f"karar katmanı daha zayıf ({runner_decision} < {leader_decision})")

    leader_entry_label = _entry_status_label(leader)
    runner_entry_label = _entry_status_label(runner_up)
    factor_rows.append(f"giriş durumu | {leader_symbol}={leader_entry_label} | {runner_symbol}={runner_entry_label}")

    leader_entry_rank = _entry_status_rank(leader)
    runner_entry_rank = _entry_status_rank(runner_up)
    if leader_entry_rank > runner_entry_rank:
        leader_reasons.append(f"canlı giriş konumu daha avantajlı ({leader_entry_label})")
        runner_reasons.append(f"canlı giriş konumu daha zayıf ({runner_entry_label})")

    leader_gap = leader.get("live_gap_pct")
    runner_gap = runner_up.get("live_gap_pct")
    if leader_gap is not None or runner_gap is not None:
        factor_rows.append(
            f"canlı giriş farkı | {leader_symbol}={_format_optional_pct(leader_gap)} | {runner_symbol}={_format_optional_pct(runner_gap)}"
        )

    if leader_gap is not None and runner_gap is not None:
        if abs(float(leader_gap)) < abs(float(runner_gap)):
            leader_reasons.append(
                f"canlı fiyat giriş referansına daha yakın ({float(leader_gap):+.2f}% vs {float(runner_gap):+.2f}%)"
            )
            runner_reasons.append(
                f"canlı fiyat giriş referansından daha uzak ({float(runner_gap):+.2f}% vs {float(leader_gap):+.2f}%)"
            )

    if not leader_reasons:
        leader_reasons.append("toplam skor ve tie-break katmanlarında önde")
    if not runner_reasons:
        runner_reasons.append("toplam skor ve tie-break katmanlarında geride")

    return {
        "leader_symbol": leader_symbol,
        "runner_symbol": runner_symbol,
        "lead_gap": lead_gap,
        "leader_reasons": leader_reasons,
        "runner_reasons": runner_reasons,
        "factor_rows": factor_rows,
        "leader_reason_text": leader.get("reason") or "",
        "runner_reason_text": runner_up.get("reason") or "",
    }


def rank_scan_candidates(
    results: Sequence[Mapping[str, Any] | dict[str, Any]],
    top_n: int | None = None,
) -> dict[str, Any]:
    normalized = [normalize_scan_candidate(x) for x in results if isinstance(x, Mapping)]
    normalized = [x for x in normalized if x["symbol"]]
    ranked: list[dict[str, Any]] = []
    for row in normalized:
        if "current_close" in row and "current_close_source" not in row:
            row["current_close_source"] = "snapshot"
        ranked.append(row)
    ranked = sorted(ranked, key=_scan_sort_key, reverse=True)

    if top_n is not None:
        try:
            n = int(top_n)
        except (TypeError, ValueError):
            n = 0
        ranked = ranked[: max(n, 0)]

    if not ranked:
        return {
            "leader": None,
            "runner_up": None,
            "ranked": [],
            "symbols": [],
            "summary": "",
            "count": 0,
            "breakdown": None,
        }

    leader = ranked[0]
    symbols = [x["symbol"] for x in ranked]

    if len(ranked) == 1:
        summary = f"{leader['symbol']} lider; tek geçerli aday mevcut."
        breakdown = None
    else:
        runner_up = ranked[1]
        lead_gap = round(float(leader["score"]) - float(runner_up["score"]), 4)
        status_bits: list[str] = []
        if leader["entry_missed"]:
            status_bits.append("giriş kaçmış")
        elif leader["is_discount_to_entry"]:
            status_bits.append("girişe göre indirimli")
        elif leader["should_wait_pullback"]:
            status_bits.append("geri çekilme beklenmeli")
        if leader["decision"] is not None:
            status_bits.append(f"karar={leader['decision']}")
        status_text = ", ".join(status_bits) if status_bits else "lider görünüm"
        summary = f"{leader['symbol']} lider; skor farkı {lead_gap:+.2f}. {status_text}."
        breakdown = _build_scan_breakdown(leader, runner_up)

    return {
        "leader": leader,
        "runner_up": ranked[1] if len(ranked) >= 2 else None,
        "ranked": ranked,
        "symbols": symbols,
        "summary": summary,
        "count": len(ranked),
        "breakdown": breakdown,
    }


def render_scan_ranking_text(
    results: Sequence[Mapping[str, Any] | dict[str, Any]],
    top_n: int | None = None,
) -> str:
    ranked = rank_scan_candidates(results, top_n=top_n)
    if not ranked["ranked"]:
        return "Sıralanacak geçerli aday yok."

    lines = [ranked["summary"]]
    breakdown = ranked.get("breakdown")

    if ranked["count"] >= 2 and breakdown is not None:
        lines.append("")
        lines.append(f"Neden {breakdown['leader_symbol']} lider:")
        for item in breakdown["leader_reasons"]:
            lines.append(f"- {item}")

        lines.append("")
        lines.append("Rakip baskısı:")
        for item in breakdown["runner_reasons"]:
            lines.append(f"- {item}")

        lines.append("")
        lines.append("Faktör farkları:")
        for row in breakdown["factor_rows"]:
            lines.append(f"- {row}")

    lines.append("")
    lines.append("Sıralama:")
    for idx, item in enumerate(ranked["ranked"], start=1):
        tail_bits: list[str] = [f"score={item['score']:.2f}"]
        if item["decision"] is not None:
            tail_bits.append(f"karar={item['decision']}")
        if item["entry_missed"]:
            tail_bits.append("giriş kaçmış")
        elif item["is_discount_to_entry"]:
            tail_bits.append("indirimli")
        elif item["should_wait_pullback"]:
            tail_bits.append("geri çekilme")
        lines.append(f"{idx}) {item['symbol']} | " + " | ".join(tail_bits))

    leader_reason = ranked["leader"].get("reason") if ranked["leader"] else ""
    if leader_reason:
        lines.append(f"Lider notu: {leader_reason}")

    if ranked["count"] >= 2 and breakdown is not None and breakdown["runner_reason_text"]:
        lines.append(f"Yakın rakip notu: {breakdown['runner_reason_text']}")

    return "\n".join(lines).strip()





