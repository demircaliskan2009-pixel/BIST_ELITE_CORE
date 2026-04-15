"""crypto_core.execution — Execution Engine skeleton.

Dry-run / paper mode only. No live order placement.
PRD reference: §7 Execution Engine.
"""

from __future__ import annotations

from crypto_core.execution.engine import ExecutionConfig, ExecutionEngine
from crypto_core.execution.models import (
    ExecutionDecision,
    ExecutionMode,
    ExecutionRequest,
    OrderIntent,
    RejectionReason,
)

__all__ = [
    "ExecutionEngine",
    "ExecutionConfig",
    "ExecutionRequest",
    "ExecutionDecision",
    "OrderIntent",
    "ExecutionMode",
    "RejectionReason",
]
