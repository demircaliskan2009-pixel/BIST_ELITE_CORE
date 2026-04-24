"""Edge detection and statistical edge engines."""

from bist_core.edge.bucket_key import edge_bucket_key, regime_from_feat
from bist_core.edge.edge_engine_v2 import EdgeEngineV2
from bist_core.edge.edge_fusion import EdgeFusion
from bist_core.edge.allocation import (
    CapitalAllocationConfig,
    CapitalAllocationResult,
    allocate_capital_to_edge,
)
from bist_core.edge.paper_trading import (
    PaperOpenPosition,
    PaperTradingConfig,
    PaperTradingResult,
    PaperTradingTrade,
    run_edge_paper_trading,
)
from bist_core.edge.portfolio_backtest import (
    PRDV3PortfolioBacktestConfig,
    PRDV3PortfolioBacktestOpenPosition,
    PRDV3PortfolioBacktestResult,
    PRDV3PortfolioBacktestTrade,
    run_prdv3_portfolio_backtest,
)
from bist_core.edge.orchestrator import (
    PRDV3MasterOrchestratorConfig,
    PRDV3MasterOrchestratorEdgeEvaluation,
    PRDV3MasterOrchestratorResult,
    run_prdv3_master_orchestrator,
)
from bist_core.edge.portfolio import (
    PRDV3PortfolioDecision,
    PRDV3PortfolioEngineConfig,
    PRDV3PortfolioEngineResult,
    PRDV3PortfolioRiskReport,
    PRDV3PortfolioTradePlanEntry,
    run_prdv3_multi_symbol_portfolio_engine,
)
from bist_core.edge.self_healing import (
    ACTIVE,
    WARNING,
    DISABLED,
    AutoEdgeKillerConfig,
    EdgePerformanceSnapshot,
    EdgeState,
    EdgeStateStore,
    apply_edge_state_to_allocation,
    apply_edge_state_to_edge_definition,
    evaluate_edge_state,
    filter_edges_for_selection,
)
from bist_core.edge.edge_store import EdgeStore
from bist_core.edge.live_edge_buffer import LiveEdgeBuffer
from bist_core.edge.live_edge_engine import LiveEdgeEngine
from bist_core.edge.multi_tf_edge import MultiTFEdge
from bist_core.edge.registry import (
    EdgeCondition,
    EdgeDefinition,
    EdgeLogic,
    EdgeRegistry,
    EdgeRequiredData,
    EdgeRiskProfile,
    EdgeValidationResult,
    build_builtin_edge_registry,
    builtin_bist_edges,
    validate_edge_definition,
)
from bist_core.edge.selection import EdgeSelectionResult, select_best_edge

__all__ = [
    "EdgeEngineV2",
    "EdgeFusion",
    "CapitalAllocationConfig",
    "CapitalAllocationResult",
    "ACTIVE",
    "AutoEdgeKillerConfig",
    "DISABLED",
    "EdgeCondition",
    "EdgeDefinition",
    "EdgeLogic",
    "EdgePerformanceSnapshot",
    "EdgeRegistry",
    "EdgeRequiredData",
    "EdgeRiskProfile",
    "EdgeSelectionResult",
    "EdgeState",
    "EdgeStateStore",
    "EdgeStore",
    "EdgeValidationResult",
    "LiveEdgeBuffer",
    "LiveEdgeEngine",
    "MultiTFEdge",
    "PaperOpenPosition",
    "PaperTradingConfig",
    "PaperTradingResult",
    "PaperTradingTrade",
    "PRDV3PortfolioBacktestConfig",
    "PRDV3PortfolioBacktestOpenPosition",
    "PRDV3PortfolioBacktestResult",
    "PRDV3PortfolioBacktestTrade",
    "PRDV3MasterOrchestratorConfig",
    "PRDV3MasterOrchestratorEdgeEvaluation",
    "PRDV3MasterOrchestratorResult",
    "PRDV3PortfolioDecision",
    "PRDV3PortfolioEngineConfig",
    "PRDV3PortfolioEngineResult",
    "PRDV3PortfolioRiskReport",
    "PRDV3PortfolioTradePlanEntry",
    "WARNING",
    "apply_edge_state_to_allocation",
    "apply_edge_state_to_edge_definition",
    "allocate_capital_to_edge",
    "build_builtin_edge_registry",
    "builtin_bist_edges",
    "edge_bucket_key",
    "evaluate_edge_state",
    "filter_edges_for_selection",
    "regime_from_feat",
    "run_edge_paper_trading",
    "run_prdv3_portfolio_backtest",
    "run_prdv3_master_orchestrator",
    "run_prdv3_multi_symbol_portfolio_engine",
    "select_best_edge",
    "validate_edge_definition",
]
