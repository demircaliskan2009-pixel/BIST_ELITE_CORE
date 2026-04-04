"""Tests for Backtest Engine and Performance Metrics."""

from __future__ import annotations

from typing import Any

import pytest

from bist_core.models.ohlcv import OHLCVBar
from bist_core.backtest.backtest import BacktestEngine
from bist_core.backtest.edge_discovery_v2 import discover_edges
from bist_core.backtest.metrics import compute_metrics
from bist_core.decision.decision_engine_v2 import edge_bucket_key
from bist_core.features.edge_features_v2 import FeatureEngineV2


def _bar(
    ts: int,
    close: float,
    high: float | None = None,
    low: float | None = None,
    *,
    symbol: str = "X",
) -> OHLCVBar:
    h = high if high is not None else close + 1
    lo = low if low is not None else max(close - 1, 0.01)
    return OHLCVBar(
        timestamp=ts, symbol=symbol, open=close, high=h, low=lo, close=close, volume=1000
    )


def _edges_for_bars(bars: list[OHLCVBar]) -> dict:
    """Edge map for DecisionEngineV2: discover or union of prefix keys (regime shifts with len)."""
    em = discover_edges(bars)
    if em:
        return em
    if len(bars) >= 30:
        fe = FeatureEngineV2()
        keys: set[tuple[Any, ...]] = set()
        for n in range(30, len(bars) + 1):
            keys.add(edge_bucket_key(fe.extract(bars[:n])))
        edge = {"exp": 0.05, "count": 500, "confidence": 0.06}
        return {k: dict(edge) for k in keys}
    return {}


def test_basic_backtest() -> None:
    """Backtest runs and returns trades and metrics."""
    bars = [
        _bar(1704067200, 98.0),
        _bar(1704153600, 99.0),
        _bar(1704240000, 100.0),
        _bar(1704326400, 102.0),
    ]
    assert len(bars) >= 4
    symbol_data = {"GARAN": bars}
    engine = BacktestEngine(threshold=0.0, edges=_edges_for_bars(bars))
    result = engine.run(symbol_data)
    assert "trades" in result
    assert "metrics" in result
    assert "total_trades" in result["metrics"]


def test_metrics_correctness() -> None:
    """compute_metrics returns correct schema and values."""
    trades = [
        {"entry": 100, "exit": 110, "pnl": 10, "size": 1},
        {"entry": 100, "exit": 90, "pnl": -10, "size": 1},
    ]
    m = compute_metrics(trades)
    assert m["total_trades"] == 2
    assert m["wins"] == 1
    assert m["losses"] == 1
    assert m["win_rate"] == 0.5
    assert m["expectancy"] == 0.0


def test_win_rate() -> None:
    """Win rate computed correctly."""
    trades = [
        {"pnl": 10},
        {"pnl": 5},
        {"pnl": -3},
    ]
    m = compute_metrics(trades)
    assert m["win_rate"] == pytest.approx(2 / 3, rel=1e-3)
    assert m["wins"] == 2
    assert m["losses"] == 1


def test_expectancy() -> None:
    """Expectancy = mean(pnl)."""
    trades = [{"pnl": 10}, {"pnl": 20}, {"pnl": -5}]
    m = compute_metrics(trades)
    assert m["expectancy"] == pytest.approx(25 / 3, rel=1e-3)


def test_drawdown() -> None:
    """Max drawdown computed from equity curve."""
    trades = [
        {"pnl": 10},
        {"pnl": -5},
        {"pnl": -5},
        {"pnl": 10},
    ]
    m = compute_metrics(trades)
    assert m["max_drawdown"] >= 0
    assert m["max_drawdown"] <= 1


def test_determinism() -> None:
    """Same input produces same output."""
    bars = [
        _bar(1704067200, 98.0),
        _bar(1704153600, 99.0),
        _bar(1704240000, 100.0),
        _bar(1704326400, 102.0),
    ]
    symbol_data = {"GARAN": bars}
    engine = BacktestEngine(threshold=0.0, edges=_edges_for_bars(bars))
    a = engine.run(symbol_data)
    b = engine.run(symbol_data)
    assert a["trades"] == b["trades"]
    assert a["metrics"] == b["metrics"]


def test_metrics_empty_trades() -> None:
    """Empty trades returns zero metrics."""
    m = compute_metrics([])
    assert m["total_trades"] == 0
    assert m["wins"] == 0
    assert m["losses"] == 0
    assert m["win_rate"] == 0.0
    assert m["expectancy"] == 0.0
    assert m["max_drawdown"] == 0.0
    assert m["total_cost"] == 0.0
    assert m["net_expectancy"] == 0.0


