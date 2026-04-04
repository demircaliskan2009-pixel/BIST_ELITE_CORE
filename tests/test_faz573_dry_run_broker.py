"""FAZ573: Dry-run broker adapter — schema validation, deterministic output, fail-closed."""

from __future__ import annotations

import io


from bist_core.execution import DryRunExecutionProvider
from bist_core.execution.adapters.dry_run import dry_run_validate_and_print


def test_dry_run_schema_validation_fail() -> None:
    """Invalid schema => ok=False, sorted error codes."""
    provider = DryRunExecutionProvider()
    invalid = {"day": "2025-01-15"}  # missing actions
    result = provider.submit_orders(invalid, dry_run=True)
    assert result["ok"] is False
    assert "orders_intent_missing_actions" in result["errors"]
    assert result["broker"] == "dry_run"
    assert result["sent"] == 0


def test_dry_run_schema_validation_missing_day() -> None:
    """Missing day => ok=False."""
    provider = DryRunExecutionProvider()
    invalid = {"actions": [{"symbol": "A", "side": "BUY"}]}
    result = provider.submit_orders(invalid, dry_run=True)
    assert result["ok"] is False
    assert "orders_intent_missing_day" in result["errors"]


def test_dry_run_deterministic_output() -> None:
    """Same input => same summary (symbols sorted)."""
    provider = DryRunExecutionProvider()
    orders = {
        "day": "2025-01-15",
        "actions": [
            {"symbol": "BBB", "side": "BUY"},
            {"symbol": "AAA", "side": "SELL"},
        ],
    }
    r1 = provider.submit_orders(orders, dry_run=True)
    r2 = provider.submit_orders(orders, dry_run=True)
    assert r1["ok"] is True
    assert r2["ok"] is True
    s1 = r1["details"]["summary"]
    s2 = r2["details"]["summary"]
    assert s1 == s2
    assert "symbols=AAA,BBB" in s1


def test_dry_run_fail_closed_gates_blocked() -> None:
    """gates.blocked=True => ok=False."""
    provider = DryRunExecutionProvider()
    orders = {
        "day": "2025-01-15",
        "actions": [{"symbol": "A", "side": "BUY"}],
        "gates": {"ok": False, "blocked": True},
    }
    result = provider.submit_orders(orders, dry_run=True)
    assert result["ok"] is False
    assert "risk_gate_blocked" in result["errors"]


def test_dry_run_valid_orders_ok() -> None:
    """Valid orders => ok=True, sent=N."""
    provider = DryRunExecutionProvider()
    orders = {
        "day": "2025-01-15",
        "actions": [
            {"symbol": "ASELS", "side": "BUY"},
            {"symbol": "GARAN", "side": "BUY"},
        ],
    }
    result = provider.submit_orders(orders, dry_run=True)
    assert result["ok"] is True
    assert result["sent"] == 2
    assert result["broker"] == "dry_run"
    assert "ASELS" in result["details"]["summary"]
    assert "GARAN" in result["details"]["summary"]


def test_dry_run_validate_and_print_standalone() -> None:
    """dry_run_validate_and_print: valid => ok, deterministic."""
    orders = {"day": "2025-01-15", "actions": [{"symbol": "X", "side": "BUY"}]}
    buf = io.StringIO()
    ok, summary = dry_run_validate_and_print(orders, out=buf)
    assert ok is True
    assert "day=2025-01-15" in summary
    assert "symbols=X" in summary
    assert buf.getvalue().strip() == summary
