"""CLI surface golden proof — behavior preserved for refactors.

BEFORE any multi-module refactor: capture CLI structure and output schema.
Refactor phases must keep these invariants. Proof type: golden_output.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    e["PYTHONPATH"] = str(_project_root() / "src")
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, "-m", "bist_core.cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=e,
        timeout=15,
    )


# Golden: top-level subcommands (order may vary in help, we check presence)
EXPECTED_SUBCOMMANDS = frozenset({
    "info",
    "healthcheck",
    "doctor",
    "eod",
    "daily",
    "plan",
    "orders",
    "broker",
    "backtest",
    "rules",
    "data",
    "ask",
    "scan",
    "evaluate-outcomes",
    "performance-report",
    "dossier",
    "events",
    "instruments",
    "market-data",
    "corporate-actions",
})


def test_cli_surface_subcommands_preserved() -> None:
    """Golden: CLI --help must list all expected subcommands."""
    result = _run_cli(["--help"])
    assert result.returncode == 0
    # Parse subcommands from usage line: {info,healthcheck,...}
    match = re.search(r"\{([^}]+)\}", result.stdout)
    assert match, "No subcommand list in --help"
    listed = {s.strip() for s in match.group(1).split(",")}
    assert EXPECTED_SUBCOMMANDS == listed, f"Subcommands changed: expected {EXPECTED_SUBCOMMANDS}, got {listed}"


def test_cli_info_json_schema_preserved(tmp_path: Path) -> None:
    """Golden: info --json must have required keys (schema invariant)."""
    registry_path = tmp_path / "registry.json"
    registry_path.write_text("{}", encoding="utf-8")
    result = _run_cli(["info", "--json"], env={"BIST_CORE_REGISTRY_PATH": str(registry_path)})
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    required = {"registry_path", "datasets", "symbols"}
    assert required.issubset(payload.keys()), f"info --json missing keys: {required - payload.keys()}"


def test_cli_healthcheck_schema_preserved() -> None:
    """Golden: healthcheck output must be object with checks array (name, ok, code per item)."""
    result = _run_cli(["healthcheck"])
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "checks" in payload
    checks = payload["checks"]
    assert isinstance(checks, list)
    for c in checks:
        assert "name" in c
        assert "ok" in c
        assert "code" in c
