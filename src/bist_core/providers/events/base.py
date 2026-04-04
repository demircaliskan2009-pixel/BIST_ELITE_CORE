from __future__ import annotations

from typing import Protocol


class EventsProvider(Protocol):
    def fetch_events_for_day(self, day: str) -> list[dict]:
        """Return raw event dicts (symbol, ts, kind, title, optional url)."""
        raise NotImplementedError
