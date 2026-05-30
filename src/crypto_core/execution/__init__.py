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

from importlib import import_module
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
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
    from crypto_core.execution.tca import TCARecord, TCAStatus, build_tca_record
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

_EXPORT_MODULES: dict[str, str] = {
    "ExecutionEngine": "crypto_core.execution.engine",
    "ExecutionConfig": "crypto_core.execution.engine",
    "ExecutionRequest": "crypto_core.execution.models",
    "ExecutionDecision": "crypto_core.execution.models",
    "OrderIntent": "crypto_core.execution.models",
    "ExecutionMode": "crypto_core.execution.models",
    "RejectionReason": "crypto_core.execution.models",
    "BookContext": "crypto_core.execution.models",
    "SlippageResult": "crypto_core.execution.models",
    "FillPricer": "crypto_core.execution.fill_pricer",
    "FillPricerConfig": "crypto_core.execution.fill_pricer",
    "TCARecord": "crypto_core.execution.tca",
    "TCAStatus": "crypto_core.execution.tca",
    "build_tca_record": "crypto_core.execution.tca",
    "TCAStore": "crypto_core.execution.tca_store",
    "TCAStoreCorruptError": "crypto_core.execution.tca_store",
    "ExecutionTCALoop": "crypto_core.execution.tca_loop",
    "TCALoopConfig": "crypto_core.execution.tca_loop",
    "TCAEmitStatus": "crypto_core.execution.tca_loop",
    "FillRegistrationResult": "crypto_core.execution.tca_loop",
    "PriceUpdateResult": "crypto_core.execution.tca_loop",
    "TradeAttribution": "crypto_core.execution.attribution",
    "AttributionStatus": "crypto_core.execution.attribution",
    "build_trade_attribution": "crypto_core.execution.attribution",
    "MarkoutObserver": "crypto_core.execution.markout",
    "MarkoutObserverConfig": "crypto_core.execution.markout",
    "MarkoutObservationSet": "crypto_core.execution.markout",
    "MarkoutHorizonStatus": "crypto_core.execution.markout",
    "MarkoutSetStatus": "crypto_core.execution.markout",
    "VenueScore": "crypto_core.execution.venue_scoring",
    "VenueStatus": "crypto_core.execution.venue_scoring",
    "VenueScoringEngine": "crypto_core.execution.venue_scoring",
    "RoutingEngine": "crypto_core.execution.venue_scoring",
    "RoutingAction": "crypto_core.execution.venue_scoring",
    "RoutingRecommendation": "crypto_core.execution.venue_scoring",
    "MetadataGatedRouter": "crypto_core.execution.route_binding",
    "MetadataGatedRouterConfig": "crypto_core.execution.route_binding",
    "RouteDecision": "crypto_core.execution.route_binding",
    "RouteDecisionOutcome": "crypto_core.execution.route_binding",
    "VenueEvaluation": "crypto_core.execution.route_binding",
    "VenueRejectReason": "crypto_core.execution.route_binding",
    "VenueMetadataSnapshot": "crypto_core.execution.venue_metadata",
    "MetadataFreshness": "crypto_core.execution.venue_metadata",
    "FeeMetadata": "crypto_core.execution.venue_metadata",
    "FundingMetadata": "crypto_core.execution.venue_metadata",
    "VenueOperationalStatus": "crypto_core.execution.venue_metadata",
    "CompositeRegimeState": "crypto_core.execution.regime_contracts",
    "OptionsRegimeState": "crypto_core.execution.regime_contracts",
    "OptionsRegimeLevel": "crypto_core.execution.regime_contracts",
    "EventRegimeState": "crypto_core.execution.regime_contracts",
    "EventRegimeLevel": "crypto_core.execution.regime_contracts",
    "EventCategory": "crypto_core.execution.regime_contracts",
    "OnChainRegimeState": "crypto_core.execution.regime_contracts",
    "OnChainRegimeLevel": "crypto_core.execution.regime_contracts",
}


def __getattr__(name: str):
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module 'crypto_core.execution' has no attribute {name!r}")
    module = import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value
