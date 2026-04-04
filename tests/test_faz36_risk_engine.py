"""FAZ36: Risk engine + rules schema â€” rules load, block on missing/invalid, allow on valid."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_faz36_rules_load_valid(tmp_path: Path) -> None:
    """Valid risk rules JSON loads with no errors."""
    from bist_core.risk import load_risk_rules, validate_risk_rules

    rules_file = tmp_path / "risk.json"
    rules_file.write_text(
        json.dumps({"schema_version": 1, "max_positions": 10, "max_names": 5}),
        encoding="utf-8",
    )
    rules, errors = load_risk_rules(rules_file)
    assert errors == []
    assert rules is not None
    assert rules.get("schema_version") == 1
    assert rules.get("max_positions") == 10
    assert validate_risk_rules(rules) == []


def test_faz36_block_on_missing(tmp_path: Path) -> None:
    """When risk rules path is set but file is missing, orders are blocked (fail-closed)."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env.pop("BIST_CORE_RISK_RULES", None)

    snapshot_root = tmp_path / "snapshots"
    day = "2099-04-01"
    (snapshot_root / day).mkdir(parents=True)
    (snapshot_root / day / "snapshot.csv").write_text("symbol,close\nAAA,1.0\n", encoding="utf-8")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    missing_rules = tmp_path / "nonexistent_risk_rules.json"
    assert not missing_rules.exists()

    outdir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "run",
            "--day",
            day,
            "--outdir",
            str(outdir),
            "--ignore-calendar",
            "--emit-orders",
            "--risk-rules-file",
            str(missing_rules),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0
    orders_path = outdir / "orders" / day / "orders_intent.json"
    assert orders_path.is_file()
    payload = json.loads(orders_path.read_text(encoding="utf-8"))
    assert payload["actions"] == []
    assert "risk_rules_file_missing" in payload.get("notes", [])

    manifest = json.loads((outdir / "_pipeline_manifest.json").read_text(encoding="utf-8"))
    assert manifest["stages"]["orders"]["ok"] == 0
    assert "risk_rules_file_missing" in manifest["stages"]["orders"]["notes"]


def test_faz36_block_on_invalid(tmp_path: Path) -> None:
    """When risk rules file has invalid schema, orders are blocked (fail-closed)."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env.pop("BIST_CORE_RISK_RULES", None)

    snapshot_root = tmp_path / "snapshots"
    day = "2099-04-02"
    (snapshot_root / day).mkdir(parents=True)
    (snapshot_root / day / "snapshot.csv").write_text("symbol,close\nAAA,1.0\n", encoding="utf-8")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    invalid_rules = tmp_path / "risk_invalid.json"
    invalid_rules.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")

    outdir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "run",
            "--day",
            day,
            "--outdir",
            str(outdir),
            "--ignore-calendar",
            "--emit-orders",
            "--risk-rules-file",
            str(invalid_rules),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0
    orders_path = outdir / "orders" / day / "orders_intent.json"
    assert orders_path.is_file()
    payload = json.loads(orders_path.read_text(encoding="utf-8"))
    assert payload["actions"] == []
    assert "risk_rules_schema_version" in payload.get("notes", [])

    manifest = json.loads((outdir / "_pipeline_manifest.json").read_text(encoding="utf-8"))
    assert manifest["stages"]["orders"]["ok"] == 0
    assert "risk_rules_schema_version" in manifest["stages"]["orders"]["notes"]


def test_faz36_allow_on_valid(tmp_path: Path) -> None:
    """When risk rules are valid and orders within limits (or no limits), orders are allowed."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env.pop("BIST_CORE_RISK_RULES", None)

    snapshot_root = tmp_path / "snapshots"
    day = "2099-04-03"
    (snapshot_root / day).mkdir(parents=True)
    (snapshot_root / day / "snapshot.csv").write_text(
        "symbol,close\nAAA,1.0\nBBB,2.0\n",
        encoding="utf-8",
    )
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    valid_rules = tmp_path / "risk_valid.json"
    valid_rules.write_text(
        json.dumps({"schema_version": 1, "max_positions": 10, "max_names": 5}),
        encoding="utf-8",
    )

    outdir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "run",
            "--day",
            day,
            "--outdir",
            str(outdir),
            "--ignore-calendar",
            "--emit-orders",
            "--risk-rules-file",
            str(valid_rules),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0
    orders_path = outdir / "orders" / day / "orders_intent.json"
    assert orders_path.is_file()
    json.loads(orders_path.read_text(encoding="utf-8"))

    manifest = json.loads((outdir / "_pipeline_manifest.json").read_text(encoding="utf-8"))
    assert manifest["stages"]["orders"]["ok"] == 1


def test_faz36_validate_max_positions_blocks(tmp_path: Path) -> None:
    """When risk rules set max_positions=0, any actions are blocked by risk engine."""
    from bist_core.risk import validate_orders_intent

    rules = {"schema_version": 1, "max_positions": 0}
    intent = {
        "schema_version": 1,
        "day": "2099-04-04",
        "actions": [
            {"symbol": "AAA", "side": "BUY", "weight": 0.5},
            {"symbol": "BBB", "side": "BUY", "weight": 0.5},
        ],
        "notes": [],
    }
    allowed, notes = validate_orders_intent(intent, rules)
    assert allowed is False
    assert "risk_max_positions_exceeded" in notes
