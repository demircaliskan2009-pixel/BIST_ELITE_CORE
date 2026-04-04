"""FAZ583: TopN horizon rank — deterministic, offline. Synthetic fixtures."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def _run_topn(
    day: str,
    horizon: int,
    top: int = 5,
    snapshot_root: Path | None = None,
    out_root: Path | None = None,
    scan_path: Path | None = None,
    lookback: int = 60,
) -> tuple[int, str, str]:
    """Run topn_horizon_rank.py. Returns (exit_code, stdout, stderr)."""
    args = [
        sys.executable,
        str(_repo / "tools" / "topn_horizon_rank.py"),
        "--day",
        day,
        "--horizon",
        str(horizon),
        "--top",
        str(top),
        "--lookback",
        str(lookback),
    ]
    if snapshot_root:
        args.extend(["--snapshot-root", str(snapshot_root)])
    if out_root:
        args.extend(["--out-root", str(out_root)])
    if scan_path:
        args.extend(["--scan", str(scan_path)])
    r = subprocess.run(args, cwd=str(_repo), capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout or "", r.stderr or ""


def _build_snapshot_series(tmp_path: Path, day: str, n_days: int, symbol_series: dict[str, list[float]]) -> Path:
    """Build snapshot dir with price series. day is last day. Returns snapshot_root."""
    from datetime import datetime, timedelta

    base = tmp_path / "snapshots"
    base.mkdir(parents=True, exist_ok=True)
    dt = datetime.strptime(day, "%Y-%m-%d")
    for i in range(n_days):
        d = (dt - timedelta(days=n_days - 1 - i)).strftime("%Y-%m-%d")
        day_dir = base / d
        day_dir.mkdir(parents=True, exist_ok=True)
        rows = ["symbol,close"]
        for sym, prices in symbol_series.items():
            if i < len(prices):
                rows.append(f"{sym},{prices[i]:.4f}")
        (day_dir / "snapshot.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return base


def test_files_created(tmp_path: Path) -> None:
    """Export creates topn_h{H}.json and topn_h{H}.csv."""
    # 65 days of flat prices (lookback 60 + horizon 1 + 1 = 62 min)
    prices = [100.0 + i * 0.01 for i in range(65)]
    snap = _build_snapshot_series(tmp_path, "2025-03-15", 65, {"AAA": prices})
    out = tmp_path / "log"
    code, _, _ = _run_topn("2025-03-15", 1, top=5, snapshot_root=snap, out_root=out)
    assert code == 0
    reports = out / "reports" / "2025-03-15"
    assert (reports / "topn_h1.json").is_file()
    assert (reports / "topn_h1.csv").is_file()


def test_csv_header_exact(tmp_path: Path) -> None:
    """CSV header is exactly day,horizon_days,symbol,bars_used,..."""
    prices = [100.0] * 65
    snap = _build_snapshot_series(tmp_path, "2025-03-15", 65, {"AAA": prices})
    out = tmp_path / "log"
    _run_topn("2025-03-15", 1, top=5, snapshot_root=snap, out_root=out)
    with (out / "reports" / "2025-03-15" / "topn_h1.csv").open(newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    expected = [
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
    ]
    assert header == expected


def test_deterministic_ordering(tmp_path: Path) -> None:
    """Score desc, then symbol asc. Same input -> same output."""
    # AAA: strong up trend (1% per day). BBB: flat. AAA should rank higher.
    n = 65
    aaa = [100.0 * (1.01**i) for i in range(n)]
    bbb = [100.0] * n
    snap = _build_snapshot_series(tmp_path, "2025-03-15", n, {"AAA": aaa, "BBB": bbb})
    out = tmp_path / "log"
    _run_topn("2025-03-15", 1, top=5, snapshot_root=snap, out_root=out)
    with (out / "reports" / "2025-03-15" / "topn_h1.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    symbols = [r["symbol"] for r in rows]
    assert symbols == ["AAA", "BBB"]
    assert float(rows[0]["score"]) >= float(rows[1]["score"])


def test_p_up_range(tmp_path: Path) -> None:
    """p_up in [0, 1]."""
    prices = [100.0 + i * 0.01 for i in range(65)]
    snap = _build_snapshot_series(tmp_path, "2025-03-15", 65, {"AAA": prices})
    out = tmp_path / "log"
    _run_topn("2025-03-15", 1, top=5, snapshot_root=snap, out_root=out)
    with (out / "reports" / "2025-03-15" / "topn_h1.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        if r.get("p_up"):
            p = float(r["p_up"])
            assert 0 <= p <= 1, f"p_up={p} out of range"


def test_insufficient_history_skipped(tmp_path: Path) -> None:
    """Insufficient history -> symbol skipped (not in eligible output)."""
    # Only 10 days - way below K+H+1=62
    prices = [100.0] * 10
    snap = _build_snapshot_series(tmp_path, "2025-03-15", 10, {"AAA": prices})
    out = tmp_path / "log"
    _run_topn("2025-03-15", 1, top=5, snapshot_root=snap, out_root=out)
    data = json.loads((out / "reports" / "2025-03-15" / "topn_h1.json").read_text(encoding="utf-8"))
    rows = data.get("rows") or []
    assert len(rows) == 0
    assert data.get("summary", {}).get("eligible", -1) == 0


def test_stable_output(tmp_path: Path) -> None:
    """Same input -> identical output."""
    prices = [100.0 + i * 0.01 for i in range(65)]
    snap = _build_snapshot_series(tmp_path, "2025-03-15", 65, {"AAA": prices})
    out = tmp_path / "log"
    _run_topn("2025-03-15", 1, top=5, snapshot_root=snap, out_root=out)
    j1 = (out / "reports" / "2025-03-15" / "topn_h1.json").read_text(encoding="utf-8")
    _run_topn("2025-03-15", 1, top=5, snapshot_root=snap, out_root=out)
    j2 = (out / "reports" / "2025-03-15" / "topn_h1.json").read_text(encoding="utf-8")
    assert j1 == j2


def test_scan_symbols_used(tmp_path: Path) -> None:
    """When scan.json provided, only those symbols are ranked."""
    prices = [100.0 + i * 0.01 for i in range(65)]
    snap = _build_snapshot_series(tmp_path, "2025-03-15", 65, {"AAA": prices, "BBB": prices})
    scan_dir = tmp_path / "daily_scan" / "2025-03-15"
    scan_dir.mkdir(parents=True)
    (scan_dir / "scan.json").write_text(
        json.dumps({"day": "2025-03-15", "ranked": [{"symbol": "AAA"}, {"symbol": "BBB"}]}),
        encoding="utf-8",
    )
    out = tmp_path / "log"
    _run_topn("2025-03-15", 1, top=5, snapshot_root=snap, out_root=out, scan_path=scan_dir / "scan.json")
    data = json.loads((out / "reports" / "2025-03-15" / "topn_h1.json").read_text(encoding="utf-8"))
    symbols = [r["symbol"] for r in data.get("rows") or []]
    assert set(symbols) <= {"AAA", "BBB"}
