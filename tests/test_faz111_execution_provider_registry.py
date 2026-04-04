"""FAZ111: Execution provider registry — dynamic registration, retrieval by key, common interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from bist_core.execution.base import ExecutionProvider, execution_result
from bist_core.execution.adapters import resolve_execution_provider
from bist_core.execution.adapters.registry import (
    get_execution_provider,
    list_execution_providers,
    register_execution_provider,
    _clear_registry_for_tests,
)


# --- Basic provider example (must implement ExecutionProvider interface) ---


class DummyExecutionProvider:
    """Basic provider example for testing; implements ExecutionProvider (submit_orders)."""

    def submit_orders(self, orders: Dict[str, Any], *, dry_run: bool = True) -> Dict[str, Any]:
        return execution_result(
            ok=True,
            errors=[],
            broker="dummy",
            sent=0,
            details={"dry_run": dry_run},
        )


def _dummy_factory(
    *,
    broker_config_path: Optional[Path] = None,
    broker_config: Optional[Dict[str, Any]] = None,
    outdir: Optional[Path] = None,
    day: Optional[str] = None,
    broker_name: str = "",
    execution: str = "live",
) -> ExecutionProvider:
    return DummyExecutionProvider()


def test_register_and_resolve_dummy_provider(tmp_path: Path) -> None:
    register_execution_provider("dummy", _dummy_factory)
    try:
        provider, err = resolve_execution_provider(
            execution="live",
            broker_name="dummy",
            broker_config={"x": 1},
            outdir=tmp_path,
            day="2025-01-01",
        )
        assert err is None
        assert provider is not None
        assert isinstance(provider, DummyExecutionProvider)
        result = provider.submit_orders({"actions": []}, dry_run=True)
        assert result.get("broker") == "dummy"
        assert result.get("ok") is True
    finally:
        _clear_registry_for_tests()


def test_unknown_broker_name_fallback_unchanged(tmp_path: Path) -> None:
    """Unknown broker name with config falls back to StubExecutionProvider (existing behavior)."""
    provider, err = resolve_execution_provider(
        execution="live",
        broker_name="unknown_broker_xyz",
        broker_config={"some": "config"},
        outdir=tmp_path,
        day="2025-01-01",
    )
    assert err is None
    assert provider is not None
    from bist_core.execution.adapters.stub_broker import StubExecutionProvider

    assert isinstance(provider, StubExecutionProvider)


def test_live_missing_broker_config_fail_closed() -> None:
    """Live with both broker_config_path and broker_config None returns error (fail-closed)."""
    provider, err = resolve_execution_provider(
        execution="live",
        broker_name="stub",
        broker_config_path=None,
        broker_config=None,
    )
    assert provider is None
    assert err == "live_execution_missing_broker_config"


def test_register_empty_name_raises() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        register_execution_provider("  ", _dummy_factory)
    with pytest.raises(ValueError, match="cannot be empty"):
        register_execution_provider("", _dummy_factory)


def test_get_execution_provider_normalized() -> None:
    register_execution_provider("Dummy", _dummy_factory)
    try:
        assert get_execution_provider("dummy") is _dummy_factory
        assert get_execution_provider("  DUMMY  ") is _dummy_factory
        assert get_execution_provider("unknown_xyz") is None
    finally:
        _clear_registry_for_tests()


def test_retrieve_by_key_and_verify_interface() -> None:
    """Retrieval by string key returns a factory that produces a provider implementing the common interface."""
    register_execution_provider("dummy", _dummy_factory)
    try:
        factory = get_execution_provider("dummy")
        assert factory is not None
        provider = factory(
            broker_config_path=None,
            broker_config={"x": 1},
            outdir=None,
            day="2025-01-01",
            broker_name="dummy",
            execution="live",
        )
        assert isinstance(provider, ExecutionProvider)
        result = provider.submit_orders({"actions": []}, dry_run=True)
        assert result.get("ok") is True
        assert result.get("broker") == "dummy"
    finally:
        _clear_registry_for_tests()


def test_basic_provider_example_implements_interface() -> None:
    """Basic provider example conforms to ExecutionProvider (common interface)."""
    provider = DummyExecutionProvider()
    assert isinstance(provider, ExecutionProvider)
    result = provider.submit_orders({}, dry_run=True)
    assert "ok" in result and "broker" in result and "sent" in result


def test_list_execution_providers() -> None:
    """Dynamic registration is visible via list of keys."""
    _clear_registry_for_tests()
    try:
        assert list_execution_providers() == []
        register_execution_provider("alpha", _dummy_factory)
        register_execution_provider("beta", _dummy_factory)
        assert list_execution_providers() == ["alpha", "beta"]
    finally:
        _clear_registry_for_tests()
