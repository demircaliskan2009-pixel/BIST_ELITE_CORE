"""FAZ393: Scoreboard leakage guard — no future data; date <= as_of; fail-closed."""
from __future__ import annotations

from pathlib import Path

from bist_core.services.backtest import run_backtest, _leakage_guard
from datetime import date as Date


def test_faz393_leakage_guard_future_date_rejected(tmp_path: Path) -> None:
    """Backtest with date_to > as_of -> error leakage_guard, no metrics written."""
    snapshot_root = tmp_path / "snapshots"
    for day in ["2099-08-01", "2099-08-02", "2099-08-03"]:
        (snapshot_root / day).mkdir(parents=True)
        (snapshot_root / day / "snapshot.csv").write_text(
            "symbol,close\nA,10.0\n",
            encoding="utf-8",
        )
    outdir = tmp_path / "out"
    result = run_backtest(
        snapshot_root=snapshot_root,
        date_from="2099-08-01",
        date_to="2099-08-03",
        outdir=outdir,
        strategy="equal_weight",
        top_n=10,
        as_of="2099-08-02",
    )
    assert result.get("error") == "leakage_guard"
    assert "LEAKAGE" in (result.get("leakage_message") or "")
    assert "2099-08-03" in (result.get("leakage_message") or "")
    assert result.get("num_days") == 0
    assert not (outdir / "backtest" / "metrics.json").exists()


def test_faz393_leakage_guard_valid_pass(tmp_path: Path) -> None:
    """Backtest with date_to <= as_of -> runs normally."""
    snapshot_root = tmp_path / "snapshots"
    for day in ["2099-09-01", "2099-09-02"]:
        (snapshot_root / day).mkdir(parents=True)
        (snapshot_root / day / "snapshot.csv").write_text(
            "symbol,close\nB,20.0\n",
            encoding="utf-8",
        )
    outdir = tmp_path / "out"
    result = run_backtest(
        snapshot_root=snapshot_root,
        date_from="2099-09-01",
        date_to="2099-09-02",
        outdir=outdir,
        strategy="equal_weight",
        top_n=10,
        as_of="2099-09-02",
    )
    assert result.get("error") is None
    assert result.get("num_days") == 2
    assert (outdir / "backtest" / "metrics.json").is_file()


def test_faz393_leakage_guard_no_as_of_backward_compat(tmp_path: Path) -> None:
    """Without as_of, backtest runs (no guard)."""
    snapshot_root = tmp_path / "snapshots"
    (snapshot_root / "2099-10-01").mkdir(parents=True)
    (snapshot_root / "2099-10-01" / "snapshot.csv").write_text(
        "symbol,close\nC,30.0\n",
        encoding="utf-8",
    )
    result = run_backtest(
        snapshot_root=snapshot_root,
        date_from="2099-10-01",
        date_to="2099-10-01",
        outdir=tmp_path / "out",
        strategy="equal_weight",
        top_n=10,
    )
    assert result.get("error") is None


def test_faz393_leakage_guard_helper_deterministic() -> None:
    """_leakage_guard same inputs -> same result."""
    d1 = Date(2099, 1, 1)
    d2 = Date(2099, 1, 2)
    as_of = Date(2099, 1, 1)
    r1 = _leakage_guard(d1, d2, as_of)
    r2 = _leakage_guard(d1, d2, as_of)
    assert r1 == r2
    assert "LEAKAGE" in (r1 or "")
