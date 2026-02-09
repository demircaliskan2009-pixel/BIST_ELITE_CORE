"""Execution provider registry: register custom live brokers without touching core."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from bist_core.execution.base import ExecutionProvider


_REGISTRY: Dict[str, Callable[..., ExecutionProvider]] = {}


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def register_execution_provider(name: str, factory: Callable[..., ExecutionProvider]) -> None:
    """
    Register a live execution provider factory by name.
    name: normalized (strip + lower); ValueError if empty or illegal.
    factory(*, broker_config_path, broker_config, outdir, day, broker_name, execution) -> ExecutionProvider
    """
    normalized = _normalize_name(name)
    if not normalized:
        raise ValueError("execution provider name cannot be empty")
    _REGISTRY[normalized] = factory


def get_execution_provider(name: str) -> Optional[Callable[..., ExecutionProvider]]:
    """Return the factory for the given name (normalized), or None if not registered."""
    normalized = _normalize_name(name)
    return _REGISTRY.get(normalized)


def _clear_registry_for_tests() -> None:
    """Clear all registered providers. For tests only."""
    _REGISTRY.clear()
