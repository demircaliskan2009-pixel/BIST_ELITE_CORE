from __future__ import annotations

import re

from collections.abc import Mapping
from typing import Any


def _as_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out <= 0:
        return None
    return out


def _pick_live_price(payload: Mapping[str, Any]) -> float | None:
    for key in ("current_price", "last_price", "price", "close", "last"):
        value = _as_float(payload.get(key))
        if value is not None:
            return value
    return None


def _pick_reference_price(advice: Mapping[str, Any]) -> float | None:
    for key in ("entry", "target", "stop"):
        value = _as_float(advice.get(key))
        if value is not None:
            return value

    refs = [
        _as_float(advice.get("entry")),
        _as_float(advice.get("stop")),
        _as_float(advice.get("target")),
    ]
    refs = [x for x in refs if x is not None]
    if not refs:
        return None
    return sum(refs) / len(refs)


def sanitize_live_payload_for_chat(
    advice_like: Mapping[str, Any] | dict[str, Any] | None,
    *,
    min_ratio: float = 0.40,
    max_ratio: float = 2.50,
) -> dict[str, Any]:
    out = dict(advice_like) if isinstance(advice_like, Mapping) else {}
    live_payload = out.get("live_payload")
    if not isinstance(live_payload, Mapping):
        return out

    live_price = _pick_live_price(live_payload)
    reference_price = _pick_reference_price(out)
    if live_price is None or reference_price is None:
        return out

    ratio = live_price / reference_price
    suspicious = ratio < min_ratio or ratio > max_ratio

    if not suspicious:
        out["live_price_sanity"] = {
            "ok": True,
            "reason": "",
            "live_price": live_price,
            "reference_price": reference_price,
            "ratio": ratio,
        }
        return out

    out.pop("live_payload", None)
    out.pop("live_gap_pct", None)
    out.pop("live_entry_status", None)
    out.pop("live_entry_text", None)
    out["live_price_sanity"] = {
        "ok": False,
        "reason": "live_price_out_of_band",
        "live_price": live_price,
        "reference_price": reference_price,
        "ratio": ratio,
    }
    return out


_GAP_PCT_RE = re.compile(r"entry gap\s*([+-]?\d+(?:\.\d+)?)%", re.IGNORECASE)
_LIVE_TEXT_PATTERNS = [
    re.compile(r"\s*Canlı bağlam:.*?(?=(?:\n\n|$))", re.DOTALL),
    re.compile(r"\s*Canlı fiyat[^\n]*", re.DOTALL),
    re.compile(r"\s*entry gap\s*[+-]?\d+(?:\.\d+)?%\.?"),
    re.compile(r"\s*Canlı/EOD farkı\s*[+-]?\d+(?:\.\d+)?%\.?"),
]


def _extract_gap_pct_from_text(text: str) -> float | None:
    match = _GAP_PCT_RE.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except (TypeError, ValueError):
        return None


def _extract_structural_entry_gap_pct(payload: Mapping[str, Any] | dict[str, Any] | None) -> float | None:
    raw = dict(payload) if isinstance(payload, Mapping) else {}

    for parent_key in ("plan", "signals"):
        parent = raw.get(parent_key)
        if isinstance(parent, Mapping):
            value = parent.get("entry_gap_pct")
            try:
                if value is not None:
                    return float(value)
            except (TypeError, ValueError):
                pass

    value = raw.get("entry_gap_pct")
    try:
        if value is not None:
            return float(value)
    except (TypeError, ValueError):
        pass

    return None


def sanitize_live_text_for_chat(
    text: Any,
    *,
    max_abs_gap_pct: float = 250.0,
) -> str:
    raw = "" if text is None else str(text)
    if not raw.strip():
        return raw

    gap_pct = _extract_gap_pct_from_text(raw)
    suspicious = gap_pct is not None and abs(gap_pct) > max_abs_gap_pct
    if not suspicious:
        return raw

    cleaned = raw
    for pattern in _LIVE_TEXT_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    note = "Canlı veri ölçek tutarsızlığı nedeniyle canlı bağlam gizlendi."

    if not cleaned:
        return note
    if note not in cleaned:
        cleaned = f"{cleaned}\n\n{note}"
    return cleaned


