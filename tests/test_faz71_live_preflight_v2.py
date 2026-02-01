"""
FAZ71: Live preflight v2 — config ok, broker config ok, BIST rule tables present, orders_intent present.
Always write execution_result.json deterministically even on failure.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _bist_fixture_dir(tmp_path: Path) -> Path:
    """Create minimal BIST rulespack + restrictions so live preflight passes."""
    d = tmp_path / "bist_fixtures"
    d.mkdir(parents=True, exist_ok=True)
    (d / "tick_sizes.csv").write_text("min_price,max_price,tick\n0,99.99,0.01\n", encoding="utf-8")
    (d / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    (d / "restrictions.json").write_text('{"blocked_symbols": [], "short_sale_ban": false}', encoding="utf-8")
    return d


def _run_eod_execute_live(
    day: str,
    outdir: Path,
    config_path: str | None = None,
    broker_config_path: str | None = None,
    broker: str | None = None,
    bist_rulespack_dir: Path | None = None,
    bist_restrictions_file: Path | None = None,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env.pop("BIST_CORE_CONFIG", None)
    env.pop("BIST_BROKER_CONFIG", None)
    if config_path is not None:
        env["BIST_CORE_CONFIG"] = config_path
    if broker_config_path is not None:
        env["BIST_BROKER_CONFIG"] = broker_config_path
    if bist_rulespack_dir is not None:
        env["BIST_RULESPACK_DIR"] = str(bist_rulespack_dir)
    if bist_restrictions_file is not None:
        env["BIST_RESTRICTIONS_FILE"] = str(bist_restrictions_file)
    cmd = [
        sys.executable, "-m", "bist_core.cli", "eod", "execute",
        "--day", day, "--outdir", str(outdir), "--live",
    ]
    if config_path is not None:
        cmd.extend(["--config", config_path])
    if broker is not None:
        cmd.extend(["--broker", broker])
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)


def test_faz71_config_fail_writes_execution_result(tmp_path: Path) -> None:
    """Live + config missing -> exit 3 and execution_result.json written with ok=False, blocked=True."""
    outdir = tmp_path / "out"
    outdir.mkdir(parents=True, exist_ok=True)
    nonexistent = tmp_path / "no_config.json"
    assert not nonexistent.is_file()
    r = _run_eod_execute_live("2099-01-15", outdir, config_path=str(nonexistent))
    assert r.returncode == 3
    result_path = outdir / "2099-01-15" / "execution_result.json"
    assert result_path.is_file(), "execution_result.json must be written on config failure"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data.get("ok") is False
    assert data.get("blocked") is True
    assert "errors" in data
    assert data.get("day") == "2099-01-15"
    assert data.get("schema_version") == 1


def test_faz71_execution_result_deterministic_schema(tmp_path: Path) -> None:
    """execution_result.json has fixed keys and errors sorted."""
    outdir = tmp_path / "out"
    outdir.mkdir(parents=True, exist_ok=True)
    bad_config = tmp_path / "bad.json"
    bad_config.write_text("{}", encoding="utf-8")
    r = _run_eod_execute_live("2099-01-16", outdir, config_path=str(bad_config))
    result_path = outdir / "2099-01-16" / "execution_result.json"
    assert result_path.is_file()
    data = json.loads(result_path.read_text(encoding="utf-8"))
    expected_keys = {"schema_version", "day", "ok", "blocked", "reason", "provider", "mode", "execution", "errors"}
    assert set(data.keys()) == expected_keys
    assert isinstance(data["errors"], list)
    assert data["errors"] == sorted(data["errors"])


def test_faz71_no_manifest_writes_execution_result(tmp_path: Path) -> None:
    """Live + valid config + broker=paper + BIST fixtures + no pipeline manifest -> execution_result.json written, exit 2."""
    bist_dir = _bist_fixture_dir(tmp_path)
    valid_config = tmp_path / "core.json"
    valid_config.write_text(
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
    outdir = tmp_path / "out"
    outdir.mkdir(parents=True, exist_ok=True)
    r = _run_eod_execute_live(
        "2099-01-17", outdir,
        config_path=str(valid_config), broker="paper",
        bist_rulespack_dir=bist_dir, bist_restrictions_file=bist_dir / "restrictions.json",
    )
    assert r.returncode == 2
    result_path = outdir / "2099-01-17" / "execution_result.json"
    assert result_path.is_file()
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data.get("ok") is False and data.get("blocked") is True
    assert "no_manifest" in (data.get("errors") or [])


def test_faz71_no_orders_intent_writes_execution_result(tmp_path: Path) -> None:
    """Live + manifest present + orders_intent missing -> execution_result.json written, exit 2."""
    bist_dir = _bist_fixture_dir(tmp_path)
    valid_config = tmp_path / "core.json"
    valid_config.write_text(
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
    outdir = tmp_path / "out"
    day = "2099-01-18"
    (outdir / day).mkdir(parents=True, exist_ok=True)
    (outdir / "pipeline_manifest.json").write_text(
        json.dumps({
            "schema_version": 2,
            "day": day,
            "stages": {},
            "orders_intent_path": str(outdir / "orders" / day / "orders_intent.json"),
        }),
        encoding="utf-8",
    )
    r = _run_eod_execute_live(
        day, outdir,
        config_path=str(valid_config), broker="paper",
        bist_rulespack_dir=bist_dir, bist_restrictions_file=bist_dir / "restrictions.json",
    )
    assert r.returncode == 2
    result_path = outdir / day / "execution_result.json"
    assert result_path.is_file()
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data.get("ok") is False
    assert "no_orders_intent" in (data.get("errors") or [])


def test_faz71_broker_config_missing_writes_execution_result(tmp_path: Path) -> None:
    """Live + broker not paper + BIST_BROKER_CONFIG missing -> execution_result.json written, exit 2."""
    valid_config = tmp_path / "core.json"
    valid_config.write_text(
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
    outdir = tmp_path / "out"
    day = "2099-01-19"
    (outdir / day).mkdir(parents=True, exist_ok=True)
    (outdir / "pipeline_manifest.json").write_text(
        json.dumps({"schema_version": 2, "day": day, "stages": {}}),
        encoding="utf-8",
    )
    (outdir / "orders" / day).mkdir(parents=True, exist_ok=True)
    (outdir / "orders" / day / "orders_intent.json").write_text(
        json.dumps({"day": day, "actions": []}),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["BIST_CORE_CONFIG"] = str(valid_config)
    env.pop("BIST_BROKER_CONFIG", None)
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "eod", "execute", "--day", day, "--outdir", str(outdir), "--live", "--execution", "live", "--broker", "stub"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 2
    result_path = outdir / day / "execution_result.json"
    assert result_path.is_file()
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data.get("ok") is False
    assert any("broker" in (e or "").lower() for e in (data.get("errors") or []))
