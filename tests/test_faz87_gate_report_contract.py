"""FAZ87: Gate report contract — run_all -> {ok, blocked, errors, codes}; blocked -> execution_result + dossier evidence links."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


from bist_core.risk.gates import run_all


def test_faz87_run_all_returns_ok_blocked_errors_codes() -> None:
    """run_all returns dict with ok, blocked, errors, codes; blocked when stages have errors."""
    orders_intent = {"day": "2024-01-01", "actions": []}
    stages_ok = {"snapshot": {"errors": 0}, "advice": {"errors": 0}}
    report_ok = run_all(orders_intent, stages_ok)
    assert report_ok["ok"] is True
    assert report_ok["blocked"] is False
    assert report_ok["errors"] == []
    assert report_ok["codes"] == []

    stages_blocked = {"snapshot": {"errors": 1}, "advice": {"errors": 0}}
    report_blocked = run_all(orders_intent, stages_blocked)
    assert report_blocked["ok"] is False
    assert report_blocked["blocked"] is True
    assert "blocked" in report_blocked["errors"]
    assert "blocked" in report_blocked["codes"]


def test_faz87_blocked_writes_report_and_dossier_evidence(tmp_path: Path) -> None:
    """When gate blocked (stage errors), execution_result.json written and dossier evidence links to it."""
    day = "2099-05-01"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    (tmp_path / "core.json").write_text(
        json.dumps(
            {
                "timezone": "Europe/Istanbul",
                "default_spread_bps_max": 80,
                "default_adv_tl_min": 30000000,
                "default_auction_ratio_max": 0.15,
                "default_price_band_pct": 20.0,
                "risk_per_trade": 0.015,
            }
        ),
        encoding="utf-8",
    )
    env["BIST_CORE_CONFIG"] = str(tmp_path / "core.json")
    (tmp_path / "bist").mkdir(parents=True)
    (tmp_path / "bist" / "tick_sizes.csv").write_text("min_price,max_price,tick\n0,99,0.01\n", encoding="utf-8")
    (tmp_path / "bist" / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    (tmp_path / "restrictions.json").write_text("{}", encoding="utf-8")
    env["BIST_RULESPACK_DIR"] = str(tmp_path / "bist")
    env["BIST_RESTRICTIONS_FILE"] = str(tmp_path / "restrictions.json")

    (tmp_path / day).mkdir(parents=True, exist_ok=True)
    orders_path = tmp_path / "orders" / day / "orders_intent.json"
    orders_path.parent.mkdir(parents=True, exist_ok=True)
    orders_path.write_text(json.dumps({"day": day, "actions": [{"symbol": "X", "side": "BUY"}]}), encoding="utf-8")
    (tmp_path / day / "pipeline_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "day": day,
                "stages": {"snapshot": {"errors": 1}, "advice": {"errors": 0}},
                "orders_intent_path": str(orders_path),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "dossier" / day).mkdir(parents=True, exist_ok=True)
    (tmp_path / "dossier" / day / "dossier.json").write_text(
        json.dumps({"schema_version": 1, "day": day, "evidence": {"orders_intent_path": str(orders_path)}}),
        encoding="utf-8",
    )

    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "execute",
            "--day",
            day,
            "--outdir",
            str(tmp_path),
            "--live",
            "--broker",
            "paper",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 2, (r.stdout, r.stderr)

    exec_path = tmp_path / day / "execution_result.json"
    assert exec_path.is_file(), "execution_result.json (report) must be written when blocked"
    exec_data = json.loads(exec_path.read_text(encoding="utf-8"))
    assert exec_data.get("ok") is False
    assert exec_data.get("blocked") is True
    assert "errors" in exec_data

    dossier_path = tmp_path / "dossier" / day / "dossier.json"
    assert dossier_path.is_file()
    dossier_data = json.loads(dossier_path.read_text(encoding="utf-8"))
    ev = dossier_data.get("evidence") or {}
    assert "execution_result_path" in ev
    assert "blocked_reason" in ev
    assert "blocked_code" in ev
    assert ev.get("blocked_reason") == "risk gate denied"
