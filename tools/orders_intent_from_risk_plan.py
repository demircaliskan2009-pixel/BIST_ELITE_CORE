#!/usr/bin/env python3
"""FAZ587: Convert risk_plan to orders_intent v2 DRAFT. Offline, deterministic."""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

HORIZONS = (1, 3, 5, 20)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def _load_risk_plan(reports_dir: Path, horizon: int) -> list[dict] | None:
    """Load risk_plan_h{H}.csv. Returns rows or None if missing."""
    for ext in ("csv", "json"):
        p = reports_dir / f"risk_plan_h{horizon}.{ext}"
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


def _run_convert(
    day: str,
    horizon: int,
    top_n: int,
    reports_root: Path,
    side: str,
    order_type: str,
    limit_price_mode: str,
    snapshot_root: Path | None,
) -> dict | None:
    """
    Build orders_intent draft from risk_plan. Returns dict or None if risk_plan missing.
    qty==0 -> skip. Deterministic order: rank then symbol.
    """
    reports_dir = reports_root / day
    rows = _load_risk_plan(reports_dir, horizon)
    if rows is None:
        return None

    closes = {}
    if limit_price_mode == "LAST_CLOSE" and snapshot_root and snapshot_root.is_dir():
        closes = _close_map(snapshot_root, day)

    actions: list[dict] = []
    skipped: list[dict] = []
    for row in rows[:top_n]:
        symbol = (row.get("symbol") or "").strip()
        if not symbol:
            continue
        try:
            qty = int(float(row.get("qty") or 0))
        except (TypeError, ValueError):
            qty = 0
        rank = row.get("rank")
        try:
            rank = int(float(rank)) if rank not in (None, "") else 999
        except (TypeError, ValueError):
            rank = 999
        notes = (row.get("notes") or "").strip()

        if qty == 0:
            skipped.append({
                "symbol": symbol,
                "rank": rank,
                "reason": notes or "qty=0",
            })
            continue

        limit_price = ""
        if order_type == "LIMIT" and limit_price_mode == "LAST_CLOSE":
            c = closes.get(symbol.upper())
            if c is not None and not (isinstance(c, float) and (c <= 0 or str(c) == "nan")):
                limit_price = str(round(float(c), 2))

        action: dict = {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_type": order_type,
            "notes": f"risk_plan_h{horizon} rank={rank}" + (f" {notes}" if notes else ""),
        }
        if limit_price:
            action["limit_price"] = limit_price
        actions.append(action)

    # Deterministic: rank then symbol (rows already in rank order from risk_plan)
    rank_map = {}
    for i, r in enumerate(rows):
        sym = (r.get("symbol") or "").strip()
        if sym:
            rank_map[sym] = int(float(r.get("rank") or i + 1))
    actions.sort(key=lambda a: (rank_map.get(a["symbol"], 999), a["symbol"]))

    return {
        "schema_version": 2,
        "day": day,
        "draft": True,
        "draft_reason": "generated_from_risk_plan",
        "horizon_days": horizon,
        "actions": actions,
        "skipped": skipped,
    }


def _write_output(reports_dir: Path, horizon: int, day: str, data: dict) -> None:
    """Write orders_intent_draft_h{H}.json."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"orders_intent_draft_h{horizon}.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="FAZ587: Convert risk_plan to orders_intent draft")
    p.add_argument("--day", required=True, help="YYYY-MM-DD")
    p.add_argument("--horizon", type=int, required=True, choices=HORIZONS)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--reports-root", default="data/log/reports")
    p.add_argument("--side", default="BUY", choices=("BUY", "SELL"))
    p.add_argument("--order-type", default="MARKET", choices=("MARKET", "LIMIT"))
    p.add_argument("--limit-price-mode", default="NONE", choices=("NONE", "LAST_CLOSE"))
    p.add_argument("--snapshot-root", default=None)
    args = p.parse_args()

    repo = _repo_root()
    reports_root = Path(args.reports_root)
    if not reports_root.is_absolute():
        reports_root = (repo / reports_root).resolve()

    snapshot_root = None
    if args.snapshot_root:
        snapshot_root = Path(args.snapshot_root)
        if not snapshot_root.is_absolute():
            snapshot_root = (repo / snapshot_root).resolve()
    elif args.limit_price_mode == "LAST_CLOSE":
        snapshot_root = Path(os.environ.get("BIST_CORE_SNAPSHOT_DIR", "data/eod/snapshots"))
        if not snapshot_root.is_absolute():
            snapshot_root = (repo / snapshot_root).resolve()

    data = _run_convert(
        day=args.day,
        horizon=args.horizon,
        top_n=args.top,
        reports_root=reports_root,
        side=args.side,
        order_type=args.order_type,
        limit_price_mode=args.limit_price_mode,
        snapshot_root=snapshot_root,
    )

    if data is None:
        print(f"risk_plan_h{args.horizon} not found", file=sys.stderr)
        return 2

    try:
        _write_output(reports_root / args.day, args.horizon, args.day, data)
        print(f"orders_intent_draft_h{args.horizon} -> {reports_root / args.day}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
