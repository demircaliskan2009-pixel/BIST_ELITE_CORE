"""FAZ80: BrokerConfig loader from BIST_BROKER_CONFIG (file path OR inline JSON); missing/invalid -> fail-closed exit 2 + execution_result.json."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


from bist_core.config import load_broker_config
from bist_core.execution.result_writer import EXECUTION_RESULT_FILENAME


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


def test_load_broker_config_valid_file(tmp_path: Path) -> None:
    """load_broker_config with path to valid JSON file returns (dict, None)."""
    cfg_path = tmp_path / "broker.json"
    cfg_path.write_text(json.dumps({"fixture_dir": str(tmp_path)}), encoding="utf-8")
    data, err = load_broker_config(str(cfg_path))
    assert err is None
    assert data is not None
    assert data.get("fixture_dir") == str(tmp_path)


def test_load_broker_config_valid_inline_json() -> None:
    """load_broker_config with inline JSON string returns (dict, None)."""
    data, err = load_broker_config('{"fixture_dir": "/tmp"}')
    assert err is None
    assert data is not None
    assert data.get("fixture_dir") == "/tmp"


def test_load_broker_config_missing() -> None:
    """load_broker_config with None or empty returns (None, broker_config_missing)."""
    data, err = load_broker_config(None)
    assert data is None
    assert err == "broker_config_missing"
    data, err = load_broker_config("")
    assert data is None
    assert err == "broker_config_missing"
    data, err = load_broker_config("   ")
    assert data is None
    assert err == "broker_config_missing"


def test_load_broker_config_invalid_file(tmp_path: Path) -> None:
    """load_broker_config with path to invalid JSON returns (None, broker_config_invalid)."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json {{{", encoding="utf-8")
    data, err = load_broker_config(str(bad))
    assert data is None
    assert err == "broker_config_invalid"


def test_load_broker_config_invalid_inline() -> None:
    """load_broker_config with invalid inline JSON returns (None, broker_config_invalid)."""
    data, err = load_broker_config("not json")
    assert data is None
    assert err == "broker_config_invalid"
    data, err = load_broker_config("[1,2,3]")
    assert data is None
    assert err == "broker_config_invalid"


def test_live_missing_broker_config_exit2_and_execution_result(tmp_path: Path) -> None:
    """--live broker=stub with no BIST_BROKER_CONFIG -> exit 2, execution_result.json written."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    (tmp_path / "core.json").write_text(json.dumps(_valid_core_config()), encoding="utf-8")
    env["BIST_CORE_CONFIG"] = str(tmp_path / "core.json")
    env.pop("BIST_BROKER_CONFIG", None)
    _bist_fixture(tmp_path)
    env["BIST_RULESPACK_DIR"] = str(tmp_path / "bist")
    env["BIST_RESTRICTIONS_FILE"] = str(tmp_path / "restrictions.json")
    day = "2099-03-01"
    (tmp_path / day).mkdir(parents=True, exist_ok=True)
    (tmp_path / "orders" / day).mkdir(parents=True, exist_ok=True)
    (tmp_path / "orders" / day / "orders_intent.json").write_text(
        json.dumps({"day": day, "actions": []}), encoding="utf-8"
    )
    (tmp_path / day / "pipeline_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "day": day,
                "stages": {},
                "orders_intent_path": str(tmp_path / "orders" / day / "orders_intent.json"),
            }
        ),
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
            "stub",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert r.returncode == 2
    result_path = tmp_path / day / EXECUTION_RESULT_FILENAME
    assert result_path.is_file()
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["ok"] is False
    codes = [e.get("code") for e in data.get("errors", []) if isinstance(e, dict)]
    assert "broker_config_missing" in codes


def test_live_invalid_broker_config_exit2_and_execution_result(tmp_path: Path) -> None:
    """--live broker=stub with invalid BIST_BROKER_CONFIG (inline) -> exit 2, execution_result.json written."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    (tmp_path / "core.json").write_text(json.dumps(_valid_core_config()), encoding="utf-8")
    env["BIST_CORE_CONFIG"] = str(tmp_path / "core.json")
    env["BIST_BROKER_CONFIG"] = "not valid json"
    _bist_fixture(tmp_path)
    env["BIST_RULESPACK_DIR"] = str(tmp_path / "bist")
    env["BIST_RESTRICTIONS_FILE"] = str(tmp_path / "restrictions.json")
    day = "2099-03-02"
    (tmp_path / day).mkdir(parents=True, exist_ok=True)
    (tmp_path / "orders" / day).mkdir(parents=True, exist_ok=True)
    (tmp_path / "orders" / day / "orders_intent.json").write_text(
        json.dumps({"day": day, "actions": []}), encoding="utf-8"
    )
    (tmp_path / day / "pipeline_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "day": day,
                "stages": {},
                "orders_intent_path": str(tmp_path / "orders" / day / "orders_intent.json"),
            }
        ),
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
            "stub",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert r.returncode == 2
    result_path = tmp_path / day / EXECUTION_RESULT_FILENAME
    assert result_path.is_file()
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["ok"] is False
    codes = [e.get("code") for e in data.get("errors", []) if isinstance(e, dict)]
    assert "broker_config_invalid" in codes


def test_live_valid_inline_broker_config_accepts(tmp_path: Path) -> None:
    """--live broker=stub with valid inline BIST_BROKER_CONFIG (minimal stub config) -> passes broker preflight (may still fail later on manifest etc)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    (tmp_path / "core.json").write_text(json.dumps(_valid_core_config()), encoding="utf-8")
    env["BIST_CORE_CONFIG"] = str(tmp_path / "core.json")
    env["BIST_BROKER_CONFIG"] = json.dumps({"fixture_dir": str(tmp_path)})
    _bist_fixture(tmp_path)
    env["BIST_RULESPACK_DIR"] = str(tmp_path / "bist")
    env["BIST_RESTRICTIONS_FILE"] = str(tmp_path / "restrictions.json")
    day = "2099-03-03"
    (tmp_path / day).mkdir(parents=True, exist_ok=True)
    (tmp_path / "orders" / day).mkdir(parents=True, exist_ok=True)
    (tmp_path / "orders" / day / "orders_intent.json").write_text(
        json.dumps({"day": day, "actions": []}), encoding="utf-8"
    )
    (tmp_path / day / "pipeline_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "day": day,
                "stages": {},
                "orders_intent_path": str(tmp_path / "orders" / day / "orders_intent.json"),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "dossier" / day).mkdir(parents=True, exist_ok=True)
    (tmp_path / "dossier" / day / "dossier.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "day": day,
                "evidence": {"orders_intent_path": str(tmp_path / "orders" / day / "orders_intent.json")},
            }
        ),
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
            "stub",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert (tmp_path / day / EXECUTION_RESULT_FILENAME).is_file()
    data = json.loads((tmp_path / day / EXECUTION_RESULT_FILENAME).read_text(encoding="utf-8"))
    assert data["ok"] is True
