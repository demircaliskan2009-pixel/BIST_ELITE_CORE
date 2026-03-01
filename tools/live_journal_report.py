#!/usr/bin/env python3
"""FAZ567: Trade journal report — join journal with artifacts, produce realized PnL + compliance flags."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_journal(path: Path) -> list[dict[str, Any]]:
    """Load journal CSV. Deterministic order. Fail-closed: missing fields => unknown."""
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            rows.append(dict(row))
    return rows


def _load_scan_symbols(out_root: Path, day: str) -> set[str]:
    """Load TOP-N symbols from scan.json for day."""
    scan_path = out_root / "daily_scan" / day / "scan.json"
    if not scan_path.is_file():
        return set()
    try:
        data = json.loads(scan_path.read_text(encoding="utf-8"))
        ranked = data.get("ranked") or []
        return {r.get("symbol", "").strip() for r in ranked if isinstance(r, dict) and r.get("symbol")}
    except (json.JSONDecodeError, OSError):
        return set()


def _compute_realized_pnl(rows: list[dict], date_from: str, date_to: str) -> tuple[float, list[dict]]:
    """
    Compute realized PnL from journal. Match BUY+SELL for same symbol.
    Returns (total_pnl_tl, trades_with_pnl).
    """
    by_symbol: dict[str, list[dict]] = {}
    for r in rows:
        day = (r.get("day") or "").strip()
        if not day or day < date_from or day > date_to:
            continue
        sym = (r.get("symbol") or "").strip().upper()
        if not sym:
            continue
        side = (r.get("side") or "").strip().upper()
        try:
            qty = float(r.get("qty") or 0)
            price = float(r.get("price") or 0)
            fees = float(r.get("fees_tl") or 0)
        except (TypeError, ValueError):
            continue
        if sym not in by_symbol:
            by_symbol[sym] = []
        by_symbol[sym].append({"day": day, "side": side, "qty": qty, "price": price, "fees_tl": fees})

    total = 0.0
    trades_with_pnl: list[dict] = []
    for sym, entries in by_symbol.items():
        buys = [e for e in entries if e["side"] == "BUY"]
        sells = [e for e in entries if e["side"] == "SELL"]
        if not buys or not sells:
            continue
        buy_cost = sum(e["qty"] * e["price"] + e["fees_tl"] for e in buys)
        sell_proceeds = sum(e["qty"] * e["price"] - e["fees_tl"] for e in sells)
        pnl = sell_proceeds - buy_cost
        total += pnl
        trades_with_pnl.append({"symbol": sym, "realized_pnl_tl": round(pnl, 2)})

    return round(total, 2), trades_with_pnl


def _check_compliance(rows: list[dict], out_root: Path, date_from: str, date_to: str) -> list[dict]:
    """Flag: traded symbol not in topN scan for that day."""
    flags: list[dict] = []
    for r in rows:
        day = (r.get("day") or "").strip()
        if not day or day < date_from or day > date_to:
            continue
        sym = (r.get("symbol") or "").strip().upper()
        if not sym:
            continue
        topn = _load_scan_symbols(out_root, day)
        if topn and sym not in topn:
            flags.append({"day": day, "symbol": sym, "flag": "traded_not_in_topn"})
    return flags


def build_report(
    journal_path: Path,
    out_root: Path,
    date_from: str,
    date_to: str,
) -> dict[str, Any]:
    """Build realized report. Deterministic. Fail-closed: missing => unknown."""
    rows = _load_journal(journal_path)
    total_pnl, trades = _compute_realized_pnl(rows, date_from, date_to)
    flags = _check_compliance(rows, out_root, date_from, date_to)
    return {
        "schema_version": 1,
        "date_from": date_from,
        "date_to": date_to,
        "realized_pnl_tl": total_pnl,
        "trades": trades,
        "compliance_flags": flags,
    }


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="FAZ567: Trade journal report")
    p.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")
    p.add_argument("--journal", required=True, help="Journal CSV path")
    p.add_argument("--out-root", default="data/log")
    args = p.parse_args()

    out_root = Path(args.out_root)
    range_str = f"{args.date_from}_to_{args.date_to}"
    report_dir = out_root / "reports" / range_str
    report_dir.mkdir(parents=True, exist_ok=True)

    report = build_report(
        Path(args.journal),
        out_root,
        args.date_from,
        args.date_to,
    )

    json_path = report_dir / "realized_report.json"
    csv_path = report_dir / "realized_report.csv"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerow(["realized_pnl_tl", report["realized_pnl_tl"]])
        w.writerow(["date_from", report["date_from"]])
        w.writerow(["date_to", report["date_to"]])

    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
