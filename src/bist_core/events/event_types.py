"""Event-Driven Engine — Core data types.

Defines the canonical event record, event classifications, and sentiment
categories used across the entire event-driven alpha pipeline.

All types are frozen dataclasses for immutability and determinism.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EventType(str, Enum):
    """Canonical event categories for BIST corporate events."""

    EARNINGS = "earnings"
    DIVIDEND = "dividend"
    BUYBACK = "buyback"
    CONTRACT = "contract"
    INVESTMENT = "investment"
    CAPACITY = "capacity"
    PARTNERSHIP = "partnership"
    MANAGEMENT = "management"
    REGULATORY = "regulatory"
    GENERAL_DISCLOSURE = "general_disclosure"
    UNKNOWN = "unknown"


class EventImpact(str, Enum):
    """Three-tier impact classification."""

    HIGH = "HIGH"
    MID = "MID"
    LOW = "LOW"


class Sentiment(str, Enum):
    """Deterministic sentiment classification."""

    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"


# ---------------------------------------------------------------------------
# Core event record
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EventRecord:
    """A single corporate event — canonical format across all providers.

    Attributes:
        symbol: BIST ticker (e.g. "AKBNK")
        timestamp: Unix seconds (TRT) — publication time. Must be BEFORE
                   any market action can occur on the event.
        event_type: Canonical event category.
        headline: Raw headline text (Turkish or English).
        source: Provider identifier (e.g. "kap", "local_csv", "synthetic").
        raw_id: Optional provider-specific unique ID for dedup.
    """

    symbol: str
    timestamp: int
    event_type: EventType
    headline: str
    source: str = ""
    raw_id: str = ""


# ---------------------------------------------------------------------------
# Classified event (after classifier + scorer)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClassifiedEvent:
    """An event enriched with impact, sentiment, and composite score."""

    event: EventRecord
    impact: EventImpact
    sentiment: Sentiment
    sentiment_score: float  # -1.0 (very negative) to +1.0 (very positive)
    impact_weight: float  # 0.0-1.0 importance weight
    composite_score: float  # final event score (sentiment * impact * confirmations)


# ---------------------------------------------------------------------------
# Constants — BIST earnings calendar quarters
# ---------------------------------------------------------------------------

# Turkish listed companies report quarterly:
#   Q4 (annual) → Feb/Mar
#   Q1          → May
#   Q2          → Aug
#   Q3          → Nov
# The exact dates vary but fall within ~2 week windows.

BIST_EARNINGS_MONTHS: Final[list[int]] = [3, 5, 8, 11]
BIST_EARNINGS_DAY_RANGE: Final[tuple[int, int]] = (1, 20)  # typically 1st-20th

__all__ = [
    "ClassifiedEvent",
    "EventImpact",
    "EventRecord",
    "EventType",
    "Sentiment",
    "BIST_EARNINGS_MONTHS",
    "BIST_EARNINGS_DAY_RANGE",
]
