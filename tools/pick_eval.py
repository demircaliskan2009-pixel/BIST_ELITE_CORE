#!/usr/bin/env python3
"""FAZ586: Evaluate locked picks against realized returns. Offline, deterministic."""

from __future__ import annotations

import csv
import json
import math
import os
import sys
from pathlib import Path

HORIZONS = (1, 3, 5, 20)
COST_BPS = 10
EVAL_FIELDS = (
    "day",
    "horizon_days",
    "rank",
    "symbol",
    "entry_close",
    "exit_close",
    "log_return",
    "simple_return",
    "hit_up",
    "hit_gt_cost",
    "status",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def _exit_day(snapshot_root: Path, day: str, horizon: int) -> str | None:
    """Return the H-th trading day after day, or None if insufficient."""
    days = _list_snapshot_days(snapshot_root)
    days_after = [d for d in days if d > day]
    if len(days_after) < horizon:
        return None
    return days_after[horizon - 1]


def _load_picks(picks_dir: Path, horizon: int) -> list[dict] | None:
    """Load picks_h{H}.csv or .json. Returns rows or None if missing."""
    for ext in ("csv", "json"):
        p = picks_dir / f"picks_h{horizon}.{ext}"
        if not p.is_file():
            continue
        try:
            if ext == "csv":
                with p.open(newline="", encoding="utf-8") as f:
                    return list(csv.DictReader(f))
            data = json.loads(p.read_text(encoding="utf-8"))
            return data.get("rows") or []
        except (json.JSONDecodeError, OSError, csv.Error):
            pass
    return None


def _run_eval(
    day: str,
    horizon: int,
    picks_root: Path,
    snapshot_root: Path,
    cost_bps: float = COST_BPS,
) -> list[dict] | None:
    """Build eval rows from picks. Returns None if picks missing."""
    picks_dir = picks_root / day
    pick_rows = _load_picks(picks_dir, horizon)
    if pick_rows is None:
        return None

    cost_threshold = cost_bps / 10000.0
    entry_closes = _close_map(snapshot_root, day)
    exit_day = _exit_day(snapshot_root, day, horizon)
    exit_closes = _close_map(snapshot_root, exit_day) if exit_day else {}

    rows: list[dict] = []
    for row in pick_rows:
        symbol = (row.get("symbol") or "").strip()
        if not symbol:
            continue
        rank = row.get("rank", "")
        try:
            rank = int(rank) if rank != "" else 0
        except (TypeError, ValueError):
            rank = 0

        entry_close = entry_closes.get(symbol.upper())
        if entry_close is None or (isinstance(entry_close, float) and (math.isnan(entry_close) or entry_close <= 0)):
            rows.append(
                {
                    "day": day,
                    "horizon_days": horizon,
                    "rank": rank,
                    "symbol": symbol,
                    "entry_close": None,
                    "exit_close": None,
                    "log_return": None,
                    "simple_return": None,
                    "hit_up": None,
                    "hit_gt_cost": None,
                    "status": "NO_DATA",
                }
            )
            continue

        if exit_day is None:
            rows.append(
                {
                    "day": day,
                    "horizon_days": horizon,
                    "rank": rank,
                    "symbol": symbol,
                    "entry_close": round(entry_close, 6),
                    "exit_close": None,
                    "log_return": None,
                    "simple_return": None,
                    "hit_up": None,
                    "hit_gt_cost": None,
                    "status": "PENDING",
                }
            )
            continue

        exit_close = exit_closes.get(symbol.upper())
        if exit_close is None or (isinstance(exit_close, float) and (math.isnan(exit_close) or exit_close <= 0)):
            rows.append(
                {
                    "day": day,
                    "horizon_days": horizon,
                    "rank": rank,
                    "symbol": symbol,
                    "entry_close": round(entry_close, 6),
                    "exit_close": None,
                    "log_return": None,
                    "simple_return": None,
                    "hit_up": None,
                    "hit_gt_cost": None,
                    "status": "PENDING",
                }
            )
            continue

        simple_return = (exit_close - entry_close) / entry_close
        log_return = math.log(exit_close / entry_close) if exit_close > 0 and entry_close > 0 else None
        hit_up = exit_close > entry_close
        hit_gt_cost = simple_return > cost_threshold

        rows.append(
            {
                "day": day,
                "horizon_days": horizon,
                "rank": rank,
                "symbol": symbol,
                "entry_close": round(entry_close, 6),
                "exit_close": round(exit_close, 6),
                "log_return": round(log_return, 6) if log_return is not None else None,
                "simple_return": round(simple_return, 6),
                "hit_up": hit_up,
                "hit_gt_cost": hit_gt_cost,
                "status": "OK",
            }
        )

    return rows


def _write_outputs(picks_dir: Path, horizon: int, day: str, rows: list[dict]) -> None:
    """Write eval_h{H}.json and eval_h{H}.csv."""
    picks_dir.mkdir(parents=True, exist_ok=True)
    h = horizon

    report = {
        "schema_version": 1,
        "day": day,
        "horizon_days": horizon,
        "rows": rows,
    }

    json_path = picks_dir / f"eval_h{h}.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    csv_path = picks_dir / f"eval_h{h}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=EVAL_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r[c]) for c in EVAL_FIELDS})


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="FAZ586: Evaluate locked picks")
    p.add_argument("--day", required=True, help="YYYY-MM-DD")
    p.add_argument("--horizon", type=int, required=True, choices=HORIZONS)
    p.add_argument("--picks-root", default="data/log/picks")
    p.add_argument("--snapshot-root", default=None)
    args = p.parse_args()

    repo = _repo_root()
    picks_root = Path(args.picks_root)
    if not picks_root.is_absolute():
        picks_root = (repo / picks_root).resolve()
    snapshot_root = args.snapshot_root or os.environ.get("BIST_CORE_SNAPSHOT_DIR", "data/eod/snapshots")
    snapshot_root = Path(snapshot_root)
    if not snapshot_root.is_absolute():
        snapshot_root = (repo / snapshot_root).resolve()

    picks_dir = picks_root / args.day
    rows = _run_eval(
        day=args.day,
        horizon=args.horizon,
        picks_root=picks_root,
        snapshot_root=snapshot_root,
    )

    if rows is None:
        print(f"picks_h{args.horizon} not found", file=sys.stderr)
        return 2

    try:
        _write_outputs(picks_dir, args.horizon, args.day, rows)
        print(f"eval_h{args.horizon} -> {picks_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
