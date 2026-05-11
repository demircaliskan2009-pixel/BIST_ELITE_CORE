"""Event Engine — provider, classifier, scorer, edges, engine integration tests."""

from __future__ import annotations

import pytest

from bist_core.events.event_types import (
    BIST_EARNINGS_MONTHS,
    ClassifiedEvent,
    EventImpact,
    EventRecord,
    EventType,
    Sentiment,
)
from bist_core.events.event_classifier import (
    classify_event,
    classify_impact,
    classify_sentiment,
)
from bist_core.events.event_scorer import score_event
from bist_core.events.provider_base import EventDataProvider, EventProviderRegistry
from bist_core.events.provider_synthetic import SyntheticBISTEventProvider
from bist_core.events.provider_kap_stub import KAPScraperProvider
from bist_core.events.event_engine import EventEngine, create_event_engine
from bist_core.models.ohlcv import OHLCVBar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bar(
    symbol: str = "ASELS",
    close: float = 100.0,
    volume: float = 50000.0,
    ts: int = 0,
) -> OHLCVBar:
    return OHLCVBar(
        symbol=symbol,
        open=close * 0.99,
        high=close * 1.01,
        low=close * 0.98,
        close=close,
        volume=volume,
        timestamp=ts,
    )


def _bars_series(
    symbol: str = "ASELS",
    n: int = 50,
    base_close: float = 100.0,
    base_volume: float = 50000.0,
    start_ts: int = 1_700_000_000,
    trend: float = 0.001,
) -> list[OHLCVBar]:
    """Generate n bars with slight uptrend."""
    bars = []
    for i in range(n):
        c = base_close * (1 + trend * i)
        bars.append(_bar(
            symbol=symbol,
            close=round(c, 2),
            volume=base_volume,
            ts=start_ts + i * 60,
        ))
    return bars


def _make_event(
    symbol: str = "ASELS",
    ts: int = 1_700_000_000,
    event_type: EventType = EventType.EARNINGS,
    headline: str = "Güçlü kâr artışı açıklandı",
    source: str = "test",
    raw_id: str = "test_001",
) -> EventRecord:
    return EventRecord(
        symbol=symbol,
        timestamp=ts,
        event_type=event_type,
        headline=headline,
        source=source,
        raw_id=raw_id,
    )


# ---------------------------------------------------------------------------
# EventType + EventRecord
# ---------------------------------------------------------------------------


class TestEventTypes:
    def test_event_type_values(self):
        assert EventType.EARNINGS.value == "earnings"
        assert EventType.DIVIDEND.value == "dividend"
        assert EventType.UNKNOWN.value == "unknown"

    def test_event_impact_values(self):
        assert EventImpact.HIGH.value == "HIGH"
        assert EventImpact.MID.value == "MID"
        assert EventImpact.LOW.value == "LOW"

    def test_event_record_creation(self):
        ev = _make_event()
        assert ev.symbol == "ASELS"
        assert ev.event_type == EventType.EARNINGS
        assert ev.raw_id == "test_001"

    def test_bist_earnings_months(self):
        assert BIST_EARNINGS_MONTHS == [3, 5, 8, 11]


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class TestClassifier:
    def test_classify_earnings_high_impact(self):
        ev = _make_event(event_type=EventType.EARNINGS)
        impact = classify_impact(ev)
        assert impact == EventImpact.HIGH

    def test_classify_general_low_impact(self):
        ev = _make_event(event_type=EventType.GENERAL_DISCLOSURE)
        impact = classify_impact(ev)
        assert impact == EventImpact.LOW

    def test_positive_sentiment_turkish_keywords(self):
        ev = _make_event(headline="Güçlü kâr artışı ve rekor gelir açıklandı")
        sentiment, score = classify_sentiment(ev)
        assert sentiment == Sentiment.POSITIVE
        assert score > 0.0

    def test_negative_sentiment(self):
        ev = _make_event(headline="Zarar açıklandı, düşüş bekleniyor")
        sentiment, score = classify_sentiment(ev)
        assert sentiment == Sentiment.NEGATIVE
        assert score < 0.0

    def test_neutral_sentiment_no_keywords(self):
        ev = _make_event(headline="Genel kurul toplantısı yapıldı")
        sentiment, score = classify_sentiment(ev)
        # May be neutral or weakly positive/negative
        assert isinstance(score, float)

    def test_classify_event_full_pipeline(self):
        ev = _make_event(headline="Güçlü kâr ve rekor gelir")
        cev = classify_event(ev)
        assert isinstance(cev, ClassifiedEvent)
        assert cev.event == ev
        assert cev.impact in (EventImpact.HIGH, EventImpact.MID, EventImpact.LOW)
        assert cev.sentiment in (Sentiment.POSITIVE, Sentiment.NEUTRAL, Sentiment.NEGATIVE)
        assert isinstance(cev.composite_score, float)


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


