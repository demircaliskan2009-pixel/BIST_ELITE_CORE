"""FAZ145: Min volume/turnover filter in scan. Test-first: schema, golden, edge, fail-closed."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_scan(tmp_path: Path, day: str, csv_content: str, *extra_args: str) -> subprocess.CompletedProcess[str]:
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / day
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(csv_content, encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)
    return subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "scan", "--day", day, "--top-n", "10", *extra_args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )


def test_faz145_scan_min_volume_filters(tmp_path: Path) -> None:
    """Scan with --min-volume filters out low-volume symbols."""
    csv = "symbol,open,high,low,close,volume,turnover_tl\nLOW,100,101,99,100,1000,50000\nHIH,50,51,49,50,1000000,50000000\n"
    result = _run_scan(tmp_path, "2099-01-04", csv, "--min-volume", "500000")
    assert result.returncode == 0
    assert "HIH" in result.stdout
    assert "LOW" not in result.stdout


def test_faz145_scan_min_turnover_filters(tmp_path: Path) -> None:
    """Scan with --min-turnover filters out low-turnover symbols."""
    csv = "symbol,open,high,low,close,volume,turnover_tl\nLOT,100,101,99,100,100000,1000000\nHIT,50,51,49,50,100000,100000000\n"
    result = _run_scan(tmp_path, "2099-01-05", csv, "--min-turnover", "50000000")
    assert result.returncode == 0
    assert "HIT" in result.stdout
    assert "LOT" not in result.stdout


def test_faz145_scan_close_only_no_crash(tmp_path: Path) -> None:
    """Fail-closed: close-only snapshot + liquidity flags -> no crash, no filtering (all symbols pass)."""
    csv = "symbol,close\nAAA,100.0\nBBB,200.0\n"
    result = _run_scan(tmp_path, "2099-01-06", csv, "--min-volume", "500000")
    assert result.returncode == 0
    assert "AAA" in result.stdout or "BBB" in result.stdout


def test_faz145_scan_both_filters(tmp_path: Path) -> None:
    """Edge case: both --min-volume and --min-turnover; symbol must pass both."""
    csv = "symbol,open,high,low,close,volume,turnover_tl\n"
    csv += "LOW,100,101,99,100,1000,1000000\n"  # low vol, high turnover
    csv += "HIT,50,51,49,50,1000000,100000000\n"  # both pass
    result = _run_scan(tmp_path, "2099-01-07", csv, "--min-volume", "500000", "--min-turnover", "50000000")
    assert result.returncode == 0
    assert "HIT" in result.stdout
    assert "LOW" not in result.stdout


def test_faz145_scan_schema_ranked_lines(tmp_path: Path) -> None:
    """Schema: scan output has ranked lines with symbol and score."""
    csv = "symbol,open,high,low,close,volume,turnover_tl\nAAA,100,101,99,100,1000000,50000000\n"
    result = _run_scan(tmp_path, "2099-01-08", csv)
    assert result.returncode == 0
    assert "AAA" in result.stdout
    assert "score=" in result.stdout or "Scan" in result.stdout
