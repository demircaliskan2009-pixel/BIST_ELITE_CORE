"""FAZ580: Provider selector — default DryRun, real_skeleton fails closed without transport."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bist_core.execution.base import ExecutionProvider
from bist_core.execution.provider_selector import get_execution_provider_from_env
from bist_core.execution.adapters.dry_run import DryRunExecutionProvider
from bist_core.execution.adapters.real_broker_skeleton import RealBrokerExecutionProvider
from bist_core.execution.broker_adapter import StubBrokerAdapter


def test_default_provider_is_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default (BIST_EXEC_PROVIDER unset) => DryRunExecutionProvider."""
    monkeypatch.delenv("BIST_EXEC_PROVIDER", raising=False)
    provider = get_execution_provider_from_env()
    assert isinstance(provider, DryRunExecutionProvider)


def test_default_provider_empty_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """BIST_EXEC_PROVIDER empty => DryRunExecutionProvider."""
    monkeypatch.setenv("BIST_EXEC_PROVIDER", "")
    provider = get_execution_provider_from_env()
    assert isinstance(provider, DryRunExecutionProvider)


def test_real_skeleton_selected_without_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """BIST_EXEC_PROVIDER=real_skeleton => RealBrokerExecutionProvider(transport=None)."""
    monkeypatch.setenv("BIST_EXEC_PROVIDER", "real_skeleton")
    provider = get_execution_provider_from_env()
    assert isinstance(provider, RealBrokerExecutionProvider)


def test_real_skeleton_dry_run_true_validation_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """real_skeleton with dry_run=True => validation only, same as DryRun."""
    monkeypatch.setenv("BIST_EXEC_PROVIDER", "real_skeleton")
    provider = get_execution_provider_from_env()
    orders = {"day": "2025-01-15", "actions": [{"symbol": "ASELS", "side": "BUY"}]}
    result = provider.submit_orders(orders, dry_run=True)
    assert result["ok"] is True
    assert result["broker"] == "real_skeleton"
    assert result["sent"] == 1
    assert "summary" in result.get("details", {})


def test_real_skeleton_dry_run_false_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """real_skeleton without transport, dry_run=False => ok=False, broker_transport_missing."""
    monkeypatch.setenv("BIST_EXEC_PROVIDER", "real_skeleton")
    provider = get_execution_provider_from_env()
    orders = {"day": "2025-01-15", "actions": [{"symbol": "ASELS", "side": "BUY"}]}
    result = provider.submit_orders(orders, dry_run=False)
    assert result["ok"] is False
    assert "broker_transport_missing" in result["errors"]
    assert result["broker"] == "real_skeleton"
    assert result["sent"] == 0


def test_real_skeleton_fail_closed_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same input => same error (deterministic)."""
    monkeypatch.setenv("BIST_EXEC_PROVIDER", "real_skeleton")
    provider = get_execution_provider_from_env()
    orders = {"day": "2025-01-15", "actions": [{"symbol": "X", "side": "BUY"}]}
    r1 = provider.submit_orders(orders, dry_run=False)
    r2 = provider.submit_orders(orders, dry_run=False)
    assert r1["errors"] == r2["errors"]
    assert r1["errors"] == ["broker_transport_missing"]


def test_real_skeleton_with_fixture_transport_offline(tmp_path: Path) -> None:
    """real_skeleton + StubBrokerAdapter (fixture) => offline place_orders works."""
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    fixture_dir.joinpath("place_orders_response.json").write_text(
        json.dumps({"ok": True, "order_ids": ["oid-1"], "fills": [], "errors": []}),
        encoding="utf-8",
    )
    transport = StubBrokerAdapter({"fixture_dir": str(fixture_dir)})
    provider = RealBrokerExecutionProvider(transport=transport)
    orders = {"day": "2025-01-15", "actions": [{"symbol": "ASELS", "side": "BUY"}]}
    result = provider.submit_orders(orders, dry_run=False)
    assert result["ok"] is True
    assert result["broker"] == "real_skeleton"
    assert result["sent"] == 1
    assert result["details"]["order_ids"] == ["oid-1"]


def test_provider_implements_execution_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Selected provider conforms to ExecutionProvider protocol."""
    monkeypatch.setenv("BIST_EXEC_PROVIDER", "real_skeleton")
    provider = get_execution_provider_from_env()
    assert isinstance(provider, ExecutionProvider)
