"""Event Policy — evidence-based event kind classification.

Derived from Phase 2 Event Alpha Study (scripts/event_alpha_study.py)
on 104,509 real KAP events joined with BIST price data (2024-09-02 to 2026-02-27).

Classification rules (1D Profit Factor based):
  POSITIVE:      PF > 1.1 AND avg_ret > 0 → boost confidence ×1.2
  NEGATIVE:      PF < 0.85 → hard block LONG signals
  SOFT_NEGATIVE: 0.85 <= PF < 0.95 → reduce confidence ×0.7 (no block)
  NEUTRAL:       otherwise → no action

Evidence:
  buyback:     PF_1D=1.44, N=3484 → POSITIVE
  partnership: PF_1D=1.45, N=420  → POSITIVE
  regulatory:  PF_1D=1.14, N=1609 → POSITIVE
  earnings:    PF_1D=0.76, N=10636 → NEGATIVE (hard block)
  contract:    PF_1D=0.82, N=1065  → NEGATIVE (hard block)
  general_disclosure: PF_1D=0.89, N=42794 → SOFT_NEGATIVE (reduce confidence)
  dividend:    PF_1D=1.00, N=1518  → NEUTRAL
  management:  PF_1D=1.06, N=1557  → NEUTRAL
  investment:  PF_1D=1.04, N=780   → NEUTRAL
"""

from __future__ import annotations

from enum import Enum
from typing import Final

# Try loading from centralized config; fall back to hardcoded defaults.
try:
    from bist_core.config.bist_prod_config import BIST_CONFIG

    _cfg = BIST_CONFIG
except Exception:  # pragma: no cover — test fallback
    _cfg = None


class EventEdgeVerdict(str, Enum):
    """Evidence-based event classification."""

    POSITIVE = "POSITIVE"          # Boost confidence ×1.2
    NEGATIVE = "NEGATIVE"          # Hard block LONG signals
    SOFT_NEGATIVE = "SOFT_NEGATIVE"  # Reduce confidence ×0.7 (no block)
    NEUTRAL = "NEUTRAL"            # No action


# Mapping from event kind string → verdict
# Keys match EventType.value and JSONL "kind" field
EVENT_POLICY: Final[dict[str, EventEdgeVerdict]] = {
    "buyback": EventEdgeVerdict.POSITIVE,
    "partnership": EventEdgeVerdict.POSITIVE,
    "regulatory": EventEdgeVerdict.POSITIVE,
    "earnings": EventEdgeVerdict.NEGATIVE,
    "contract": EventEdgeVerdict.NEGATIVE,
    "general_disclosure": EventEdgeVerdict.SOFT_NEGATIVE,
    "dividend": EventEdgeVerdict.NEUTRAL,
    "management": EventEdgeVerdict.NEUTRAL,
    "investment": EventEdgeVerdict.NEUTRAL,
    "capacity": EventEdgeVerdict.NEUTRAL,
    "unknown": EventEdgeVerdict.NEUTRAL,
}

# Confidence multipliers (evidence-based)
POSITIVE_CONFIDENCE_MULT: Final[float] = 1.2    # ×1.2 for positive events
SOFT_NEGATIVE_CONFIDENCE_MULT: Final[float] = 0.7  # ×0.7 for weak negative events

# Legacy constant (kept for backward compat, use multiplier in new code)
POSITIVE_EVENT_BOOST: Final[float] = 0.10

# Position size multipliers (evidence-based, per event kind)
# Applied directly: position_size = base_size × regime_factor × event_multiplier
EVENT_SIZE_MULTIPLIER: Final[dict[str, float]] = {
    "buyback": 1.3,              # PF_1D=1.44 → increase size
    "partnership": 1.5,          # PF_1D=1.45 → largest boost
    "regulatory": 1.1,           # PF_1D=1.14 → modest boost
    "general_disclosure": 0.7,   # PF_1D=0.89 → reduce size
    "earnings": 0.0,             # PF_1D=0.76 → BLOCKED (never reaches sizing)
    "contract": 0.0,             # PF_1D=0.82 → BLOCKED (never reaches sizing)
    "dividend": 1.0,
    "management": 1.0,
    "investment": 1.0,
    "capacity": 1.0,
    "unknown": 1.0,
}


def get_event_size_multiplier(kind: str) -> float:
    """Get the position size multiplier for an event kind.

    Reads from centralized BIST config if available, else hardcoded map.
    Unknown kinds return 1.0 (no effect).
    """
    if _cfg is not None:
        return _cfg.event_policy.size_multipliers.get(kind, 1.0)
    return EVENT_SIZE_MULTIPLIER.get(kind, 1.0)


def get_event_verdict(kind: str) -> EventEdgeVerdict:
    """Look up the evidence-based verdict for an event kind.

    Unknown kinds default to NEUTRAL (fail-closed: do nothing).
    """
    return EVENT_POLICY.get(kind, EventEdgeVerdict.NEUTRAL)


def get_event_entry_kinds() -> frozenset[str]:
    """Return the set of event kinds that can generate standalone entries."""
    if _cfg is not None:
        return _cfg.event_policy.entry_kinds
    return frozenset({"partnership"})


__all__ = [
    "EVENT_POLICY",
    "EVENT_SIZE_MULTIPLIER",
    "EventEdgeVerdict",
    "POSITIVE_CONFIDENCE_MULT",
    "POSITIVE_EVENT_BOOST",
    "SOFT_NEGATIVE_CONFIDENCE_MULT",
    "get_event_entry_kinds",
    "get_event_size_multiplier",
    "get_event_verdict",
]
