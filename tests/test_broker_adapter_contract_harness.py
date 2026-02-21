"""FAZ578: Broker adapter contract harness — any ExecutionProvider must pass. Dry-run is default safe path."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
if str(_repo / "src") not in sys.path:
    sys.path.insert(0, str(_repo / "src"))

from bist_core.execution import DryRunExecutionProvider
from bist_core.execution.base import ExecutionProvider, execution_result
from tools.broker_harness import run_harness


# --- Contract: ExecutionProvider interface ---

def test_execution_provider_contract_result_shape() -> None:
    """ExecutionResult must have ok, errors, broker, sent, details."""
    result = execution_result(ok=True, errors=[], broker="test", sent=0)
    assert "ok" in result
    assert "errors" in result
    assert "broker" in result
    assert "sent" in result
    assert "details" in result
    assert isinstance(result["errors"], list)
    assert isinstance(result["sent"], int)


def test_dry_run_provider_implements_contract() -> None:
    """DryRunExecutionProvider conforms to ExecutionProvider protocol."""
    provider = DryRunExecutionProvider()
    assert isinstance(provider, ExecutionProvider)


def test_dry_run_provider_submit_returns_contract_shape() -> None:
    """submit_orders returns dict with required keys."""
    provider = DryRunExecutionProvider()
    orders = {"day": "2025-01-15", "actions": [{"symbol": "A", "side": "BUY"}]}
    result = provider.submit_orders(orders, dry_run=True)
    assert "ok" in result
    assert "errors" in result
    assert "broker" in result
    assert "sent" in result
    assert "details" in result
    assert result["broker"] == "dry_run"


# --- Harness: load from file, run DryRun deterministically ---

def test_harness_valid_orders(tmp_path: Path) -> None:
    """Harness with valid orders_intent => exit 0, ok=True."""
    orders_file = tmp_path / "orders_intent.json"
    orders_file.write_text(
        json.dumps({"day": "2025-01-15", "actions": [{"symbol": "ASELS", "side": "BUY"}]}),
        encoding="utf-8",
    )
    exit_code, result = run_harness(orders_file)
    assert exit_code == 0
    assert result["ok"] is True
    assert result["sent"] == 1
    assert "ASELS" in str(result.get("details", {}).get("summary", ""))


def test_harness_invalid_schema(tmp_path: Path) -> None:
    """Harness with invalid schema => exit 1, ok=False."""
    orders_file = tmp_path / "orders_intent.json"
    orders_file.write_text(json.dumps({"day": "2025-01-15"}), encoding="utf-8")  # missing actions
    exit_code, result = run_harness(orders_file)
    assert exit_code == 1
    assert result["ok"] is False
    assert "orders_intent_missing_actions" in result["errors"]


def test_harness_missing_file() -> None:
    """Harness with missing file => exit 2."""
    exit_code, result = run_harness(Path("/nonexistent/orders_intent.json"))
    assert exit_code == 2
    assert result["ok"] is False
    assert "orders_file_not_found" in result["errors"]


def test_harness_deterministic(tmp_path: Path) -> None:
    """Same input => same result (deterministic)."""
    orders_file = tmp_path / "orders_intent.json"
    orders_file.write_text(
        json.dumps({
            "day": "2025-01-15",
            "actions": [{"symbol": "BBB", "side": "BUY"}, {"symbol": "AAA", "side": "SELL"}],
        }),
        encoding="utf-8",
    )
    _, r1 = run_harness(orders_file)
    _, r2 = run_harness(orders_file)
    assert r1["ok"] == r2["ok"]
    assert r1["details"]["summary"] == r2["details"]["summary"]
    assert "symbols=AAA,BBB" in r1["details"]["summary"]


def test_harness_cli_exit_codes(tmp_path: Path) -> None:
    """CLI returns correct exit codes."""
    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps({"day": "2025-01-15", "actions": [{"symbol": "X", "side": "BUY"}]}), encoding="utf-8")
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({}), encoding="utf-8")

    r_valid = subprocess.run(
        [sys.executable, str(_repo / "tools" / "broker_harness.py"), "--orders", str(valid)],
        cwd=str(_repo),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert r_valid.returncode == 0

    r_invalid = subprocess.run(
        [sys.executable, str(_repo / "tools" / "broker_harness.py"), "--orders", str(invalid)],
        cwd=str(_repo),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert r_invalid.returncode == 1
