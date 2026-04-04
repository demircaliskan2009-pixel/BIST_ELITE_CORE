"""Risk engine: validates orders_intent against position/notional/name/cap rules (fail-closed)."""

from __future__ import annotations

from bist_core.risk.portfolio_state import PortfolioState
from bist_core.risk.portfolio_risk_engine import PortfolioRiskEngine
from bist_core.risk.risk_engine import TradeRiskEngine, validate_orders_intent
from bist_core.risk.risk_rules_schema import load_risk_rules, validate_risk_rules
from bist_core.risk.rulespack import (
    get_rulespack_dir,
    load_rulespack,
    validate_tick,
    validate_band,
    validate_price_tick,
    validate_price_band,
)

__all__ = [
    "PortfolioState",
    "PortfolioRiskEngine",
    "TradeRiskEngine",
    "load_risk_rules",
    "validate_risk_rules",
    "validate_orders_intent",
    "get_rulespack_dir",
    "load_rulespack",
    "validate_tick",
    "validate_band",
    "validate_price_tick",
    "validate_price_band",
]
