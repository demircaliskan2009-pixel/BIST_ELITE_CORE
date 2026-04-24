"""BIST market module — re-exports from existing BIST-specific code.

This package establishes the `markets/bist/` boundary per the PRDV3
architecture split. Existing code under `bist_core.events.*` and
`bist_core.decision.*` continues to work. New code should import
from `bist_core.markets.bist` for market-specific logic.

Migration: existing modules will be incrementally moved here.
"""

from __future__ import annotations

# Re-export BIST event system
from bist_core.events.event_engine import EventEngine  # noqa: F401
from bist_core.events.event_policy import (  # noqa: F401
    EVENT_POLICY,
    EVENT_SIZE_MULTIPLIER,
    EventEdgeVerdict,
    get_event_entry_kinds,
    get_event_size_multiplier,
)

# Re-export BIST-specific decision components
from bist_core.decision.meta_engine import MetaDecisionEngine  # noqa: F401
from bist_core.decision.portfolio_decision import PortfolioDecisionEngine  # noqa: F401

# Re-export BIST config
from bist_core.config.bist_prod_config import BIST_CONFIG, load_bist_config  # noqa: F401

MARKET = "bist"

__all__ = [
    "MARKET",
    "BIST_CONFIG",
    "load_bist_config",
    "EventEngine",
    "EVENT_POLICY",
    "EVENT_SIZE_MULTIPLIER",
    "EventEdgeVerdict",
    "get_event_entry_kinds",
    "get_event_size_multiplier",
    "MetaDecisionEngine",
    "PortfolioDecisionEngine",
]
