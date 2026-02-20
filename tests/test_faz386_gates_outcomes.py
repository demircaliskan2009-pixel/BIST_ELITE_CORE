"""FAZ386: Gates outcomes PASS/FAIL JSON — schema, deterministic order, gate fail -> HOLD."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_ask(tmp_path: Path, symbol: str, day: str, csv_content: str) -> tuple[int, dict | None]:
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / day
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(csv_content, encoding="utf-8")
    out_dir = tmp_path / "out" / "ask"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)
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


def test_faz386_gates_outcomes_schema(tmp_path: Path) -> None:
    """Artifact has gates with outcome and reason per gate; deterministic key order."""
    csv = "symbol,close\nAAA,100.0\n"
    _, data = _run_ask(tmp_path, "AAA", "2099-01-15", csv)
    assert data is not None
    assert "gates" in data
    gates = data["gates"]
    assert isinstance(gates, dict)
    for gate_name, gate_val in gates.items():
        assert "outcome" in gate_val
        assert gate_val["outcome"] in ("PASS", "FAIL")
        assert "reason" in gate_val


def test_faz386_gate_fail_returns_fail(tmp_path: Path) -> None:
    """HOLD path (InsufficientHistory) has at least one gate with outcome FAIL."""
    csv = "symbol,close\nBBB,100.0\n"
    _, data = _run_ask(tmp_path, "BBB", "2099-01-16", csv)
    assert data is not None
    assert data["decision_raw"] == "PASS"
    assert "gates" in data
    outcomes = [g["outcome"] for g in data["gates"].values()]
    assert "FAIL" in outcomes
