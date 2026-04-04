"""
Market data provider registry: pluggable registration and retrieval of vendors by string key.
Mirrors execution adapter logic: register factories by key; resolve via get_market_data_provider.
Allows external feed integration without touching core (register_market_data_provider).
Each provider must implement the MarketDataProvider interface (symbols, close_map, validate).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from bist_core.market_data.base import MarketDataProvider


_REGISTRY: Dict[str, Callable[..., MarketDataProvider]] = {}

# Static dummy data for test / demo provider (deterministic)
STATIC_DUMMY_SYMBOLS: List[str] = ["DUMMY_A", "DUMMY_B"]
STATIC_DUMMY_CLOSE_MAP: Dict[str, float] = {"DUMMY_A": 100.0, "DUMMY_B": 200.0}


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def register_market_data_provider(name: str, factory: Callable[..., MarketDataProvider]) -> None:
    """
    Register a market data provider factory by string key (pluggable; for external feed integration).
    name: normalized (strip + lower); ValueError if empty.
    factory must return an instance implementing MarketDataProvider.
    factory(*, snapshot_root, **kwargs) -> MarketDataProvider
    """
    normalized = _normalize_name(name)
    if not normalized:
        raise ValueError("market data provider name cannot be empty")
    _REGISTRY[normalized] = factory


def get_market_data_provider(name: str) -> Optional[Callable[..., MarketDataProvider]]:
    """Retrieve the factory for the given string key (normalized). Returns None if not registered."""
    normalized = _normalize_name(name)
    return _REGISTRY.get(normalized)


def list_market_data_providers() -> List[str]:
    """Return sorted list of registered provider keys (for introspection)."""
    return sorted(_REGISTRY.keys())


def _clear_registry_for_tests() -> None:
    """Clear all registered providers. For tests only."""
    _REGISTRY.clear()


# --- Dummy provider with static data (for test purposes and external feed examples) ---


class StaticDummyMarketDataProvider:
    """Dummy provider that returns static dummy data; implements MarketDataProvider for tests."""

    def symbols(self, day: str) -> List[str]:
        return list(STATIC_DUMMY_SYMBOLS)

    def close_map(self, day: str) -> Dict[str, float]:
        return dict(STATIC_DUMMY_CLOSE_MAP)

    def validate(self, day: str) -> tuple[bool, str]:
        return (True, "ok")


def static_dummy_factory(
    *,
    snapshot_root: Optional[Path] = None,
    **kwargs: Any,
) -> MarketDataProvider:
    """Factory for StaticDummyMarketDataProvider; use with register_market_data_provider(\"dummy\", static_dummy_factory)."""
    return StaticDummyMarketDataProvider()
