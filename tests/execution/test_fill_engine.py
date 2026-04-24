from __future__ import annotations

import pytest

from bist_core.execution.broker_adapter import BrokerResponse, OrderStatus
from bist_core.execution.fill_engine import FillEngine
from bist_core.execution.order_state_machine import Order, OrderState
from bist_core.execution.paper_engine import OrderSide
from bist_core.models.ohlcv import OHLCVBar
from bist_core.providers.base import FailClosedError


def _order(**overrides: object) -> Order:
    payload = {
        "order_id": "ORD-0001",
        "symbol": "ASELS",
        "side": OrderSide.BUY,
        "quantity": 50,
        "filled_quantity": 0,
        "price": 100.0,
        "state": OrderState.SENT,
        "timestamp": 1,
        "last_update": 2,
    }
    payload.update(overrides)
    return Order(**payload)


def _bar(**overrides: object) -> OHLCVBar:
    payload = {
        "timestamp": 1_704_067_200,
        "symbol": "ASELS",
        "open": 99.0,
        "high": 101.0,
        "low": 98.0,
        "close": 100.0,
        "volume": 10_000.0,
    }
    payload.update(overrides)
    return OHLCVBar(**payload)


def test_full_fill() -> None:
    engine = FillEngine()

    response = engine.simulate_fill(_order(quantity=50, price=100.0), _bar(volume=10_000.0))

    assert response == BrokerResponse(
        order_id="ORD-0001",
        status=OrderStatus.FILLED,
        filled_quantity=50,
        avg_price=100.0,
        timestamp=1_704_067_200,
        reason=None,
    )


def test_partial_fill() -> None:
    engine = FillEngine()

    response = engine.simulate_fill(_order(quantity=120, price=100.0), _bar(volume=5_000.0))

    assert response is not None
    assert response.status is OrderStatus.PARTIALLY_FILLED
    assert response.filled_quantity == 50
    assert response.avg_price == 100.0


def test_no_fill_case() -> None:
    engine = FillEngine()

    response = engine.simulate_fill(_order(price=97.0), _bar(low=98.0, high=101.0))

    assert response is None


def test_invalid_data_fails() -> None:
    engine = FillEngine()

    with pytest.raises(FailClosedError, match="invalid_market_bar:negative_volume"):
        engine.simulate_fill(_order(), _bar(volume=-1.0))

    with pytest.raises(FailClosedError, match="invalid_market_bar:high_bound"):
        engine.simulate_fill(_order(), _bar(open=100.0, high=99.0, low=98.0, close=100.0))


def test_deterministic_output() -> None:
    first_engine = FillEngine()
    second_engine = FillEngine()
    order = _order(quantity=120, price=100.0)
    bar = _bar(volume=5_000.0)

    first = first_engine.simulate_fill(order, bar)
    second = second_engine.simulate_fill(_order(quantity=120, price=100.0), _bar(volume=5_000.0))

    assert first == second