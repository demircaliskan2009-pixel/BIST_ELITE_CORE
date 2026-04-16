"""crypto_core.risk — Risk Engine v1 + v2.

Fail-closed approval gate sitting between edge output and execution.
PRD reference: §1.14–§1.28.
"""

from __future__ import annotations

from crypto_core.risk.contracts import (
    KS_BLOCK_THRESHOLD,
    KS_LEVEL_BLOCK,
    KS_LEVEL_FLATTEN,
    KS_LEVEL_HALT,
    KS_LEVEL_NORMAL,
    KS_LEVEL_REDUCE,
    CVaRInput,
    DTLInput,
    KellyInput,
    PortfolioRiskSnapshot,
    RiskInput,
)
from crypto_core.risk.engine import RiskEngine
from crypto_core.risk.kill_switch import (
    TRIGGER_LEVELS,
    ExecutionQuality,
    KillSwitchEngine,
    KillSwitchInput,
    KillSwitchResult,
)
from crypto_core.risk.models import (
    RiskBlockReason,
    RiskDecision,
    RiskEvaluation,
)

__all__ = [
    # Engine
    "RiskEngine",
    # Kill-switch engine
    "KillSwitchEngine",
    "KillSwitchInput",
    "KillSwitchResult",
    "ExecutionQuality",
    "TRIGGER_LEVELS",
    # v1 models
    "RiskDecision",
    "RiskBlockReason",
    "RiskEvaluation",
    # v2 contracts
    "RiskInput",
    "DTLInput",
    "KellyInput",
    "CVaRInput",
    "PortfolioRiskSnapshot",
    # KS level constants
    "KS_LEVEL_NORMAL",
    "KS_LEVEL_REDUCE",
    "KS_LEVEL_BLOCK",
    "KS_LEVEL_FLATTEN",
    "KS_LEVEL_HALT",
    "KS_BLOCK_THRESHOLD",
]
