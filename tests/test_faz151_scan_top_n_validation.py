"""FAZ151: Scan top_n validation — validate top_n within bounds. Test-first."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_scan(tmp_path: Path, day: str, csv_content: str, *extra_args: str) -> tuple[int, str]:
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "snapshot.csv").write_text(csv_content, encoding="utf-8")
    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)
    env.pop("BIST_CORE_ALLOW_NETWORK", None)
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "scan", "--day", day, "--json", *extra_args],
        cwd=str(_repo_root()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )
    return r.returncode, r.stdout


def test_faz151_top_n_zero_fails(tmp_path: Path) -> None:
    """top_n=0 must fail (fail-closed)."""
    csv = "symbol,close\nAKBNK,50.0\n"
    code, _ = _run_scan(tmp_path, "2025-01-15", csv, "--top-n", "0")
    assert code != 0, "top_n=0 must not succeed"


def test_faz151_top_n_respects_bounds(tmp_path: Path) -> None:
    """top_n=2 returns at most 2 ranked items."""
    csv = "symbol,open,high,low,close,volume,turnover_tl\n"
    csv += "AKBNK,50,51,49,50,1000000,50000000\nGARAN,100,101,99,100,1000000,50000000\nTHYAO,25,26,24,25,1000000,25000000\n"
    code, out = _run_scan(tmp_path, "2025-01-15", csv, "--top-n", "2")
    assert code == 0
    data = json.loads(out)
    assert len(data["ranked"]) <= 2


def test_faz151_top_n_exceeds_symbols(tmp_path: Path) -> None:
    """top_n=100 with 2 symbols returns 2 (no crash, graceful)."""
    csv = "symbol,close\nAKBNK,50.0\nGARAN,100.0\n"
    code, out = _run_scan(tmp_path, "2025-01-15", csv, "--top-n", "100")
    assert code == 0
    data = json.loads(out)
    assert len(data["ranked"]) == 2


def test_faz151_top_n_default(tmp_path: Path) -> None:
    """Default top_n yields ranked list (schema)."""
    csv = "symbol,close\nAKBNK,50.0\n"
    code, out = _run_scan(tmp_path, "2025-01-15", csv)
    assert code == 0
    data = json.loads(out)
    assert "ranked" in data
    assert isinstance(data["ranked"], list)
