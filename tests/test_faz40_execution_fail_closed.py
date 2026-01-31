"""FAZ40: Execution fail-closed — stage errors -> denied; dry-run -> no file; live -> file written."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_faz40_case_a_stage_errors_denied_provider_not_called(tmp_path: Path) -> None:
    """Case A: stage errors -> denied, provider not called, exit code nonzero, output contains 'blocked'."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    day = "2099-08-01"
    outdir = tmp_path / "out"
    (outdir / day).mkdir(parents=True)
    (outdir / "orders" / day).mkdir(parents=True)
    orders_intent = {
        "schema_version": 1,
        "day": day,
        "actions": [{"symbol": "A", "side": "BUY", "weight": 0.5}],
        "notes": [],
    }
    (outdir / "orders" / day / "orders_intent.json").write_text(
        json.dumps(orders_intent),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "day": day,
        "stages": {
            "snapshot": {"errors": 1, "ok": 0},
            "advice": {"errors": 0},
            "orders": {"errors": 0},
        },
        "orders_intent_path": str(outdir / "orders" / day / "orders_intent.json"),
    }
    (outdir / day / "pipeline_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "execute",
            "--day",
            day,
            "--outdir",
            str(outdir),
            "--provider",
            "paper",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode != 0
    assert "blocked" in (result.stdout + result.stderr).lower()
    assert not (outdir / day / "orders_sent.json").exists()


def test_faz40_case_b_clean_stages_dry_run_no_file_written(tmp_path: Path) -> None:
    """Case B: clean stages + dry-run -> allowed, provider called, no file written."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    day = "2099-08-02"
    outdir = tmp_path / "out"
    (outdir / day).mkdir(parents=True)
    (outdir / "orders" / day).mkdir(parents=True)
    orders_intent = {
        "schema_version": 1,
        "day": day,
        "actions": [{"symbol": "B", "side": "BUY", "weight": 1.0}],
        "notes": [],
    }
    (outdir / "orders" / day / "orders_intent.json").write_text(
        json.dumps(orders_intent),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "day": day,
        "stages": {
            "snapshot": {"errors": 0},
            "advice": {"errors": 0},
            "orders": {"errors": 0},
        },
        "orders_intent_path": str(outdir / "orders" / day / "orders_intent.json"),
    }
    (outdir / day / "pipeline_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "execute",
            "--day",
            day,
            "--outdir",
            str(outdir),
            "--provider",
            "paper",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert not (outdir / day / "orders_sent.json").exists()
    assert "execute:" in result.stdout or "sent=" in result.stdout


def test_faz40_case_c_live_file_written_at_deterministic_path(tmp_path: Path) -> None:
    """Case C: live -> allowed, file written at expected deterministic path outdir/<day>/orders_sent.json."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    day = "2099-08-03"
    outdir = tmp_path / "out"
    (outdir / day).mkdir(parents=True)
    (outdir / "orders" / day).mkdir(parents=True)
    # FAZ57: live requires BIST rule data (rulespack + restrictions)
    rules_dir = tmp_path / "bist_rules"
    rules_dir.mkdir()
    (rules_dir / "tick_sizes.csv").write_text("min_price,max_price,tick\n0,9999,0.01\n", encoding="utf-8")
    (rules_dir / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    (tmp_path / "restrictions.json").write_text('{"blocked_symbols": [], "short_sale_ban": false}', encoding="utf-8")
    env["BIST_RULESPACK_DIR"] = str(rules_dir)
    env["BIST_RESTRICTIONS_FILE"] = str(tmp_path / "restrictions.json")
    orders_intent = {
        "schema_version": 1,
        "day": day,
        "actions": [{"symbol": "C", "side": "BUY", "weight": 0.5}],
        "notes": [],
    }
    (outdir / "orders" / day / "orders_intent.json").write_text(
        json.dumps(orders_intent),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "day": day,
        "stages": {
            "snapshot": {"errors": 0},
            "advice": {"errors": 0},
            "orders": {"errors": 0},
        },
        "orders_intent_path": str(outdir / "orders" / day / "orders_intent.json"),
    }
    (outdir / day / "pipeline_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "execute",
            "--day",
            day,
            "--outdir",
            str(outdir),
            "--provider",
            "paper",
            "--live",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0
    expected_path = outdir / day / "orders_sent.json"
    assert expected_path.is_file()
    loaded = json.loads(expected_path.read_text(encoding="utf-8"))
    assert loaded.get("day") == day
    assert loaded.get("actions") == orders_intent["actions"]
