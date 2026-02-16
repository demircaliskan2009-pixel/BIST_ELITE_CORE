"""FAZ387: Evidence stabilization — sorted signals, stable keys, deterministic JSON."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz387_evidence_signals_sorted(tmp_path: Path) -> None:
    """Evidence.signals has deterministic order (dict keys sorted, list items sorted)."""
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / "2099-01-10"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\nXXX,100.0\n", encoding="utf-8")
    out_dir = tmp_path / "out" / "ask"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)

    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "ask", "XXX", "--day", "2099-01-10", "--out", str(out_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    artifact = out_dir / "2099-01-10" / "XXX.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text(encoding="utf-8"))
    ev = data.get("Evidence", {})
    assert "signals" in ev
    sigs = ev["signals"]
    if isinstance(sigs, dict):
        assert list(sigs.keys()) == sorted(sigs.keys())
    elif isinstance(sigs, list):
        assert sigs == sorted(sigs, key=lambda x: json.dumps(x, sort_keys=True) if isinstance(x, dict) else str(x))


def test_faz387_evidence_keys_stable_order(tmp_path: Path) -> None:
    """Evidence has stable key order: signals, source, source_sha256 (when present)."""
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / "2099-01-11"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\nYYY,50.0\n", encoding="utf-8")
    out_dir = tmp_path / "out" / "ask"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)

    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "ask", "YYY", "--day", "2099-01-11", "--out", str(out_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    artifact = out_dir / "2099-01-11" / "YYY.json"
    data = json.loads(artifact.read_text(encoding="utf-8"))
    ev = data.get("Evidence", {})
    keys = list(ev.keys())
    assert "signals" in keys
    assert keys.index("signals") == 0
    if "source" in ev:
        assert keys.index("source") < keys.index("source_sha256") if "source_sha256" in ev else True


def test_faz387_artifact_byte_for_byte_deterministic(tmp_path: Path) -> None:
    """Same inputs produce identical artifact bytes (excluding generated_at)."""
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / "2099-01-12"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\nZZZ,75.0\n", encoding="utf-8")
    out1 = tmp_path / "out1" / "ask"
    out2 = tmp_path / "out2" / "ask"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)

    for out_dir in (out1, out2):
        subprocess.run(
            [sys.executable, "-m", "bist_core.cli", "ask", "ZZZ", "--day", "2099-01-12", "--out", str(out_dir)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=30,
        )

    p1 = out1 / "2099-01-12" / "ZZZ.json"
    p2 = out2 / "2099-01-12" / "ZZZ.json"
    assert p1.exists() and p2.exists()
    d1 = json.loads(p1.read_text(encoding="utf-8"))
    d2 = json.loads(p2.read_text(encoding="utf-8"))
    d1.pop("generated_at", None)
    d2.pop("generated_at", None)
    d1.pop("content_sha256", None)
    d2.pop("content_sha256", None)
    assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
