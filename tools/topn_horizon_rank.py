#!/usr/bin/env python3
"""FAZ583: Horizon probabilistic TopN ranker — offline, deterministic. No network, no secrets."""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from pathlib import Path

LOOKBACK_K = 60
COST_BPS_DEFAULT = 10
HORIZONS = (1, 3, 5, 20)
OUTPUT_FIELDS = (
    "day", "horizon_days", "symbol", "bars_used", "lookback_used",
    "mu_hat", "sigma_hat", "p_up", "p_gt_cost", "score", "notes",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _phi(x: float) -> float:
    """Standard normal CDF. Uses math.erf. Deterministic."""
    if math.isnan(x) or math.isinf(x):
        return 0.5
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _list_snapshot_days(snapshot_root: Path) -> list[str]:
    """List available days (YYYY-MM-DD) with snapshot.csv. Sorted ascending."""
    if not snapshot_root.is_dir():
        return []
    days = []
    for sub in sorted(snapshot_root.iterdir()):
        if sub.is_dir() and (sub / "snapshot.csv").is_file():
            name = sub.name
            if len(name) == 10 and name[4] == "-" and name[7] == "-":
                try:
                    int(name[:4])
                    int(name[5:7])
                    int(name[8:10])
                    days.append(name)
                except ValueError:
                    pass
    return sorted(days)


def _close_map(snapshot_root: Path, day: str) -> dict[str, float]:
    """Read symbol->close from snapshot. Deterministic (sorted)."""
    for name in (f"{day}/snapshot.csv", f"{day}.csv"):
        p = snapshot_root / name
        if not p.is_file():
            continue
        out: dict[str, float] = {}
        try:
            with p.open(newline="", encoding="utf-8", errors="replace") as f:
                rdr = csv.DictReader(f)
                for row in rdr:
                    sym = (row.get("symbol") or "").strip().upper()
                    if not sym:
                        continue
                    c = row.get("close")
                    try:
                        out[sym] = float(c) if c not in (None, "") else float("nan")
                    except (TypeError, ValueError):
                        out[sym] = float("nan")
            return dict(sorted(out.items()))
        except (OSError, csv.Error):
            pass
    return {}


def _load_symbols_from_scan(scan_path: Path | None) -> list[str]:
    """Load symbol list from scan.json. Returns [] if missing/invalid."""
    if not scan_path or not scan_path.is_file():
        return []
    try:
        data = json.loads(scan_path.read_text(encoding="utf-8"))
        ranked = data.get("ranked") or []
        return sorted(
            item["symbol"] for item in ranked
            if isinstance(item, dict) and item.get("symbol")
        )
    except (json.JSONDecodeError, OSError):
        return []


def _get_close_series(
    snapshot_root: Path,
    day: str,
    symbol: str,
    min_days: int,
) -> list[float]:
    """Get close prices for symbol over last min_days ending at day. Oldest first. Gaps -> []."""
    days = _list_snapshot_days(snapshot_root)
    candidates = [d for d in days if d <= day]
    if not candidates or day not in candidates:
        return []
    window = candidates[-min_days:]
    closes = []
    for d in window:
        cm = _close_map(snapshot_root, d)
        c = cm.get(symbol)
        if c is not None and not (isinstance(c, float) and (math.isnan(c) or c <= 0)):
            closes.append(float(c))
        else:
            return []
    return closes


def _log_returns(closes: list[float]) -> list[float]:
    """Compute log returns. len(closes)>=2 required."""
    if len(closes) < 2:
        return []
    return [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]


def _rank_symbol(
    day: str,
    horizon: int,
    symbol: str,
    snapshot_root: Path,
    lookback: int,
    cost_bps: float,
) -> dict | None:
    """
    Compute ranking row for symbol. Returns None if skipped (notes set).
    Returns dict with OUTPUT_FIELDS.
    """
    min_bars = lookback + horizon + 1
    closes = _get_close_series(snapshot_root, day, symbol, min_bars)
    bars_count = len(closes)

    if bars_count == 0:
        return {
            "day": day,
            "horizon_days": horizon,
            "symbol": symbol,
            "bars_used": 0,
            "lookback_used": lookback,
            "mu_hat": None,
            "sigma_hat": None,
            "p_up": None,
            "p_gt_cost": None,
            "score": None,
            "notes": "NoBars",
        }

    if bars_count < min_bars:
        return {
            "day": day,
            "horizon_days": horizon,
            "symbol": symbol,
            "bars_used": bars_count,
            "lookback_used": lookback,
            "mu_hat": None,
            "sigma_hat": None,
            "p_up": None,
            "p_gt_cost": None,
            "score": None,
            "notes": "InsufficientHistory",
        }

    returns = _log_returns(closes[-lookback - 1 :])
    if len(returns) < lookback:
        return {
            "day": day,
            "horizon_days": horizon,
            "symbol": symbol,
            "bars_used": bars_count,
            "lookback_used": lookback,
            "mu_hat": None,
            "sigma_hat": None,
            "p_up": None,
            "p_gt_cost": None,
            "score": None,
            "notes": "InsufficientHistory",
        }

    mu_daily = sum(returns) / len(returns)
    var_daily = sum((r - mu_daily) ** 2 for r in returns) / len(returns) if len(returns) > 1 else 0.0
    sigma_daily = math.sqrt(var_daily) if var_daily > 0 else 0.0

    mu_hat = mu_daily * horizon
    sigma_hat = sigma_daily * math.sqrt(horizon) if sigma_daily > 0 else 0.0

    if sigma_hat == 0:
        p_up = 0.5
        p_gt_cost = 0.5
    else:
        p_up = 1.0 - _phi((0.0 - mu_hat) / sigma_hat)
        cost_log = math.log(1.0 + cost_bps / 10000.0)
        p_gt_cost = 1.0 - _phi((cost_log - mu_hat) / sigma_hat)

    score = (mu_hat - math.log(1.0 + cost_bps / 10000.0)) * p_gt_cost if p_gt_cost is not None else 0.0

    return {
        "day": day,
        "horizon_days": horizon,
        "symbol": symbol,
        "bars_used": bars_count,
        "lookback_used": lookback,
        "mu_hat": round(mu_hat, 8),
        "sigma_hat": round(sigma_hat, 8),
        "p_up": round(p_up, 6),
        "p_gt_cost": round(p_gt_cost, 6),
        "score": round(score, 8),
        "notes": "",
    }


def _run_rank(
    day: str,
    horizon: int,
    top_n: int,
    snapshot_root: Path,
    scan_path: Path | None,
    reports_dir: Path,
    lookback: int,
    cost_bps: float,
) -> dict:
    """Build ranking report. Returns dict with schema_version, day, horizon_days, rows, summary."""
    symbols = _load_symbols_from_scan(scan_path)
    if not symbols:
        all_days = _list_snapshot_days(snapshot_root)
        if all_days and day in [d for d in all_days if d <= day]:
            cm = _close_map(snapshot_root, day)
            symbols = sorted(cm.keys())

    rows_all: list[dict] = []
    for sym in sorted(symbols):
        row = _rank_symbol(day, horizon, sym, snapshot_root, lookback, cost_bps)
        if row is None:
            continue
        if row.get("notes"):
            continue
        rows_all.append(row)

    rows_all.sort(key=lambda r: (-(r["score"] or -1e9), r["symbol"]))
    rows = rows_all[:top_n]

    return {
        "schema_version": 1,
        "day": day,
        "horizon_days": horizon,
        "lookback": lookback,
        "cost_bps": cost_bps,
        "rows": rows,
        "summary": {
            "eligible": len(rows_all),
            "returned": len(rows),
            "top_n": top_n,
        },
    }


def _write_outputs(reports_dir: Path, horizon: int, report: dict) -> None:
    """Write topn_h{H}.json and topn_h{H}.csv."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    h = horizon
    json_path = reports_dir / f"topn_h{h}.json"
    csv_path = reports_dir / f"topn_h{h}.csv"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    rows = report.get("rows") or []
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r[k]) for k in OUTPUT_FIELDS})


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="FAZ583: Horizon probabilistic TopN ranker")
    p.add_argument("--day", required=True, help="YYYY-MM-DD")
    p.add_argument("--horizon", type=int, required=True, choices=HORIZONS, help="1,3,5,20")
    p.add_argument("--top", type=int, default=5, help="Top N (default 5)")
    p.add_argument("--scan", default=None, help="Path to scan.json (optional)")
    p.add_argument("--out-root", default="data/log", help="Output root")
    p.add_argument("--snapshot-root", default=None)
    p.add_argument("--lookback", type=int, default=LOOKBACK_K)
    p.add_argument("--cost-bps", type=float, default=COST_BPS_DEFAULT)
    args = p.parse_args()

    repo = _repo_root()
    out_root = Path(args.out_root)
    if not out_root.is_absolute():
        out_root = (repo / out_root).resolve()

    snapshot_root = args.snapshot_root or os.environ.get("BIST_CORE_SNAPSHOT_DIR", "data/eod/snapshots")
    snapshot_root = Path(snapshot_root)
    if not snapshot_root.is_absolute():
        snapshot_root = (repo / snapshot_root).resolve()

    scan_path = None
    if args.scan:
        scan_path = Path(args.scan)
        if not scan_path.is_absolute():
            scan_path = (repo / scan_path).resolve()
    else:
        default_scan = out_root / "daily_scan" / args.day / "scan.json"
        if default_scan.is_file():
            scan_path = default_scan

    reports_dir = out_root / "reports" / args.day

    try:
        report = _run_rank(
            day=args.day,
            horizon=args.horizon,
            top_n=args.top,
            snapshot_root=snapshot_root,
            scan_path=scan_path,
            reports_dir=reports_dir,
            lookback=args.lookback,
            cost_bps=args.cost_bps,
        )
        _write_outputs(reports_dir, args.horizon, report)
        print(f"topn_h{args.horizon} -> {reports_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
