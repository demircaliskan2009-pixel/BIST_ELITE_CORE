"""FAZ86: Rulespack validator — tick/bands/vbts/restrictions required; missing -> exit 2 + execution_result.json."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bist_core.rules.validator import validate_rulespack


def test_faz86_validator_missing_rulespack_returns_errors(tmp_path: Path) -> None:
    """validate_rulespack with nonexistent rulespack dir -> errors contain bist_rules_tick_bands_missing."""
    ok, errors = validate_rulespack(rulespack_dir=tmp_path / "nonexistent", restrictions_path=tmp_path / "nonexistent.json")
    assert ok is False
    assert "bist_rules_tick_bands_missing" in errors


def test_faz86_validator_missing_restrictions_returns_errors(tmp_path: Path) -> None:
    """validate_rulespack with nonexistent restrictions path -> errors contain bist_rules_vbts_missing."""
    (tmp_path / "bist").mkdir()
    (tmp_path / "bist" / "tick_sizes.csv").write_text("min_price,max_price,tick\n0,99,0.01\n", encoding="utf-8")
    (tmp_path / "bist" / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    ok, errors = validate_rulespack(rulespack_dir=tmp_path / "bist", restrictions_path=tmp_path / "nonexistent_restrictions.json")
    assert ok is False
    assert "bist_rules_vbts_missing" in errors


def test_faz86_live_execute_missing_rules_exit_2_and_execution_result(tmp_path: Path) -> None:
    """Live execute with missing rulespack/restrictions -> exit 2 and execution_result.json written with errors[]."""
    day = "2099-04-01"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    (tmp_path / "core.json").write_text(
        json.dumps({"timezone": "Europe/Istanbul", "default_spread_bps_max": 80, "default_adv_tl_min": 30000000, "default_auction_ratio_max": 0.15, "default_price_band_pct": 20.0, "risk_per_trade": 0.015}),
        encoding="utf-8",
    )
    env["BIST_CORE_CONFIG"] = str(tmp_path / "core.json")
    env["BIST_RULESPACK_DIR"] = str(tmp_path / "nonexistent_rulespack")
    env["BIST_RESTRICTIONS_FILE"] = str(tmp_path / "nonexistent_restrictions.json")

    (tmp_path / day).mkdir(parents=True, exist_ok=True)
    orders_path = tmp_path / "orders" / day / "orders_intent.json"
    orders_path.parent.mkdir(parents=True, exist_ok=True)
    orders_path.write_text(json.dumps({"day": day, "actions": []}), encoding="utf-8")
    (tmp_path / day / "pipeline_manifest.json").write_text(
        json.dumps({"schema_version": 2, "day": day, "stages": {}, "orders_intent_path": str(orders_path)}),
        encoding="utf-8",
    )
    (tmp_path / "dossier" / day).mkdir(parents=True, exist_ok=True)
    (tmp_path / "dossier" / day / "dossier.json").write_text(
        json.dumps({"schema_version": 1, "day": day, "evidence": {"orders_intent_path": str(orders_path)}}),
        encoding="utf-8",
    )

    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "eod", "execute", "--day", day, "--outdir", str(tmp_path), "--live", "--broker", "paper"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 2, (r.stdout, r.stderr)

    exec_path = tmp_path / day / "execution_result.json"
    assert exec_path.is_file(), "execution_result.json must be written"
    data = json.loads(exec_path.read_text(encoding="utf-8"))
    assert data.get("ok") is False
    errs = data.get("errors", [])
    assert "bist_rules_tick_bands_missing" in errs or "bist_rules_vbts_missing" in errs
