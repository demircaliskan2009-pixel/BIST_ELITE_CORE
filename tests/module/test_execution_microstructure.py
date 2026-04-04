"""Slippage / spread / latency models — deterministic."""

from __future__ import annotations

from bist_core.execution.latency_model import LatencyModel
from bist_core.execution.slippage_model import SlippageModel
from bist_core.execution.spread_model import SpreadModel


def test_slippage_model() -> None:
    m = SlippageModel()
    assert m.compute(100.0, 0.5) == 100.0 * 0.0005 + 0.5 * 0.1


def test_spread_model() -> None:
    m = SpreadModel()
    assert m.compute(200.0) == 0.2


def test_latency_model() -> None:
    m = LatencyModel()
    assert m.apply(100.0) == 100.0 * 1.0002
