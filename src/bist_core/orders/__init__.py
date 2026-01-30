"""Orders: strategy registry for building orders_intent."""
from __future__ import annotations

from bist_core.orders.strategies import resolve_strategy, list_strategies

__all__ = ["resolve_strategy", "list_strategies"]
