"""BIST tick ladder."""

from __future__ import annotations

from bist_core.execution.tick_size import get_tick_size, round_to_tick


def test_tick_ladder() -> None:
    assert get_tick_size(5.0) == 0.01
    assert get_tick_size(25.0) == 0.02
    assert get_tick_size(75.0) == 0.05
    assert get_tick_size(150.0) == 0.10


def test_round_to_tick() -> None:
    assert round_to_tick(100.023) == 100.0


def test_zero_price() -> None:
    assert get_tick_size(0.0) == 0.0
    assert round_to_tick(0.0) == 0.0
