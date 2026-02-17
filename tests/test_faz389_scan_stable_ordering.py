"""FAZ389: Scan stable ordering - equal score tie-break by symbol ascending, deterministic."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_scan_json(tmp_path: Path, day: str, csv_content: str, *extra_args: str) -> subprocess.CompletedProcess[str]:
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "snapshot.csv").write_text(csv_content, encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)
    return subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "scan", "--day", day, "--top-n", "10", "--json", *extra_args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )


def test_faz389_scan_equal_scores_alphabetical(tmp_path: Path) -> None:
    """Equal scores tie-break by symbol ascending (AAA before BBB before CCC)."""
    csv = "symbol,open,high,low,close,volume,turnover_tl\n"
    csv += "ZZZ,100,101,99,100,1000000,50000000\n"
    csv += "AAA,100,101,99,100,1000000,50000000\n"
    csv += "MMM,100,101,99,100,1000000,50000000\n"
    result = _run_scan_json(tmp_path, "2099-01-15", csv)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    ranked = data["ranked"]
    symbols = [r["symbol"] for r in ranked]
    assert symbols == sorted(symbols), f"Expected alphabetical order, got {symbols}"


def test_faz389_scan_deterministic_twice(tmp_path: Path) -> None:
    """Same input produces same ranked order twice (excluding generated_at)."""
    csv = "symbol,open,high,low,close,volume,turnover_tl\n"
    csv += "X,100,101,99,100,1000000,50000000\n"
    csv += "Y,100,101,99,100,1000000,50000000\n"
    csv += "Z,100,101,99,100,1000000,50000000\n"
    r1 = _run_scan_json(tmp_path, "2099-01-16", csv)
    r2 = _run_scan_json(tmp_path, "2099-01-16", csv)
    assert r1.returncode == 0 and r2.returncode == 0
    d1 = json.loads(r1.stdout)
    d2 = json.loads(r2.stdout)
    assert d1["ranked"] == d2["ranked"], "Ranked order must be identical"
    assert d1["day"] == d2["day"]
    assert d1["schema_version"] == d2["schema_version"]
