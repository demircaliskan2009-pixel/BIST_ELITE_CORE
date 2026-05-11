"""crypto_core.guard — Fail-closed No-Trade Guard.

Evaluates whether trading is permitted before any signal proceeds downstream.
PRD reference: §1.21 — No-Trade Conditions v2 (25 rules, 6 families).
"""

from __future__ import annotations

from crypto_core.guard.models import (
    NT_D_CODES,
    NT_E_CODES,
    NT_M_CODES,
    NT_R_CODES,
    NT_T_CODES,
    REASON_SEVERITY,
    BlockSeverity,
    EdgeHealthInput,
    MarketRegimeInput,
    NoTradeContext,
    NoTradeDecision,
    NoTradeReason,
    RiskGuardInput,
    TemporalInput,
)
from crypto_core.guard.no_trade_guard import NoTradeConfig, NoTradeGuard

__all__ = [
    "NoTradeGuard",
    "NoTradeConfig",
    "NoTradeContext",
    "NoTradeDecision",
    "NoTradeReason",
    "BlockSeverity",
    "REASON_SEVERITY",
    "NT_D_CODES",
    "NT_R_CODES",
    "NT_M_CODES",
    "NT_E_CODES",
    "NT_T_CODES",
    "RiskGuardInput",
    "MarketRegimeInput",
    "EdgeHealthInput",
    "TemporalInput",
]
