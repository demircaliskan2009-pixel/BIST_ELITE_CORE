"""crypto_core.guard — Fail-closed No-Trade Guard.

Evaluates whether trading is permitted before any signal proceeds downstream.
PRD reference: §1.21 — No-Trade Conditions.
"""

from __future__ import annotations

from crypto_core.guard.models import (
    BlockSeverity,
    NoTradeContext,
    NoTradeDecision,
    NoTradeReason,
)
from crypto_core.guard.no_trade_guard import NoTradeConfig, NoTradeGuard

__all__ = [
    "NoTradeGuard",
    "NoTradeConfig",
    "NoTradeContext",
    "NoTradeDecision",
    "NoTradeReason",
    "BlockSeverity",
]
