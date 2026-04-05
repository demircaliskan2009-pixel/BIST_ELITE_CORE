"""E2E multi-day scenario: snapshot → eod run → plan → orders.

Given sample data for 3 days, validates entire pipeline produces consistent outputs.
Golden checks: no data gaps, all expected artifacts present.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli(args: list[str], env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    e["PYTHONPATH"] = str(_project_root() / "src")
    e.pop("BIST_CORE_ALLOW_NETWORK", None)
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, "-m", "bist_core.cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=e,
        cwd=str(cwd or _project_root()),
        timeout=60,
    )


# Weekdays to pass calendar gate (Mon–Wed)
SCENARIO_DAYS = ["2099-01-06", "2099-01-07", "2099-01-08"]


def _setup_three_day_snapshots(snapshot_root: Path) -> None:
    """Create 3 days of sample snapshots: AAA, BBB, CCC with valid close prices."""
    days = SCENARIO_DAYS
    for day in days:
        day_dir = snapshot_root / day
        day_dir.mkdir(parents=True, exist_ok=True)
        (day_dir / "snapshot.csv").write_text(
            "symbol,close\nAAA,100.0\nBBB,200.0\nCCC,150.0\n",
            encoding="utf-8",
        )


def test_e2e_multi_day_no_data_gaps(tmp_path: Path) -> None:
    """3-day scenario: eod run + plan + orders for each day; no intermediate failures."""
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(parents=True)
    _setup_three_day_snapshots(snapshot_root)

    outdir = tmp_path / "out"
    env = {"BIST_CORE_SNAPSHOT_DIR": str(snapshot_root)}
    days = SCENARIO_DAYS

    for day in days:
        r = _run_cli(["eod", "run", "--day", day, "--outdir", str(outdir)], env=env)
        assert r.returncode == 0, f"eod run {day} failed: {r.stderr or r.stdout}"

        r = _run_cli(["plan", "--date", day], env=env)
        assert r.returncode == 0, f"plan {day} failed: {r.stderr or r.stdout}"

        r = _run_cli(["orders", "--date", day], env=env)
        assert r.returncode == 0, f"orders {day} failed: {r.stderr or r.stdout}"


def test_e2e_multi_day_all_outputs_produced(tmp_path: Path) -> None:
    """After 3-day run, verify all expected artifacts exist."""
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(parents=True)
    _setup_three_day_snapshots(snapshot_root)

    outdir = tmp_path / "out"
    env = {"BIST_CORE_SNAPSHOT_DIR": str(snapshot_root)}
    days = SCENARIO_DAYS

    for day in days:
        _run_cli(["eod", "run", "--day", day, "--outdir", str(outdir)], env=env)
        _run_cli(["plan", "--date", day], env=env)
        _run_cli(["orders", "--date", day], env=env)

    # Pipeline manifest (last run overwrites)
    manifest_path = outdir / "_pipeline_manifest.json"
    assert manifest_path.exists(), "pipeline manifest missing"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("schema_version") or "day" in manifest or "stages" in manifest

    # Advice for each day
    for day in days:
        advice_path = outdir / "advice" / day / "advice_records.jsonl"
        assert advice_path.exists(), f"advice {day} missing"
        lines = advice_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) >= 3, f"advice {day} should have >= 3 records"

    # Dossiers
    dossier_dir = outdir / "dossiers"
    assert dossier_dir.exists()
    dossier_files = list(dossier_dir.glob("*.json"))
    assert len(dossier_files) >= 3, "expected >= 3 dossier files"

    # Plan and orders for each day
    for day in days:
        plan_path = snapshot_root / day / "plan_equal_weight.csv"
        assert plan_path.exists(), f"plan {day} missing"
        with plan_path.open(encoding="utf-8") as handle:
            plan_rows = list(csv.DictReader(handle))
        assert len(plan_rows) == 3, f"plan {day} should have 3 symbols"

        orders_path = snapshot_root / day / "orders_equal_weight.csv"
        assert orders_path.exists(), f"orders {day} missing"
        meta_path = snapshot_root / day / "orders_meta.txt"
        assert meta_path.exists(), f"orders_meta {day} missing"
        assert meta_path.read_text(encoding="utf-8").strip() == "PASS", (
            f"orders {day} should PASS (3 symbols -> 0.333 each)"
        )


def test_e2e_final_orders_golden(tmp_path: Path) -> None:
    """Golden: Given 3-day scenario, final day orders have expected symbols and weights."""
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(parents=True)
    _setup_three_day_snapshots(snapshot_root)

    outdir = tmp_path / "out"
    env = {"BIST_CORE_SNAPSHOT_DIR": str(snapshot_root)}

    for day in SCENARIO_DAYS:
        _run_cli(["eod", "run", "--day", day, "--outdir", str(outdir)], env=env)
        _run_cli(["plan", "--date", day], env=env)
        _run_cli(["orders", "--date", day], env=env)

    last_day = SCENARIO_DAYS[-1]
    orders_path = snapshot_root / last_day / "orders_equal_weight.csv"
    with orders_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    symbols = {r["symbol"] for r in rows}
    assert symbols == {"AAA", "BBB", "CCC"}, f"Expected AAA,BBB,CCC got {symbols}"
    for r in rows:
        w = float(r["target_weight"])
        assert abs(w - 1.0 / 3) < 1e-5, f"weight {w} not ~0.333 for {r['symbol']}"


def test_e2e_ask_flow_integration(tmp_path: Path) -> None:
    """ask --json for a symbol after eod run produces valid artifact."""
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(parents=True)
    _setup_three_day_snapshots(snapshot_root)

    outdir = tmp_path / "out"
    env = {"BIST_CORE_SNAPSHOT_DIR": str(snapshot_root)}
    day = SCENARIO_DAYS[0]
    _run_cli(["eod", "run", "--day", day, "--outdir", str(outdir)], env=env)

    r = _run_cli(["ask", "AAA", "--day", day, "--json"], env=env)
    assert r.returncode == 0, f"ask failed: {r.stderr or r.stdout}"
    data = json.loads(r.stdout)
    assert "symbol" in data or "decision_raw" in data or "score" in data
