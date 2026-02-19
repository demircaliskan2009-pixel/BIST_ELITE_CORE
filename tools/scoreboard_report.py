#!/usr/bin/env python3
"""FAZ572: Live test scoreboard — BUY/SELL/HOLD + forward returns. Purely derived from artifacts + bars."""
from __future__ import annotations

import csv
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _add_days(day: str, n: int) -> str:
    """Add n calendar days to YYYY-MM-DD. Deterministic."""
    dt = datetime.strptime(day, "%Y-%m-%d")
    return (dt + timedelta(days=n)).strftime("%Y-%m-%d")


def _close_map(snapshot_root: Path, day: str) -> dict[str, float] | None:
    """Read symbol->close from snapshot. None if missing. Deterministic (sorted)."""
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
            return None
    return None


def _decision_from_artifact(ask_path: Path) -> str:
    """Extract decision_raw from ask JSON. Default HOLD."""
    if not ask_path.is_file():
        return "HOLD"
    try:
        data = json.loads(ask_path.read_text(encoding="utf-8"))
        dec = data.get("decision_raw") or data.get("Decision", {}).get("decision_raw")
        if isinstance(dec, str):
            u = dec.upper()
            if u in ("BUY", "SELL", "HOLD"):
                return u
    except (json.JSONDecodeError, OSError):
        pass
    return "HOLD"


def build_scoreboard(
    day: str,
    out_root: Path,
    snapshot_root: Path,
    horizons: list[int] | None = None,
) -> dict:
    """
    Build scoreboard from scan + ask artifacts + bars.
    Returns dict with schema_version, day, rows (sorted by symbol).
    """
    horizons = horizons or [1, 5, 20]
    out_root = Path(out_root)
    snapshot_root = Path(snapshot_root)

    scan_path = out_root / "daily_scan" / day / "scan.json"
    ask_dir = out_root / "ask" / day

    symbols: list[str] = []
    if scan_path.is_file():
        try:
            data = json.loads(scan_path.read_text(encoding="utf-8"))
            ranked = data.get("ranked") or []
            symbols = sorted(
                item["symbol"] for item in ranked
                if isinstance(item, dict) and item.get("symbol")
            )
        except (json.JSONDecodeError, OSError):
            pass

    if not symbols and ask_dir.is_dir():
        symbols = sorted(
            p.stem for p in ask_dir.glob("*.json")
            if p.stem and not p.name.startswith(".")
        )

    close_today = _close_map(snapshot_root, day)
    if close_today is None:
        close_today = {}

    rows: list[dict] = []
    for sym in symbols:
        decision = _decision_from_artifact(ask_dir / f"{sym}.json")
        p0 = close_today.get(sym)
        if p0 is None or (isinstance(p0, float) and (p0 <= 0 or math.isnan(p0))):
            p0 = None

        row: dict = {"symbol": sym, "decision_raw": decision}
        for h in horizons:
            day_h = _add_days(day, h)
            close_h = _close_map(snapshot_root, day_h)
            p_h = (close_h or {}).get(sym) if close_h else None
            if p_h is not None and isinstance(p_h, float) and not math.isnan(p_h):
                pass
            else:
                p_h = None

            if p0 is not None and p_h is not None and p0 > 0:
                ret = (p_h - p0) / p0
                row[f"ret_{h}d"] = round(ret, 6)
            else:
                row[f"ret_{h}d"] = None
        rows.append(row)

    return {
        "schema_version": 1,
        "day": day,
        "horizons": horizons,
        "rows": rows,
    }


def write_scoreboard(report: dict, reports_dir: Path) -> None:
    """Write scoreboard.json and scoreboard.csv. Deterministic ordering."""
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_path = reports_dir / "scoreboard.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    rows = report.get("rows") or []
    if not rows:
        csv_path = reports_dir / "scoreboard.csv"
        csv_path.write_text("symbol,decision_raw\n", encoding="utf-8")
        return

    horizons = report.get("horizons") or []
    cols = ["symbol", "decision_raw"] + [f"ret_{h}d" for h in horizons]
    csv_path = reports_dir / "scoreboard.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r[c]) for c in cols})


def main() -> int:
    import argparse
    import os

    p = argparse.ArgumentParser(description="FAZ572: Live test scoreboard")
    p.add_argument("--day", required=True, help="YYYY-MM-DD")
    p.add_argument("--out-root", default="data/log")
    p.add_argument("--snapshot-root", default=None)
    p.add_argument("--horizons", default="1,5,20", help="Comma-separated: e.g. 1,5,20")
    args = p.parse_args()

    out_root = Path(args.out_root)
    if not out_root.is_absolute():
        out_root = (_repo_root() / out_root).resolve()

    snapshot_root = args.snapshot_root or os.environ.get("BIST_CORE_SNAPSHOT_DIR", "data/eod/snapshots")
    snapshot_root = Path(snapshot_root)
    if not snapshot_root.is_absolute():
        snapshot_root = (_repo_root() / snapshot_root).resolve()

    horizons = [int(x.strip()) for x in args.horizons.split(",") if x.strip()]

    try:
        report = build_scoreboard(args.day, out_root, snapshot_root, horizons)
        reports_dir = out_root / "reports" / args.day
        write_scoreboard(report, reports_dir)
        print(str(reports_dir / "scoreboard.json"))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
