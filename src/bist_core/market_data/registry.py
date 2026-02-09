"""Market data provider registry: register custom vendors without touching core."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from bist_core.market_data.base import MarketDataProvider


_REGISTRY: Dict[str, Callable[..., MarketDataProvider]] = {}


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def register_market_data_provider(name: str, factory: Callable[..., MarketDataProvider]) -> None:
    """
    Register a market data provider factory by name.
    name: normalized (strip + lower); ValueError if empty or illegal.
    factory(*, snapshot_root, **kwargs) -> MarketDataProvider
    """
    normalized = _normalize_name(name)
    if not normalized:
        raise ValueError("market data provider name cannot be empty")
    _REGISTRY[normalized] = factory


def get_market_data_provider(name: str) -> Optional[Callable[..., MarketDataProvider]]:
    """Return the factory for the given name (normalized), or None if not registered."""
    normalized = _normalize_name(name)
    return _REGISTRY.get(normalized)


def _clear_registry_for_tests() -> None:
    """Clear all registered providers. For tests only."""
    _REGISTRY.clear()
