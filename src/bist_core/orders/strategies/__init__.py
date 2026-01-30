"""Orders strategy registry: base protocol + resolve_strategy(name). Deterministic top_n + stable ordering."""
from __future__ import annotations

from typing import Any, Dict, List, Protocol


class OrdersStrategy(Protocol):
    """Protocol for order-building strategies: build_intent(day, universe, advice_records, params) -> dict."""

    name: str

    def build_intent(
        self,
        *,
        day: str,
        universe: List[str],
        advice_records: List[Dict[str, Any]],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        ...


_REGISTRY: Dict[str, OrdersStrategy] = {}


def register_strategy(name: str, strategy: OrdersStrategy) -> None:
    _REGISTRY[str(name)] = strategy


def resolve_strategy(name: str) -> OrdersStrategy:
    key = str(name)
    if key not in _REGISTRY:
        raise ValueError(f"UnknownStrategy:{key}")
    return _REGISTRY[key]


def list_strategies() -> List[str]:
    return sorted(_REGISTRY.keys())


# Register built-in strategies (route existing implementations through registry)
from bist_core.strategies.equal_weight import EqualWeightStrategy
from bist_core.strategies.deny_all import DenyAllStrategy
from bist_core.strategies.top_n_by_signal import TopNBySignalStrategy

register_strategy("equal_weight", EqualWeightStrategy())
register_strategy("deny_all", DenyAllStrategy())
register_strategy("top_n_by_signal", TopNBySignalStrategy())


__all__ = [
    "OrdersStrategy",
    "register_strategy",
    "resolve_strategy",
    "list_strategies",
]
