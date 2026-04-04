"""BIST-style tick size ladder (deterministic rounding)."""

from __future__ import annotations


def get_tick_size(price: float) -> float:
    if price <= 0:
        return 0.0
    if price < 10:
        return 0.01
    if price < 50:
        return 0.02
    if price < 100:
        return 0.05
    return 0.10


def round_to_tick(price: float) -> float:
    tick = get_tick_size(price)
    if tick <= 0:
        return 0.0
    return round(price / tick) * tick


__all__ = ["get_tick_size", "round_to_tick"]
