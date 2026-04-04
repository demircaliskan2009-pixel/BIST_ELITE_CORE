"""Feature registry unit tests."""

from __future__ import annotations

import pytest

from bist_core.features.feature_registry import (
    FEATURE_REGISTRY,
    get_feature,
    list_features,
    register_feature,
)


class TestFeatureRegistry:
    def test_registry_has_standard_features(self) -> None:
        expected = {"sma_20", "sma_50", "ema_20", "rsi_14", "atr_14", "returns", "momentum_20"}
        assert expected.issubset(set(FEATURE_REGISTRY.keys()))

    def test_list_features_sorted(self) -> None:
        features = list_features()
        assert features == sorted(features)

    def test_get_feature_returns_callable(self) -> None:
        fn = get_feature("sma_20")
        assert callable(fn)

    def test_get_feature_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown feature"):
            get_feature("nonexistent_indicator")

    def test_register_custom_feature(self) -> None:
        def custom_fn(bars):
            return [1.0] * len(bars)
        register_feature("test_custom", custom_fn)
        assert "test_custom" in FEATURE_REGISTRY
        assert get_feature("test_custom") is custom_fn
        del FEATURE_REGISTRY["test_custom"]

    def test_registry_returns_correct_feature_function(self) -> None:
        fn = get_feature("returns")
        from bist_core.features.indicator_library import returns
        assert fn is returns
