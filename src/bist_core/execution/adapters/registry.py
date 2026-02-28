"""
Modular execution provider registry: dynamic registration and retrieval of live brokers by string key.
Each provider must implement the ExecutionProvider interface (submit_orders).
Register factories with register_execution_provider; resolve by key with get_execution_provider.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from bist_core.execution.base import ExecutionProvider


_REGISTRY: Dict[str, Callable[..., ExecutionProvider]] = {}


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def register_execution_provider(name: str, factory: Callable[..., ExecutionProvider]) -> None:
    """
    Register an execution provider factory by string key (dynamic registration).
    name: normalized (strip + lower); ValueError if empty.
    factory must return an instance implementing ExecutionProvider.
    factory(*, broker_config_path, broker_config, outdir, day, broker_name, execution) -> ExecutionProvider
    """
    normalized = _normalize_name(name)
    if not normalized:
        raise ValueError("execution provider name cannot be empty")
    _REGISTRY[normalized] = factory


def get_execution_provider(name: str) -> Optional[Callable[..., ExecutionProvider]]:
    """Retrieve the factory for the given string key (normalized). Returns None if not registered."""
    normalized = _normalize_name(name)
    return _REGISTRY.get(normalized)


def list_execution_providers() -> List[str]:
    """Return sorted list of registered provider keys (for introspection)."""
    return sorted(_REGISTRY.keys())


def _clear_registry_for_tests() -> None:
    """Clear all registered providers. For tests only."""
    _REGISTRY.clear()
