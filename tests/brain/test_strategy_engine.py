"""Strategy engine unit tests — indicators, signals, decisions, batch, determinism."""

from __future__ import annotations

import pytest

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.brain.strategy_engine import Decision, StrategyEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bar(ts: str, close: float, high: float | None = None, low: float | None = None) -> OHLCVBar:
    h = high if high is not None else close + 1
    lo = low if low is not None else max(close - 1, 0.01)
    return OHLCVBar(timestamp=ts, symbol="X", open=close, high=h, low=lo, close=close, volume=1_000_000)


def _make_crossover_long_bars() -> list[OHLCVBar]:
    """Build 60 bars where SMA20 crosses above SMA50 at the final bar."""
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
        bars.append(_bar(f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}", round(price, 4)))
    return bars


def _make_crossover_short_bars() -> list[OHLCVBar]:
    """Build 60 bars where SMA20 crosses below SMA50 at the final bar."""
    n = 60
    bars: list[OHLCVBar] = []
    for i in range(n):
        if i < 50:
            price = 100.0 + i * 0.08
        elif i < 58:
            price = 100.0 + 49 * 0.08 - (i - 50) * 0.6
        elif i == 58:
            price = 100.0 + 49 * 0.08 - 8 * 0.6 - 4.0
        else:
            price = 100.0 + 49 * 0.08 - 8 * 0.6 - 4.0 - 4.0
        bars.append(_bar(f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}", round(price, 4)))
    return bars


def _make_flat_bars(n: int = 60, price: float = 100.0) -> list[OHLCVBar]:
    return [_bar(f"2026-01-{i + 1:02d}", price) for i in range(n)]


# ── Compute indicators ───────────────────────────────────────────────────

class TestComputeIndicators:
    def test_compute_indicators_returns_values(self) -> None:
        bars = _make_crossover_long_bars()
        engine = StrategyEngine()
        ind = engine.compute_indicators(bars)
        assert "sma20" in ind
        assert "sma50" in ind
        assert "atr" in ind
        assert ind["sma20"] is not None
        assert ind["sma50"] is not None
        assert ind["atr"] is not None

    def test_compute_indicators_insufficient_bars(self) -> None:
        bars = _make_flat_bars(10)
        engine = StrategyEngine()
        ind = engine.compute_indicators(bars)
        assert ind["sma50"] is None


# ── Signal detection ──────────────────────────────────────────────────────

class TestDetectSignal:
    def test_detect_long_signal(self) -> None:
        bars = _make_crossover_long_bars()
        engine = StrategyEngine(lookback=50)
        signal = engine.detect_signal(bars)
        assert signal == "long"

    def test_detect_short_signal(self) -> None:
        bars = _make_crossover_short_bars()
        engine = StrategyEngine(lookback=50)
        signal = engine.detect_signal(bars)
        assert signal == "short"

    def test_no_signal_returns_none(self) -> None:
        bars = _make_flat_bars(60)
        engine = StrategyEngine(lookback=50)
        signal = engine.detect_signal(bars)
        assert signal is None

    def test_no_signal_insufficient_bars(self) -> None:
        bars = _make_flat_bars(10)
        engine = StrategyEngine(lookback=50)
        assert engine.detect_signal(bars) is None


# ── Decision generation ──────────────────────────────────────────────────

class TestGenerateDecision:
    def test_generate_decision_long(self) -> None:
        bars = _make_crossover_long_bars()
        engine = StrategyEngine(lookback=50, risk_reward=2.0)
        dec = engine.generate_decision("GARAN", bars)
        assert dec is not None
        assert dec.side == "long"
        assert dec.symbol == "GARAN"
        assert dec.entry > 0
        assert dec.stop < dec.entry
        assert dec.target > dec.entry
        assert dec.confidence > 0
        assert "yükseliş" in dec.reasoning
        assert "SMA20" in dec.reasoning

    def test_generate_decision_short(self) -> None:
        bars = _make_crossover_short_bars()
        engine = StrategyEngine(lookback=50, risk_reward=2.0)
        dec = engine.generate_decision("THYAO", bars)
        assert dec is not None
        assert dec.side == "short"
        assert dec.symbol == "THYAO"
        assert dec.stop > dec.entry
        assert dec.target < dec.entry
        assert "düşüş" in dec.reasoning

    def test_generate_decision_none_on_flat(self) -> None:
        bars = _make_flat_bars(60)
        engine = StrategyEngine()
        assert engine.generate_decision("X", bars) is None

    def test_generate_decision_none_insufficient_bars(self) -> None:
        bars = _make_flat_bars(10)
        engine = StrategyEngine()
        assert engine.generate_decision("X", bars) is None

    def test_decision_to_dict(self) -> None:
        bars = _make_crossover_long_bars()
        engine = StrategyEngine(lookback=50)
        dec = engine.generate_decision("ASELS", bars)
        assert dec is not None
        d = dec.to_dict()
        assert d["symbol"] == "ASELS"
        assert "entry" in d
        assert "stop" in d
        assert "target" in d
        assert "side" in d
        assert "confidence" in d
        assert "reasoning" in d
        assert "timestamp" in d


# ── Batch generation ─────────────────────────────────────────────────────

class TestBatchGeneration:
    def test_batch_generation_multiple_symbols(self) -> None:
        engine = StrategyEngine(lookback=50)
        symbol_bars = {
            "GARAN": _make_crossover_long_bars(),
            "THYAO": _make_crossover_short_bars(),
            "FLAT": _make_flat_bars(60),
        }
        decisions = engine.batch_generate(symbol_bars)
        symbols = [d.symbol for d in decisions]
        assert "FLAT" not in symbols
        assert len(decisions) >= 1

    def test_batch_sorted_by_symbol(self) -> None:
        engine = StrategyEngine(lookback=50)
        symbol_bars = {
            "Z_SYM": _make_crossover_long_bars(),
            "A_SYM": _make_crossover_long_bars(),
        }
        decisions = engine.batch_generate(symbol_bars)
        if len(decisions) >= 2:
            assert decisions[0].symbol <= decisions[1].symbol


# ── Determinism ───────────────────────────────────────────────────────────

class TestDeterminism:
    def test_determinism_same_input_same_output(self) -> None:
        bars = _make_crossover_long_bars()
        engine = StrategyEngine(lookback=50, risk_reward=2.0)
        d1 = engine.generate_decision("ASELS", bars)
        d2 = engine.generate_decision("ASELS", bars)
        assert d1 is not None and d2 is not None
        assert d1.to_dict() == d2.to_dict()
