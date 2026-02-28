"""FAZ150: Scan drill-down determinism — same params produce same ask command."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_scan_text(tmp_path: Path, day: str, csv_content: str, *extra_args: str) -> tuple[int, str]:
    """Run scan without --json to get drill-down section."""
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "snapshot.csv").write_text(csv_content, encoding="utf-8")
    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)
    env.pop("BIST_CORE_ALLOW_NETWORK", None)
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "scan", "--day", day, "--top-n", "5", *extra_args],
        cwd=str(_repo_root()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )
    return r.returncode, r.stdout


def _extract_drill_down(stdout: str) -> list[str]:
    """Extract drill-down ask commands from scan output."""
    lines = stdout.splitlines()
    in_drill = False
    result = []
    for line in lines:
        if line.strip() == "Drill-down:":
            in_drill = True
            continue
        if in_drill and line.strip().startswith("python -m bist_core.cli ask"):
            result.append(line.strip())
    return result


def test_faz150_scan_drill_down_deterministic(tmp_path: Path) -> None:
    """Same params produce same drill-down ask commands twice."""
    csv = "symbol,open,high,low,close,volume,turnover_tl\n"
    csv += "AKBNK,50,51,49,50,1000000,50000000\nGARAN,100,101,99,100,1000000,50000000\n"
    code1, out1 = _run_scan_text(tmp_path, "2025-01-15", csv)
    code2, out2 = _run_scan_text(tmp_path, "2025-01-15", csv)
    assert code1 == 0 and code2 == 0
    drill1 = _extract_drill_down(out1)
    drill2 = _extract_drill_down(out2)
    assert drill1 == drill2, "Drill-down must be identical for same params"


def test_faz150_scan_drill_down_contains_day(tmp_path: Path) -> None:
    """Drill-down ask commands include --day param."""
    csv = "symbol,close\nAKBNK,50.0\n"
    code, out = _run_scan_text(tmp_path, "2025-02-20", csv)
    assert code == 0
    drill = _extract_drill_down(out)
    assert len(drill) >= 1
    assert "--day" in drill[0]
    assert "2025-02-20" in drill[0]
    assert "AKBNK" in drill[0]
