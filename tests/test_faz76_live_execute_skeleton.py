"""FAZ76: Minimal live execute skeleton — BrokerAdapter, ledger, portfolio; idempotent. Stub broker fixtures."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bist_core.execution.live_skeleton import run_live_execute_skeleton
from bist_core.execution.adapters.stub_broker import StubExecutionProvider
from bist_core.execution.result_writer import EXECUTION_RESULT_FILENAME

ROOT = Path(__file__).resolve().parent
FIXTURE_DIR = ROOT / "fixtures" / "broker_adapter"


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


def test_skeleton_writes_ledger_and_portfolio(tmp_path: Path) -> None:
    """run_live_execute_skeleton writes orders.jsonl, fills.jsonl, positions.jsonl and portfolio state."""
    day = "2025-01-22"
    orders_dir = tmp_path / "orders" / day
    orders_dir.mkdir(parents=True)
    orders_intent_path = orders_dir / "orders_intent.json"
    orders_intent = {
        "day": day,
        "actions": [
            {"symbol": "THYAO", "side": "BUY", "weight": 0.5},
            {"symbol": "AKBNK", "side": "BUY", "weight": 0.5},
        ],
    }
    orders_intent_path.write_text(json.dumps(orders_intent), encoding="utf-8")
    broker_config = {"fixture_dir": str(FIXTURE_DIR)}
    provider = StubExecutionProvider(broker_config)
    ok, err = run_live_execute_skeleton(tmp_path, day, orders_intent_path, provider, provider_name="stub", execution_mode="live")
    assert ok, err
    assert err is None
    ledger_dir = tmp_path / "ledger" / day
    assert (ledger_dir / "orders.jsonl").is_file()
    assert (ledger_dir / "fills.jsonl").is_file()
    assert (ledger_dir / "positions.jsonl").is_file()
    orders_lines = (ledger_dir / "orders.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(orders_lines) == 2
    fills_lines = (ledger_dir / "fills.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(fills_lines) == 2
    state_path = tmp_path / "portfolio" / "state.json"
    assert state_path.is_file()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "cash" in state
    assert "positions" in state
    assert (tmp_path / day / EXECUTION_RESULT_FILENAME).is_file()
    result = json.loads((tmp_path / day / EXECUTION_RESULT_FILENAME).read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert "orders_intent_sha256" in result


def test_skeleton_idempotent_second_run_no_duplicate(tmp_path: Path) -> None:
    """Re-running same day with same orders_intent does not duplicate ledger/portfolio (idempotent)."""
    day = "2025-01-23"
    orders_dir = tmp_path / "orders" / day
    orders_dir.mkdir(parents=True)
    orders_intent_path = orders_dir / "orders_intent.json"
    orders_intent = {"day": day, "actions": [{"symbol": "X", "side": "BUY", "weight": 1.0}]}
    orders_intent_path.write_text(json.dumps(orders_intent), encoding="utf-8")
    provider = StubExecutionProvider({"fixture_dir": str(FIXTURE_DIR)})
    ok1, _ = run_live_execute_skeleton(tmp_path, day, orders_intent_path, provider, provider_name="stub", execution_mode="live")
    assert ok1
    fills_path = tmp_path / "ledger" / day / "fills.jsonl"
    first_fills = fills_path.read_text(encoding="utf-8")
    state_path = tmp_path / "portfolio" / "state.json"
    first_state = state_path.read_text(encoding="utf-8")
    ok2, _ = run_live_execute_skeleton(tmp_path, day, orders_intent_path, provider, provider_name="stub", execution_mode="live")
    assert ok2
    assert fills_path.read_text(encoding="utf-8") == first_fills
    assert state_path.read_text(encoding="utf-8") == first_state


def test_live_cli_uses_skeleton_and_writes_ledger(tmp_path: Path) -> None:
    """CLI eod execute --live with stub broker fixture writes ledger and execution_result (fail-closed gates intact)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT.parent / "src")
    config_path = tmp_path / "core.json"
    config_path.write_text(json.dumps(_valid_core_config()), encoding="utf-8")
    env["BIST_CORE_CONFIG"] = str(config_path)
    broker_config_path = tmp_path / "broker.json"
    broker_config_path.write_text(json.dumps({"fixture_dir": str(FIXTURE_DIR)}), encoding="utf-8")
    env["BIST_BROKER_CONFIG"] = str(broker_config_path)
    bist_dir = _bist_fixture_dir(tmp_path)
    env["BIST_RULESPACK_DIR"] = str(bist_dir)
    env["BIST_RESTRICTIONS_FILE"] = str(tmp_path / "restrictions.json")
    day = "2025-01-24"
    manifest_dir = tmp_path / day
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "pipeline_manifest.json").write_text(
        json.dumps({
            "schema_version": 2,
            "day": day,
            "stages": {},
            "orders_intent_path": str(tmp_path / "orders" / day / "orders_intent.json"),
        }),
        encoding="utf-8",
    )
    orders_dir = tmp_path / "orders" / day
    orders_dir.mkdir(parents=True)
    (orders_dir / "orders_intent.json").write_text(
        json.dumps({"day": day, "actions": [{"symbol": "THYAO", "side": "BUY", "weight": 0.5}]}),
        encoding="utf-8",
    )
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "eod", "execute", "--day", day, "--outdir", str(tmp_path), "--live"],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert (tmp_path / "ledger" / day / "fills.jsonl").is_file()
    assert (tmp_path / "portfolio" / "state.json").is_file()
    result = json.loads((tmp_path / day / EXECUTION_RESULT_FILENAME).read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert "orders_intent_sha256" in result


def test_fail_closed_no_manifest_still_exits_2(tmp_path: Path) -> None:
    """Fail-closed gates intact: no pipeline manifest -> exit 2, execution_result written."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT.parent / "src")
    config_path = tmp_path / "core.json"
    config_path.write_text(json.dumps(_valid_core_config()), encoding="utf-8")
    env["BIST_CORE_CONFIG"] = str(config_path)
    broker_config_path = tmp_path / "broker.json"
    broker_config_path.write_text(json.dumps({"fixture_dir": str(FIXTURE_DIR)}), encoding="utf-8")
    env["BIST_BROKER_CONFIG"] = str(broker_config_path)
    bist_dir = _bist_fixture_dir(tmp_path)
    env["BIST_RULESPACK_DIR"] = str(bist_dir)
    env["BIST_RESTRICTIONS_FILE"] = str(tmp_path / "restrictions.json")
    day = "2025-01-25"
    tmp_path.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "eod", "execute", "--day", day, "--outdir", str(tmp_path), "--live"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert r.returncode == 2
    assert (tmp_path / day / EXECUTION_RESULT_FILENAME).is_file()
    data = json.loads((tmp_path / day / EXECUTION_RESULT_FILENAME).read_text(encoding="utf-8"))
    assert data["ok"] is False
    err_codes = [e.get("code") for e in data.get("errors", []) if isinstance(e, dict)]
    assert "no_manifest" in err_codes
