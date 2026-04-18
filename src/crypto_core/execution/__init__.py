"""crypto_core.execution — Execution Engine (dry-run / paper mode).

No live order placement.  Phase 6A adds fill pricing, slippage model,
impact gate, enriched ExecutionDecision, and SyntheticFillFactory bridge.
Phase 9A adds TCA, venue scoring, and attribution primitives.
PRD reference: §7 Execution Engine.
"""

from __future__ import annotations

from crypto_core.execution.attribution import (
    AttributionStatus,
    TradeAttribution,
    build_trade_attribution,
)
from crypto_core.execution.engine import ExecutionConfig, ExecutionEngine
from crypto_core.execution.fill_pricer import FillPricer, FillPricerConfig
from crypto_core.execution.models import (
    BookContext,
    ExecutionDecision,
    ExecutionMode,
    ExecutionRequest,
    OrderIntent,
    RejectionReason,
    SlippageResult,
)
from crypto_core.execution.tca import (
    TCARecord,
    TCAStatus,
    build_tca_record,
)
from crypto_core.execution.venue_scoring import (
    RoutingAction,
    RoutingEngine,
    RoutingRecommendation,
    VenueScore,
    VenueScoringEngine,
    VenueStatus,
)

__all__ = [
    "ExecutionEngine",
    "ExecutionConfig",
    "ExecutionRequest",
    "ExecutionDecision",
    "OrderIntent",
    "ExecutionMode",
    "RejectionReason",
    "BookContext",
    "SlippageResult",
    "FillPricer",
    "FillPricerConfig",
    # TCA
    "TCARecord",
    "TCAStatus",
    "build_tca_record",
    # Attribution
    "TradeAttribution",
    "AttributionStatus",
    "build_trade_attribution",
    # Venue scoring / routing
    "VenueScore",
    "VenueStatus",
    "VenueScoringEngine",
    "RoutingEngine",
    "RoutingAction",
    "RoutingRecommendation",
]
