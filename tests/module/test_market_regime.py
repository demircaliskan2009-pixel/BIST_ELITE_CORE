"""Market regime detection — deterministic."""

from __future__ import annotations

from bist_core.live.market_regime import detect_market_regime


def test_detect_calm() -> None:
    assert detect_market_regime(0.008, 0.02) == "CALM"


def test_detect_trending() -> None:
    assert detect_market_regime(0.025, 0.03) == "TRENDING"


def test_detect_choppy() -> None:
    assert detect_market_regime(0.03, 0.005) == "CHOPPY"
