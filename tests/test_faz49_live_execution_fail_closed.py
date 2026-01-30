"""
FAZ49: Broker adapter skeleton + strict dry-run vs live separation (fail-closed).
Test: live without config returns nonzero; paper ok.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_faz49_live_without_config_returns_nonzero(tmp_path: Path) -> None:
    """Live execution without broker config (no BIST_BROKER_CONFIG, no --broker-config) -> exit code != 0."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env.pop("BIST_BROKER_CONFIG", None)
    outdir = tmp_path / "out"
    outdir.mkdir()
    day = "2024-01-01"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "execute",
            "--day",
            day,
            "--outdir",
            str(outdir),
            "--execution",
            "live",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(repo_root),
    )
    assert result.returncode != 0
    assert "live_execution_missing_broker_config" in result.stderr or "blocked" in result.stderr
    exec_path = outdir / day / "execution_result.json"
    assert exec_path.is_file()
    data = json.loads(exec_path.read_text(encoding="utf-8"))
    assert data.get("ok") is False
    assert "live_execution_missing_broker_config" in data.get("errors", [])
    assert data.get("execution") == "live"


def test_faz49_paper_execution_ok(tmp_path: Path) -> None:
    """Paper execution with minimal manifest and orders_intent -> exit code 0."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    outdir = tmp_path / "out"
    outdir.mkdir()
    day = "2024-01-01"
    (outdir / day).mkdir(parents=True, exist_ok=True)
    (outdir / "orders" / day).mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "day": day,
        "stages": {
            "snapshot": {"errors": 0},
            "advice": {"errors": 0},
            "orders": {"errors": 0},
        },
        "orders_intent_path": str(outdir / "orders" / day / "orders_intent.json"),
    }
    (outdir / day / "pipeline_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    orders_intent = {
        "schema_version": 1,
        "day": day,
        "actions": [],
        "notes": [],
    }
    (outdir / "orders" / day / "orders_intent.json").write_text(
        json.dumps(orders_intent, indent=2), encoding="utf-8"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "execute",
            "--day",
            day,
            "--outdir",
            str(outdir),
            "--execution",
            "paper",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(repo_root),
    )
    assert result.returncode == 0
    assert "broker=" in result.stdout or "execute:" in result.stdout
