"""crypto_core.execution — Execution Engine (dry-run / paper mode).

No live order placement.  Phase 6A adds fill pricing, slippage model,
impact gate, enriched ExecutionDecision, and SyntheticFillFactory bridge.
PRD reference: §7 Execution Engine.
"""

from __future__ import annotations

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
]
