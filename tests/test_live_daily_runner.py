"""FAZ566: Live daily runner — scan, ask, evaluate, report. Offline. Deterministic."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# Import from tools (repo root in path for tests)
import sys
_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
from tools.live_daily_runner import run_live_daily, _ensure_dirs, _run_scan


def test_live_daily_ensure_dirs(tmp_path: Path) -> None:
    """_ensure_dirs creates expected directories."""
    paths = _ensure_dirs(tmp_path, "2025-01-15")
    assert (tmp_path / "daily_scan" / "2025-01-15").is_dir()
    assert (tmp_path / "ask" / "2025-01-15").is_dir()
    assert (tmp_path / "outcomes" / "2025-01-15").is_dir()
    assert (tmp_path / "reports" / "2025-01-15").is_dir()
    assert paths["daily_scan"].name == "2025-01-15"
    assert paths["reports"].name == "2025-01-15"


def test_live_daily_full_workflow(tmp_path: Path) -> None:
    """Run full workflow with minimal fixture snapshot. Assert outputs exist."""
    snap = tmp_path / "snapshots"
    (snap / "2099-01-01").mkdir(parents=True)
    (snap / "2099-01-01" / "snapshot.csv").write_text(
        "symbol,close\nAAA,100.0\nBBB,99.0\nCCC,98.0\n",
        encoding="utf-8",
    )
    out_root = tmp_path / "log"

    code, symbols, paths = run_live_daily(
        day="2099-01-01",
        top_n=2,
        out_root=out_root,
        snapshot_root=snap,
    )

    assert code == 0
    assert len(symbols) >= 1
    assert "AAA" in symbols or "BBB" in symbols or "CCC" in symbols

    scan_json = paths["daily_scan"].parent / "2099-01-01" / "scan.json"
    assert scan_json.is_file(), f"Expected scan artifact at {scan_json}"
    scan_data = json.loads(scan_json.read_text(encoding="utf-8"))
    assert "ranked" in scan_data
    assert scan_data["day"] == "2099-01-01"

    for sym in symbols:
        ask_artifact = paths["ask"] / f"{sym}.json"
        assert ask_artifact.is_file(), f"Expected ask artifact for {sym}"

    reports_dir = paths["reports"]
    json_report = reports_dir / "performance.json"
    csv_report = reports_dir / "performance.csv"
    assert json_report.is_file(), f"Expected performance.json at {json_report}"
    assert csv_report.is_file(), f"Expected performance.csv at {csv_report}"

    # FAZ572: Scoreboard written (BUY/SELL/HOLD + horizon returns)
    scoreboard_json = reports_dir / "scoreboard.json"
    scoreboard_csv = reports_dir / "scoreboard.csv"
    assert scoreboard_json.is_file(), f"Expected scoreboard.json at {scoreboard_json}"
    assert scoreboard_csv.is_file(), f"Expected scoreboard.csv at {scoreboard_csv}"


def test_live_daily_fail_closed_empty_snapshot(tmp_path: Path) -> None:
    """Missing snapshot: scan returns empty, we continue with empty symbols (exit 0, HOLD-like)."""
    snap = tmp_path / "empty_snap"
    snap.mkdir()
    out_root = tmp_path / "log"

    code, symbols, paths = run_live_daily(
        day="2099-01-02",
        top_n=5,
        out_root=out_root,
        snapshot_root=snap,
    )

    assert code == 0
    assert symbols == []
    assert paths["daily_scan"].is_dir()
    assert paths["reports"].is_dir()
