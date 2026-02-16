"""FAZ139: Advice artifact schema, golden determinism, HOLD path.

Test Realism: schema test (keys/types), golden output (stable deterministic fields),
missing-data test (fail-closed HOLD path). No mocks; fixture-based integration.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_ask(snap_root: Path, out_dir: Path, symbol: str, day: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "ask",
            symbol,
            "--day",
            day,
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )


def _minimal_snapshot(tmp_path: Path, day: str, symbol: str, bars: int = 1) -> Path:
    """Create snapshot with N bars for symbol. Default 1 bar -> HOLD."""
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / day
    day_dir.mkdir(parents=True)
    rows = ["symbol,close"]
    for i in range(bars):
        rows.append(f"{symbol},{100.0 - i}")
    (day_dir / "snapshot.csv").write_text("\n".join(rows), encoding="utf-8")
    for i in range(1, bars):
        prev_day = f"2098-12-{31 - i:02d}" if i < 31 else f"2098-11-{30 - (i - 31):02d}"
        prev_dir = snap_root / prev_day
        prev_dir.mkdir(parents=True, exist_ok=True)
        (prev_dir / "snapshot.csv").write_text(
            f"symbol,close\n{symbol},{100.0 - i}\n",
            encoding="utf-8",
        )
    return snap_root


def test_faz139_advice_artifact_schema(tmp_path: Path) -> None:
    """Schema test: artifact has required keys and correct types."""
    snap_root = _minimal_snapshot(tmp_path, "2099-01-01", "AAA", bars=1)
    out_dir = tmp_path / "out" / "ask"
    result = _run_ask(snap_root, out_dir, "AAA", "2099-01-01")
    assert result.returncode == 0
    artifact_path = out_dir / "2099-01-01" / "AAA.json"
    assert artifact_path.exists()
    data = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert isinstance(data.get("symbol"), str)
    assert isinstance(data.get("day"), str)
    assert isinstance(data.get("decision_raw"), str)
    assert isinstance(data.get("score"), (int, float))
    assert isinstance(data.get("signals"), list)
    assert isinstance(data.get("schema_version"), int)
    assert data["schema_version"] == 1
    assert isinstance(data.get("generated_at"), str)
    assert "T" in data["generated_at"]

    decision = data.get("Decision")
    assert isinstance(decision, dict)
    assert "decision_raw" in decision
    assert "score" in decision

    evidence = data.get("Evidence")
    assert isinstance(evidence, dict)
    assert "signals" in evidence
    assert isinstance(evidence["signals"], list)

    cause_effect = data.get("Cause-Effect")
    assert isinstance(cause_effect, dict)
    assert "why" in cause_effect
    assert "invalidates" in cause_effect
    assert "watch_next" in cause_effect

    ev = data.get("Evidence", {})
    if ev.get("source"):
        assert "source_sha256" in ev
        assert len(ev["source_sha256"]) == 64

    assert data.get("Entry/Stop/Targets") is None or isinstance(data["Entry/Stop/Targets"], dict)
    assert data.get("plan") is None or isinstance(data["plan"], dict)
    assert isinstance(data.get("text"), str)


def test_faz139_advice_artifact_deterministic_fields(tmp_path: Path) -> None:
    """Golden: same fixture -> same deterministic output (excluding generated_at)."""
    snap_root = _minimal_snapshot(tmp_path, "2099-01-01", "AAA", bars=1)
    out_dir = tmp_path / "out" / "ask"
    result1 = _run_ask(snap_root, out_dir, "AAA", "2099-01-01")
    assert result1.returncode == 0
    path1 = out_dir / "2099-01-01" / "AAA.json"
    data1 = json.loads(path1.read_text(encoding="utf-8"))

    out_dir2 = tmp_path / "out2" / "ask"
    result2 = _run_ask(snap_root, out_dir2, "AAA", "2099-01-01")
    assert result2.returncode == 0
    path2 = out_dir2 / "2099-01-01" / "AAA.json"
    data2 = json.loads(path2.read_text(encoding="utf-8"))

    exclude = {"generated_at"}
    d1 = {k: v for k, v in data1.items() if k not in exclude}
    d2 = {k: v for k, v in data2.items() if k not in exclude}
    assert d1 == d2


def test_faz139_advice_artifact_hold_path(tmp_path: Path) -> None:
    """Missing-data: 1 bar -> HOLD with InsufficientHistory, fail-closed."""
    snap_root = _minimal_snapshot(tmp_path, "2099-01-01", "BBB", bars=1)
    out_dir = tmp_path / "out" / "ask"
    result = _run_ask(snap_root, out_dir, "BBB", "2099-01-01")
    assert result.returncode == 0
    artifact_path = out_dir / "2099-01-01" / "BBB.json"
    assert artifact_path.exists()
    data = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert data["decision_raw"] == "HOLD"
    assert data["score"] == 0.0
    assert data["plan"] is None
    assert "InsufficientHistory" in data["text"]
    assert data["Evidence"]["signals"] == []
    assert data["Cause-Effect"]["why"] != "" or "InsufficientHistory" in data["text"]
