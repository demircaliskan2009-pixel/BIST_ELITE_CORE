#!/usr/bin/env python3
"""FAZ586: Lock TopN picks into immutable log. Offline, deterministic."""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

HORIZONS = (1, 3, 5, 20)
PICK_FIELDS = (
    "day", "horizon_days", "rank", "symbol", "score", "p_up", "p_gt_cost",
    "mu_hat", "sigma_hat", "locked_at",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_topn(reports_dir: Path, horizon: int) -> list[dict] | None:
    """Load topn_h{H}.csv or .json. Returns rows or None if missing."""
    for ext in ("csv", "json"):
        p = reports_dir / f"topn_h{horizon}.{ext}"
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


def _run_lock(
    day: str,
    horizon: int,
    top_n: int,
    reports_root: Path,
    picks_root: Path,
) -> list[dict] | None:
    """Build pick rows from topn. Returns None if topn missing."""
    reports_dir = reports_root / day
    topn_rows = _load_topn(reports_dir, horizon)
    if topn_rows is None:
        return None

    locked_at = f"{day}T00:00:00Z"
    rows: list[dict] = []
    for rank, row in enumerate(topn_rows[:top_n], 1):
        symbol = (row.get("symbol") or "").strip()
        if not symbol:
            continue
        rows.append({
            "day": day,
            "horizon_days": horizon,
            "rank": rank,
            "symbol": symbol,
            "score": _safe_float(row.get("score")),
            "p_up": _safe_float(row.get("p_up")),
            "p_gt_cost": _safe_float(row.get("p_gt_cost")),
            "mu_hat": _safe_float(row.get("mu_hat")),
            "sigma_hat": _safe_float(row.get("sigma_hat")),
            "locked_at": locked_at,
        })
    return rows


def _safe_float(v: str | float | None) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _write_outputs(picks_dir: Path, horizon: int, day: str, rows: list[dict]) -> None:
    """Write picks_h{H}.json and picks_h{H}.csv."""
    picks_dir.mkdir(parents=True, exist_ok=True)
    h = horizon

    report = {
        "schema_version": 1,
        "day": day,
        "horizon_days": horizon,
        "rows": rows,
    }

    json_path = picks_dir / f"picks_h{h}.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    csv_path = picks_dir / f"picks_h{h}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PICK_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r[c]) for c in PICK_FIELDS})


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="FAZ586: Lock TopN picks")
    p.add_argument("--day", required=True, help="YYYY-MM-DD")
    p.add_argument("--horizon", type=int, required=True, choices=HORIZONS)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--reports-root", default="data/log/reports")
    p.add_argument("--picks-root", default="data/log/picks")
    args = p.parse_args()

    repo = _repo_root()
    reports_root = Path(args.reports_root)
    if not reports_root.is_absolute():
        reports_root = (repo / reports_root).resolve()
    picks_root = Path(args.picks_root)
    if not picks_root.is_absolute():
        picks_root = (repo / picks_root).resolve()

    picks_dir = picks_root / args.day
    rows = _run_lock(
        day=args.day,
        horizon=args.horizon,
        top_n=args.top,
        reports_root=reports_root,
        picks_root=picks_root,
    )

    if rows is None:
        print(f"topn_h{args.horizon} not found", file=sys.stderr)
        return 2

    try:
        _write_outputs(picks_dir, args.horizon, args.day, rows)
        print(f"picks_h{args.horizon} -> {picks_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
