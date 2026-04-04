"""Feature engine unit tests."""

from __future__ import annotations

import pytest

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.features.feature_engine import RegistryFeatureEngine


def _bars(n: int = 25, start_price: float = 100.0) -> list[OHLCVBar]:
    bars: list[OHLCVBar] = []
    price = start_price
    for i in range(n):
        c = round(price + (i % 3) * 0.5, 4)
        bars.append(OHLCVBar(
            timestamp=1_704_067_200 + i * 86400,
            symbol="X",
            open=c - 0.5,
            high=c + 1,
            low=c - 1,
            close=c,
            volume=1_000_000,
        ))
        price = c
    return bars


class TestComputeSingleFeature:
    def test_feature_engine_computes_single_feature(self) -> None:
        engine = RegistryFeatureEngine()
        bars = _bars()
        result = engine.compute_feature(bars, "sma_20")
        assert len(result) == len(bars)
        assert result[19] is not None

    def test_returns_feature(self) -> None:
        engine = RegistryFeatureEngine()
        bars = _bars(5)
        result = engine.compute_feature(bars, "returns")
        assert result[0] is None
        assert len(result) == 5


class TestComputeMultipleFeatures:
    def test_feature_engine_computes_multiple_features(self) -> None:
        engine = RegistryFeatureEngine()
        bars = _bars()
        result = engine.compute_features(bars, ["sma_20", "returns", "rsi_14"])
        assert "sma_20" in result
        assert "returns" in result
        assert "rsi_14" in result
        for key in result:
            assert len(result[key]) == len(bars)


class TestFeatureFrame:
    def test_feature_frame_contains_timestamp_and_features(self) -> None:
        engine = RegistryFeatureEngine()
        bars = _bars(10)
        frame = engine.compute_feature_frame(bars, ["returns", "sma_20"])
        assert len(frame) == 10
        for row in frame:
            assert "timestamp" in row
            assert "returns" in row
            assert "sma_20" in row

    def test_feature_frame_sorted_by_timestamp(self) -> None:
        engine = RegistryFeatureEngine()
        bars = _bars(10)
        frame = engine.compute_feature_frame(bars, ["returns"])
        timestamps = [r["timestamp"] for r in frame]
        assert timestamps == sorted(timestamps)


class TestFailClosed:
    def test_feature_engine_unknown_feature_raises_error(self) -> None:
        engine = RegistryFeatureEngine()
        bars = _bars(5)
        with pytest.raises(KeyError, match="Unknown feature"):
            engine.compute_feature(bars, "does_not_exist")

    def test_compute_features_unknown_raises(self) -> None:
        engine = RegistryFeatureEngine()
        bars = _bars(5)
        with pytest.raises(KeyError):
            engine.compute_features(bars, ["returns", "bogus"])


class TestDeterminism:
    def test_deterministic_output_same_input_same_features(self) -> None:
        engine = RegistryFeatureEngine()
        bars = _bars()
        r1 = engine.compute_features(bars, ["sma_20", "rsi_14", "returns"])
        r2 = engine.compute_features(bars, ["sma_20", "rsi_14", "returns"])
        assert r1 == r2

    def test_frame_deterministic(self) -> None:
        engine = RegistryFeatureEngine()
        bars = _bars()
        f1 = engine.compute_feature_frame(bars, ["sma_20", "returns"])
        f2 = engine.compute_feature_frame(bars, ["sma_20", "returns"])
        assert f1 == f2
