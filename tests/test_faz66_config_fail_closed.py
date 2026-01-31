"""
FAZ66: Production-grade config loader with strict schema v1.
Tests: missing/invalid config in live mode fail-closed with explicit exit code;
--config and BIST_CORE_CONFIG; paper mode does not require config.
No new deps.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bist_core.config import (
    REPO_ROOT,
    load_core_config_strict,
    resolve_core_config_path,
    CORE_SCHEMA_V1_REQUIRED,
)
from bist_core.cli.observability import ERROR_CONFIG_MISSING, ERROR_CONFIG_INVALID


# ---- Unit: loader and resolver ----

def test_faz66_resolve_config_prefers_arg(tmp_path: Path) -> None:
    """--config (arg) overrides BIST_CORE_CONFIG and default."""
    explicit = tmp_path / "custom.json"
    explicit.write_text("{}", encoding="utf-8")
    env_path = tmp_path / "env.json"
    env_path.write_text("{}", encoding="utf-8")
    prev = os.environ.pop("BIST_CORE_CONFIG", None)
    try:
        os.environ["BIST_CORE_CONFIG"] = str(env_path)
        got = resolve_core_config_path(str(explicit), REPO_ROOT)
        assert got is not None and got == explicit
    finally:
        if prev is not None:
            os.environ["BIST_CORE_CONFIG"] = prev
        else:
            os.environ.pop("BIST_CORE_CONFIG", None)


def test_faz66_resolve_config_uses_env_when_no_arg(tmp_path: Path) -> None:
    """BIST_CORE_CONFIG used when --config not provided."""
    env_path = tmp_path / "env_core.json"
    env_path.write_text("{}", encoding="utf-8")
    prev = os.environ.pop("BIST_CORE_CONFIG", None)
    try:
        os.environ["BIST_CORE_CONFIG"] = str(env_path)
        got = resolve_core_config_path(None, REPO_ROOT)
        assert got is not None and got == env_path
    finally:
        if prev is not None:
            os.environ["BIST_CORE_CONFIG"] = prev
        else:
            os.environ.pop("BIST_CORE_CONFIG", None)


def test_faz66_resolve_config_default_when_no_arg_no_env() -> None:
    """Default repo_root/config/core.json when no arg and no env."""
    prev = os.environ.pop("BIST_CORE_CONFIG", None)
    try:
        got = resolve_core_config_path(None, REPO_ROOT)
        assert got is not None and got == REPO_ROOT / "config" / "core.json"
    finally:
        if prev is not None:
            os.environ["BIST_CORE_CONFIG"] = prev
        else:
            os.environ.pop("BIST_CORE_CONFIG", None)


def test_faz66_load_strict_missing_returns_config_missing(tmp_path: Path) -> None:
    """Missing file -> (None, CONFIG_MISSING)."""
    missing = tmp_path / "nonexistent.json"
    cfg, err = load_core_config_strict(missing)
    assert cfg is None
    assert err == ERROR_CONFIG_MISSING
    cfg2, err2 = load_core_config_strict(None)
    assert cfg2 is None
    assert err2 == ERROR_CONFIG_MISSING


def test_faz66_load_strict_invalid_json_returns_config_invalid(tmp_path: Path) -> None:
    """Invalid JSON file -> (None, CONFIG_INVALID)."""
    bad = tmp_path / "bad.json"
    bad.write_text("{ invalid }", encoding="utf-8")
    cfg, err = load_core_config_strict(bad)
    assert cfg is None
    assert err == ERROR_CONFIG_INVALID


def test_faz66_load_strict_invalid_schema_returns_config_invalid(tmp_path: Path) -> None:
    """Valid JSON but missing required keys or wrong types -> CONFIG_INVALID."""
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    cfg, err = load_core_config_strict(empty)
    assert cfg is None
    assert err == ERROR_CONFIG_INVALID

    wrong_type = tmp_path / "wrong_type.json"
    wrong_type.write_text(json.dumps({"timezone": 123}), encoding="utf-8")
    cfg2, err2 = load_core_config_strict(wrong_type)
    assert cfg2 is None
    assert err2 == ERROR_CONFIG_INVALID


def test_faz66_load_strict_valid_schema_returns_config(tmp_path: Path) -> None:
    """Valid schema v1 -> (dict, None)."""
    valid = tmp_path / "core.json"
    valid.write_text(
        json.dumps({
            "timezone": "Europe/Istanbul",
            "default_spread_bps_max": 80,
            "default_adv_tl_min": 30000000,
            "default_auction_ratio_max": 0.15,
            "default_price_band_pct": 20.0,
            "risk_per_trade": 0.015,
        }),
        encoding="utf-8",
    )
    cfg, err = load_core_config_strict(valid)
    assert err is None
    assert cfg is not None and cfg["timezone"] == "Europe/Istanbul"
    assert set(CORE_SCHEMA_V1_REQUIRED.keys()) <= set(cfg.keys())


# ---- Integration: CLI live mode fail-closed ----

def _run_eod_execute(day: str, outdir: Path, live: bool = False, config_path: str | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    if config_path is not None:
        env["BIST_CORE_CONFIG"] = config_path
    else:
        env.pop("BIST_CORE_CONFIG", None)
    cmd = [
        sys.executable, "-m", "bist_core.cli", "eod", "execute",
        "--day", day, "--outdir", str(outdir),
    ]
    if live:
        cmd.append("--live")
    else:
        cmd.extend(["--execution", "paper"])
    if config_path is not None:
        cmd.extend(["--config", config_path])
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)


def test_faz66_live_missing_config_exit_3(tmp_path: Path) -> None:
    """Live mode with missing config file -> exit 3 and structured error CONFIG_MISSING."""
    nonexistent = tmp_path / "no_such_config.json"
    assert not nonexistent.is_file()
    r = _run_eod_execute("2099-01-01", tmp_path / "out", live=True, config_path=str(nonexistent))
    assert r.returncode == 3
    assert ERROR_CONFIG_MISSING in r.stderr or "CONFIG_MISSING" in r.stderr


def test_faz66_live_invalid_config_exit_3(tmp_path: Path) -> None:
    """Live mode with invalid JSON config -> exit 3 and CONFIG_INVALID."""
    bad = tmp_path / "bad_core.json"
    bad.write_text("{ broken json", encoding="utf-8")
    r = _run_eod_execute("2099-01-01", tmp_path / "out", live=True, config_path=str(bad))
    assert r.returncode == 3
    assert ERROR_CONFIG_INVALID in r.stderr or "CONFIG_INVALID" in r.stderr


def test_faz66_live_invalid_schema_exit_3(tmp_path: Path) -> None:
    """Live mode with valid JSON but invalid schema -> exit 3."""
    empty = tmp_path / "empty_core.json"
    empty.write_text("{}", encoding="utf-8")
    r = _run_eod_execute("2099-01-01", tmp_path / "out", live=True, config_path=str(empty))
    assert r.returncode == 3
    assert ERROR_CONFIG_INVALID in r.stderr or "CONFIG_INVALID" in r.stderr


def test_faz66_live_valid_config_no_exit_3(tmp_path: Path) -> None:
    """Live mode with valid config via --config -> exit not 3 (may be 2 for broker/manifest)."""
    valid = tmp_path / "core.json"
    valid.write_text(
        json.dumps({
            "timezone": "Europe/Istanbul",
            "default_spread_bps_max": 80,
            "default_adv_tl_min": 30000000,
            "default_auction_ratio_max": 0.15,
            "default_price_band_pct": 20.0,
            "risk_per_trade": 0.015,
        }),
        encoding="utf-8",
    )
    r = _run_eod_execute("2099-01-01", tmp_path / "out", live=True, config_path=str(valid))
    assert r.returncode != 3, "valid config must not yield config fail-closed exit code"


def test_faz66_paper_mode_no_config_required(tmp_path: Path) -> None:
    """Paper mode does not require config; must not exit 3 for config."""
    r = _run_eod_execute("2099-01-01", tmp_path / "out", live=False)
    assert r.returncode != 3
