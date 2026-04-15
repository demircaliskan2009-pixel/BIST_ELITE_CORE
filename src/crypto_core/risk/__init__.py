"""crypto_core.risk — Risk Engine v1.

Fail-closed approval gate that sits between edge output and execution.
PRD reference: §1.14–§1.28.
"""

from __future__ import annotations

from crypto_core.risk.engine import RiskEngine
from crypto_core.risk.models import (
    RiskBlockReason,
    RiskDecision,
    RiskEvaluation,
)

__all__ = [
    "RiskEngine",
    "RiskDecision",
    "RiskBlockReason",
    "RiskEvaluation",
]
