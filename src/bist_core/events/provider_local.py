"""Local File Event Provider — reads events from CSV/JSON files.

Supports two formats:
  1. CSV with columns: symbol, timestamp, event_type, headline
  2. JSON array of objects with the same fields

Files are loaded once at construction and cached. No network access.
Drop event files into data/events/ for automatic discovery.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Sequence

from bist_core.events.event_types import EventRecord, EventType
from bist_core.events.provider_base import EventDataProvider


def _parse_event_type(raw: str) -> EventType:
    """Map raw event type string to canonical EventType."""
    raw_lower = raw.strip().lower()
    mapping = {
        "earnings": EventType.EARNINGS,
        "kazanc": EventType.EARNINGS,
        "finansal": EventType.EARNINGS,
        "dividend": EventType.DIVIDEND,
        "temettü": EventType.DIVIDEND,
        "kar payi": EventType.DIVIDEND,
        "buyback": EventType.BUYBACK,
        "geri alim": EventType.BUYBACK,
        "contract": EventType.CONTRACT,
        "sözleşme": EventType.CONTRACT,
        "ihale": EventType.CONTRACT,
        "investment": EventType.INVESTMENT,
        "yatirim": EventType.INVESTMENT,
        "capacity": EventType.CAPACITY,
        "kapasite": EventType.CAPACITY,
        "partnership": EventType.PARTNERSHIP,
        "ortaklik": EventType.PARTNERSHIP,
        "management": EventType.MANAGEMENT,
        "yönetim": EventType.MANAGEMENT,
        "regulatory": EventType.REGULATORY,
        "düzenleyici": EventType.REGULATORY,
        "spk": EventType.REGULATORY,
        "genel": EventType.GENERAL_DISCLOSURE,
        "özel durum": EventType.GENERAL_DISCLOSURE,
        "disclosure": EventType.GENERAL_DISCLOSURE,
    }
    for key, val in mapping.items():
        if key in raw_lower:
            return val
    return EventType.UNKNOWN


def _make_event_id(symbol: str, ts: int, headline: str) -> str:
    """Deterministic ID for dedup."""
    canonical = f"{symbol}\t{ts}\t{headline}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class LocalFileEventProvider(EventDataProvider):
    """Read events from local CSV/JSON files.

    Usage:
        provider = LocalFileEventProvider(Path("data/events"))
        events = provider.fetch_events(["AKBNK"], start_ts, end_ts)

    CSV format: symbol,timestamp,event_type,headline
    JSON format: [{"symbol":"AKBNK","timestamp":1234,"event_type":"earnings","headline":"..."}]
    """

    def __init__(self, data_dir: Path | str) -> None:
        self._data_dir = Path(data_dir)
        self._events: list[EventRecord] = []
        self._loaded = False

    def _load(self) -> None:
        """Load all event files from data directory."""
        if self._loaded:
            return
        self._loaded = True

        if not self._data_dir.exists():
            return

        events: list[EventRecord] = []

        # Load CSV files
        for csv_path in sorted(self._data_dir.glob("*.csv")):
            try:
                events.extend(self._load_csv(csv_path))
            except Exception:
                continue

        # Load JSON files
        for json_path in sorted(self._data_dir.glob("*.json")):
            try:
                events.extend(self._load_json(json_path))
            except Exception:
                continue

        # Dedup by raw_id
        seen: set[str] = set()
        deduped: list[EventRecord] = []
        for ev in events:
            if ev.raw_id not in seen:
                seen.add(ev.raw_id)
                deduped.append(ev)

        deduped.sort(key=lambda e: (e.timestamp, e.symbol))
        self._events = deduped

    def _load_csv(self, path: Path) -> list[EventRecord]:
        """Parse a CSV event file."""
        records: list[EventRecord] = []
        with path.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = (row.get("symbol") or "").strip().upper()
                ts_raw = (row.get("timestamp") or "").strip()
                etype_raw = row.get("event_type") or ""
                headline = (row.get("headline") or "").strip()

                if not sym or not ts_raw or not headline:
                    continue
                try:
                    ts = int(float(ts_raw))
                except (ValueError, TypeError):
                    continue

                etype = _parse_event_type(etype_raw)
                raw_id = _make_event_id(sym, ts, headline)
                records.append(EventRecord(
                    symbol=sym,
                    timestamp=ts,
                    event_type=etype,
                    headline=headline,
                    source="local_csv",
                    raw_id=raw_id,
                ))
        return records

    def _load_json(self, path: Path) -> list[EventRecord]:
        """Parse a JSON event file."""
        records: list[EventRecord] = []
        data = json.loads(path.read_text(encoding="utf-8"))

        # Support both flat array and {events: [...]} format
        items = data if isinstance(data, list) else data.get("events", [])
        for item in items:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("symbol", "")).strip().upper()
            ts_raw = item.get("timestamp") or item.get("ts", 0)
            headline = str(item.get("headline") or item.get("title", "")).strip()
            etype_raw = str(item.get("event_type") or item.get("kind", ""))

            if not sym or not headline:
                continue
            try:
                ts = int(float(str(ts_raw)))
            except (ValueError, TypeError):
                continue

            etype = _parse_event_type(etype_raw)
            raw_id = _make_event_id(sym, ts, headline)
            records.append(EventRecord(
                symbol=sym,
                timestamp=ts,
                event_type=etype,
                headline=headline,
                source="local_json",
                raw_id=raw_id,
            ))
        return records

    def fetch_events(
        self,
        symbols: Sequence[str],
        start_ts: int,
        end_ts: int,
    ) -> list[EventRecord]:
        """Return events within time range for the requested symbols."""
        self._load()
        sym_set = set(s.upper() for s in symbols)
        return [
            ev
            for ev in self._events
            if ev.symbol in sym_set and start_ts <= ev.timestamp <= end_ts
        ]

    def provider_name(self) -> str:
        return "local_file"


__all__ = ["LocalFileEventProvider"]
