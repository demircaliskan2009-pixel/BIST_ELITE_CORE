from __future__ import annotations

from typing import Any

from .base import DisclosureRecord


def _pick(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def normalize_kap_item(raw: dict[str, Any]) -> DisclosureRecord:
    disclosure_id = _pick(raw, "disclosureId", "disclosure_id", "id", "kapId")
    symbol = _pick(raw, "stockCode", "symbol", "ticker", "code")
    title = _pick(raw, "title", "headline", "subject")
    published_at = _pick(raw, "publishedAt", "publishDate", "date", "disclosureTime")
    url = _pick(raw, "url", "detailUrl", "detailURL")
    category = _pick(raw, "category", "topic", "type")

    if disclosure_id in (None, ""):
        raise ValueError("KAP disclosure item missing disclosure id")
    if title in (None, ""):
        raise ValueError("KAP disclosure item missing title")
    if published_at in (None, ""):
        raise ValueError("KAP disclosure item missing published_at")

    normalized_symbol = None if symbol in (None, "") else str(symbol).strip().upper()

    return DisclosureRecord(
        provider_name="kap",
        disclosure_id=str(disclosure_id),
        symbol=normalized_symbol,
        title=str(title),
        published_at=str(published_at),
        url=None if url in (None, "") else str(url),
        category=None if category in (None, "") else str(category).strip().upper(),
    )


def normalize_kap_items(items: list[dict[str, Any]]) -> list[DisclosureRecord]:
    return [normalize_kap_item(item) for item in items]