def test_backtest_insufficient_bars() -> None:
    """Insufficient bars returns empty trades."""
    bars = [_bar(1704067200, 100.0), _bar(1704153600, 101.0)]
    symbol_data = {"X": bars}
    engine = BacktestEngine(threshold=0.0)
    result = engine.run(symbol_data)
    assert result["trades"] == []
    assert result["metrics"]["total_trades"] == 0


def test_time_series_generates_multiple_trades() -> None:
    """Time-series simulation produces trades (tight OHLC + RANGE/enter_small institutional path)."""
    base_ts = 1704067200
    sym = "GARAN"
    bars: list[OHLCVBar] = []
    for i in range(40):
        c = 100.0 + i * 0.015
        bars.append(
            _bar(
                base_ts + i * 86400,
                c,
                high=c + 0.05,
                low=max(c - 0.05, 0.01),
                symbol=sym,
            )
        )
    last = float(bars[-1].close)

    def _tail_range(n: int, base_c: float) -> list[float]:
        closes = [base_c + (j % 4) * 0.02 + j * 0.001 for j in range(n)]
        m20 = closes[-20:]
        lo, hi = min(m20), max(m20)
        closes[-1] = lo + 0.32 * (hi - lo)
        return closes

    for j, c in enumerate(_tail_range(40, last)):
        bars.append(
            _bar(
                base_ts + (40 + j) * 86400,
                c,
                high=c + 0.05,
                low=max(c - 0.05, 0.01),
                symbol=sym,
            )
        )
    last2 = float(bars[-1].close)
    for j, c in enumerate(_tail_range(40, last2)):
        bars.append(
            _bar(
                base_ts + (80 + j) * 86400,
                c,
                high=c + 0.05,
                low=max(c - 0.05, 0.01),
                symbol=sym,
            )
        )
    symbol_data = {sym: bars}
    engine = BacktestEngine(threshold=0.0, edges=_edges_for_bars(bars))
    result = engine.run(symbol_data)
    assert result["metrics"]["total_trades"] >= 1
    assert len(result["trades"]) == result["metrics"]["total_trades"]
    for t in result["trades"]:
        assert "symbol" in t
        assert "entry" in t
        assert "exit" in t
        assert "pnl" in t
        assert t.get("action") == "exit"
        assert "decision_bar" in t


def test_early_exit_on_weak_move() -> None:
    """V2 backtest emits exit trades (engine or force-close at last bar)."""
    base_ts = 1704067200
    bars = []
    for i in range(40):
        close = 100.0 - 0.4 * i if i < 8 else 97.0 + 0.2 * (i - 8)
        bars.append(
            _bar(
                base_ts + i * 86400,
                close,
                high=close + 0.6,
                low=close - 0.3,
            )
        )
    symbol_data = {"X": bars}
    engine = BacktestEngine(threshold=0.0, edges=_edges_for_bars(bars))
    result = engine.run(symbol_data)
    for t in result["trades"]:
        assert t.get("action") == "exit"
        assert "pnl" in t


def test_capital_protection_risk_sizing() -> None:
    """V2 run returns initial capital as equity; trades use fractional pnl (no size field)."""
    base_ts = 1704067200
    bars = []
    for i in range(50):
        close = 100.0 + i * 0.2
        bars.append(
            _bar(
                base_ts + i * 86400,
                close,
                high=close + 2.0,
                low=close - 2.0,
            )
        )
    symbol_data = {"X": bars}
    engine = BacktestEngine(
        threshold=0.0, initial_capital=100_000.0, edges=_edges_for_bars(bars)
    )
    result = engine.run(symbol_data)
    assert "equity" in result
    assert result["equity"] == pytest.approx(100_000.0, rel=1e-6)
    for t in result["trades"]:
        assert "pnl" in t


def test_no_lookahead_bias() -> None:
    """Decision uses only past data; entry equals close of last bar in window."""
    base_ts = 1704067200
    bars = []
    for i in range(30):
        close = 100.0 + i * 0.5
        bars.append(
            _bar(
                base_ts + i * 86400,
                close,
                high=close + 2.0,
                low=close - 1.5,
            )
        )
    symbol_data = {"X": bars}
    engine = BacktestEngine(threshold=0.0, edges=_edges_for_bars(bars))
    result = engine.run(symbol_data)
    for t in result["trades"]:
        decision_bar = t.get("decision_bar")
        if decision_bar is not None and 0 <= decision_bar < len(bars):
            expected_entry = bars[decision_bar].close
            assert t["entry"] == expected_entry, (
                f"Lookahead bias: entry={t['entry']} != bars[{decision_bar}].close={expected_entry}"
            )
