"""Strategy registry — ask/scan append to strategies.jsonl. Deterministic keys, fail-closed."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_ask(tmp_path: Path, symbol: str, day: str, csv_content: str) -> tuple[int, dict | None]:
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / day
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(csv_content, encoding="utf-8")
    out_dir = tmp_path / "out" / "ask"
    log_path = tmp_path / "strategies.jsonl"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)
    env["BIST_CORE_STRATEGY_LOG"] = str(log_path)
    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "ask", symbol, "--day", day, "--out", str(out_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )
    artifact = out_dir / day / f"{symbol}.json"
    if artifact.exists():
        return result.returncode, json.loads(artifact.read_text(encoding="utf-8"))
    return result.returncode, None


def _run_scan_json(tmp_path: Path, day: str, csv_content: str, *extra_args: str) -> tuple[int, str]:
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "snapshot.csv").write_text(csv_content, encoding="utf-8")
    log_path = tmp_path / "strategies.jsonl"
    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)
    env["BIST_CORE_STRATEGY_LOG"] = str(log_path)
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


def _read_strategy_log(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    lines = [ln.strip() for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def test_strategy_registry_ask_appends_entry(tmp_path: Path) -> None:
    """ask appends a strategy record to strategies.jsonl with required fields."""
    csv = "symbol,close\nAAA,100.0\n"
    code, data = _run_ask(tmp_path, "AAA", "2099-01-01", csv)
    assert code == 0
    assert data is not None

    log_path = tmp_path / "strategies.jsonl"
    assert log_path.exists()
    entries = _read_strategy_log(log_path)
    assert len(entries) >= 1
    rec = entries[-1]
    assert rec.get("symbol") == "AAA"
    assert rec.get("day") == "2099-01-01"
    assert rec.get("source") == "ask"
    assert "timestamp" in rec
    assert "params" in rec
    assert "strategy_detail" in rec
    assert rec.get("schema_version") == 1


def test_strategy_registry_scan_appends_entries(tmp_path: Path) -> None:
    """scan appends one record per symbol in top-N to strategies.jsonl."""
    csv = "symbol,close\nAKBNK,50.0\nGARAN,100.0\nTHYAO,25.0\n"
    code, out = _run_scan_json(tmp_path, "2099-01-01", csv, "--top-n", "2")
    assert code == 0

    log_path = tmp_path / "strategies.jsonl"
    assert log_path.exists()
    entries = _read_strategy_log(log_path)
    assert len(entries) >= 2
    symbols = [e["symbol"] for e in entries]
    assert "GARAN" in symbols or "AKBNK" in symbols
    for rec in entries:
        assert rec.get("source") == "scan"
        assert rec.get("day") == "2099-01-01"
        assert "strategy_detail" in rec
        assert "rank" in rec.get("strategy_detail", {})
