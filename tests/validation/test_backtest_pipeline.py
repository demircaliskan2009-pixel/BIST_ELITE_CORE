from bist_core.validation.backtest_pipeline import (
    compute_metrics, run_backtest, run_walk_forward, MIN_TRADES_REQUIRED
)
from bist_core.models.ohlcv import OHLCVBar
import math


def _make_trending_bars(n: int, symbol: str = "TEST",
                        start: float = 100.0, step: float = 0.5) -> list[OHLCVBar]:
    bars = []
    price = start
    for i in range(n):
        price += step
        bars.append(OHLCVBar(
            symbol=symbol, open=price - 0.1, high=price + 0.5,
            low=price - 0.5, close=price, volume=100000.0, timestamp=1700000000 + i * 86400
        ))
    return bars


def test_compute_metrics_empty():
    r = compute_metrics([], 100000)
    assert not r["valid"]
    assert r["trades"] == 0


def test_compute_metrics_wins():
    trades = [{"net_pnl": 100.0} for _ in range(10)]
    r = compute_metrics(trades, 100000)
    assert r["win_rate"] == 1.0
    assert r["expectancy"] == 100.0
    assert r["trades"] == 10
    assert r["max_drawdown"] == 0.0


def test_compute_metrics_losses():
    trades = [{"net_pnl": -100.0} for _ in range(10)]
    r = compute_metrics(trades, 100000)
    assert r["win_rate"] == 0.0
    assert r["expectancy"] == -100.0
    assert not r["valid"]


def test_compute_metrics_drawdown():
    trades = [{"net_pnl": 1000.0}, {"net_pnl": -2000.0}, {"net_pnl": 1000.0}] * 3
    r = compute_metrics(trades, 100000)
    assert r["max_drawdown"] > 0


def test_run_backtest_insufficient_bars():
    r = run_backtest("X", [], initial_capital=100000)
    assert not r["valid"]
    assert r["reason"] == "insufficient_bars"


def test_run_backtest_trending():
    bars = _make_trending_bars(300)
    r = run_backtest("TEST", bars, initial_capital=100000, warmup_bars=50)
    assert "trades" in r
    assert "valid" in r
    assert "expectancy" in r
    assert "max_drawdown" in r
    assert isinstance(r["win_rate"], float)


def test_run_walk_forward_insufficient():
    bars = _make_trending_bars(10)
    r = run_walk_forward("X", bars)
    assert not r["valid"]


def test_run_walk_forward_segments():
    bars = _make_trending_bars(400)
    r = run_walk_forward("TEST", bars, train_size=200, test_size=50, step_size=50)
    assert "segments" in r
    assert r["segments"] >= 1
    assert "avg_expectancy" in r
