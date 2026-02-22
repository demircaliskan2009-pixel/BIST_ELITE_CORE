#!/usr/bin/env python3
"""FAZ567: Snapshot validity gate. Fail-closed. Exit 0=ok, 2=invalid/missing, 1=programmer error."""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _valid_day_format(s: str) -> bool:
    """YYYY-MM-DD format."""
    if not s or len(s) != 10:
        return False
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_snapshot_for_day(
    day: str,
    snapshot_root: Path,
) -> tuple[bool, list[str], list[str], dict]:
    """
    Validate snapshot for a given day.
    Returns (ok, reasons, checked_paths, details).
    Fail-closed: missing/invalid => ok=False, reasons populated.
    """
    reasons: list[str] = []
    checked_paths: list[str] = []
    details: dict = {}

    if not _valid_day_format(day):
        reasons.append("invalid_day_format")
        return False, reasons, checked_paths, details

    root = Path(snapshot_root)
    if not root.is_dir():
        reasons.append("snapshot_root_missing")
        return False, reasons, checked_paths, details

    day_dir = root / day
    if not day_dir.is_dir():
        reasons.append("day_dir_missing")
        return False, reasons, checked_paths, details

    snapshot_path = day_dir / "snapshot.csv"
    alt_path = root / (day + ".csv")
    if snapshot_path.is_file():
        path_used = snapshot_path
    elif alt_path.is_file():
        path_used = alt_path
    else:
        reasons.append("snapshot_csv_missing")
        return False, reasons, checked_paths, details

    checked_paths.append(str(path_used))

    try:
        with path_used.open(newline="", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except (OSError, csv.Error) as e:
        reasons.append(f"read_error:{e!s}")
        return False, reasons, checked_paths, details

    if not rows:
        reasons.append("empty_snapshot")
        return False, reasons, checked_paths, details

    def _symbol(row: dict) -> str:
        return (row.get("symbol") or row.get("\ufeffsymbol") or "").strip()

    dates_seen: list[str] = []
    for i, row in enumerate(rows):
        sym = _symbol(row)
        if not sym:
            reasons.append(f"row_{i+2}_missing_symbol")
            continue
        c = row.get("close")
        if c is None or (isinstance(c, str) and c.strip() == ""):
            reasons.append(f"row_{i+2}_missing_close")
            continue
        try:
            val = float(c)
            if math.isnan(val) or val <= 0 or val >= 1e12:
                reasons.append(f"row_{i+2}_invalid_close")
        except (TypeError, ValueError):
            reasons.append(f"row_{i+2}_invalid_close_numeric")
        dates_seen.append(day)

    symbols = [_symbol(r) for r in rows if _symbol(r)]
    details["symbol_count"] = len(symbols)
    details["row_count"] = len(rows)

    if not symbols:
        reasons.append("no_valid_symbols")

    ok = len(reasons) == 0
    return ok, reasons, checked_paths, details


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="FAZ567: Snapshot validity gate")
    p.add_argument("--day", required=True, help="YYYY-MM-DD")
    p.add_argument("--snapshot-root", default=None)
    args = p.parse_args()

    snapshot_root = args.snapshot_root or os.environ.get("BIST_CORE_SNAPSHOT_DIR", "data/eod/snapshots")
    snapshot_root = Path(snapshot_root)

    try:
        ok, reasons, checked_paths, details = validate_snapshot_for_day(args.day, snapshot_root)
    except Exception as e:
        print(json.dumps({"ok": False, "reasons": [f"exception:{e!s}"], "checked_paths": []}, indent=2))
        return 1

    report = {
        "ok": ok,
        "reasons": reasons,
        "checked_paths": checked_paths,
        **details,
    }
    print(json.dumps(report, indent=2))
    if ok:
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
