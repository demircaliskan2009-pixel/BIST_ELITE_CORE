"""Strategy router, plugins, and metrics — deterministic."""

from __future__ import annotations

from bist_core.strategy.mean_reversion_strategy import MeanReversionStrategy
from bist_core.strategy.strategy_metrics import StrategyMetrics
from bist_core.strategy.strategy_router import StrategyRouter
from bist_core.strategy.trend_strategy import TrendStrategy


def test_router_trend_uses_trend_strategy() -> None:
    r = StrategyRouter()
    out = r.route({"regime": "trend", "score": 0.9, "mean_reversion": 0.0})
    assert out == {"signal": "long", "strategy": "trend"}


def test_router_range_uses_mean_reversion() -> None:
    r = StrategyRouter()
    out = r.route({"regime": "range", "score": 0.5, "mean_reversion": -0.03})
    assert out == {"signal": "long", "strategy": "mean_reversion"}


def test_router_unknown_holds() -> None:
    r = StrategyRouter()
    assert r.route({"regime": "unknown", "score": 0.9, "mean_reversion": 0.0}) == {
        "signal": "hold",
        "strategy": "none",
    }


def test_trend_strategy_thresholds() -> None:
    t = TrendStrategy()
    assert t.evaluate({"score": 0.7})["signal"] == "long"
    assert t.evaluate({"score": 0.3})["signal"] == "exit"
    assert t.evaluate({"score": 0.5})["signal"] == "long"
    assert t.evaluate({"score": 0.42})["signal"] == "hold"


def test_mean_reversion_strategy_thresholds() -> None:
    m = MeanReversionStrategy()
    assert m.evaluate({"mean_reversion": -0.03})["signal"] == "long"
    assert m.evaluate({"mean_reversion": 0.03})["signal"] == "exit"
    assert m.evaluate({"mean_reversion": 0.0})["signal"] == "hold"


def test_strategy_metrics_record_and_get() -> None:
    sm = StrategyMetrics()
    sm.record("trend", 0.01)
    sm.record("trend", -0.02)
    sm.record("mean_reversion", 0.05)
    g = sm.get()
    assert g["trend"] == [0.01, -0.02]
    assert g["mean_reversion"] == [0.05]
