"""FAZ556: Orders export — CSV/JSON schema, --out, orders_meta.txt format."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_orders(date: str, out: str | None = None, snap_dir: str | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    if snap_dir:
        env["BIST_CORE_SNAPSHOT_DIR"] = snap_dir
    cmd = [sys.executable, "-m", "bist_core.cli", "orders", "--date", date]
    if out:
        cmd.extend(["--out", out])
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env, timeout=30)


ORDERS_CSV_HEADERS = ["symbol", "target_weight"]
ORDERS_META_VALUES = frozenset({"PASS", "FAIL"})


def test_faz556_orders_csv_headers(tmp_path: Path) -> None:
    """orders CSV has exact headers: symbol, target_weight."""
    snap = tmp_path / "snap"
    day_dir = snap / "2025-01-15"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\nAAA,100.0\nBBB,200.0\n", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap)
    subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "plan", "--date", "2025-01-15"],
        capture_output=True,
        env=env,
        timeout=15,
        check=True,
    )
    r = _run_orders("2025-01-15", snap_dir=str(snap))
    assert r.returncode == 0
    csv_path = day_dir / "orders_equal_weight.csv"
    assert csv_path.exists()
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ORDERS_CSV_HEADERS


def test_faz556_orders_json_schema(tmp_path: Path) -> None:
    """orders JSON has schema_version, day, rows with symbol and target_weight."""
    snap = tmp_path / "snap"
    day_dir = snap / "2025-01-15"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\nAAA,100.0\nBBB,200.0\n", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap)
    subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "plan", "--date", "2025-01-15"],
        capture_output=True,
        env=env,
        timeout=15,
        check=True,
    )
    r = _run_orders("2025-01-15", snap_dir=str(snap))
    assert r.returncode == 0
    json_path = day_dir / "orders_equal_weight.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert "schema_version" in data
    assert data["schema_version"] == 1
    assert data["day"] == "2025-01-15"
    assert "rows" in data
    assert len(data["rows"]) == 2
    for row in data["rows"]:
        assert "symbol" in row
        assert "target_weight" in row
        assert isinstance(row["target_weight"], (int, float))


def test_faz556_orders_meta_format(tmp_path: Path) -> None:
    """orders_meta.txt contains exactly PASS or FAIL."""
    snap = tmp_path / "snap"
    day_dir = snap / "2025-01-15"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\nAAA,100.0\nBBB,200.0\n", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap)
    subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "plan", "--date", "2025-01-15"],
        capture_output=True,
        env=env,
        timeout=15,
        check=True,
    )
    r = _run_orders("2025-01-15", snap_dir=str(snap))
    assert r.returncode == 0
    meta_path = day_dir / "orders_meta.txt"
    assert meta_path.exists()
    content = meta_path.read_text(encoding="utf-8").strip()
    assert content in ORDERS_META_VALUES


def test_faz556_orders_out_dir_created(tmp_path: Path) -> None:
    """orders --out creates directory if it does not exist."""
    snap = tmp_path / "snap"
    out = tmp_path / "export"
    day_dir = snap / "2025-01-15"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\nAAA,100.0\nBBB,200.0\n", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap)
    subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "plan", "--date", "2025-01-15"],
        capture_output=True,
        env=env,
        timeout=15,
        check=True,
    )
    assert not out.exists()
    r = _run_orders("2025-01-15", out=str(out), snap_dir=str(snap))
    assert r.returncode == 0
    assert (out / "2025-01-15" / "orders_equal_weight.csv").exists()
    assert (out / "2025-01-15" / "orders_equal_weight.json").exists()
    assert (out / "2025-01-15" / "orders_meta.txt").exists()


def test_faz556_orders_fail_meta(tmp_path: Path) -> None:
    """orders risk FAIL: orders_meta.txt contains FAIL, no CSV/JSON."""
    snap = tmp_path / "snap"
    day_dir = snap / "2025-01-16"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\nTEST,10.0\n", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap)
    subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "plan", "--date", "2025-01-16"],
        capture_output=True,
        env=env,
        timeout=15,
        check=True,
    )
    r = _run_orders("2025-01-16", snap_dir=str(snap))
    assert r.returncode == 2
    meta_path = day_dir / "orders_meta.txt"
    assert meta_path.exists()
    assert meta_path.read_text(encoding="utf-8").strip() == "FAIL"
    assert not (day_dir / "orders_equal_weight.csv").exists()
    assert not (day_dir / "orders_equal_weight.json").exists()