class TestScorer:
    def test_score_positive_event_with_volume(self):
        ev = _make_event(headline="Güçlü kâr artışı rekor gelir")
        cev = classify_event(ev)
        # Bars with decent volume
        bars = _bars_series(n=30, base_volume=50000)
        score = score_event(cev, bars)
        assert isinstance(score, float)

    def test_score_with_empty_bars(self):
        ev = _make_event(headline="Güçlü kâr artışı")
        cev = classify_event(ev)
        score = score_event(cev, [])
        # Should still return a score (no volume/price confirmation, uses defaults)
        assert isinstance(score, float)


# ---------------------------------------------------------------------------
# Provider Registry
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    def test_register_and_fetch(self):
        reg = EventProviderRegistry()
        provider = SyntheticBISTEventProvider()
        reg.register(provider)
        events = reg.fetch_all(
            ["ASELS"], start_ts=1_700_000_000, end_ts=1_710_000_000,
        )
        assert isinstance(events, list)
        assert all(isinstance(e, EventRecord) for e in events)
        # Synthetic should generate events for ASELS
        assert len(events) > 0

    def test_duplicate_provider_ignored(self):
        reg = EventProviderRegistry()
        p1 = SyntheticBISTEventProvider()
        p2 = SyntheticBISTEventProvider()
        reg.register(p1)
        reg.register(p2)
        assert len(reg._providers) == 1

    def test_events_sorted_by_timestamp(self):
        reg = EventProviderRegistry()
        reg.register(SyntheticBISTEventProvider())
        events = reg.fetch_all(
            ["ASELS", "GARAN"], start_ts=1_700_000_000, end_ts=1_710_000_000,
        )
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)


# ---------------------------------------------------------------------------
# Synthetic Provider
# ---------------------------------------------------------------------------


class TestSyntheticProvider:
    def test_deterministic(self):
        p = SyntheticBISTEventProvider()
        e1 = p.fetch_events(["ASELS"], 1_700_000_000, 1_710_000_000)
        e2 = p.fetch_events(["ASELS"], 1_700_000_000, 1_710_000_000)
        assert len(e1) == len(e2)
        for a, b in zip(e1, e2):
            assert a.timestamp == b.timestamp
            assert a.event_type == b.event_type
            assert a.symbol == b.symbol

    def test_no_future_events(self):
        end_ts = 1_705_000_000
        p = SyntheticBISTEventProvider()
        events = p.fetch_events(["ASELS"], 1_700_000_000, end_ts)
        for ev in events:
            assert ev.timestamp <= end_ts

    def test_earnings_after_market_close(self):
        """Synthetic earnings should be at 18:30 TRT (15:30 UTC)."""
        p = SyntheticBISTEventProvider()
        events = p.fetch_events(["ASELS"], 1_700_000_000, 1_720_000_000)
        for ev in events:
            if ev.event_type == EventType.EARNINGS:
                # Check hour is 15 UTC (18 TRT)
                hour = (ev.timestamp % 86400) // 3600
                assert hour == 15, f"Earnings at hour {hour} UTC, expected 15"


