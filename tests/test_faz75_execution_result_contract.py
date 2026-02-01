"""FAZ75: Single ExecutionResult schema + writer; stable JSON fields and path outdir/<day>/execution_result.json on ALL exit paths."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bist_core.execution.result_writer import (
    EXECUTION_RESULT_FILENAME,
    EXECUTION_RESULT_KEYS,
    EXECUTION_RESULT_SCHEMA_VERSION,
    build_execution_result_payload,
    write_execution_result,
)


def test_execution_result_stable_json_fields() -> None:
    """Payload has exactly schema_version, day, ok, blocked, reason, provider, mode, execution, errors."""
    payload = build_execution_result_payload(
        day="2025-01-15",
        ok=False,
        blocked=True,
        reason="test",
        provider="stub",
        mode="live",
        errors=["a", "b"],
    )
    assert list(payload.keys()) == list(EXECUTION_RESULT_KEYS)
    assert payload["schema_version"] == EXECUTION_RESULT_SCHEMA_VERSION
    assert payload["day"] == "2025-01-15"
    assert payload["ok"] is False
    assert payload["blocked"] is True
    assert payload["reason"] == "test"
    assert payload["provider"] == "stub"
    assert payload["mode"] == "live"
    assert payload["execution"] == "live"
    errs = payload["errors"]
    assert len(errs) == 2 and all(isinstance(e, dict) and e.get("code") in ("a", "b") for e in errs)


def test_execution_result_errors_sorted() -> None:
    """Errors list is always sorted for deterministic output."""
    payload = build_execution_result_payload(
        day="x",
        ok=False,
        blocked=True,
        reason="",
        provider="p",
        mode="live",
        errors=["z", "a", "m"],
    )
    codes = [e.get("code") for e in payload["errors"]]
    assert codes == ["a", "m", "z"]


def test_write_execution_result_path(tmp_path: Path) -> None:
    """write_execution_result writes outdir/<day>/execution_result.json and returns that path."""
    out = write_execution_result(
        tmp_path,
        "2025-01-16",
        ok=True,
        blocked=False,
        reason="",
        provider="paper",
        mode="paper",
    )
    assert out == tmp_path / "2025-01-16" / EXECUTION_RESULT_FILENAME
    assert out.is_file()
    assert (tmp_path / "2025-01-16").is_dir()


def test_write_execution_result_content(tmp_path: Path) -> None:
    """Written file has stable schema and matches build payload."""
    payload = build_execution_result_payload(
        day="2025-01-17",
        ok=False,
        blocked=True,
        reason="bist_rules_missing",
        provider="stub",
        mode="live",
        errors=["tick_missing", "bands_missing"],
    )
    path = write_execution_result(
        tmp_path,
        "2025-01-17",
        ok=payload["ok"],
        blocked=payload["blocked"],
        reason=payload["reason"],
        provider=payload["provider"],
        mode=payload["mode"],
        errors=["tick_missing", "bands_missing"],
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data.keys()) == set(EXECUTION_RESULT_KEYS)
    codes = [e.get("code") for e in data["errors"]]
    assert "bands_missing" in codes and "tick_missing" in codes


def test_fail_closed_config_writes_execution_result(tmp_path: Path) -> None:
    """Live + invalid config -> exit 3, execution_result.json at outdir/<day>/execution_result.json."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env.pop("BIST_CORE_CONFIG", None)
    bad_config = tmp_path / "bad.json"
    bad_config.write_text("{}", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "eod", "execute", "--day", "2025-01-18", "--outdir", str(tmp_path), "--live", "--config", str(bad_config)],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert r.returncode == 3
    result_path = tmp_path / "2025-01-18" / EXECUTION_RESULT_FILENAME
    assert result_path.is_file()
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["ok"] is False
    assert data["blocked"] is True
    assert set(data.keys()) == set(EXECUTION_RESULT_KEYS)


def _valid_core_config() -> dict:
    """Minimal valid core config (schema v1)."""
    return {
        "timezone": "Europe/Istanbul",
        "default_spread_bps_max": 80,
        "default_adv_tl_min": 30000000,
        "default_auction_ratio_max": 0.15,
        "default_price_band_pct": 20.0,
        "risk_per_trade": 0.015,
    }


