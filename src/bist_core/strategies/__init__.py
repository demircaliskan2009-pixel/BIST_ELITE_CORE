from __future__ import annotations

from bist_core.strategies.base import Strategy
from bist_core.strategies.registry import register_strategy, resolve_strategy, list_strategies
from bist_core.strategies.equal_weight import EqualWeightStrategy
from bist_core.strategies.top_n_by_signal import TopNBySignalStrategy
from bist_core.strategies.deny_all import DenyAllStrategy

register_strategy("equal_weight", EqualWeightStrategy())
register_strategy("top_n_by_signal", TopNBySignalStrategy())
register_strategy("deny_all", DenyAllStrategy())

__all__ = [
    "Strategy",
    "register_strategy",
    "resolve_strategy",
    "list_strategies",
    "EqualWeightStrategy",
    "TopNBySignalStrategy",
    "DenyAllStrategy",
]
