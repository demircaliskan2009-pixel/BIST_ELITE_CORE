"""FAZ79: Subprocess E2E smoke test — eod execute --live --broker paper; assert rc=0 and deterministic artifacts (tmp-only)."""
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


def _bist_fixture_dir(tmp_path: Path) -> Path:
    d = tmp_path / "bist"
    d.mkdir(parents=True, exist_ok=True)
    (d / "tick_sizes.csv").write_text("min_price,max_price,tick\n0,99,0.01\n", encoding="utf-8")
    (d / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    (d / "restrictions.json").write_text("{}", encoding="utf-8")
    (tmp_path / "restrictions.json").write_text("{}", encoding="utf-8")
    return d


def test_faz79_e2e_execute_live_paper_rc0_and_artifacts(tmp_path: Path) -> None:
    """E2E: python -m bist_core.cli eod execute --day 2099-02-01 --outdir <tmp> --live --broker paper -> rc=0, execution_result.json + reconciliation.json + dossier with minimal schema."""
    day = "2099-02-01"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    (tmp_path / "core.json").write_text(json.dumps(_valid_core_config()), encoding="utf-8")
    env["BIST_CORE_CONFIG"] = str(tmp_path / "core.json")
    _bist_fixture_dir(tmp_path)
    env["BIST_RULESPACK_DIR"] = str(tmp_path / "bist")
    env["BIST_RESTRICTIONS_FILE"] = str(tmp_path / "restrictions.json")

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
    assert r.returncode == 0, (r.stdout, r.stderr)

    outdir = tmp_path
    day_dir = outdir / day

    execution_result_path = day_dir / "execution_result.json"
    assert execution_result_path.is_file(), "execution_result.json must exist"
    exec_data = json.loads(execution_result_path.read_text(encoding="utf-8"))
    assert exec_data.get("schema_version") == 1
    assert exec_data.get("day") == day
    assert exec_data.get("ok") is True
    assert "errors" in exec_data

    reconciliation_path = day_dir / "reconciliation.json"
    assert reconciliation_path.is_file(), "reconciliation.json must exist"
    recon_data = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    assert recon_data.get("schema_version") == 1
    assert recon_data.get("day") == day
    assert "status" in recon_data
    assert "intended_count" in recon_data
    assert "fills_count" in recon_data

    dossier_path = outdir / "dossier" / day / "dossier.json"
    assert dossier_path.is_file(), "dossier output must exist"
    dossier_data = json.loads(dossier_path.read_text(encoding="utf-8"))
    assert dossier_data.get("schema_version") == 1
    assert dossier_data.get("day") == day
    assert "evidence" in dossier_data
    ev = dossier_data["evidence"]
    assert "reconciliation_path" in ev or "execution_result_path" in ev or "ledger_fills_path" in ev
