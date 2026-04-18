"""crypto_core.execution — Execution Engine (dry-run / paper mode).

No live order placement.  Phase 6A adds fill pricing, slippage model,
impact gate, enriched ExecutionDecision, and SyntheticFillFactory bridge.
Phase 9A adds TCA, venue scoring, and attribution primitives.
Phase 9B adds markout lifecycle, TCA persistence, venue metadata,
regime contracts, and live-readiness surface.
Phase 9C adds route binding, metadata-gated routing, and TCA closed loop.
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
from crypto_core.execution.markout import (
    MarkoutHorizonStatus,
    MarkoutObservationSet,
    MarkoutObserver,
    MarkoutObserverConfig,
    MarkoutSetStatus,
)
from crypto_core.execution.models import (
    BookContext,
    ExecutionDecision,
    ExecutionMode,
    ExecutionRequest,
    OrderIntent,
    RejectionReason,
    SlippageResult,
)
from crypto_core.execution.regime_contracts import (
    CompositeRegimeState,
    EventCategory,
    EventRegimeLevel,
    EventRegimeState,
    OnChainRegimeLevel,
    OnChainRegimeState,
    OptionsRegimeLevel,
    OptionsRegimeState,
)
from crypto_core.execution.route_binding import (
    MetadataGatedRouter,
    MetadataGatedRouterConfig,
    RouteDecision,
    RouteDecisionOutcome,
    VenueEvaluation,
    VenueRejectReason,
)
from crypto_core.execution.tca import (
    TCARecord,
    TCAStatus,
    build_tca_record,
)
from crypto_core.execution.tca_loop import (
    ExecutionTCALoop,
    FillRegistrationResult,
    PriceUpdateResult,
    TCAEmitStatus,
    TCALoopConfig,
)
from crypto_core.execution.tca_store import TCAStore, TCAStoreCorruptError
from crypto_core.execution.venue_metadata import (
    FeeMetadata,
    FundingMetadata,
    MetadataFreshness,
    VenueMetadataSnapshot,
    VenueOperationalStatus,
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
    # TCA persistence
    "TCAStore",
    "TCAStoreCorruptError",
    # TCA closed loop (Phase 9C)
    "ExecutionTCALoop",
    "TCALoopConfig",
    "TCAEmitStatus",
    "FillRegistrationResult",
    "PriceUpdateResult",
    # Attribution
    "TradeAttribution",
    "AttributionStatus",
    "build_trade_attribution",
    # Markout lifecycle
    "MarkoutObserver",
    "MarkoutObserverConfig",
    "MarkoutObservationSet",
    "MarkoutHorizonStatus",
    "MarkoutSetStatus",
    # Venue scoring / routing
    "VenueScore",
    "VenueStatus",
    "VenueScoringEngine",
    "RoutingEngine",
    "RoutingAction",
    "RoutingRecommendation",
    # Route binding (Phase 9C)
    "MetadataGatedRouter",
    "MetadataGatedRouterConfig",
    "RouteDecision",
    "RouteDecisionOutcome",
    "VenueEvaluation",
    "VenueRejectReason",
    # Venue metadata
    "VenueMetadataSnapshot",
    "MetadataFreshness",
    "FeeMetadata",
    "FundingMetadata",
    "VenueOperationalStatus",
    # Regime contracts
    "CompositeRegimeState",
    "OptionsRegimeState",
    "OptionsRegimeLevel",
    "EventRegimeState",
    "EventRegimeLevel",
    "EventCategory",
    "OnChainRegimeState",
    "OnChainRegimeLevel",
]
