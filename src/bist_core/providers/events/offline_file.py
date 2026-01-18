from __future__ import annotations

import json
from pathlib import Path

from bist_core.providers.events.base import EventsProvider


class OfflineFileEventsProvider(EventsProvider):
    name = "offline_file"

    def __init__(self, path: Path) -> None:
        self.path = path

    def fetch_events_for_day(self, day: str) -> list[dict]:
        text = self.path.read_text(encoding="utf-8")
        if self.path.suffix.lower() == ".jsonl":
            rows: list[dict] = []
            for line in text.splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
            return rows
        data = json.loads(text)
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        return []
