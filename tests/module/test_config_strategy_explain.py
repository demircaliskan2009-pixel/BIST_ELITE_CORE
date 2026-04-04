"""Config toggles, explanation engine — additive behavior."""

from __future__ import annotations

from bist_core.ai.explanation_engine import ExplanationEngine
from bist_core.config.system_config import CONFIG
from bist_core.live.paper_trader import PaperTrader
from bist_core.strategy.strategy_router import StrategyRouter


class _PermissiveBistRules:
    def is_price_valid(self, price: float) -> bool:
        return True

    def is_liquid(self, bars) -> bool:
        return True

    def is_trade_allowed(self, price: float, prev_close: float) -> bool:
        return True


def test_config_disables_trend_router() -> None:
    prev = CONFIG.enable_trend
    try:
        CONFIG.enable_trend = False
        out = StrategyRouter().route({"regime": "trend", "score": 0.9, "mean_reversion": 0.0})
        assert out == {"signal": "hold", "strategy": "disabled"}
    finally:
        CONFIG.enable_trend = prev


def test_config_disables_mean_reversion_router() -> None:
    prev = CONFIG.enable_mean_reversion
    try:
        CONFIG.enable_mean_reversion = False
        out = StrategyRouter().route({"regime": "range", "score": 0.5, "mean_reversion": -0.03})
        assert out == {"signal": "hold", "strategy": "disabled"}
    finally:
        CONFIG.enable_mean_reversion = prev


def test_audit_decision_log_includes_explanation() -> None:
    import bist_core.live.paper_trader as pt_mod

    orig = pt_mod.get_current_price
    pt_mod.get_current_price = lambda s: 10.0 if s == "G" else None
    try:

        class DE:
            def evaluate_symbol(self, ctx):
                return {
                    "action": "hold",
                    "reason": "t",
                    "score": 0.5,
                    "regime": "range",
                    "strategy": "mean_reversion",
                    "risk": {"stop_price": 9.0},
                    "vol_adj": 1.0,
                }

        pt = PaperTrader(["G"], bist_rules=_PermissiveBistRules())
        pt.decision_engine = DE()
        pt.run_once()
        logs = pt.get_audit_logs()
        sym = [x for x in logs if x.get("event") == "decision" and x.get("symbol") == "G"]
        assert sym
        data = sym[-1].get("data") or {}
        assert "explanation" in data
        assert "G" in data["explanation"]
    finally:
        pt_mod.get_current_price = orig


def test_explanation_engine_deterministic_string() -> None:
    eng = ExplanationEngine()
    s = eng.explain(
        {
            "symbol": "ASELS",
            "action": "hold",
            "score": 0.5,
            "regime": "trend",
            "strategy": "trend",
        }
    )
    assert "ASELS" in s
    assert "hold" in s
    assert "0.5" in s
    assert eng.explain({}) == eng.build_prompt({})
