from __future__ import annotations

from typing import Dict

from bist_core.strategies.base import Strategy


_REGISTRY: Dict[str, Strategy] = {}


def register_strategy(name: str, strategy: Strategy) -> None:
    _REGISTRY[str(name)] = strategy


def resolve_strategy(name: str) -> Strategy:
    key = str(name)
    if key not in _REGISTRY:
        raise ValueError(f"UnknownStrategy:{key}")
    return _REGISTRY[key]


def list_strategies() -> list[str]:
    return sorted(_REGISTRY.keys())