def test_fail_closed_no_manifest_writes_execution_result(tmp_path: Path) -> None:
    """Live + valid config + broker=paper + BIST rules + no manifest -> exit 2, execution_result.json written."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    config_path = tmp_path / "core.json"
    config_path.write_text(json.dumps(_valid_core_config()), encoding="utf-8")
    env["BIST_CORE_CONFIG"] = str(config_path)
    env.pop("BIST_BROKER_CONFIG", None)
    bist_dir = tmp_path / "bist"
    bist_dir.mkdir()
    (bist_dir / "tick_sizes.csv").write_text("min_price,max_price,tick\n0,99,0.01\n", encoding="utf-8")
    (bist_dir / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    (bist_dir / "restrictions.json").write_text("{}", encoding="utf-8")
    restr = tmp_path / "restrictions.json"
    restr.write_text("{}", encoding="utf-8")
    env["BIST_RULESPACK_DIR"] = str(bist_dir)
    env["BIST_RESTRICTIONS_FILE"] = str(restr)
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "eod", "execute", "--day", "2025-01-19", "--outdir", str(tmp_path), "--live", "--broker", "paper"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert r.returncode == 2
    result_path = tmp_path / "2025-01-19" / EXECUTION_RESULT_FILENAME
    assert result_path.is_file()
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["ok"] is False
    codes = [e.get("code") for e in data.get("errors", []) if isinstance(e, dict)]
    assert "no_manifest" in codes


def test_fail_closed_invalid_manifest_writes_execution_result(tmp_path: Path) -> None:
    """Invalid pipeline manifest (bad JSON) -> exit 2, execution_result.json with errors=['invalid_manifest']."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    config_path = tmp_path / "core.json"
    config_path.write_text(json.dumps(_valid_core_config()), encoding="utf-8")
    env["BIST_CORE_CONFIG"] = str(config_path)
    bist_dir = tmp_path / "bist"
    bist_dir.mkdir()
    (bist_dir / "tick_sizes.csv").write_text("min_price,max_price,tick\n0,99,0.01\n", encoding="utf-8")
    (bist_dir / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    (bist_dir / "restrictions.json").write_text("{}", encoding="utf-8")
    restr = tmp_path / "restrictions.json"
    restr.write_text("{}", encoding="utf-8")
    env["BIST_RULESPACK_DIR"] = str(bist_dir)
    env["BIST_RESTRICTIONS_FILE"] = str(restr)
    day_dir = tmp_path / "2025-01-20"
    day_dir.mkdir(parents=True)
    (day_dir / "pipeline_manifest.json").write_text("not valid json {{{", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "eod", "execute", "--day", "2025-01-20", "--outdir", str(tmp_path), "--live", "--broker", "paper"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert r.returncode == 2
    result_path = tmp_path / "2025-01-20" / EXECUTION_RESULT_FILENAME
    assert result_path.is_file()
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["ok"] is False
    codes = [e.get("code") for e in data.get("errors", []) if isinstance(e, dict)]
    assert "invalid_manifest" in codes


def test_success_writes_execution_result(tmp_path: Path) -> None:
    """Paper execute success -> exit 0, execution_result.json with ok=True."""
    day = "2025-01-21"
    manifest_dir = tmp_path / day
    manifest_dir.mkdir(parents=True)
    manifest_path = manifest_dir / "pipeline_manifest.json"
    manifest_path.write_text(
        json.dumps({"schema_version": 2, "day": day, "stages": {}, "orders_intent_path": str(tmp_path / "orders" / day / "orders_intent.json")}),
        encoding="utf-8",
    )
    orders_dir = tmp_path / "orders" / day
    orders_dir.mkdir(parents=True)
    (orders_dir / "orders_intent.json").write_text(json.dumps({"day": day, "actions": []}), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "eod", "execute", "--day", day, "--outdir", str(tmp_path), "--execution", "paper"],
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    result_path = tmp_path / day / EXECUTION_RESULT_FILENAME
    assert result_path.is_file()
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert data["blocked"] is False
