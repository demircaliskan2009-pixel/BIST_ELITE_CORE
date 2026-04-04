"""Analytics, replay, scenario runner — deterministic layers."""

from __future__ import annotations

from bist_core.analytics.error_classifier import ErrorClassifier
from bist_core.analytics.performance_attribution import PerformanceAttribution
from bist_core.analytics.trade_analytics import TradeAnalytics, compute_expectancy
from bist_core.models.ohlcv import OHLCVBar
from bist_core.replay.replay_engine import ReplayEngine
from bist_core.research.scenario_runner import ScenarioRunner


def _bar(close: float, ts: int = 0) -> OHLCVBar:
    return OHLCVBar(
        symbol="X",
        open=close,
        high=close + 0.5,
        low=max(close - 0.5, 0.01),
        close=close,
        volume=1000.0,
        timestamp=ts,
    )


def test_performance_attribution_sums() -> None:
    pa = PerformanceAttribution()
    trades = [
        {"symbol": "A", "strategy": "trend", "pnl": 0.1},
        {"symbol": "A", "strategy": "trend", "pnl": -0.05},
        {"symbol": "B", "strategy": "mean_reversion", "pnl": 0.02},
    ]
    out = pa.compute(trades)
    assert out["by_symbol"]["A"] == 0.05
    assert out["by_symbol"]["B"] == 0.02
    assert out["by_strategy"]["trend"] == 0.05
    assert out["by_strategy"]["mean_reversion"] == 0.02


def test_compute_expectancy_mean_pure() -> None:
    """Expectancy is arithmetic mean of trade pnls (no filtering)."""
    trades = [
        {"pnl": 0.02},
        {"pnl": -0.01},
        {"pnl": 0.0005},
    ]
    assert compute_expectancy(trades) == (0.02 - 0.01 + 0.0005) / 3.0
    only_tiny = [{"pnl": 0.0005}, {"pnl": -0.0005}]
    assert compute_expectancy(only_tiny) == 0.0


def test_trade_analytics_win_rate() -> None:
    ta = TradeAnalytics()
    out = ta.compute(
        [
            {"pnl": 1.0},
            {"pnl": -0.5},
            {"pnl": 0.0},
        ]
    )
    assert out["win_rate"] == 1.0 / 3.0
    assert out["avg_win"] == 1.0
    assert out["avg_loss"] == -0.5


def test_error_classifier_counts() -> None:
    ec = ErrorClassifier()
    logs = [
        {"event": "risk", "data": {"reason": "a"}},
        {"event": "risk", "data": {"reason": "a"}},
        {"event": "decision", "data": {}},
    ]
    c = ec.classify(logs)
    assert c["a"] == 2


def test_replay_engine_deterministic() -> None:
    closes = [100.0 + i * 0.1 for i in range(25)]
    bars = [_bar(c, ts=i) for i, c in enumerate(closes)]

    class T:
        def __init__(self) -> None:
            self._symbols = ["G"]
            self.calls = 0

        def feed_data(self, step_data: object) -> None:
            self._replay_feed = step_data

        def run_once(self) -> dict:
            self.calls += 1
            return {"step": self.calls}

    t = T()
    seq = [
        {"G": {"current_price": closes[-1], "bars": bars}},
        {"G": {"current_price": closes[-1], "bars": bars}},
    ]
    r = ReplayEngine().replay(t, seq)
    assert r == [{"step": 1}, {"step": 2}]


def test_scenario_runner_multiple_outputs() -> None:
    class T:
        def __init__(self) -> None:
            self._symbols = ["G"]
            self.n = 0

        def feed_data(self, step_data: object) -> None:
            self._replay_feed = step_data

        def run_once(self) -> dict:
            self.n += 1
            return {"n": self.n}

    t = T()
    seq = [{"G": {"current_price": 100.0, "bars": [_bar(100.0, ts=i) for i in range(25)]}}]
    out = ScenarioRunner().run(t, {"s1": seq, "s2": seq})
    assert set(out.keys()) == {"s1", "s2"}
    assert len(out["s1"]) == 1
    assert len(out["s2"]) == 1
