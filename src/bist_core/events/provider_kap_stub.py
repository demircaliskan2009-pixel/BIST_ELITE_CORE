"""KAP Scraper Provider — STUB ONLY, OFF by default.

This provider is designed for future integration with KAP (Public Disclosure
Platform / Kamuyu Aydinlatma Platformu) for real-time event data.

CURRENTLY: Non-functional stub. Always returns empty list.
ACTIVATION: Set environment variable BIST_KAP_ENABLED=1

When implemented, this will:
  - Scrape KAP disclosures for given symbols
  - Parse HTML/JSON responses into EventRecord format
  - Cache locally to avoid repeated requests
  - Respect rate limits
"""

from __future__ import annotations

import os
from typing import Sequence

from bist_core.events.event_types import EventRecord
from bist_core.events.provider_base import EventDataProvider


class KAPScraperProvider(EventDataProvider):
    """KAP disclosure scraper — STUB, OFF by default.

    Guarded by BIST_KAP_ENABLED env var. Returns empty when disabled.
    """

    def __init__(self) -> None:
        self._enabled = os.environ.get("BIST_KAP_ENABLED", "0") == "1"

    def fetch_events(
        self,
        symbols: Sequence[str],
        start_ts: int,
        end_ts: int,
    ) -> list[EventRecord]:
        """STUB: Returns empty. Future: fetch from KAP."""
        if not self._enabled:
            return []
        # Future implementation:
        # 1. Query KAP API/HTML for each symbol
        # 2. Parse response into EventRecord
        # 3. Cache to local file for idempotency
        # 4. Return sorted by timestamp
        return []

    def provider_name(self) -> str:
        return "kap_scraper"


__all__ = ["KAPScraperProvider"]
