"""Rule-based KAP headline classifier — deterministic, fail-closed."""

from __future__ import annotations

from typing import Any

# Priority order: first matching category wins (risk before neutral categories).
_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("risk", ("ceza", "dava", "iptal")),
    ("bonus_issue", ("bedelsiz",)),
    ("buyback", ("geri alım", "geri alim")),
    ("dividend", ("temettü", "temettu")),
    ("earnings", ("finansal", "bilanço", "bilanco")),
    ("contract", ("ihale", "sözleşme", "sozlesme")),
)

EVENT_STRENGTH: dict[str, float] = {
    "bonus_issue": 1.5,
    "buyback": 1.3,
    "contract": 1.2,
    "earnings": 1.1,
    "dividend": 1.0,
    "risk": -1.5,
}


def classify_kap_event(item: dict[str, Any]) -> dict[str, Any] | None:
    """
    Classify a KAP RSS item by title keywords (case-insensitive).

    Returns ``None`` if symbol/timestamp invalid or no keyword match.
    Output: symbol, event_type, strength, timestamp.
    """
    if not isinstance(item, dict):
        return None

    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        return None

    sym = str(item.get("symbol", "")).strip().upper()
    if not sym:
        return None

    try:
        ts = int(item["timestamp"])
    except (KeyError, TypeError, ValueError):
        return None
    if ts <= 0:
        return None

    hay = title.casefold()

    for event_type, keywords in _CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw.casefold() in hay:
                strength = float(EVENT_STRENGTH.get(event_type, 0.0))
                return {
                    "symbol": sym,
                    "event_type": event_type,
                    "strength": strength,
                    "timestamp": ts,
                }
    return None


__all__ = ["classify_kap_event", "EVENT_STRENGTH"]
