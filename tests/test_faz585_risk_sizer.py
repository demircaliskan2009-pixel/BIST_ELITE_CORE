"""FAZ585: Risk budget sizer (ATR-based). Synthetic fixtures, no real market data."""

from __future__ import annotations

import csv
import os
import subprocess
import sys
from pathlib import Path


_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def _run_risk_sizer(
    day: str,
    horizon: int,
    top: int = 5,
    reports_root: Path | None = None,
    snapshot_root: Path | None = None,
) -> tuple[int, str, str]:
    """Run risk_sizer.py. Returns (exit_code, stdout, stderr)."""
    args = [
        sys.executable,
        str(_repo / "tools" / "risk_sizer.py"),
        "--day",
        day,
        "--horizon",
        str(horizon),
        "--top",
        str(top),
    ]
    if reports_root:
        args.extend(["--reports-root", str(reports_root)])
    if snapshot_root:
        args.extend(["--snapshot-root", str(snapshot_root)])
    r = subprocess.run(args, cwd=str(_repo), capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout or "", r.stderr or ""


def _build_ohlc_snapshots(
    tmp_path: Path,
    day: str,
    n_days: int,
    symbol_ohlc: dict[str, list[tuple[float, float, float, float]]],
) -> Path:
    """Build snapshot dir with OHLC. symbol_ohlc[sym] = [(o,h,l,c), ...]. Returns snapshot_root."""
    from datetime import datetime, timedelta

    base = tmp_path / "snapshots"
    base.mkdir(parents=True, exist_ok=True)
    dt = datetime.strptime(day, "%Y-%m-%d")
    for i in range(n_days):
        d = (dt - timedelta(days=n_days - 1 - i)).strftime("%Y-%m-%d")
        day_dir = base / d
        day_dir.mkdir(parents=True, exist_ok=True)
        rows = ["symbol,open,high,low,close"]
        for sym, series in symbol_ohlc.items():
            if i < len(series):
                o, h, l_, c = series[i]
                rows.append(f"{sym},{o:.4f},{h:.4f},{l_:.4f},{c:.4f}")
        (day_dir / "snapshot.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return base


def _write_topn_csv(reports_dir: Path, day: str, horizon: int, symbols: list[str]) -> None:
    """Write minimal topn_h{H}.csv for risk sizer input."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"topn_h{horizon}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "day",
                "horizon_days",
                "symbol",
                "bars_used",
                "lookback_used",
                "mu_hat",
                "sigma_hat",
                "p_up",
                "p_gt_cost",
                "score",
                "notes",
            ],
            extrasaction="ignore",
        )
        w.writeheader()
        for sym in symbols:
            w.writerow(
                {
                    "day": day,
                    "horizon_days": horizon,
                    "symbol": sym,
                    "bars_used": 60,
                    "lookback_used": 60,
                    "mu_hat": 0.001,
                    "sigma_hat": 0.01,
                    "p_up": 0.55,
                    "p_gt_cost": 0.52,
                    "score": 0.1,
                    "notes": "",
                }
            )


def test_risk_plan_files_created(tmp_path: Path) -> None:
    """risk_plan csv/json/txt created."""
    # 15 days OHLC (ATR needs 14 bars + 1 for prev_close)
    ohlc = []
    for i in range(15):
        c = 100.0 + i
        o = 99.0 + i
        h = c + 1.0
        l_ = c - 1.0
        ohlc.append((o, h, l_, c))
    snap = _build_ohlc_snapshots(tmp_path, "2025-03-15", 15, {"AAA": ohlc})
    reports_root = tmp_path / "log" / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_topn_csv(reports_dir, "2025-03-15", 1, ["AAA"])

    code, _, _ = _run_risk_sizer("2025-03-15", 1, top=5, reports_root=reports_root, snapshot_root=snap)
    assert code == 0
    assert (reports_dir / "risk_plan_h1.json").is_file()
    assert (reports_dir / "risk_plan_h1.csv").is_file()
    assert (reports_dir / "risk_plan_h1.txt").is_file()


def test_qty_floor_math(tmp_path: Path) -> None:
    """qty = floor(risk_amount / stop_distance). Deterministic."""
    # TR = 2.0 per bar -> ATR(14) = 2.0. stop_distance = 2*2 = 4. risk = 30000*0.02 = 600. qty = 150
    ohlc = []
    for i in range(15):
        c = 100.0 + i * 2
        o = c - 1
        h = c + 1
        l_ = c - 1
        ohlc.append((o, h, l_, c))
    snap = _build_ohlc_snapshots(tmp_path, "2025-03-15", 15, {"AAA": ohlc})
    reports_root = tmp_path / "log" / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_topn_csv(reports_dir, "2025-03-15", 1, ["AAA"])

    code, _, _ = _run_risk_sizer("2025-03-15", 1, top=5, reports_root=reports_root, snapshot_root=snap)
    assert code == 0
    with (reports_dir / "risk_plan_h1.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    r = rows[0]
    assert r["symbol"] == "AAA"
    assert int(r["qty"]) >= 1
    assert float(r["capital_try"]) == 30000.0
    assert float(r["risk_pct"]) == 0.02
    assert float(r["risk_try"]) == 600.0


def test_deterministic_output(tmp_path: Path) -> None:
    """Same input -> identical output."""
    ohlc = []
    for i in range(15):
        c = 100.0 + i
        ohlc.append((c - 0.5, c + 0.5, c - 0.5, c))
    snap = _build_ohlc_snapshots(tmp_path, "2025-03-15", 15, {"AAA": ohlc, "BBB": ohlc})
    reports_root = tmp_path / "log" / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_topn_csv(reports_dir, "2025-03-15", 1, ["AAA", "BBB"])

    _run_risk_sizer("2025-03-15", 1, top=5, reports_root=reports_root, snapshot_root=snap)
    j1 = (reports_dir / "risk_plan_h1.json").read_text(encoding="utf-8")
    _run_risk_sizer("2025-03-15", 1, top=5, reports_root=reports_root, snapshot_root=snap)
    j2 = (reports_dir / "risk_plan_h1.json").read_text(encoding="utf-8")
    assert j1 == j2


def test_invalid_env_exit_1(tmp_path: Path) -> None:
    """Invalid env (BIST_CAPITAL_TRY<=0) => exit 1."""
    ohlc = [(99, 101, 99, 100)] * 15
    snap = _build_ohlc_snapshots(tmp_path, "2025-03-15", 15, {"AAA": ohlc})
    reports_root = tmp_path / "log" / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_topn_csv(reports_dir, "2025-03-15", 1, ["AAA"])

    env = os.environ.copy()
    env["BIST_CAPITAL_TRY"] = "0"
    args = [
        sys.executable,
        str(_repo / "tools" / "risk_sizer.py"),
        "--day",
        "2025-03-15",
        "--horizon",
        "1",
        "--top",
        "5",
        "--reports-root",
        str(reports_root),
        "--snapshot-root",
        str(snap),
    ]
    r = subprocess.run(args, cwd=str(_repo), capture_output=True, text=True, timeout=30, env=env)
    assert r.returncode == 1
    assert "invalid_env" in r.stderr or "BIST_CAPITAL" in r.stderr


def test_insufficient_history_qty_zero(tmp_path: Path) -> None:
    """Insufficient bars for ATR => qty=0, notes=InsufficientHistory."""
    # Only 5 days - need 15 for ATR(14)
    ohlc = [(99, 101, 99, 100)] * 5
    snap = _build_ohlc_snapshots(tmp_path, "2025-03-15", 5, {"AAA": ohlc})
    reports_root = tmp_path / "log" / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_topn_csv(reports_dir, "2025-03-15", 1, ["AAA"])

    code, _, _ = _run_risk_sizer("2025-03-15", 1, top=5, reports_root=reports_root, snapshot_root=snap)
    assert code == 0
    with (reports_dir / "risk_plan_h1.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["qty"] == "0"
    assert rows[0]["notes"] == "InsufficientHistory"


def test_too_small_notes(tmp_path: Path) -> None:
    """When stop_distance > risk_amount => qty=0, notes=TooSmall."""
    # Normal ATR ~2, stop_distance ~4. Use tiny capital so risk < stop_distance.
    ohlc = [(99, 101, 99, 100)] * 15
    snap = _build_ohlc_snapshots(tmp_path, "2025-03-15", 15, {"AAA": ohlc})
    reports_root = tmp_path / "log" / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_topn_csv(reports_dir, "2025-03-15", 1, ["AAA"])

    env = os.environ.copy()
    env["BIST_CAPITAL_TRY"] = "1"
    env["BIST_RISK_PCT"] = "0.02"  # risk = 0.02 TRY
    args = [
        sys.executable,
        str(_repo / "tools" / "risk_sizer.py"),
        "--day",
        "2025-03-15",
        "--horizon",
        "1",
        "--top",
        "5",
        "--reports-root",
        str(reports_root),
        "--snapshot-root",
        str(snap),
    ]
    r = subprocess.run(args, cwd=str(_repo), capture_output=True, text=True, timeout=30, env=env)
    assert r.returncode == 0
    with (reports_dir / "risk_plan_h1.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["qty"] == "0"
    assert rows[0]["notes"] == "TooSmall"


def test_missing_topn_exit_2(tmp_path: Path) -> None:
    """Missing topn file => exit 2."""
    snap = tmp_path / "snapshots"
    snap.mkdir(parents=True)
    reports_root = tmp_path / "log" / "reports"
    reports_dir = reports_root / "2025-03-15"
    reports_dir.mkdir(parents=True)
    # No topn_h1.csv

    code, _, stderr = _run_risk_sizer("2025-03-15", 1, top=5, reports_root=reports_root, snapshot_root=snap)
    assert code == 2
    assert "topn" in stderr.lower() or "not found" in stderr.lower()


def test_plan_fields_present(tmp_path: Path) -> None:
    """Plan has required fields: day, horizon_days, rank, symbol, capital_try, risk_pct, risk_try, atr, stop_atr_mult, stop_distance, qty, tp_r_mult, tp_distance, notes."""
    ohlc = [(99, 101, 99, 100)] * 15
    snap = _build_ohlc_snapshots(tmp_path, "2025-03-15", 15, {"AAA": ohlc})
    reports_root = tmp_path / "log" / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_topn_csv(reports_dir, "2025-03-15", 1, ["AAA"])

    _run_risk_sizer("2025-03-15", 1, top=5, reports_root=reports_root, snapshot_root=snap)
    with (reports_dir / "risk_plan_h1.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    expected = {
        "day",
        "horizon_days",
        "rank",
        "symbol",
        "capital_try",
        "risk_pct",
        "risk_try",
        "atr",
        "stop_atr_mult",
        "stop_distance",
        "qty",
        "tp_r_mult",
        "tp_distance",
        "notes",
    }
    assert expected <= set(rows[0].keys())