def sanitize_chat_result_live_text(
    result: Mapping[str, Any] | dict[str, Any] | None,
    *,
    max_abs_gap_pct: float = 250.0,
) -> dict[str, Any]:
    out = dict(result) if isinstance(result, Mapping) else {}
    live_ctx = dict(out.get("live_context_meta") or {})
    suppression_triggered = bool(live_ctx.get("suppressed"))
    suppression_reason = str(live_ctx.get("suppression_reason") or "")
    payload_reason = suppression_reason == "live_price_out_of_band"

    for key in ("text", "preview"):
        if out.get(key) is not None:
            original = str(out.get(key))
            cleaned = sanitize_live_text_for_chat(
                original,
                max_abs_gap_pct=max_abs_gap_pct,
            )
            if cleaned != original:
                suppression_triggered = True
                if not suppression_reason and not payload_reason:
                    suppression_reason = "suspicious_live_gap_text"
            out[key] = cleaned

    cards = out.get("cards")
    if isinstance(cards, list):
        new_cards: list[Any] = []
        for item in cards:
            if isinstance(item, Mapping):
                card = dict(item)
                for key in ("body", "preview"):
                    if card.get(key) is not None:
                        original = str(card.get(key))
                        cleaned = sanitize_live_text_for_chat(
                            original,
                            max_abs_gap_pct=max_abs_gap_pct,
                        )
                        if cleaned != original:
                            suppression_triggered = True
                            if not suppression_reason:
                                suppression_reason = "suspicious_live_gap_text"
                        card[key] = cleaned
                new_cards.append(card)
            else:
                new_cards.append(item)
        out["cards"] = new_cards

    ui = out.get("ui")
    if isinstance(ui, Mapping):
        ui_dict = dict(ui)
        primary = ui_dict.get("primary_card")
        if isinstance(primary, Mapping):
            primary_card = dict(primary)
            for key in ("body", "preview"):
                if primary_card.get(key) is not None:
                    original = str(primary_card.get(key))
                    cleaned = sanitize_live_text_for_chat(
                        original,
                        max_abs_gap_pct=max_abs_gap_pct,
                    )
                    if cleaned != original:
                        suppression_triggered = True
                        if not suppression_reason:
                            suppression_reason = "suspicious_live_gap_text"
                    primary_card[key] = cleaned
            ui_dict["primary_card"] = primary_card
        out["ui"] = ui_dict

    raw = out.get("raw")
    if isinstance(raw, Mapping):
        raw_dict = dict(raw)
        for key in ("body", "preview", "text"):
            if raw_dict.get(key) is not None:
                original = str(raw_dict.get(key))
                cleaned = sanitize_live_text_for_chat(
                    original,
                    max_abs_gap_pct=max_abs_gap_pct,
                )
                if cleaned != original:
                    suppression_triggered = True
                    if not suppression_reason:
                        suppression_reason = "suspicious_live_gap_text"
                raw_dict[key] = cleaned
        out["raw"] = raw_dict

    live_ctx["suppressed"] = bool(suppression_triggered)
    live_ctx["suppression_reason"] = suppression_reason if suppression_triggered else ""
    out["live_context_meta"] = live_ctx
    return out


def sanitize_advice_payload_for_chat(
    advice_like: Mapping[str, Any] | dict[str, Any] | None,
    *,
    min_ratio: float = 0.40,
    max_ratio: float = 2.50,
    max_abs_gap_pct: float = 250.0,
) -> dict[str, Any]:
    out = sanitize_live_payload_for_chat(
        advice_like,
        min_ratio=min_ratio,
        max_ratio=max_ratio,
    )

    live_ctx = dict(out.get("live_context_meta") or {})
    sanity = dict(out.get("live_price_sanity") or {})
    structural_gap_pct = _extract_structural_entry_gap_pct(out)

    if sanity.get("ok") is False:
        live_ctx["suppressed"] = True
        live_ctx["suppression_reason"] = "live_price_out_of_band"
    elif structural_gap_pct is not None and abs(structural_gap_pct) > max_abs_gap_pct:
        live_ctx["suppressed"] = True
        live_ctx["suppression_reason"] = "live_price_out_of_band"

    text_suppressed = False
    for key in ("text", "summary", "rationale_text", "compact_rationale"):
        if out.get(key) is not None:
            original = str(out.get(key))
            cleaned = sanitize_live_text_for_chat(
                original,
                max_abs_gap_pct=max_abs_gap_pct,
            )
            if cleaned != original:
                text_suppressed = True
            out[key] = cleaned

    if text_suppressed:
        live_ctx["suppressed"] = True
        if not str(live_ctx.get("suppression_reason") or "").strip():
            live_ctx["suppression_reason"] = "suspicious_live_gap_text"

    if "suppressed" not in live_ctx:
        live_ctx["suppressed"] = False
    if not live_ctx["suppressed"]:
        live_ctx["suppression_reason"] = ""

    out["live_context_meta"] = live_ctx
    return out
