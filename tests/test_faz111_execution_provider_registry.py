"""FAZ111: Execution provider registry — register custom live brokers without touching core."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from bist_core.execution.base import ExecutionProvider, execution_result
from bist_core.execution.adapters import resolve_execution_provider
from bist_core.execution.adapters.registry import (
    get_execution_provider,
    register_execution_provider,
    _clear_registry_for_tests,
)


class DummyExecutionProvider:
    """Dummy provider for tests; implements submit_orders."""

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
