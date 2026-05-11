"""Events subsystem: KAP ingest, event types, classification, scoring, edges, engine."""

from __future__ import annotations

from bist_core.events.event_classifier import classify_event
from bist_core.events.event_edges import (
    detect_earnings_drift,
    detect_event_breakout,
    detect_fake_reaction,
    detect_news_momentum,
)
from bist_core.events.event_engine import EventEngine, create_event_engine
from bist_core.events.event_scorer import score_event
from bist_core.events.event_types import (
    ClassifiedEvent,
    EventImpact,
    EventRecord,
    EventType,
    Sentiment,
)
from bist_core.events.kap_ingest import ingest_kap_html, write_events_json
from bist_core.events.kap_scraper import KAPScraper
from bist_core.events.provider_base import EventDataProvider, EventProviderRegistry
from bist_core.events.provider_realistic_synthetic import (
    RealisticSyntheticEventProvider,
)

__all__ = [
    "ClassifiedEvent",
    "EventDataProvider",
    "EventEngine",
    "EventImpact",
    "EventProviderRegistry",
    "EventRecord",
    "EventType",
    "KAPScraper",
    "RealisticSyntheticEventProvider",
    "Sentiment",
    "classify_event",
    "create_event_engine",
    "detect_earnings_drift",
    "detect_event_breakout",
    "detect_fake_reaction",
    "detect_news_momentum",
    "ingest_kap_html",
    "score_event",
    "write_events_json",
]
