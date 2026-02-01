"""FAZ77: Reconciliation stage (intended vs fills), deterministic reconciliation.json; dossier evidence includes reconciliation + execution_result + ledger paths."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bist_core.reconciliation.write import (
    RECONCILIATION_FILENAME,
    RECONCILIATION_SCHEMA_VERSION,
    build_reconciliation_payload,
    write_reconciliation,
)
from bist_core.dossier.write import write_dossier, update_dossier_evidence

ROOT = Path(__file__).resolve().parent
FIXTURE_DIR = ROOT / "fixtures" / "broker_adapter"


def test_reconciliation_payload_matched() -> None:
    """build_reconciliation_payload: all intended symbols have fills -> matched, status ok."""
    actions = [{"symbol": "THYAO", "side": "BUY"}, {"symbol": "AKBNK", "side": "BUY"}]
    fills = [
        {"order_id": "1", "symbol": "THYAO", "side": "BUY", "qty": 100, "price": 42.5, "notional": 4250},
        {"order_id": "2", "symbol": "AKBNK", "side": "BUY", "qty": 50, "price": 38, "notional": 1900},
    ]
    payload = build_reconciliation_payload("2025-01-26", actions, fills)
    assert payload["schema_version"] == RECONCILIATION_SCHEMA_VERSION
    assert payload["day"] == "2025-01-26"
    assert payload["intended_count"] == 2
    assert payload["fills_count"] == 2
    assert payload["matched"] == ["AKBNK", "THYAO"]
    assert payload["unmatched_actions"] == []
    assert payload["unmatched_fills"] == []
    assert payload["status"] == "ok"


def test_reconciliation_payload_mismatch() -> None:
    """build_reconciliation_payload: intended without fill -> unmatched_actions; fill without intended -> unmatched_fills."""
    actions = [{"symbol": "X", "side": "BUY"}, {"symbol": "Y", "side": "BUY"}]
    fills = [{"order_id": "1", "symbol": "Y", "side": "BUY", "qty": 10, "price": 1, "notional": 10}]
    payload = build_reconciliation_payload("2025-01-27", actions, fills)
    assert payload["matched"] == ["Y"]
    assert payload["unmatched_actions"] == ["X"]
    assert payload["unmatched_fills"] == []
    assert payload["status"] == "mismatch"


def test_write_reconciliation_path_and_content(tmp_path: Path) -> None:
    """write_reconciliation writes outdir/<day>/reconciliation.json with deterministic content."""
    day = "2025-01-28"
    orders_dir = tmp_path / "orders" / day
    orders_dir.mkdir(parents=True)
    (orders_dir / "orders_intent.json").write_text(
        json.dumps({"day": day, "actions": [{"symbol": "A", "side": "BUY"}]}),
        encoding="utf-8",
    )
    ledger_dir = tmp_path / "ledger" / day
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "fills.jsonl").write_text(
        json.dumps({"order_id": "1", "symbol": "A", "side": "BUY", "qty": 10, "price": 1, "notional": 10}) + "\n",
        encoding="utf-8",
    )
    out = write_reconciliation(tmp_path, day, orders_dir / "orders_intent.json", ledger_dir / "fills.jsonl")
    assert out == tmp_path / day / RECONCILIATION_FILENAME
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["matched"] == ["A"]
    assert data["status"] == "ok"
    assert set(data.keys()) >= {"schema_version", "day", "intended_count", "fills_count", "matched", "unmatched_actions", "unmatched_fills", "status"}


def test_dossier_includes_reconciliation_and_ledger_paths(tmp_path: Path) -> None:
    """write_dossier stores reconciliation_path, execution_result_path, ledger paths in evidence."""
    day = "2025-01-29"
    evidence = {
        "advice_path": str(tmp_path / "advice" / day / "advice_records.jsonl"),
        "orders_intent_path": str(tmp_path / "orders" / day / "orders_intent.json"),
        "reconciliation_path": str(tmp_path / day / RECONCILIATION_FILENAME),
        "execution_result_path": str(tmp_path / day / "execution_result.json"),
        "ledger_orders_path": str(tmp_path / "ledger" / day / "orders.jsonl"),
        "ledger_fills_path": str(tmp_path / "ledger" / day / "fills.jsonl"),
        "ledger_positions_path": str(tmp_path / "ledger" / day / "positions.jsonl"),
    }
    out = write_dossier(day, tmp_path, evidence)
    data = json.loads(out.read_text(encoding="utf-8"))
    ev = data["evidence"]
    assert ev["reconciliation_path"] == str(tmp_path / day / RECONCILIATION_FILENAME)
    assert ev["execution_result_path"] == str(tmp_path / day / "execution_result.json")
    assert ev["ledger_orders_path"] == str(tmp_path / "ledger" / day / "orders.jsonl")
    assert ev["ledger_fills_path"] == str(tmp_path / "ledger" / day / "fills.jsonl")
    assert ev["ledger_positions_path"] == str(tmp_path / "ledger" / day / "positions.jsonl")
    assert list(ev.keys()) == sorted(ev.keys())


def test_update_dossier_evidence_merges_paths(tmp_path: Path) -> None:
    """update_dossier_evidence merges extra evidence into existing dossier and rewrites."""
    day = "2025-01-30"
    evidence = {"advice_path": str(tmp_path / "advice.jsonl"), "orders_intent_path": str(tmp_path / "orders.json")}
    write_dossier(day, tmp_path, evidence)
    dossier_file = tmp_path / "dossier" / day / "dossier.json"
    assert dossier_file.is_file()
    extra = {
        "reconciliation_path": str(tmp_path / day / "reconciliation.json"),
        "execution_result_path": str(tmp_path / day / "execution_result.json"),
        "ledger_fills_path": str(tmp_path / "ledger" / day / "fills.jsonl"),
    }
    update_dossier_evidence(tmp_path, day, extra)
    data = json.loads(dossier_file.read_text(encoding="utf-8"))
    ev = data["evidence"]
    assert ev["reconciliation_path"] == extra["reconciliation_path"]
    assert ev["execution_result_path"] == extra["execution_result_path"]
    assert ev["ledger_fills_path"] == extra["ledger_fills_path"]
    assert ev["advice_path"] == evidence["advice_path"]


def _valid_core_config() -> dict:
    return {
        "timezone": "Europe/Istanbul",
        "default_spread_bps_max": 80,
        "default_adv_tl_min": 30000000,
        "default_auction_ratio_max": 0.15,
        "default_price_band_pct": 20.0,
        "risk_per_trade": 0.015,
    }


def _bist_fixture(tmp_path: Path) -> None:
    d = tmp_path / "bist"
    d.mkdir(parents=True, exist_ok=True)
    (d / "tick_sizes.csv").write_text("min_price,max_price,tick\n0,99,0.01\n", encoding="utf-8")
    (d / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    (d / "restrictions.json").write_text("{}", encoding="utf-8")
    (tmp_path / "restrictions.json").write_text("{}", encoding="utf-8")


def test_live_execute_writes_reconciliation_and_updates_dossier(tmp_path: Path) -> None:
    """CLI eod execute --live with stub broker: reconciliation.json written, dossier evidence updated with reconciliation + execution_result + ledger paths."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT.parent / "src")
    (tmp_path / "core.json").write_text(json.dumps(_valid_core_config()), encoding="utf-8")
    env["BIST_CORE_CONFIG"] = str(tmp_path / "core.json")
    (tmp_path / "broker.json").write_text(json.dumps({"fixture_dir": str(FIXTURE_DIR)}), encoding="utf-8")
    env["BIST_BROKER_CONFIG"] = str(tmp_path / "broker.json")
    _bist_fixture(tmp_path)
    env["BIST_RULESPACK_DIR"] = str(tmp_path / "bist")
    env["BIST_RESTRICTIONS_FILE"] = str(tmp_path / "restrictions.json")
    day = "2025-01-31"
    (tmp_path / day).mkdir(parents=True)
    (tmp_path / day / "pipeline_manifest.json").write_text(
        json.dumps({"schema_version": 2, "day": day, "stages": {}, "orders_intent_path": str(tmp_path / "orders" / day / "orders_intent.json")}),
        encoding="utf-8",
    )
    (tmp_path / "orders" / day).mkdir(parents=True)
    (tmp_path / "orders" / day / "orders_intent.json").write_text(
        json.dumps({"day": day, "actions": [{"symbol": "THYAO", "side": "BUY", "weight": 0.5}, {"symbol": "AKBNK", "side": "BUY", "weight": 0.5}]}),
        encoding="utf-8",
    )
    (tmp_path / "dossier" / day).mkdir(parents=True)
    write_dossier(day, tmp_path, {"advice_path": str(tmp_path / "advice.jsonl"), "orders_intent_path": str(tmp_path / "orders" / day / "orders_intent.json")})
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "eod", "execute", "--day", day, "--outdir", str(tmp_path), "--live"],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert (tmp_path / day / RECONCILIATION_FILENAME).is_file()
    recon = json.loads((tmp_path / day / RECONCILIATION_FILENAME).read_text(encoding="utf-8"))
    assert recon["status"] == "ok"
    assert set(recon["matched"]) >= {"THYAO", "AKBNK"}
    dossier_data = json.loads((tmp_path / "dossier" / day / "dossier.json").read_text(encoding="utf-8"))
    ev = dossier_data["evidence"]
    assert "reconciliation_path" in ev
    assert "execution_result_path" in ev
    assert "ledger_fills_path" in ev
    assert "ledger_orders_path" in ev
    assert "ledger_positions_path" in ev
