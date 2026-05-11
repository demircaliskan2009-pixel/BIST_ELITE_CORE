"""crypto_core.orchestrator — Deterministic pipeline orchestrator v1.

Wires: data → state → guard → edge → risk.
PRD reference: §2 — System Orchestration.
"""

from __future__ import annotations

from crypto_core.orchestrator.models import MarketDataInput, PipelineResult
from crypto_core.orchestrator.pipeline import PipelineConfig, PipelineOrchestrator

__all__ = [
    "PipelineOrchestrator",
    "PipelineConfig",
    "MarketDataInput",
    "PipelineResult",
]
