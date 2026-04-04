"""Backtest engine unit tests — replay, equity curve, walk-forward, determinism, metrics."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from bist_core.backtest.backtest_engine import (
    BacktestEngine,
    CostModel,
    OHLCVBar,
    WalkForwardEngine,
    _compute_metrics,
    _split_windows,
)
from bist_core.execution.paper_engine import PaperTrade, SlippageModel
from bist_core.execution.order_state_machine import RiskLimits


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bars(
    symbol: str = "ASELS",
    days: int = 10,
    start_price: float = 100.0,
    daily_return: float = 0.01,
) -> list[OHLCVBar]:
    bars: list[OHLCVBar] = []
    price = start_price
    for i in range(days):
        ts = 1_704_067_200 + i * 86400
        o = round(price, 4)
        c = round(price * (1.0 + daily_return), 4)
        h = round(max(o, c) * 1.005, 4)
        lo = round(min(o, c) * 0.995, 4)
        bars.append(OHLCVBar(
            timestamp=ts,
            symbol=symbol,
            open=o,
            high=h,
            low=lo,
            close=c,
            volume=1_000_000,
        ))
        price = c
    return bars


def _always_buy_decision(
    symbol: str,
    bars: List[OHLCVBar],
    bar_index: int,
) -> Optional[Dict[str, Any]]:
    if bar_index < 1:
        return None
    bar = bars[bar_index]
    return {
        "symbol": symbol,
        "entry": bar.close,
        "stop": round(bar.close * 0.95, 4),
        "target": round(bar.close * 1.10, 4),
        "position_size": 10,
    }


def _never_buy_decision(
    symbol: str,
    bars: List[OHLCVBar],
    bar_index: int,
) -> Optional[Dict[str, Any]]:
    return None


# ── Historical replay ─────────────────────────────────────────────────────

class TestHistoricalReplay:
    def test_basic_replay_returns_result(self) -> None:
        bars = _make_bars(days=5)
        bt = BacktestEngine(
            cost_model=CostModel(slippage=SlippageModel(base_slippage_bps=0.0), commission_bps=0.0, exchange_fee_bps=0.0),
            decision_fn=_always_buy_decision,
        )
        result = bt.run(bars)
        assert "metrics" in result
        assert "equity_curve" in result
        assert "trades" in result
        assert "regime_summary" in result

    def test_no_trades_when_no_decisions(self) -> None:
        bars = _make_bars(days=5)
        bt = BacktestEngine(
            cost_model=CostModel(slippage=SlippageModel(base_slippage_bps=0.0), commission_bps=0.0, exchange_fee_bps=0.0),
            decision_fn=_never_buy_decision,
        )
        result = bt.run(bars)
        assert result["metrics"]["total_trades"] == 0
        assert len(result["trades"]) == 0

    def test_replay_processes_all_bars(self) -> None:
        bars = _make_bars(days=10)
        bt = BacktestEngine(
            cost_model=CostModel(slippage=SlippageModel(base_slippage_bps=0.0), commission_bps=0.0, exchange_fee_bps=0.0),
            decision_fn=_never_buy_decision,
        )
        result = bt.run(bars)
        assert len(result["equity_curve"]) == 10


# ── Equity curve ──────────────────────────────────────────────────────────

class TestEquityCurve:
    def test_equity_curve_length_matches_bars(self) -> None:
        bars = _make_bars(days=7)
        bt = BacktestEngine(
            cost_model=CostModel(slippage=SlippageModel(base_slippage_bps=0.0), commission_bps=0.0, exchange_fee_bps=0.0),
            decision_fn=_always_buy_decision,
        )
        result = bt.run(bars)
        assert len(result["equity_curve"]) == 7

    def test_equity_curve_has_required_fields(self) -> None:
        bars = _make_bars(days=3)
        bt = BacktestEngine(
            cost_model=CostModel(slippage=SlippageModel(base_slippage_bps=0.0), commission_bps=0.0, exchange_fee_bps=0.0),
            decision_fn=_never_buy_decision,
        )
        result = bt.run(bars)
        for pt in result["equity_curve"]:
            assert "timestamp" in pt
            assert "equity" in pt
            assert "close" in pt

    def test_equity_starts_at_initial(self) -> None:
        bars = _make_bars(days=3)
        bt = BacktestEngine(
            cost_model=CostModel(slippage=SlippageModel(base_slippage_bps=0.0), commission_bps=0.0, exchange_fee_bps=0.0),
            initial_equity=50_000.0,
            decision_fn=_never_buy_decision,
        )
        result = bt.run(bars)
        assert result["equity_curve"][0]["equity"] == 50_000.0


# ── Walk-forward windows ─────────────────────────────────────────────────

class TestWalkForwardWindows:
    def test_split_windows_basic(self) -> None:
        timestamps = [f"2026-01-{d:02d}" for d in range(1, 31)]
        windows = _split_windows(timestamps, train_window=10, test_window=5)
        assert len(windows) >= 1
        for w in windows:
            assert w["train_size"] == 10
            assert w["test_size"] == 5
            assert w["train_start"] < w["test_start"]

    def test_split_windows_insufficient_data(self) -> None:
        timestamps = [f"2026-01-{d:02d}" for d in range(1, 5)]
        windows = _split_windows(timestamps, train_window=10, test_window=5)
        assert windows == []

    def test_split_windows_empty(self) -> None:
        assert _split_windows([], 10, 5) == []

    def test_walk_forward_engine_runs(self) -> None:
        bars = _make_bars(days=30)
        wf = WalkForwardEngine(
            train_window=10,
            test_window=5,
            cost_model=CostModel(slippage=SlippageModel(base_slippage_bps=0.0), commission_bps=0.0, exchange_fee_bps=0.0),
            decision_fn=_always_buy_decision,
        )
        result = wf.run(bars)
        assert "windows" in result
        assert "aggregate_metrics" in result
        assert result["num_windows"] >= 1

    def test_walk_forward_no_data(self) -> None:
        wf = WalkForwardEngine(train_window=10, test_window=5)
        result = wf.run([])
        assert result["num_windows"] == 0
        assert result["windows"] == []


# ── Deterministic replay ─────────────────────────────────────────────────

class TestDeterministicReplay:
    def test_identical_runs_produce_identical_results(self) -> None:
        bars = _make_bars(days=10, daily_return=0.02)
        cost = CostModel(slippage=SlippageModel(base_slippage_bps=0.0), commission_bps=0.0, exchange_fee_bps=0.0)

        bt1 = BacktestEngine(cost_model=cost, decision_fn=_always_buy_decision)
        r1 = bt1.run(bars)

        bt2 = BacktestEngine(cost_model=cost, decision_fn=_always_buy_decision)
        r2 = bt2.run(bars)

        assert r1["metrics"] == r2["metrics"]
        assert len(r1["trades"]) == len(r2["trades"])
        for t1, t2 in zip(r1["trades"], r2["trades"]):
            assert t1["symbol"] == t2["symbol"]
            assert t1["entry_price"] == t2["entry_price"]
            assert t1["pnl"] == t2["pnl"]
            assert t1["status"] == t2["status"]

    def test_equity_curve_deterministic(self) -> None:
        bars = _make_bars(days=5)
        cost = CostModel(slippage=SlippageModel(base_slippage_bps=0.0), commission_bps=0.0, exchange_fee_bps=0.0)

        r1 = BacktestEngine(cost_model=cost, decision_fn=_always_buy_decision).run(bars)
        r2 = BacktestEngine(cost_model=cost, decision_fn=_always_buy_decision).run(bars)

        for e1, e2 in zip(r1["equity_curve"], r2["equity_curve"]):
            assert e1["equity"] == e2["equity"]


# ── Metric calculations ──────────────────────────────────────────────────

class TestMetricCalculations:
    def _make_closed_trade(
        self,
        entry: float,
        exit: float,
        stop: float,
        size: int = 10,
    ) -> PaperTrade:
        t = PaperTrade(
            trade_id="x",
            symbol="SYM",
            entry_price=entry,
            stop_price=stop,
            target_price=entry * 1.1,
            position_size=size,
            entry_time="t0",
        )
        t.close(exit, "t1")
        return t

    def test_win_rate_all_winners(self) -> None:
        trades = [
            self._make_closed_trade(100, 110, 95),
            self._make_closed_trade(100, 105, 95),
        ]
        m = _compute_metrics(trades, [{"equity": 100_000}, {"equity": 101_500}], 100_000)
        assert m["win_rate"] == 1.0

    def test_win_rate_mixed(self) -> None:
        trades = [
            self._make_closed_trade(100, 110, 95),
            self._make_closed_trade(100, 90, 95),
        ]
        m = _compute_metrics(trades, [{"equity": 100_000}, {"equity": 100_000}], 100_000)
        assert m["win_rate"] == 0.5

    def test_max_drawdown_from_equity(self) -> None:
        curve = [
            {"equity": 100_000},
            {"equity": 110_000},
            {"equity": 95_000},
            {"equity": 105_000},
        ]
        m = _compute_metrics([], curve, 100_000)
        expected_dd = (110_000 - 95_000) / 110_000
        assert m["max_drawdown"] == pytest.approx(expected_dd, abs=0.001)

    def test_profit_factor(self) -> None:
        trades = [
            self._make_closed_trade(100, 110, 95, size=10),
            self._make_closed_trade(100, 95, 95, size=10),
        ]
        m = _compute_metrics(trades, [{"equity": 100_000}], 100_000)
        assert m["profit_factor"] == pytest.approx(100.0 / 50.0, abs=0.01)

    def test_empty_trades_zero_metrics(self) -> None:
        m = _compute_metrics([], [{"equity": 100_000}], 100_000)
        assert m["total_trades"] == 0
        assert m["win_rate"] == 0.0
        assert m["sharpe_ratio"] == 0.0

    def test_sharpe_ratio_nonzero(self) -> None:
        curve = [
            {"equity": 100_000},
            {"equity": 101_000},
            {"equity": 102_000},
            {"equity": 103_000},
        ]
        trades = [self._make_closed_trade(100, 110, 95)]
        m = _compute_metrics(trades, curve, 100_000)
        assert m["sharpe_ratio"] > 0


# ── Regime summary ────────────────────────────────────────────────────────

class TestRegimeSummary:
    def test_bullish_regime(self) -> None:
        bars = _make_bars(days=10, daily_return=0.02)
        bt = BacktestEngine(
            cost_model=CostModel(slippage=SlippageModel(base_slippage_bps=0.0), commission_bps=0.0, exchange_fee_bps=0.0),
            decision_fn=_never_buy_decision,
        )
        result = bt.run(bars)
        assert result["regime_summary"]["regime"] in ("bullish", "sideways")
        assert result["regime_summary"]["bars_processed"] == 10

    def test_empty_bars(self) -> None:
        bt = BacktestEngine(decision_fn=_never_buy_decision)
        result = bt.run([])
        assert result["regime_summary"]["regime"] == "unknown"


# ── Multi-symbol ──────────────────────────────────────────────────────────

class TestMultiSymbol:
    def test_two_symbols_processed(self) -> None:
        bars_a = _make_bars("ASELS", days=5, daily_return=0.01)
        bars_b = _make_bars("THYAO", days=5, start_price=50.0, daily_return=0.02)
        combined = sorted(bars_a + bars_b, key=lambda b: (b.timestamp, b.symbol))
        bt = BacktestEngine(
            cost_model=CostModel(slippage=SlippageModel(base_slippage_bps=0.0), commission_bps=0.0, exchange_fee_bps=0.0),
            decision_fn=_always_buy_decision,
        )
        result = bt.run(combined)
        assert len(result["equity_curve"]) == 10
        symbols = {t["symbol"] for t in result["trades"]}
        assert "ASELS" in symbols or "THYAO" in symbols
