"""Context engine unit tests — entry validity, missed entry, pullback, regime, determinism."""

from __future__ import annotations

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.brain.context_engine import ContextEngine
from bist_core.brain.regime_engine import RANGE, TREND_DOWN, TREND_UP
from bist_core.brain.strategy_engine import Decision


def _bar(ts: int, close: float) -> OHLCVBar:
    return OHLCVBar(ts, "X", close, close + 1, max(close - 1, 0.01), close, 1_000_000)


def _trending_up_bars(n: int = 60) -> list[OHLCVBar]:
    return [_bar(1_704_067_200 + i * 86400, 100.0 + i * 0.5) for i in range(n)]


def _decision(
    entry: float = 120.0,
    stop: float = 115.0,
    target: float = 130.0,
    side: str = "long",
    symbol: str = "GARAN",
) -> Decision:
    return Decision(
        symbol=symbol, entry=entry, stop=stop, target=target,
        side=side, confidence=1.5, reasoning="test", timestamp=1_704_067_200,
    )


class TestEntryValidity:
    def test_entry_valid_long_close_at_entry(self) -> None:
        bars = _trending_up_bars(60)
        close = bars[-1].close
        dec = _decision(entry=close)
        ctx = ContextEngine().evaluate_context(dec, bars)
        assert ctx is not None
        assert ctx.entry_valid is True

    def test_entry_valid_long_close_slightly_above(self) -> None:
        bars = _trending_up_bars(60)
        close = bars[-1].close
        dec = _decision(entry=close * 0.995)
        ctx = ContextEngine().evaluate_context(dec, bars)
        assert ctx is not None
        assert ctx.entry_valid is True

    def test_entry_invalid_long_close_far_above(self) -> None:
        bars = _trending_up_bars(60)
        close = bars[-1].close
        dec = _decision(entry=close * 0.95)
        ctx = ContextEngine().evaluate_context(dec, bars)
        assert ctx is not None
        assert ctx.entry_valid is False


class TestMissedEntry:
    def test_missed_entry_detection_long(self) -> None:
        bars = _trending_up_bars(60)
        close = bars[-1].close
        dec = _decision(entry=close * 0.90)
        ctx = ContextEngine().evaluate_context(dec, bars)
        assert ctx is not None
        assert ctx.missed_entry is True

    def test_not_missed_when_close_near_entry(self) -> None:
        bars = _trending_up_bars(60)
        close = bars[-1].close
        dec = _decision(entry=close)
        ctx = ContextEngine().evaluate_context(dec, bars)
        assert ctx is not None
        assert ctx.missed_entry is False


class TestPullbackPossible:
    def test_pullback_possible_trend_up_close_below_entry(self) -> None:
        bars = _trending_up_bars(60)
        close = bars[-1].close
        dec = _decision(entry=close + 5.0)
        ctx = ContextEngine().evaluate_context(dec, bars)
        assert ctx is not None
        assert ctx.regime == TREND_UP
        assert ctx.pullback_possible is True

    def test_no_pullback_when_close_above_entry(self) -> None:
        bars = _trending_up_bars(60)
        close = bars[-1].close
        dec = _decision(entry=close - 5.0)
        ctx = ContextEngine().evaluate_context(dec, bars)
        assert ctx is not None
        assert ctx.pullback_possible is False


class TestContextContainsRegime:
    def test_context_contains_regime(self) -> None:
        bars = _trending_up_bars(60)
        dec = _decision(entry=bars[-1].close)
        ctx = ContextEngine().evaluate_context(dec, bars)
        assert ctx is not None
        assert ctx.regime in (TREND_UP, TREND_DOWN, RANGE)

    def test_context_to_dict(self) -> None:
        bars = _trending_up_bars(60)
        dec = _decision(entry=bars[-1].close)
        ctx = ContextEngine().evaluate_context(dec, bars)
        assert ctx is not None
        d = ctx.to_dict()
        assert "symbol" in d
        assert "entry_valid" in d
        assert "missed_entry" in d
        assert "pullback_possible" in d
        assert "trend_strength" in d
        assert "regime" in d

    def test_context_none_insufficient_bars(self) -> None:
        bars = [_bar(1_704_067_200, 100.0)] * 10
        dec = _decision()
        ctx = ContextEngine().evaluate_context(dec, bars)
        assert ctx is None

    def test_context_none_when_regime_fail_closes(self) -> None:
        bars = [_bar(i, 100.0 + ((i % 5) - 2) * 0.55 + i * 0.03) for i in range(60)]
        dec = _decision()
        ctx = ContextEngine().evaluate_context(dec, bars)
        assert ctx is None

    def test_context_none_empty_bars(self) -> None:
        dec = _decision()
        ctx = ContextEngine().evaluate_context(dec, [])
        assert ctx is None


class TestDeterminism:
    def test_context_deterministic(self) -> None:
        bars = _trending_up_bars(60)
        dec = _decision(entry=bars[-1].close)
        engine = ContextEngine()
        c1 = engine.evaluate_context(dec, bars)
        c2 = engine.evaluate_context(dec, bars)
        assert c1 is not None and c2 is not None
        assert c1.to_dict() == c2.to_dict()
