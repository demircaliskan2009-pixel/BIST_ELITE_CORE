"""FAZ586: Pick lock + outcome evaluator. Synthetic fixtures, deterministic."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path


_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def _run_pick_lock(
    day: str,
    horizon: int,
    top: int = 5,
    reports_root: Path | None = None,
    picks_root: Path | None = None,
) -> tuple[int, str, str]:
    """Run pick_lock.py. Returns (exit_code, stdout, stderr)."""
    args = [
        sys.executable,
        str(_repo / "tools" / "pick_lock.py"),
        "--day",
        day,
        "--horizon",
        str(horizon),
        "--top",
        str(top),
    ]
    if reports_root:
        args.extend(["--reports-root", str(reports_root)])
    if picks_root:
        args.extend(["--picks-root", str(picks_root)])
    r = subprocess.run(args, cwd=str(_repo), capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout or "", r.stderr or ""


def _run_pick_eval(
    day: str,
    horizon: int,
    picks_root: Path | None = None,
    snapshot_root: Path | None = None,
) -> tuple[int, str, str]:
    """Run pick_eval.py. Returns (exit_code, stdout, stderr)."""
    args = [
        sys.executable,
        str(_repo / "tools" / "pick_eval.py"),
        "--day",
        day,
        "--horizon",
        str(horizon),
    ]
    if picks_root:
        args.extend(["--picks-root", str(picks_root)])
    if snapshot_root:
        args.extend(["--snapshot-root", str(snapshot_root)])
    r = subprocess.run(args, cwd=str(_repo), capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout or "", r.stderr or ""


def _write_topn_csv(reports_dir: Path, day: str, horizon: int, symbols: list[str]) -> None:
    """Write minimal topn_h{H}.csv for pick_lock input."""
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


def _build_snapshots(tmp_path: Path, day_prices: dict[str, dict[str, float]]) -> Path:
    """Build snapshots. day_prices[day][symbol] = close. Returns snapshot_root."""
    base = tmp_path / "snapshots"
    base.mkdir(parents=True, exist_ok=True)
    for day, sym_prices in sorted(day_prices.items()):
        day_dir = base / day
        day_dir.mkdir(parents=True, exist_ok=True)
        rows = ["symbol,close"]
        for sym, close in sorted(sym_prices.items()):
            rows.append(f"{sym},{close:.4f}")
        (day_dir / "snapshot.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return base


def test_pick_lock_files_created(tmp_path: Path) -> None:
    """pick_lock creates picks_h{H}.json and picks_h{H}.csv."""
    reports_root = tmp_path / "log" / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_topn_csv(reports_dir, "2025-03-15", 1, ["AAA", "BBB"])
    picks_root = tmp_path / "log" / "picks"

    code, _, _ = _run_pick_lock("2025-03-15", 1, top=5, reports_root=reports_root, picks_root=picks_root)
    assert code == 0
    picks_dir = picks_root / "2025-03-15"
    assert (picks_dir / "picks_h1.json").is_file()
    assert (picks_dir / "picks_h1.csv").is_file()


def test_pick_lock_deterministic(tmp_path: Path) -> None:
    """Same input -> identical picks output."""
    reports_root = tmp_path / "log" / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_topn_csv(reports_dir, "2025-03-15", 1, ["AAA", "BBB"])
    picks_root = tmp_path / "log" / "picks"

    _run_pick_lock("2025-03-15", 1, top=5, reports_root=reports_root, picks_root=picks_root)
    j1 = (picks_root / "2025-03-15" / "picks_h1.json").read_text(encoding="utf-8")
    _run_pick_lock("2025-03-15", 1, top=5, reports_root=reports_root, picks_root=picks_root)
    j2 = (picks_root / "2025-03-15" / "picks_h1.json").read_text(encoding="utf-8")
    assert j1 == j2


def test_pick_lock_fields(tmp_path: Path) -> None:
    """Picks have day, horizon_days, rank, symbol, score, p_up, p_gt_cost, mu_hat, sigma_hat, locked_at."""
    reports_root = tmp_path / "log" / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_topn_csv(reports_dir, "2025-03-15", 1, ["AAA", "BBB"])
    picks_root = tmp_path / "log" / "picks"

    _run_pick_lock("2025-03-15", 1, top=5, reports_root=reports_root, picks_root=picks_root)
    with (picks_root / "2025-03-15" / "picks_h1.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) >= 2
    expected = {
        "day",
        "horizon_days",
        "rank",
        "symbol",
        "score",
        "p_up",
        "p_gt_cost",
        "mu_hat",
        "sigma_hat",
        "locked_at",
    }
    assert expected <= set(rows[0].keys())
    by_sym = {r["symbol"]: r for r in rows}
    assert "AAA" in by_sym and "BBB" in by_sym
    assert int(float(by_sym["AAA"]["rank"])) == 1
    assert int(float(by_sym["BBB"]["rank"])) == 2


def test_pick_lock_missing_topn_exit_2(tmp_path: Path) -> None:
    """Missing topn file => exit 2."""
    reports_root = tmp_path / "log" / "reports"
    (reports_root / "2025-03-15").mkdir(parents=True)
    picks_root = tmp_path / "log" / "picks"

    code, _, stderr = _run_pick_lock("2025-03-15", 1, reports_root=reports_root, picks_root=picks_root)
    assert code == 2
    assert "topn" in stderr.lower() or "not found" in stderr.lower()


def test_pick_eval_ok_return_math(tmp_path: Path) -> None:
    """eval computes entry_close, exit_close, log_return, simple_return, hit_up, hit_gt_cost correctly."""
    # Entry 2025-03-15: AAA=100, BBB=50. Exit 2025-03-16: AAA=105, BBB=50.5
    # simple_return AAA = 0.05, BBB = 0.01. hit_up both True. hit_gt_cost (10bps=0.001): both True
    snap = _build_snapshots(
        tmp_path,
        {
            "2025-03-15": {"AAA": 100.0, "BBB": 50.0},
            "2025-03-16": {"AAA": 105.0, "BBB": 50.5},
        },
    )
    reports_root = tmp_path / "log" / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_topn_csv(reports_dir, "2025-03-15", 1, ["AAA", "BBB"])
    picks_root = tmp_path / "log" / "picks"

    _run_pick_lock("2025-03-15", 1, reports_root=reports_root, picks_root=picks_root)
    code, _, _ = _run_pick_eval("2025-03-15", 1, picks_root=picks_root, snapshot_root=snap)
    assert code == 0

    with (picks_root / "2025-03-15" / "eval_h1.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    aaa = next(r for r in rows if r["symbol"] == "AAA")
    assert float(aaa["entry_close"]) == 100.0
    assert float(aaa["exit_close"]) == 105.0
    assert abs(float(aaa["simple_return"]) - 0.05) < 1e-5
    assert aaa["hit_up"] == "True"
    assert aaa["hit_gt_cost"] == "True"
    assert aaa["status"] == "OK"

    bbb = next(r for r in rows if r["symbol"] == "BBB")
    assert float(bbb["simple_return"]) == 0.01
    assert bbb["status"] == "OK"


def test_pick_eval_pending_when_exit_missing(tmp_path: Path) -> None:
    """When exit-day snapshot missing -> status PENDING, do not fail."""
    # Only entry day, no exit day
    snap = _build_snapshots(
        tmp_path,
        {
            "2025-03-15": {"AAA": 100.0, "BBB": 50.0},
        },
    )
    reports_root = tmp_path / "log" / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_topn_csv(reports_dir, "2025-03-15", 1, ["AAA", "BBB"])
    picks_root = tmp_path / "log" / "picks"

    _run_pick_lock("2025-03-15", 1, reports_root=reports_root, picks_root=picks_root)
    code, _, _ = _run_pick_eval("2025-03-15", 1, picks_root=picks_root, snapshot_root=snap)
    assert code == 0

    with (picks_root / "2025-03-15" / "eval_h1.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for r in rows:
        assert r["status"] == "PENDING"
        assert r["exit_close"] == ""
        assert r["simple_return"] == ""


def test_pick_eval_no_data_when_entry_missing(tmp_path: Path) -> None:
    """When entry-day close missing for symbol -> status NO_DATA."""
    # Entry day has no AAA/BBB - use different symbols in snapshot
    snap = _build_snapshots(
        tmp_path,
        {
            "2025-03-15": {"XXX": 100.0},  # no AAA, BBB
            "2025-03-16": {"XXX": 105.0},
        },
    )
    reports_root = tmp_path / "log" / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_topn_csv(reports_dir, "2025-03-15", 1, ["AAA", "BBB"])
    picks_root = tmp_path / "log" / "picks"

    _run_pick_lock("2025-03-15", 1, reports_root=reports_root, picks_root=picks_root)
    code, _, _ = _run_pick_eval("2025-03-15", 1, picks_root=picks_root, snapshot_root=snap)
    assert code == 0

    with (picks_root / "2025-03-15" / "eval_h1.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for r in rows:
        assert r["status"] == "NO_DATA"


def test_pick_eval_missing_picks_exit_2(tmp_path: Path) -> None:
    """Missing picks file => exit 2."""
    picks_root = tmp_path / "log" / "picks"
    (picks_root / "2025-03-15").mkdir(parents=True)
    snap = tmp_path / "snapshots"
    snap.mkdir()

    code, _, stderr = _run_pick_eval("2025-03-15", 1, picks_root=picks_root, snapshot_root=snap)
    assert code == 2
    assert "picks" in stderr.lower() or "not found" in stderr.lower()


def test_pick_eval_deterministic(tmp_path: Path) -> None:
    """Same input -> identical eval output."""
    snap = _build_snapshots(
        tmp_path,
        {
            "2025-03-15": {"AAA": 100.0},
            "2025-03-16": {"AAA": 102.0},
        },
    )
    reports_root = tmp_path / "log" / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_topn_csv(reports_dir, "2025-03-15", 1, ["AAA"])
    picks_root = tmp_path / "log" / "picks"

    _run_pick_lock("2025-03-15", 1, reports_root=reports_root, picks_root=picks_root)
    _run_pick_eval("2025-03-15", 1, picks_root=picks_root, snapshot_root=snap)
    j1 = (picks_root / "2025-03-15" / "eval_h1.json").read_text(encoding="utf-8")
    _run_pick_eval("2025-03-15", 1, picks_root=picks_root, snapshot_root=snap)
    j2 = (picks_root / "2025-03-15" / "eval_h1.json").read_text(encoding="utf-8")
    assert j1 == j2
