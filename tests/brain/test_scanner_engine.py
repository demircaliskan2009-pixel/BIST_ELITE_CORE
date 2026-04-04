"""Scanner engine unit tests — scan, top-N, empty, determinism."""

from __future__ import annotations

import pytest

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.brain.ranking_engine import RankingEngine
from bist_core.brain.scanner_engine import ScannerEngine, ScanResult
from bist_core.brain.strategy_engine import StrategyEngine


def _bar(ts: int, close: float) -> OHLCVBar:
    return OHLCVBar(
        timestamp=ts, symbol="X", open=close, high=close + 1,
        low=max(close - 1, 0.01), close=close, volume=1_000_000,
    )


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


def _flat_bars(n: int = 60, price: float = 100.0) -> list[OHLCVBar]:
    return [_bar(1_704_067_200 + i * 86400, price) for i in range(n)]


class TestScan:
    def test_scan_generates_signals(self) -> None:
        scanner = ScannerEngine(
            strategy_engine=StrategyEngine(lookback=50),
            ranking_engine=RankingEngine(),
        )
        symbol_bars = {"GARAN": _crossover_long_bars()}
        result = scanner.scan(symbol_bars)
        assert isinstance(result, ScanResult)
        assert len(result.signals) >= 1
        assert result.signals[0].symbol == "GARAN"

    def test_scan_skips_symbols_without_signal(self) -> None:
        scanner = ScannerEngine(
            strategy_engine=StrategyEngine(lookback=50),
            ranking_engine=RankingEngine(),
        )
        symbol_bars = {
            "GARAN": _crossover_long_bars(),
            "FLAT": _flat_bars(),
        }
        result = scanner.scan(symbol_bars)
        symbols = [s.symbol for s in result.signals]
        assert "FLAT" not in symbols
        assert "GARAN" in symbols

    def test_scan_handles_empty_dataset(self) -> None:
        scanner = ScannerEngine()
        result = scanner.scan({})
        assert result.signals == []
        assert result.timestamp == 0

    def test_scan_handles_empty_bars(self) -> None:
        scanner = ScannerEngine()
        result = scanner.scan({"X": []})
        assert result.signals == []


class TestScanTop:
    def test_scan_top_returns_n(self) -> None:
        scanner = ScannerEngine(
            strategy_engine=StrategyEngine(lookback=50),
            ranking_engine=RankingEngine(),
        )
        symbol_bars = {"GARAN": _crossover_long_bars()}
        top = scanner.scan_top(symbol_bars, 1)
        assert len(top) <= 1

    def test_scan_top_zero(self) -> None:
        scanner = ScannerEngine()
        top = scanner.scan_top({"GARAN": _crossover_long_bars()}, 0)
        assert top == []


class TestScanUniverse:
    def test_scan_universe_returns_all(self) -> None:
        scanner = ScannerEngine(
            strategy_engine=StrategyEngine(lookback=50),
            ranking_engine=RankingEngine(),
        )
        result = scanner.scan_universe({"GARAN": _crossover_long_bars()})
        assert len(result) >= 1


class TestScanResult:
    def test_to_dict(self) -> None:
        scanner = ScannerEngine(
            strategy_engine=StrategyEngine(lookback=50),
            ranking_engine=RankingEngine(),
        )
        result = scanner.scan({"GARAN": _crossover_long_bars()})
        d = result.to_dict()
        assert "timestamp" in d
        assert "signals" in d
        assert "count" in d


class TestDeterminism:
    def test_scan_deterministic_order(self) -> None:
        scanner = ScannerEngine(
            strategy_engine=StrategyEngine(lookback=50),
            ranking_engine=RankingEngine(),
        )
        bars = {"GARAN": _crossover_long_bars()}
        r1 = scanner.scan(bars).to_dict()
        r2 = scanner.scan(bars).to_dict()
        assert r1 == r2
