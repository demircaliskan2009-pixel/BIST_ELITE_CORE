"""
FAZ118: CLI doctor command for production readiness.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz118_doctor_offline_ok_in_minimal_repo(tmp_path: Path) -> None:
    """doctor offline passes in minimal tmp repo with config and scripts."""
    # Create minimal repo structure
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "core.json").write_text(
        '{"timezone":"Europe/Istanbul","default_spread_bps_max":80,"default_adv_tl_min":30000000,'
        '"default_auction_ratio_max":0.15,"default_price_band_pct":20.0,"risk_per_trade":0.015}',
        encoding="utf-8",
    )
    (tmp_path / "tools").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tools" / "clean_repo.ps1").write_text("# clean_repo\nRemove-Item -Recurse __pycache__", encoding="utf-8")
    (tmp_path / "tools" / "proof_pack.ps1").write_text("# proof_pack\npytest", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "doctor", "--repo", str(tmp_path), "--mode", "offline"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout} stderr={result.stderr}"
    assert "repo_root" in result.stdout or "PASS" in result.stdout
    assert "core_json" in result.stdout or "ok" in result.stdout


def test_faz118_doctor_offline_json(tmp_path: Path) -> None:
    """doctor --json outputs valid schema with checks."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "core.json").write_text(
        '{"timezone":"Europe/Istanbul","default_spread_bps_max":80,"default_adv_tl_min":30000000,'
        '"default_auction_ratio_max":0.15,"default_price_band_pct":20.0,"risk_per_trade":0.015}',
        encoding="utf-8",
    )
    (tmp_path / "tools").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tools" / "clean_repo.ps1").write_text("# clean", encoding="utf-8")
    (tmp_path / "tools" / "proof_pack.ps1").write_text("# proof", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "doctor", "--repo", str(tmp_path), "--json"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "schema_version" in data
    assert "ok" in data
    assert "checks" in data
    names = {c.get("name") for c in data["checks"]}
    assert "repo_root" in names
    assert "core_json" in names
    assert "script_clean_repo" in names
    assert "script_proof_pack" in names


def test_faz118_doctor_openai_without_key_exit_2(tmp_path: Path) -> None:
    """doctor openai without OPENAI_API_KEY => exit 2, contains PowerShell hint, no secret value."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "core.json").write_text(
        '{"timezone":"Europe/Istanbul","default_spread_bps_max":80,"default_adv_tl_min":30000000,'
        '"default_auction_ratio_max":0.15,"default_price_band_pct":20.0,"risk_per_trade":0.015}',
        encoding="utf-8",
    )
    (tmp_path / "tools").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tools" / "clean_repo.ps1").write_text("# clean", encoding="utf-8")
    (tmp_path / "tools" / "proof_pack.ps1").write_text("# proof", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_ALLOW_NETWORK"] = "1"
    env.pop("OPENAI_API_KEY", None)

    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "doctor", "--repo", str(tmp_path), "--mode", "openai"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    out = result.stdout + result.stderr
    assert "$env:OPENAI_API_KEY" in out or "OPENAI_API_KEY" in out
    # Must NOT contain any actual secret (e.g. sk-xxx from env)
    assert "sk-" not in out or "sk-..." in out


def test_faz118_doctor_openai_without_key_no_secret_leak(tmp_path: Path) -> None:
    """Ensure we never print API key value even when set (redaction)."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "core.json").write_text(
        '{"timezone":"Europe/Istanbul","default_spread_bps_max":80,"default_adv_tl_min":30000000,'
        '"default_auction_ratio_max":0.15,"default_price_band_pct":20.0,"risk_per_trade":0.015}',
        encoding="utf-8",
    )
    (tmp_path / "tools").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tools" / "clean_repo.ps1").write_text("# clean", encoding="utf-8")
    (tmp_path / "tools" / "proof_pack.ps1").write_text("# proof", encoding="utf-8")

    secret_key = "sk-proj-abc123secret456"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_ALLOW_NETWORK"] = "1"
    env["OPENAI_API_KEY"] = secret_key

    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "doctor", "--repo", str(tmp_path), "--mode", "openai"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = result.stdout + result.stderr
    assert secret_key not in out, "API key must never appear in output"
