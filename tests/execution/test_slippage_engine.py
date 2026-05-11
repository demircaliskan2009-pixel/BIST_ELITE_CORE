from __future__ import annotations

import pytest

from bist_core.execution.paper_engine import OrderSide
from bist_core.execution.slippage_engine import SlippageEngine
from bist_core.models.ohlcv import OHLCVBar
from bist_core.providers.base import FailClosedError


def _bar(**overrides: object) -> OHLCVBar:
    payload = {
        "timestamp": 1_704_067_200,
        "symbol": "ASELS",
        "open": 100.0,
        "high": 102.0,
        "low": 98.0,
        "close": 101.0,
        "volume": 10_000.0,
    }
    payload.update(overrides)
    return OHLCVBar(**payload)


def test_buy_slippage() -> None:
    engine = SlippageEngine()

    adjusted_price = engine.apply_slippage(100.0, OrderSide.BUY, _bar())

    assert adjusted_price == 101.0


def test_sell_slippage() -> None:
    engine = SlippageEngine()

    adjusted_price = engine.apply_slippage(100.0, OrderSide.SELL, _bar())

    assert adjusted_price == 99.0


def test_deterministic_output() -> None:
    first_engine = SlippageEngine()
    second_engine = SlippageEngine()
    bar = _bar()

    first = first_engine.apply_slippage(100.0, OrderSide.BUY, bar)
    second = second_engine.apply_slippage(100.0, OrderSide.BUY, _bar())

    assert first == second


def test_invalid_spread_fails() -> None:
    engine = SlippageEngine()

    with pytest.raises(FailClosedError, match="invalid_spread"):
        engine.apply_slippage(100.0, OrderSide.BUY, _bar(high=98.0, low=98.0))


def test_invalid_adjusted_price_fails() -> None:
    engine = SlippageEngine()

    with pytest.raises(FailClosedError, match="invalid_slippage_price"):
        engine.apply_slippage(0.2, OrderSide.SELL, _bar(high=100.0, low=98.0))