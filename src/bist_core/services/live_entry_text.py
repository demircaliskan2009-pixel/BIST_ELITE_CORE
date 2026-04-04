from __future__ import annotations

from typing import Any

from bist_core.services.live_price_logic import classify_live_entry_status


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "?"
    return f"{value:+.2f}%"


def build_live_entry_context(
    entry_price: float | int | None,
    payload_or_price: dict[str, Any] | float | int | None,
) -> dict[str, Any]:
    status = classify_live_entry_status(entry_price, payload_or_price)
    gap_text = _fmt_pct(status.get("gap_pct"))
    state = status.get("status")

    if state == "extended_above_entry":
        text = f"Canlı fiyat girişin {gap_text} üzerinde; giriş kaçmış görünüyor, geri çekilme beklenmeli."
    elif state == "slightly_above_entry":
        text = f"Canlı fiyat girişin {gap_text} üzerinde; girişin bir miktar üstünde."
    elif state == "below_entry_discount":
        text = f"Canlı fiyat girişin {gap_text} altında; girişe göre daha indirimli bölgede."
    elif state == "near_entry":
        text = f"Canlı fiyat girişe çok yakın ({gap_text})."
    else:
        text = ""

    return {
        **status,
        "gap_text": gap_text,
        "text": text,
        "has_live_commentary": bool(text),
    }


def build_live_entry_text(
    entry_price: float | int | None,
    payload_or_price: dict[str, Any] | float | int | None,
) -> str:
    return build_live_entry_context(entry_price, payload_or_price)["text"]


def append_live_entry_text(
    base_text: str,
    entry_price: float | int | None,
    payload_or_price: dict[str, Any] | float | int | None,
) -> str:
    base = (base_text or "").strip()
    live_text = build_live_entry_text(entry_price, payload_or_price).strip()

    if not live_text:
        return base
    if not base:
        return live_text
    if base.endswith((".", "!", "?")):
        return f"{base} {live_text}"
    return f"{base}. {live_text}"
