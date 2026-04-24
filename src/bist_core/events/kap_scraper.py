"""KAP Scraper — fetch and parse BIST corporate disclosures from kap.org.tr.

Two modes:
  OFFLINE (default): Parse local HTML files from data_dir. No network.
  ONLINE (guarded):  HTTP fetch from kap.org.tr. Requires BIST_KAP_ENABLED=1.

Converts KAP disclosures to EventRecord format for the event engine pipeline.
Uses kap_ingest.py for HTML table parsing (deterministic, no network).

Security:
  - Online mode OFF by default (AGENTS.md: no network unless guarded)
  - Input sanitized (HTML, encoding)
  - Fail-closed on errors
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final, Sequence

from bist_core.events.event_types import EventRecord, EventType
from bist_core.events.kap_ingest import ingest_kap_html
from bist_core.events.provider_base import EventDataProvider

_TRT: Final = timezone(timedelta(hours=3))

# KAP "kind" field → canonical EventType mapping
_KIND_MAP: Final[dict[str, EventType]] = {
    # Turkish
    "finansal rapor": EventType.EARNINGS,
    "bilanço": EventType.EARNINGS,
    "gelir tablosu": EventType.EARNINGS,
    "temettü": EventType.DIVIDEND,
    "kar dağıtım": EventType.DIVIDEND,
    "pay geri alım": EventType.BUYBACK,
    "geri alım": EventType.BUYBACK,
    "özel durum": EventType.GENERAL_DISCLOSURE,
    "yönetim": EventType.MANAGEMENT,
    "ortaklık": EventType.PARTNERSHIP,
    "sözleşme": EventType.CONTRACT,
    "yatırım": EventType.INVESTMENT,
    "kapasite": EventType.CAPACITY,
    "sermaye": EventType.GENERAL_DISCLOSURE,
    "mevzuat": EventType.REGULATORY,
    "bağımsız denetim": EventType.GENERAL_DISCLOSURE,
    "genel kurul": EventType.GENERAL_DISCLOSURE,
    # English
    "financial report": EventType.EARNINGS,
    "dividend": EventType.DIVIDEND,
    "buyback": EventType.BUYBACK,
    "contract": EventType.CONTRACT,
    "investment": EventType.INVESTMENT,
    "management": EventType.MANAGEMENT,
    "partnership": EventType.PARTNERSHIP,
    "regulatory": EventType.REGULATORY,
}


def _classify_kind(kind: str) -> EventType:
    """Map KAP disclosure kind to canonical EventType."""
    kind_lower = kind.lower()
    for keyword, event_type in _KIND_MAP.items():
        if keyword in kind_lower:
            return event_type
    return EventType.GENERAL_DISCLOSURE


def _iso_to_unix(iso_str: str) -> int:
    """Convert ISO timestamp string to Unix seconds (TRT)."""
    if not iso_str:
        return 0
    try:
        # kap_ingest normalizes to "%Y-%m-%dT%H:%M:%SZ"
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        return 0


def _kap_events_to_records(
    kap_data: dict,
    symbols: set[str],
    start_ts: int,
    end_ts: int,
) -> list[EventRecord]:
    """Convert kap_ingest output dict to list[EventRecord]."""
    records: list[EventRecord] = []

    for ev in kap_data.get("events", []):
        sym = ev.get("symbol", "").upper()
        if symbols and sym not in symbols:
            continue

        ts = _iso_to_unix(ev.get("ts", ""))
        if ts == 0 or ts < start_ts or ts > end_ts:
            continue

        kind = ev.get("kind", "")
        event_type = _classify_kind(kind)
        headline = ev.get("title", "")
        raw_id = ev.get("id", "")

        records.append(EventRecord(
            symbol=sym,
            timestamp=ts,
            event_type=event_type,
            headline=headline,
            source="kap",
            raw_id=raw_id,
        ))

    return records


class KAPScraper(EventDataProvider):
    """KAP disclosure scraper — offline (default) + online (guarded) modes.

    Offline: reads HTML files from data_dir (e.g., pre-downloaded KAP pages).
    Online: fetches from kap.org.tr (requires BIST_KAP_ENABLED=1 env var).

    Usage (offline):
        scraper = KAPScraper(data_dir=Path("data/kap_html"))
        events = scraper.fetch_events(["ASELS"], start_ts, end_ts)

    Usage (online, guarded):
        os.environ["BIST_KAP_ENABLED"] = "1"
        scraper = KAPScraper()
        events = scraper.fetch_events(["ASELS"], start_ts, end_ts)
    """

    def __init__(
        self,
        data_dir: Path | None = None,
        base_url: str = "https://www.kap.org.tr/tr/bildirim-sorgu",
    ) -> None:
        self._data_dir = data_dir
        self._base_url = base_url
        self._enabled = os.environ.get("BIST_KAP_ENABLED", "0") == "1"

    def provider_name(self) -> str:
        return "kap_scraper"

    def fetch_events(
        self,
        symbols: Sequence[str],
        start_ts: int,
        end_ts: int,
    ) -> list[EventRecord]:
        symbols_set = {s.upper() for s in symbols}
        events: list[EventRecord] = []

        # Offline mode: parse local HTML files
        if self._data_dir is not None and self._data_dir.exists():
            for html_file in sorted(self._data_dir.glob("*.html")):
                kap_data = ingest_kap_html(html_file)
                records = _kap_events_to_records(kap_data, symbols_set, start_ts, end_ts)
                events.extend(records)

        # Online mode: fetch from KAP (guarded)
        if self._enabled:
            for symbol in symbols:
                fetched = self._fetch_online(symbol, start_ts, end_ts, symbols_set)
                events.extend(fetched)

        return events

    def _fetch_online(
        self,
        symbol: str,
        start_ts: int,
        end_ts: int,
        symbols_set: set[str],
    ) -> list[EventRecord]:
        """Fetch disclosures from kap.org.tr. Guarded: BIST_KAP_ENABLED=1 required."""
        if not self._enabled:
            return []

        import urllib.parse
        import urllib.request

        start_dt = datetime.fromtimestamp(start_ts, tz=_TRT)
        end_dt = datetime.fromtimestamp(end_ts, tz=_TRT)

        params = urllib.parse.urlencode({
            "fromDate": start_dt.strftime("%Y-%m-%d"),
            "toDate": end_dt.strftime("%Y-%m-%d"),
            "member": symbol,
        })
        url = f"{self._base_url}?{params}"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "BIST-Elite-Core/1.0"},
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                html = response.read()

            kap_data = ingest_kap_html(html, source=f"kap_online_{symbol}")
            return _kap_events_to_records(kap_data, symbols_set, start_ts, end_ts)
        except Exception:
            # Fail-closed: network error → empty list, never crash
            return []
