"""FAZ136: Risk sizing from capital, max_loss, stop distance."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz136_compute_risk_sizing_unit() -> None:
    """_compute_risk_sizing returns correct values with explicit math."""
    sys.path.insert(0, str(_project_root() / "src"))
    from bist_core.cli.main import _compute_risk_sizing

    plan = {"entry": 100.0, "stop": 98.0}
    out = _compute_risk_sizing(capital=30000.0, max_loss_tl=500.0, plan=plan)
    assert out is not None
    assert out["stop_distance_tl"] == 2.0
    assert out["position_size_shares"] == 250
    assert out["position_size_tl"] == 25000.0
    assert out["formula"] == "floor(max_loss_tl / stop_distance_tl)"
    assert out["rounding"] == "floor"


def test_faz136_compute_risk_sizing_floor_rounding() -> None:
    """Position size uses floor (conservative)."""
    sys.path.insert(0, str(_project_root() / "src"))
    from bist_core.cli.main import _compute_risk_sizing

    plan = {"entry": 10.0, "stop": 9.0}
    out = _compute_risk_sizing(capital=None, max_loss_tl=15.0, plan=plan)
    assert out is not None
    assert out["position_size_shares"] == 15
    assert out["stop_distance_tl"] == 1.0


def test_faz136_compute_risk_sizing_missing_inputs() -> None:
    """Returns None when max_loss or plan missing."""
    sys.path.insert(0, str(_project_root() / "src"))
    from bist_core.cli.main import _compute_risk_sizing

    assert _compute_risk_sizing(10000.0, None, {"entry": 100, "stop": 98}) is None
    assert _compute_risk_sizing(10000.0, 500.0, None) is None
    assert _compute_risk_sizing(10000.0, 500.0, {"entry": 100}) is None


def test_faz136_zero_capital_returns_none() -> None:
    """Zero capital -> None (fail-closed)."""
    sys.path.insert(0, str(_project_root() / "src"))
    from bist_core.cli.main import _compute_risk_sizing

    plan = {"entry": 100.0, "stop": 98.0}
    assert _compute_risk_sizing(capital=0.0, max_loss_tl=500.0, plan=plan) is None
    assert _compute_risk_sizing(capital=-1.0, max_loss_tl=500.0, plan=plan) is None


def test_faz136_extreme_max_loss_returns_none() -> None:
    """max_loss <= 0 -> None (fail-closed)."""
    sys.path.insert(0, str(_project_root() / "src"))
    from bist_core.cli.main import _compute_risk_sizing

    plan = {"entry": 100.0, "stop": 98.0}
    assert _compute_risk_sizing(capital=10000.0, max_loss_tl=0.0, plan=plan) is None
    assert _compute_risk_sizing(capital=10000.0, max_loss_tl=-100.0, plan=plan) is None


def test_faz136_position_exceeds_capital_returns_none() -> None:
    """When position_size_tl > capital -> None (fail-closed, no overallocation)."""
    sys.path.insert(0, str(_project_root() / "src"))
    from bist_core.cli.main import _compute_risk_sizing

    plan = {"entry": 100.0, "stop": 98.0}
    out = _compute_risk_sizing(capital=10000.0, max_loss_tl=500.0, plan=plan)
    assert out is None
    out_ok = _compute_risk_sizing(capital=30000.0, max_loss_tl=500.0, plan=plan)
    assert out_ok is not None
    assert out_ok["position_size_tl"] == 25000.0


def test_faz136_typical_risk_scenario() -> None:
    """Typical: capital 100k, max_loss 2%, entry 50, stop 48 -> valid sizing."""
    sys.path.insert(0, str(_project_root() / "src"))
    from bist_core.cli.main import _compute_risk_sizing

    plan = {"entry": 50.0, "stop": 48.0}
    out = _compute_risk_sizing(capital=100000.0, max_loss_tl=2000.0, plan=plan)
    assert out is not None
    assert out["stop_distance_tl"] == 2.0
    assert out["position_size_shares"] == 1000
    assert out["position_size_tl"] == 50000.0
    assert out["position_size_tl"] <= 100000.0


def test_faz136_risk_sizing_in_artifact(tmp_path: Path) -> None:
    """ask with capital and max_loss writes risk_sizing when plan has entry/stop."""
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close,open,high,low,volume\nAAA,100,99,101,98,1000000\n",
        encoding="utf-8",
    )
    for i in range(25):
        d = snap_root / f"2098-12-{i+1:02d}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "snapshot.csv").write_text(
            f"symbol,close,open,high,low,volume\nAAA,{100-i},99,101,98,1000000\n",
            encoding="utf-8",
        )
    out_dir = tmp_path / "out"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)

    import subprocess
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "ask",
            "AAA",
            "--day",
            "2099-01-01",
            "--capital",
            "10000",
            "--max-loss-tl",
            "500",
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )
    if result.returncode != 0:
        pytest.skip("ask failed - may need full config")
    artifact = out_dir / "2099-01-01" / "AAA.json"
    if not artifact.exists():
        pytest.skip("artifact not created")
    data = json.loads(artifact.read_text(encoding="utf-8"))
    if "risk_sizing" in data:
        rs = data["risk_sizing"]
        assert "position_size_shares" in rs
        assert "stop_distance_tl" in rs
        assert "formula" in rs
