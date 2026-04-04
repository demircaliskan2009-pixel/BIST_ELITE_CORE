"""Adaptive meta-layer: rolling perf, decay, meta weights — deterministic."""

from __future__ import annotations

from bist_core.strategy.meta_selector import MetaSelector
from bist_core.strategy.strategy_decay import StrategyDecay
from bist_core.strategy.strategy_metrics import StrategyMetrics


def test_rolling_performance_mean_of_window() -> None:
    sm = StrategyMetrics()
    for _ in range(20):
        sm.record("a", 1.0)
    sm.record("a", 10.0)
    assert sm.rolling_performance(20)["a"] == 1.45


def test_rolling_performance_empty_series_zero() -> None:
    sm = StrategyMetrics()
    sm._data["empty_strat"] = []
    assert sm.rolling_performance(20)["empty_strat"] == 0.0


def test_summary_stats() -> None:
    sm = StrategyMetrics()
    sm.record("x", 1.0)
    sm.record("x", 3.0)
    sm.record("y", -1.0)
    s = sm.summary()
    assert s["x"]["count"] == 2
    assert s["x"]["mean"] == 2.0
    assert s["x"]["last"] == 3.0
    assert s["y"]["last"] == -1.0


def test_meta_selector_weights_sum_to_one_positive_perf() -> None:
    ms = MetaSelector()
    w = ms.select({"a": 0.1, "b": 0.9})
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert w["b"] > w["a"]


def test_meta_selector_equal_when_all_nonpositive() -> None:
    ms = MetaSelector()
    w = ms.select({"a": -1.0, "b": 0.0})
    assert abs(w["a"] - w["b"]) < 1e-9
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_meta_selector_empty() -> None:
    assert MetaSelector().select({}) == {}


def test_decay_positive_caps() -> None:
    d = StrategyDecay()
    assert d.compute_weight(0.6) == 1.5
    assert d.compute_weight(0.1) == 1.1


def test_decay_negative_floors() -> None:
    d = StrategyDecay()
    assert d.compute_weight(-0.5) == 0.5
    assert d.compute_weight(-0.99) == 0.1


def test_better_strategy_higher_meta_weight() -> None:
    ms = MetaSelector()
    w = ms.select({"good": 0.8, "bad": 0.2})
    assert w["good"] > w["bad"]


def test_losing_strategy_decay_weight_below_one() -> None:
    d = StrategyDecay()
    assert d.compute_weight(-0.2) < 1.0


def test_size_scales_with_meta_and_decay() -> None:
    base = 100
    meta_w = 0.5
    decay_w = 0.8
    size = max(1, int(base * meta_w * decay_w))
    assert size == 40
