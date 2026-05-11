"""Brain regime engine unit tests for deterministic PRDV3 labels."""

from __future__ import annotations

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.brain.regime_engine import (LOW_LIQUIDITY, NO_REGIME, RANGE,
                                           TREND_DOWN, TREND_UP, VOLATILE,
                                           MarketRegime, RegimeEngine)


def _bar(ts: int, close: float, spread: float, volume: float) -> OHLCVBar:
    open_price = close - (spread * 0.2)
    high = close + spread
    low = max(close - spread, 0.01)
    return OHLCVBar(ts, "X", open_price, high, low, close, volume)


def _trend_up_bars(n: int = 60, step: float = 0.45, spread: float = 0.55) -> list[OHLCVBar]:
    return [_bar(1_704_067_200 + i * 86400, 100.0 + i * step, spread, 1_000_000.0) for i in range(n)]


def _trend_down_bars(n: int = 60, step: float = 0.45, spread: float = 0.55) -> list[OHLCVBar]:
    return [_bar(1_704_067_200 + i * 86400, 130.0 - i * step, spread, 1_050_000.0) for i in range(n)]


def _range_bars(n: int = 60) -> list[OHLCVBar]:
    closes = [100.0 + ((i % 4) - 1.5) * 0.18 for i in range(n)]
    return [_bar(1_704_067_200 + i * 86400, close, 0.28, 900_000.0) for i, close in enumerate(closes)]


def _volatile_bars(n: int = 60) -> list[OHLCVBar]:
    closes = [100.0 + ((i % 2) * 2 - 1) * 2.8 + (i % 3) * 0.35 for i in range(n)]
    return [_bar(1_704_067_200 + i * 86400, close, 3.6, 1_200_000.0) for i, close in enumerate(closes)]


def _low_liquidity_bars(n: int = 60) -> list[OHLCVBar]:
    bars = []
    for i in range(n):
        volume = 1_000_000.0
        if i >= n - 10:
            volume = 0.0 if i % 2 == 0 else 40_000.0
        bars.append(_bar(1_704_067_200 + i * 86400, 100.0 + (i % 3) * 0.12, 0.35, volume))
    return bars


def _ambiguous_bars(n: int = 60) -> list[OHLCVBar]:
    closes = [100.0 + ((i % 5) - 2) * 0.55 + i * 0.03 for i in range(n)]
    return [_bar(1_704_067_200 + i * 86400, close, 1.05, 850_000.0) for i, close in enumerate(closes)]


def _gentle_up_bars(n: int = 60) -> list[OHLCVBar]:
    return _trend_up_bars(n=n, step=0.10, spread=0.30)


class TestDetectRegime:
    def test_detect_trend_up_regime(self) -> None:
        regime = RegimeEngine().detect_regime(_trend_up_bars())
        assert regime.regime == TREND_UP
        assert regime.confidence > 0.6
        assert regime.sma_fast > regime.sma_slow
        assert "directional persistence" in regime.explanation

    def test_detect_trend_down_regime(self) -> None:
        regime = RegimeEngine().detect_regime(_trend_down_bars())
        assert regime.regime == TREND_DOWN
        assert regime.confidence > 0.6
        assert regime.sma_fast < regime.sma_slow

    def test_detect_range_regime(self) -> None:
        regime = RegimeEngine().detect_regime(_range_bars())
        assert regime.regime == RANGE
        assert regime.confidence > 0.5
        assert "compressed" in regime.explanation

    def test_detect_volatile_regime(self) -> None:
        regime = RegimeEngine().detect_regime(_volatile_bars())
        assert regime.regime == VOLATILE
        assert regime.confidence > 0.5
        assert "realized volatility" in regime.explanation

    def test_detect_low_liquidity_regime(self) -> None:
        regime = RegimeEngine().detect_regime(_low_liquidity_bars())
        assert regime.regime == LOW_LIQUIDITY
        assert regime.confidence > 0.5
        assert "recent volume" in regime.explanation

    def test_fail_closed_returns_no_regime_for_insufficient_bars(self) -> None:
        regime = RegimeEngine().detect_regime(_range_bars(12))
        assert regime.regime == NO_REGIME
        assert regime.confidence == 0.0

    def test_fail_closed_returns_no_regime_for_ambiguous_structure(self) -> None:
        regime = RegimeEngine().detect_regime(_ambiguous_bars())
        assert regime.regime == NO_REGIME
        assert regime.confidence == 0.0

    def test_to_dict_contains_required_explainable_fields(self) -> None:
        regime = RegimeEngine().detect_regime(_trend_up_bars())
        result = regime.to_dict()
        assert result["regime"] == TREND_UP
        assert "confidence" in result
        assert "strength" in result
        assert "explanation" in result
        assert "sma_fast" in result
        assert "sma_slow" in result
        assert "atr_ratio" in result
        assert "recent_volume_ratio" in result

    def test_deterministic_output(self) -> None:
        bars = _trend_up_bars()
        engine = RegimeEngine()
        assert engine.detect_regime(bars).to_dict() == engine.detect_regime(bars).to_dict()

    def test_hysteresis_keeps_previous_trend_on_marginal_softening(self) -> None:
        engine = RegimeEngine()
        previous = engine.detect_regime(_trend_up_bars())
        softened = engine.detect_regime(_gentle_up_bars(), previous_regime=previous)
        assert previous.regime == TREND_UP
        assert softened.regime == TREND_UP
        assert "hysteresis_hold" in softened.explanation

    def test_transition_switches_when_new_regime_is_clear(self) -> None:
        previous = MarketRegime(
            regime=RANGE,
            confidence=0.62,
            explanation="seed",
            timestamp=1_704_067_200,
            metrics=RegimeEngine().detect_regime(_range_bars()).metrics,
        )
        switched = RegimeEngine().detect_regime(_trend_up_bars(), previous_regime=previous)
        assert switched.regime == TREND_UP
        assert "switched_from_RANGE" in switched.explanation
