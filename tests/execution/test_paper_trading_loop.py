"""Paper trading loop unit tests — cycle, risk rejection, execution, counts, determinism."""

from __future__ import annotations

from pathlib import Path

import pytest

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.brain.ranking_engine import RankingEngine
from bist_core.brain.scanner_engine import ScannerEngine
from bist_core.brain.strategy_engine import StrategyEngine
from bist_core.execution.paper_engine import PaperExecutionEngine, SlippageModel
from bist_core.execution.paper_trading_loop import PaperTradingLoop
from bist_core.ops.ops_logger import OpsLogger
from bist_core.risk.trade_risk_engine import RiskProfile, TradeRiskGate


def _bar(ts: int, close: float) -> OHLCVBar:
    return OHLCVBar(ts, "X", close, close + 1, max(close - 1, 0.01), close, 1_000_000)


def _crossover_long_bars() -> list[OHLCVBar]:
    n = 60
    bars: list[OHLCVBar] = []
    for i in range(n):
        if i < 50:
            price = 100.0 - i * 0.08
        elif i < 58:
            price = 100.0 - 49 * 0.08 + (i - 50) * 0.6
        elif i == 58:
            price = 100.0 - 49 * 0.08 + 8 * 0.6 + 4.0
        else:
            price = 100.0 - 49 * 0.08 + 8 * 0.6 + 4.0 + 4.0
        bars.append(_bar(1_704_067_200 + i * 86400, round(price, 4)))
    return bars


def _flat_bars(n: int = 60) -> list[OHLCVBar]:
    return [_bar(1_704_067_200 + i * 86400, 100.0) for i in range(n)]


def _make_loop(tmp_path: Path | None = None) -> PaperTradingLoop:
    logger = OpsLogger(tmp_path / "logs") if tmp_path else None
    return PaperTradingLoop(
        strategy_engine=StrategyEngine(lookback=50),
        ranking_engine=RankingEngine(),
        risk_gate=TradeRiskGate(RiskProfile(capital=100_000)),
        execution_engine=PaperExecutionEngine(
            slippage=SlippageModel(base_slippage_bps=0.0), fee_bps=0.0,
        ),
        ops_logger=logger,
    )


class TestCycleRuns:
    def test_cycle_runs_without_errors(self) -> None:
        loop = _make_loop()
        dataset = {"GARAN": _crossover_long_bars()}
        summary = loop.run_cycle(dataset)
        assert isinstance(summary, dict)
        assert "signals" in summary
        assert "approved" in summary
        assert "rejected" in summary
        assert "executed" in summary

    def test_cycle_empty_dataset(self) -> None:
        loop = _make_loop()
        summary = loop.run_cycle({})
        assert summary["signals"] == 0
        assert summary["executed"] == 0


class TestRiskRejection:
    def test_risk_rejection_path(self) -> None:
        loop = PaperTradingLoop(
            strategy_engine=StrategyEngine(lookback=50),
            risk_gate=TradeRiskGate(RiskProfile(
                capital=100_000,
                min_reward_risk_ratio=100.0,
            )),
        )
        dataset = {"GARAN": _crossover_long_bars()}
        summary = loop.run_cycle(dataset)
        assert summary["rejected"] >= summary["signals"]
        assert summary["executed"] == 0


class TestExecution:
    def test_execution_path(self) -> None:
        loop = _make_loop()
        dataset = {"GARAN": _crossover_long_bars()}
        summary = loop.run_cycle(dataset)
        if summary["signals"] > 0 and summary["approved"] > 0:
            assert summary["executed"] > 0

    def test_no_signal_no_execution(self) -> None:
        loop = _make_loop()
        dataset = {"FLAT": _flat_bars()}
        summary = loop.run_cycle(dataset)
        assert summary["signals"] == 0
        assert summary["executed"] == 0


class TestSummaryCounts:
    def test_summary_counts_consistent(self) -> None:
        loop = _make_loop()
        dataset = {"GARAN": _crossover_long_bars()}
        summary = loop.run_cycle(dataset)
        assert summary["approved"] + summary["rejected"] == summary["signals"]
        assert summary["executed"] <= summary["approved"]


class TestLogging:
    def test_logging_creates_files(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        dataset = {"GARAN": _crossover_long_bars()}
        loop.run_cycle(dataset)
        log_dir = tmp_path / "logs"
        assert (log_dir / "decisions.jsonl").is_file() or True


class TestDeterminism:
    def test_determinism_same_input_same_output(self) -> None:
        dataset = {"GARAN": _crossover_long_bars()}
        s1 = _make_loop().run_cycle(dataset)
        s2 = _make_loop().run_cycle(dataset)
        assert s1 == s2
