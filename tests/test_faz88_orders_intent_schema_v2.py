"""FAZ88: Orders intent schema v2 — validate; invalid -> exit 2 + execution_result."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bist_core.orders.schema import ORDERS_INTENT_SCHEMA_VERSION, validate_orders_intent_v2


def test_faz88_validate_v2_ok() -> None:
    """Valid orders_intent (day + actions with symbol/side) passes."""
    ok, errs = validate_orders_intent_v2({"day": "2024-01-01", "actions": [{"symbol": "X", "side": "BUY"}]})
    assert ok is True
    assert errs == []


def test_faz88_validate_v2_missing_day() -> None:
    """Missing day -> orders_intent_missing_day."""
    ok, errs = validate_orders_intent_v2({"actions": []})
    assert ok is False
    assert "orders_intent_missing_day" in errs


def test_faz88_validate_v2_missing_actions() -> None:
    """Missing actions -> orders_intent_missing_actions."""
    ok, errs = validate_orders_intent_v2({"day": "2024-01-01"})
    assert ok is False
    assert "orders_intent_missing_actions" in errs


def test_faz88_validate_v2_action_missing_symbol() -> None:
    """Action without symbol -> orders_intent_action_missing_symbol."""
    ok, errs = validate_orders_intent_v2({"day": "2024-01-01", "actions": [{"side": "BUY"}]})
    assert ok is False
    assert "orders_intent_action_missing_symbol" in errs


def test_faz88_validate_v2_action_missing_side() -> None:
    """Action without side -> orders_intent_action_missing_side."""
    ok, errs = validate_orders_intent_v2({"day": "2024-01-01", "actions": [{"symbol": "X"}]})
    assert ok is False
    assert "orders_intent_action_missing_side" in errs


def test_faz88_execute_invalid_orders_intent_exit_2_and_execution_result(tmp_path: Path) -> None:
    """CLI execute with invalid orders_intent (missing day) -> exit 2 and execution_result.json written."""
    day = "2099-06-01"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    (tmp_path / "core.json").write_text(
        json.dumps({"timezone": "Europe/Istanbul", "default_spread_bps_max": 80, "default_adv_tl_min": 30000000, "default_auction_ratio_max": 0.15, "default_price_band_pct": 20.0, "risk_per_trade": 0.015}),
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
    orders_path.write_text(json.dumps({"actions": [{"symbol": "X", "side": "BUY"}]}), encoding="utf-8")
    (tmp_path / day / "pipeline_manifest.json").write_text(
        json.dumps({"schema_version": 2, "day": day, "stages": {"snapshot": {"errors": 0}, "advice": {"errors": 0}}, "orders_intent_path": str(orders_path)}),
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
    assert exec_path.is_file()
    data = json.loads(exec_path.read_text(encoding="utf-8"))
    assert data.get("ok") is False
    codes = [e.get("code") for e in data.get("errors", []) if isinstance(e, dict)]
    assert "orders_intent_missing_day" in codes
