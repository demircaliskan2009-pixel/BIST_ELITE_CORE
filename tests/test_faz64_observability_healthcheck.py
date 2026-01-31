"""
FAZ64: Structured JSON logging + error taxonomy; CLI healthcheck validates environment + config.
No noisy prints; healthcheck outputs JSON only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bist_core.cli.observability import (
    ERROR_ARGS_REQUIRED,
    ERROR_ARTIFACT_HASH_MISMATCH,
    ERROR_CORE_JSON_MISSING,
    ERROR_REPO_ROOT_MISSING,
    log_struct,
    err_struct,
)


def test_faz64_log_struct_produces_json_line() -> None:
    """log_struct writes one JSON line with level, code, message."""
    import io
    buf = io.StringIO()
    log_struct("error", "TEST_CODE", "test message", stream=buf, extra="value")
    line = buf.getvalue()
    data = json.loads(line.strip())
    assert data["level"] == "error"
    assert data["code"] == "TEST_CODE"
    assert data["message"] == "test message"
    assert data.get("extra") == "value"


def test_faz64_err_struct_produces_error_level() -> None:
    """err_struct writes level=error."""
    import io
    buf = io.StringIO()
    err_struct(ERROR_ARGS_REQUIRED, "missing args", stream=buf)
    data = json.loads(buf.getvalue().strip())
    assert data["level"] == "error"
    assert data["code"] == ERROR_ARGS_REQUIRED


def test_faz64_error_codes_are_stable_strings() -> None:
    """Error taxonomy codes are non-empty strings."""
    assert ERROR_ARGS_REQUIRED == "ARGS_REQUIRED"
    assert ERROR_ARTIFACT_HASH_MISMATCH == "ARTIFACT_HASH_MISMATCH"
    assert ERROR_CORE_JSON_MISSING == "CORE_JSON_MISSING"
    assert ERROR_REPO_ROOT_MISSING == "REPO_ROOT_MISSING"


def test_faz64_healthcheck_outputs_json_only(tmp_path: Path) -> None:
    """healthcheck prints single JSON blob to stdout; no other lines."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    # Point to empty dir so repo_root/core_json fail; we only care about output shape
    env["BIST_CORE_SNAPSHOT_DIR"] = str(tmp_path)
    cmd = [
        sys.executable,
        "-m",
        "bist_core.cli",
        "healthcheck",
    ]
    # Run from tmp_path so REPO_ROOT (from config) may still be project root when config is loaded
    result = subprocess.run(
        cmd,
        env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
    )
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    # No noisy prints: stderr should be empty (healthcheck only prints JSON to stdout)
    assert not stderr
    data = json.loads(stdout)
    assert "schema_version" in data
    assert "ok" in data
    assert "checks" in data
    assert isinstance(data["checks"], list)
    names = {c.get("name") for c in data["checks"]}
    assert "repo_root" in names
    assert "core_json" in names


def test_faz64_healthcheck_schema() -> None:
    """healthcheck JSON has schema_version 1, ok bool, checks with name/code/ok/message."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "healthcheck"],
        env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout.strip())
    assert data["schema_version"] == 1
    assert isinstance(data["ok"], bool)
    for c in data["checks"]:
        assert "name" in c
        assert "code" in c
        assert "ok" in c
        assert "message" in c


def test_faz64_healthcheck_exit_code() -> None:
    """healthcheck exits 0 when ok, 2 when not."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "healthcheck"],
        env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout.strip())
    if data["ok"]:
        assert result.returncode == 0
    else:
        assert result.returncode == 2


def test_faz64_daily_run_uses_error_code_on_missing_args() -> None:
    """daily run with empty outdir emits structured error code to stderr (hits _cmd_daily_run)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    # --outdir "" so argparse passes but _cmd_daily_run rejects and emits err_struct(ERROR_ARGS_REQUIRED)
    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "daily", "run", "--day", "2099-01-01", "--outdir", ""],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    err = result.stderr.strip()
    assert "ARGS_REQUIRED" in err
    lines = [l for l in err.split("\n") if l.strip() and l.strip().startswith("{")]
    if lines:
        data = json.loads(lines[0])
        assert data.get("code") == "ARGS_REQUIRED"
        assert data.get("level") == "error"