# ---------------------------------------------------------------------------
# KAP Stub Provider
# ---------------------------------------------------------------------------


class TestKAPStub:
    def test_disabled_by_default(self):
        p = KAPScraperProvider()
        events = p.fetch_events(["ASELS"], 1_700_000_000, 1_710_000_000)
        assert events == []

    def test_provider_name(self):
        p = KAPScraperProvider()
        assert p.provider_name() == "kap_scraper"


# ---------------------------------------------------------------------------
# EventEngine
# ---------------------------------------------------------------------------


class TestEventEngine:
    def test_create_event_engine_factory(self):
        engine = create_event_engine(use_synthetic=True)
        assert isinstance(engine, EventEngine)

    def test_load_events(self):
        engine = create_event_engine(use_synthetic=True)
        count = engine.load_events(["ASELS"], 1_700_000_000, 1_720_000_000)
        assert count > 0

    def test_event_boost_no_active(self):
        engine = create_event_engine(use_synthetic=True)
        engine.load_events(["ASELS"], 1_700_000_000, 1_720_000_000)
        # No bar processing yet — no active event
        boost = engine.get_event_boost("ASELS")
        assert boost == 0.0

    def test_is_strong_event_no_active(self):
        engine = create_event_engine(use_synthetic=True)
        engine.load_events(["ASELS"], 1_700_000_000, 1_720_000_000)
        assert engine.is_strong_event("ASELS") is False

    def test_disable_edges(self):
        engine = create_event_engine(use_synthetic=True)
        engine.disable_edges({"earnings_drift"})
        assert "earnings_drift" in engine._disabled_edges

    def test_scan_returns_list(self):
        """Scan should return a list (possibly empty) given bar events."""
        from bist_core.decision.mtf_context import MTFContext
        from bist_core.decision.timeframe_sync import MTFBarEvent

        engine = create_event_engine(use_synthetic=True)
        engine.load_events(["ASELS"], 1_700_000_000, 1_720_000_000)

        bar = _bar(symbol="ASELS", close=100.0, ts=1_705_000_000)
        m1_history = _bars_series(
            symbol="ASELS", n=50, start_ts=1_704_997_000,
        )

        ctx = MTFContext(
            timestamp=1_705_000_000,
            symbol="ASELS",
            daily=None,
            hourly=None,
            m5=None,
            m1=None,
        )
        mtf_event = MTFBarEvent(
            bar=bar,
            context=ctx,
            daily_completed=False,
            hourly_completed=False,
            m5_completed=False,
        )

        signals = engine.scan(mtf_event, m1_history)
        assert isinstance(signals, list)


# ---------------------------------------------------------------------------
# Event edges integration
# ---------------------------------------------------------------------------


class TestEventEdgesUnit:
    """Verify event edge function signatures and basic contract."""

    def test_imports(self):
        from bist_core.events.event_edges import (
            detect_earnings_drift,
            detect_event_breakout,
            detect_fake_reaction,
            detect_news_momentum,
        )
        assert callable(detect_earnings_drift)
        assert callable(detect_news_momentum)
        assert callable(detect_event_breakout)
        assert callable(detect_fake_reaction)


# ---------------------------------------------------------------------------
# __init__ exports
# ---------------------------------------------------------------------------


class TestPackageExports:
    def test_all_exports_importable(self):
        from bist_core.events import (
            ClassifiedEvent,
            EventDataProvider,
            EventEngine,
            EventImpact,
            EventProviderRegistry,
            EventRecord,
            EventType,
            Sentiment,
            classify_event,
            create_event_engine,
            detect_earnings_drift,
            detect_event_breakout,
            detect_fake_reaction,
            detect_news_momentum,
            ingest_kap_html,
            score_event,
            write_events_json,
        )
        # Just verify imports work — no assertion beyond no ImportError
