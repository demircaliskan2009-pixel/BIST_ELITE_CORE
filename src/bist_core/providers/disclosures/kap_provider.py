from __future__ import annotations

from typing import Any, Sequence

from ..base import FailClosedError
from .base import DisclosureProvider, DisclosureRecord
from .normalize import normalize_kap_items


class KapDisclosureProvider(DisclosureProvider):
    provider_name = "kap"

    def __init__(
        self,
        api_key: str | None,
        base_url: str | None,
        company_filter: Sequence[str] | None = None,
        topic_filter: Sequence[str] | None = None,
    ) -> None:
        self.api_key = None if api_key is None else str(api_key).strip()
        self.base_url = None if base_url is None else str(base_url).strip()
        self.company_filter = sorted({str(x).strip().upper() for x in (company_filter or []) if str(x).strip()})
        self.topic_filter = sorted({str(x).strip().upper() for x in (topic_filter or []) if str(x).strip()})

    def build_recent_request(
        self,
        symbols: Sequence[str] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        runtime_symbols = {str(x).strip().upper() for x in (symbols or []) if str(x).strip()}
        merged_symbols = sorted(set(self.company_filter).union(runtime_symbols))

        safe_limit = max(1, min(int(limit), 250))

        return {
            "provider_name": self.provider_name,
            "ready": bool(self.api_key and self.base_url),
            "base_url": self.base_url,
            "headers": {
                "X-API-Key": "***configured***" if self.api_key else None,
            },
            "params": {
                "limit": safe_limit,
                "symbols": merged_symbols or None,
                "topics": self.topic_filter or None,
            },
        }

    def recent(
        self,
        symbols: Sequence[str] | None = None,
        limit: int = 50,
    ) -> list[DisclosureRecord]:
        if not self.api_key or not self.base_url:
            raise FailClosedError(
                "KAP disclosure provider selected but BIST_KAP_API_KEY or "
                "BIST_KAP_BASE_URL is missing."
            )

        raise FailClosedError(
            "KAP disclosure provider contract is ready, but live HTTP fetch wiring "
            "is intentionally deferred to the credentials/endpoint package."
        )

    def normalize_items(self, items: list[dict[str, Any]]) -> list[DisclosureRecord]:
        return normalize_kap_items(items)
