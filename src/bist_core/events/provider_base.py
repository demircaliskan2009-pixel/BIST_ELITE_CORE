"""Event Data Provider — Abstract base and provider registry.

Defines the plugin-ready provider interface. Concrete implementations:
  - LocalFileEventProvider: reads from local CSV/JSON files
  - SyntheticBISTEventProvider: generates deterministic backtest events
  - KAPScraperProvider: stub (OFF by default, guarded by env var)

All providers return sorted EventRecord sequences with no lookahead.
"""

from __future__ import annotations

import abc
from typing import Sequence

from bist_core.events.event_types import EventRecord


class EventDataProvider(abc.ABC):
    """Abstract base class for event data providers.

    Implementations must:
    - Return events sorted by timestamp ascending
    - Return only events with timestamp <= end_ts (no lookahead)
    - Be deterministic: same inputs → same outputs
    - Handle missing data gracefully (return empty, don't raise)
    """

    @abc.abstractmethod
    def fetch_events(
        self,
        symbols: Sequence[str],
        start_ts: int,
        end_ts: int,
    ) -> list[EventRecord]:
        """Fetch events for given symbols within time range.

        Args:
            symbols: BIST tickers to query.
            start_ts: Start Unix timestamp (inclusive).
            end_ts: End Unix timestamp (inclusive).

        Returns:
            List of EventRecord sorted by timestamp ascending.
        """
        ...

    @abc.abstractmethod
    def provider_name(self) -> str:
        """Return identifier string for this provider."""
        ...


class EventProviderRegistry:
    """Simple registry allowing runtime provider selection.

    Usage:
        registry = EventProviderRegistry()
        registry.register(LocalFileEventProvider(...))
        registry.register(SyntheticBISTEventProvider(...))

        events = registry.fetch_all(symbols, start_ts, end_ts)
    """

    def __init__(self) -> None:
        self._providers: list[EventDataProvider] = []

    def register(self, provider: EventDataProvider) -> None:
        """Register a provider. Duplicates by name are silently ignored."""
        names = {p.provider_name() for p in self._providers}
        if provider.provider_name() not in names:
            self._providers.append(provider)

    def fetch_all(
        self,
        symbols: Sequence[str],
        start_ts: int,
        end_ts: int,
    ) -> list[EventRecord]:
        """Fetch events from all registered providers, dedup by raw_id, sorted."""
        all_events: list[EventRecord] = []
        seen_ids: set[str] = set()

        for provider in self._providers:
            try:
                events = provider.fetch_events(symbols, start_ts, end_ts)
                for ev in events:
                    # Dedup by raw_id if present
                    if ev.raw_id and ev.raw_id in seen_ids:
                        continue
                    if ev.raw_id:
                        seen_ids.add(ev.raw_id)
                    all_events.append(ev)
            except Exception:
                # Fail-closed: skip broken provider, don't crash
                continue

        # Sort by timestamp ascending, then symbol for determinism
        all_events.sort(key=lambda e: (e.timestamp, e.symbol, e.event_type.value))
        return all_events

    @property
    def providers(self) -> list[EventDataProvider]:
        return list(self._providers)


__all__ = [
    "EventDataProvider",
    "EventProviderRegistry",
]
