#!/usr/bin/env python3
"""FAZ570: Snapshot prepare SOP. Ensure folder exists, validate. Fail-closed. Exit 0=ok, 2=invalid/missing."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
from tools.live_validate import validate_snapshot_for_day


def _valid_day_format(s: str) -> bool:
    if not s or len(s) != 10:
        return False
    try:
        from datetime import datetime
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def prepare_snapshot(
    day: str,
    snapshot_root: Path,
    template_source: Path | None = None,
) -> tuple[bool, list[str], list[str]]:
    """
    Ensure snapshot folder exists, optionally copy template, validate.
    Returns (ok, missing_paths, reasons).
    """
    root = Path(snapshot_root)
    day_dir = root / day
    missing_paths: list[str] = []
    reasons: list[str] = []

    if not _valid_day_format(day):
        reasons.append("invalid_day_format")
        return False, missing_paths, reasons

    root.mkdir(parents=True, exist_ok=True)
    day_dir.mkdir(parents=True, exist_ok=True)

    if template_source and Path(template_source).is_file():
        dest = day_dir / "snapshot.csv"
        if not dest.is_file():
            shutil.copy2(template_source, dest)

    ok, reasons, checked_paths, _ = validate_snapshot_for_day(day, root)

    if not ok:
        if "snapshot_root_missing" in reasons:
            missing_paths.append(str(root))
        if "day_dir_missing" in reasons:
            missing_paths.append(str(day_dir))
        if "snapshot_csv_missing" in reasons:
            missing_paths.append(str(day_dir / "snapshot.csv"))
        if "empty_snapshot" in reasons or "no_valid_symbols" in reasons:
            missing_paths.append(str(day_dir / "snapshot.csv"))
        if reasons and not missing_paths:
            missing_paths.append(str(day_dir / "snapshot.csv"))

    return ok, missing_paths, reasons


def main() -> int:
    import argparse
    import os

    p = argparse.ArgumentParser(description="FAZ570: Snapshot prepare SOP")
    p.add_argument("--day", default=None, help="YYYY-MM-DD (default: Istanbul today)")
    p.add_argument("--snapshot-root", default=None)
    p.add_argument("--template-source", default=None, help="Copy minimal fixture if snapshot missing")
    args = p.parse_args()

    day = args.day
    if not day:
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime
            now = datetime.now(ZoneInfo("Europe/Istanbul"))
            day = now.strftime("%Y-%m-%d")
        except ImportError:
            from datetime import datetime
            day = datetime.now().strftime("%Y-%m-%d")

    snapshot_root = args.snapshot_root or os.environ.get("BIST_CORE_SNAPSHOT_DIR", "data/eod/snapshots")
    snapshot_root = Path(snapshot_root)
    if not snapshot_root.is_absolute():
        snapshot_root = (_repo / snapshot_root).resolve()

    template = None
    if args.template_source:
        template = Path(args.template_source)
        if not template.is_absolute():
            template = (_repo / template).resolve()
    elif (_repo / "templates" / "snapshot_minimal.csv").is_file():
        template = _repo / "templates" / "snapshot_minimal.csv"

    try:
        ok, missing_paths, reasons = prepare_snapshot(day, snapshot_root, template)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if ok:
        return 0

    for p in missing_paths:
        print(f"Missing: {p}", file=sys.stderr)
    for r in reasons:
        if not r.startswith("row_") and r not in ("snapshot_root_missing", "day_dir_missing", "snapshot_csv_missing", "empty_snapshot", "no_valid_symbols"):
            print(f"Reason: {r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
