"""FAZ82: Integration test — live execute with missing BIST rulespack/restrictions -> returncode 2, stderr has error code, execution_result.json written, dossier evidence includes blocked reason/code."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _valid_core_config() -> dict:
    return {
        "timezone": "Europe/Istanbul",
        "default_spread_bps_max": 80,
        "default_adv_tl_min": 30000000,
        "default_auction_ratio_max": 0.15,
        "default_price_band_pct": 20.0,
        "risk_per_trade": 0.015,
    }


def test_faz82_live_execute_missing_bist_rules_returncode_2_and_dossier(tmp_path: Path) -> None:
    """Live execute with missing BIST rulespack/restrictions -> returncode 2, stderr has error code, execution_result.json written, dossier evidence includes blocked_reason and blocked_code."""
    day = "2099-03-01"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    (tmp_path / "core.json").write_text(json.dumps(_valid_core_config()), encoding="utf-8")
    env["BIST_CORE_CONFIG"] = str(tmp_path / "core.json")
    env["BIST_BROKER_CONFIG"] = json.dumps({"fixture_dir": str(tmp_path)})
    env["BIST_RULESPACK_DIR"] = str(tmp_path / "nonexistent_rulespack")
    env["BIST_RESTRICTIONS_FILE"] = str(tmp_path / "nonexistent_restrictions.json")

    (tmp_path / day).mkdir(parents=True, exist_ok=True)
    orders_path = tmp_path / "orders" / day / "orders_intent.json"
    orders_path.parent.mkdir(parents=True, exist_ok=True)
    orders_path.write_text(
        json.dumps({"day": day, "actions": [{"symbol": "X", "side": "BUY", "weight": 1.0}]}),
        encoding="utf-8",
    )
    (tmp_path / day / "pipeline_manifest.json").write_text(
        json.dumps({"schema_version": 2, "day": day, "stages": {}, "orders_intent_path": str(orders_path)}),
        encoding="utf-8",
    )
    (tmp_path / "dossier" / day).mkdir(parents=True, exist_ok=True)
    (tmp_path / "dossier" / day / "dossier.json").write_text(
        json.dumps({"schema_version": 1, "day": day, "evidence": {"advice_path": "", "orders_intent_path": str(orders_path)}}),
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
    assert "bist_rules_missing" in r.stderr, "stderr must contain error code bist_rules_missing"

    day_dir = tmp_path / day
    exec_result_path = day_dir / "execution_result.json"
    assert exec_result_path.is_file(), "execution_result.json must be written"
    exec_data = json.loads(exec_result_path.read_text(encoding="utf-8"))
    assert exec_data.get("ok") is False
    assert exec_data.get("blocked") is True
    assert "errors" in exec_data
    errs = exec_data.get("errors", [])
    codes = [e.get("code") for e in errs if isinstance(e, dict)]
    assert "bist_rules_tick_bands_missing" in codes or "bist_rules_vbts_missing" in codes

    dossier_path = tmp_path / "dossier" / day / "dossier.json"
    assert dossier_path.is_file(), "dossier must exist"
    dossier_data = json.loads(dossier_path.read_text(encoding="utf-8"))
    ev = dossier_data.get("evidence") or {}
    assert "execution_result_path" in ev
    assert "blocked_reason" in ev
    assert "blocked_code" in ev
    assert ev.get("blocked_code") == "bist_rules_missing"
    assert "BIST rule data missing" in ev.get("blocked_reason", "")
