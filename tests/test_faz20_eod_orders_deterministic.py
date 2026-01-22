from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_eod(tmp_path: Path, day: str, outdir: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day_dir = snapshot_root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\n",
        encoding="utf-8",
    )
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "run",
            "--day",
            day,
            "--outdir",
            str(outdir),
            "--ignore-calendar",
            "--emit-orders",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0


def test_eod_orders_deterministic(tmp_path: Path) -> None:
    day = "2099-01-04"
    outdir_a = tmp_path / "run_a"
    outdir_b = tmp_path / "run_b"

    _run_eod(tmp_path, day, outdir_a)
    _run_eod(tmp_path, day, outdir_b)

    a_payload = (outdir_a / "orders" / "orders_intent.json").read_text(encoding="utf-8")
    b_payload = (outdir_b / "orders" / "orders_intent.json").read_text(encoding="utf-8")
    assert a_payload == b_payload
