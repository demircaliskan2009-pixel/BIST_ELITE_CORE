"""Event Classifier — Deterministic rule-based impact + sentiment classification.

Uses keyword matching and rule logic (NO black-box models, NO ML).
Turkish and English keywords supported.

Impact classification:
  HIGH: earnings, major contracts, large investments, buybacks
  MID:  capacity increase, partnerships, management changes
  LOW:  routine disclosures, regulatory filings

Sentiment classification:
  POSITIVE: growth, profit increase, new contract, capacity expansion
  NEGATIVE: loss, lawsuit, management departure, production halt
  NEUTRAL:  everything else
"""

from __future__ import annotations

from typing import Final, Sequence

from bist_core.events.event_types import (
    ClassifiedEvent,
    EventImpact,
    EventRecord,
    EventType,
    Sentiment,
)

# ---------------------------------------------------------------------------
# Impact rules — event_type → default impact
# ---------------------------------------------------------------------------

_TYPE_IMPACT: Final[dict[EventType, EventImpact]] = {
    EventType.EARNINGS: EventImpact.HIGH,
    EventType.BUYBACK: EventImpact.HIGH,
    EventType.CONTRACT: EventImpact.HIGH,
    EventType.INVESTMENT: EventImpact.HIGH,
    EventType.DIVIDEND: EventImpact.MID,
    EventType.CAPACITY: EventImpact.MID,
    EventType.PARTNERSHIP: EventImpact.MID,
    EventType.MANAGEMENT: EventImpact.MID,
    EventType.REGULATORY: EventImpact.LOW,
    EventType.GENERAL_DISCLOSURE: EventImpact.LOW,
    EventType.UNKNOWN: EventImpact.LOW,
}

_IMPACT_WEIGHT: Final[dict[EventImpact, float]] = {
    EventImpact.HIGH: 1.0,
    EventImpact.MID: 0.5,
    EventImpact.LOW: 0.2,
}

# ---------------------------------------------------------------------------
# Sentiment keyword dictionaries — Turkish + English
# ---------------------------------------------------------------------------

_POSITIVE_KEYWORDS: Final[frozenset[str]] = frozenset({
    # English
    "profit", "growth", "increase", "record", "expansion",
    "exceeds", "beat", "outperform", "strong", "surpass",
    "new contract", "revenue growth", "margin improvement",
    "buyback", "share repurchase", "dividend increase",
    "capacity expansion", "strategic partnership", "acquisition",
    "upgraded", "positive", "milestone",
    # Turkish
    "kâr", "kar", "büyüme", "artış", "artiş", "rekor",
    "güçlü", "aşan", "yeni sözleşme", "gelir artışı",
    "temettü artışı", "kapasite artışı", "stratejik ortaklık",
    "devralma", "pay geri alım", "olumlu",
})

_NEGATIVE_KEYWORDS: Final[frozenset[str]] = frozenset({
    # English
    "loss", "decline", "decrease", "negative", "weak",
    "miss", "underperform", "lawsuit", "investigation",
    "halt", "suspension", "penalty", "fine", "downgrade",
    "departure", "resignation", "restructuring", "impairment",
    "writedown", "default", "debt", "liquidity concern",
    # Turkish
    "zarar", "düşüş", "azalış", "olumsuz", "zayıf",
    "dava", "soruşturma", "durma", "askıya", "ceza",
    "istifa", "yeniden yapılandırma", "değer düşüklüğü",
    "temerrüt", "borç",
})

# Headlines that amplify impact (upgrade to HIGH regardless of type)
_HIGH_IMPACT_AMPLIFIERS: Final[frozenset[str]] = frozenset({
    "record", "rekor", "major", "büyük", "significant",
    "önemli", "strategic", "stratejik", "billion", "milyar",
})


# ---------------------------------------------------------------------------
# Classification functions
# ---------------------------------------------------------------------------


def classify_impact(event: EventRecord) -> EventImpact:
    """Classify event impact based on type + headline keywords."""
    base_impact = _TYPE_IMPACT.get(event.event_type, EventImpact.LOW)

    # Check for amplifiers in headline
    headline_lower = event.headline.lower()
    for amp in _HIGH_IMPACT_AMPLIFIERS:
        if amp in headline_lower:
            return EventImpact.HIGH

    return base_impact


def classify_sentiment(event: EventRecord) -> tuple[Sentiment, float]:
    """Classify sentiment and return (sentiment, score).

    Score range: -1.0 (very negative) to +1.0 (very positive).
    Uses simple keyword counting — deterministic, no ML.
    """
    headline_lower = event.headline.lower()

    pos_count = sum(1 for kw in _POSITIVE_KEYWORDS if kw in headline_lower)
    neg_count = sum(1 for kw in _NEGATIVE_KEYWORDS if kw in headline_lower)

    if pos_count == 0 and neg_count == 0:
        return Sentiment.NEUTRAL, 0.0

    total = pos_count + neg_count
    # Normalized score: positive minus negative, scaled by total matches
    raw_score = (pos_count - neg_count) / total

    if raw_score > 0.15:
        return Sentiment.POSITIVE, round(min(1.0, raw_score), 3)
    elif raw_score < -0.15:
        return Sentiment.NEGATIVE, round(max(-1.0, raw_score), 3)
    else:
        return Sentiment.NEUTRAL, round(raw_score, 3)


def classify_event(event: EventRecord) -> ClassifiedEvent:
    """Full classification: impact + sentiment → ClassifiedEvent."""
    impact = classify_impact(event)
    sentiment, sentiment_score = classify_sentiment(event)
    impact_weight = _IMPACT_WEIGHT[impact]

    # Composite score = sentiment_score * impact_weight
    # Range: -1.0 to +1.0, weighted by importance
    composite = round(sentiment_score * impact_weight, 4)

    return ClassifiedEvent(
        event=event,
        impact=impact,
        sentiment=sentiment,
        sentiment_score=sentiment_score,
        impact_weight=impact_weight,
        composite_score=composite,
    )


def classify_events(events: Sequence[EventRecord]) -> list[ClassifiedEvent]:
    """Classify a batch of events. Preserves order."""
    return [classify_event(ev) for ev in events]


__all__ = [
    "classify_event",
    "classify_events",
    "classify_impact",
    "classify_sentiment",
]
