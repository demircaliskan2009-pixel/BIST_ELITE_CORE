from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bist_core.services.live_entry_overlay import augment_result_with_live_entry_context


_DECISION_KEYS = ("decision", "action", "signal", "verdict")
_SCORE_KEYS = ("score", "rank_score", "composite_score", "normalized_score", "final_score")
_ENTRY_KEYS = ("entry", "entry_price", "suggested_entry", "entry_level", "buy_below", "plan_entry")
_STOP_KEYS = ("stop", "stop_loss", "invalidation", "invalid_below")
_TARGET_KEYS = ("target", "hedef", "take_profit", "tp", "first_target")
_REASON_KEYS = ("compact_rationale", "rationale", "summary", "text", "live_entry_text")


def _as_float(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _pick_first(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def build_single_symbol_brief(
    result: Mapping[str, Any] | dict[str, Any] | None,
    live_payload: Mapping[str, Any] | dict[str, Any] | None = None,
) -> str:
    if not isinstance(result, Mapping):
        return ""

    enriched = augment_result_with_live_entry_context(result, live_payload)
    symbol = str(enriched.get("symbol") or enriched.get("ticker") or "").upper().strip()
    if not symbol:
        return ""

    decision = _pick_first(enriched, _DECISION_KEYS)
    score = _as_float(_pick_first(enriched, _SCORE_KEYS))
    entry = _as_float(_pick_first(enriched, _ENTRY_KEYS))
    stop = _as_float(_pick_first(enriched, _STOP_KEYS))
    target = _as_float(_pick_first(enriched, _TARGET_KEYS))
    reason = _pick_first(enriched, _REASON_KEYS)
    live_text = enriched.get("live_entry_text")

    head_bits: list[str] = [symbol]
    if decision is not None:
        head_bits.append(f"karar={decision}")
    if score is not None:
        head_bits.append(f"score={score:.2f}")

    level_bits: list[str] = []
    if entry is not None:
        level_bits.append(f"giriş={entry:.2f}")
    if stop is not None:
        level_bits.append(f"stop={stop:.2f}")
    if target is not None:
        level_bits.append(f"hedef={target:.2f}")

    sentences: list[str] = [" | ".join(head_bits) + "."]
    if level_bits:
        sentences.append(" | ".join(level_bits) + ".")

    if reason:
        reason_text = str(reason).strip()
        if reason_text:
            if reason_text.endswith((".", "!", "?")):
                sentences.append(reason_text)
            else:
                sentences.append(reason_text + ".")

    if live_text:
        live_text = str(live_text).strip()
        if live_text and live_text not in " ".join(sentences):
            if live_text.endswith((".", "!", "?")):
                sentences.append(live_text)
            else:
                sentences.append(live_text + ".")

    return " ".join(x.strip() for x in sentences if x.strip()).strip()
