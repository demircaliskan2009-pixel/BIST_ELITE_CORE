"""FAZ566: Live daily runner — scan, ask, evaluate, report. Offline. Deterministic."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Import from tools (repo root in path for tests)
import sys
_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
from tools.live_daily_runner import run_live_daily, _ensure_dirs, _run_scan


def _build_snapshot_series(base: Path, day: str, n_days: int, symbol_prices: dict[str, list[float]]) -> None:
    """Build snapshot dir with price series. day is last day."""
    dt = datetime.strptime(day, "%Y-%m-%d")
    for i in range(n_days):
        d = (dt - timedelta(days=n_days - 1 - i)).strftime("%Y-%m-%d")
        day_dir = base / d
        day_dir.mkdir(parents=True, exist_ok=True)
        rows = ["symbol,close"]
        for sym, prices in symbol_prices.items():
            if i < len(prices):
                rows.append(f"{sym},{prices[i]:.4f}")
        (day_dir / "snapshot.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _append_future_days(base: Path, from_day: str, n_future: int, symbol_prices: dict[str, float]) -> None:
    """Append n_future calendar days after from_day. symbol_prices[sym]=close for each."""
    dt = datetime.strptime(from_day, "%Y-%m-%d")
    for i in range(1, n_future + 1):
        d = (dt + timedelta(days=i)).strftime("%Y-%m-%d")
        day_dir = base / d
        day_dir.mkdir(parents=True, exist_ok=True)
        rows = ["symbol,close"]
        for sym, close in sorted(symbol_prices.items()):
            rows.append(f"{sym},{close:.4f}")
        (day_dir / "snapshot.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_live_daily_ensure_dirs(tmp_path: Path) -> None:
    """_ensure_dirs creates expected directories."""
    paths = _ensure_dirs(tmp_path, "2025-01-15")
    assert (tmp_path / "daily_scan" / "2025-01-15").is_dir()
    assert (tmp_path / "ask" / "2025-01-15").is_dir()
    assert (tmp_path / "outcomes" / "2025-01-15").is_dir()
    assert (tmp_path / "reports" / "2025-01-15").is_dir()
    assert paths["daily_scan"].name == "2025-01-15"
    assert paths["reports"].name == "2025-01-15"


def test_live_daily_full_workflow(tmp_path: Path) -> None:
    """Run full workflow with minimal fixture snapshot. Assert outputs exist."""
    snap = tmp_path / "snapshots"
    snap.mkdir(parents=True)
    # 85 days: topn needs lookback(60)+horizon(20)+1=81 for H=20
    n = 85
    prices = [100.0 + i * 0.01 for i in range(n)]
    _build_snapshot_series(snap, "2099-01-01", n, {"AAA": prices, "BBB": prices, "CCC": prices})
    # FAZ592: Add future days so eval has exit snapshot for H=1 (status OK); H=20 may be PENDING
    last_close = 100.0 + (n - 1) * 0.01
    _append_future_days(snap, "2099-01-01", 25, {"AAA": last_close, "BBB": last_close, "CCC": last_close})
    out_root = tmp_path / "log"

    code, symbols, paths = run_live_daily(
        day="2099-01-01",
        top_n=2,
        out_root=out_root,
        snapshot_root=snap,
    )

    assert code == 0
    assert len(symbols) >= 1
    assert "AAA" in symbols or "BBB" in symbols or "CCC" in symbols

    scan_json = paths["daily_scan"].parent / "2099-01-01" / "scan.json"
    assert scan_json.is_file(), f"Expected scan artifact at {scan_json}"
    scan_data = json.loads(scan_json.read_text(encoding="utf-8"))
    assert "ranked" in scan_data
    assert scan_data["day"] == "2099-01-01"

    for sym in symbols:
        ask_artifact = paths["ask"] / f"{sym}.json"
        assert ask_artifact.is_file(), f"Expected ask artifact for {sym}"

    reports_dir = paths["reports"]
    json_report = reports_dir / "performance.json"
    csv_report = reports_dir / "performance.csv"
    assert json_report.is_file(), f"Expected performance.json at {json_report}"
    assert csv_report.is_file(), f"Expected performance.csv at {csv_report}"

    # FAZ572: Scoreboard written (BUY/SELL/HOLD + horizon returns)
    scoreboard_json = reports_dir / "scoreboard.json"
    scoreboard_csv = reports_dir / "scoreboard.csv"
    assert scoreboard_json.is_file(), f"Expected scoreboard.json at {scoreboard_json}"
    assert scoreboard_csv.is_file(), f"Expected scoreboard.csv at {scoreboard_csv}"

    # FAZ590: Horizon artifacts (topn, bundle, risk_plan) under reports/<DAY>/
    assert (reports_dir / "topn_h3.csv").is_file(), "Expected topn_h3.csv"
    assert (reports_dir / "risk_plan_h3.csv").is_file(), "Expected risk_plan_h3.csv"
    assert (reports_dir / "topn_bundle_h3.html").is_file(), "Expected topn_bundle_h3.html"

    # FAZ592: Picks and eval under picks/<DAY>/
    picks_dir = out_root / "picks" / "2099-01-01"
    assert (picks_dir / "picks_h3.json").is_file(), "Expected picks_h3.json"
    assert (picks_dir / "picks_h3.csv").is_file(), "Expected picks_h3.csv"
    assert (picks_dir / "eval_h3.json").is_file(), "Expected eval_h3.json"
    assert (picks_dir / "eval_h3.csv").is_file(), "Expected eval_h3.csv"
    # With future days: H=1 has exit snapshot -> status OK; H=20 may be PENDING or OK
    eval_h1 = json.loads((picks_dir / "eval_h1.json").read_text(encoding="utf-8"))
    rows1 = eval_h1.get("rows") or []
    assert rows1, "eval_h1 should have rows"
    statuses1 = {r.get("status") for r in rows1 if r.get("status")}
    assert statuses1, f"eval_h1 rows should have status, got {rows1}"
    assert "OK" in statuses1 or "PENDING" in statuses1, f"eval_h1 expected OK or PENDING, got {statuses1}"
    eval_h20 = json.loads((picks_dir / "eval_h20.json").read_text(encoding="utf-8"))
    rows20 = eval_h20.get("rows") or []
    assert rows20, "eval_h20 should have rows"


def test_live_daily_fail_closed_empty_snapshot(tmp_path: Path) -> None:
    """Missing snapshot: scan returns empty, we continue with empty symbols (exit 0, HOLD-like)."""
    snap = tmp_path / "empty_snap"
    snap.mkdir()
    out_root = tmp_path / "log"

    code, symbols, paths = run_live_daily(
        day="2099-01-02",
        top_n=5,
        out_root=out_root,
        snapshot_root=snap,
    )

    assert code == 0
    assert symbols == []
    assert paths["daily_scan"].is_dir()
    assert paths["reports"].is_dir()
