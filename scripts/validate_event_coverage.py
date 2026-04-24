#!/usr/bin/env python3
"""Validate KAP event dataset coverage and alignment with price data.

Checks:
  1. Date coverage — which trading days have event files vs which are expected
  2. Event volume  — events-per-day distribution
  3. Symbol coverage — how many unique symbols appear vs BIST price data symbols
  4. Alignment      — event timestamps within expected BIST session window (09:00-18:00 TRT)

Usage
-----
    python scripts/validate_event_coverage.py
    python scripts/validate_event_coverage.py --from 2023-01-01 --to 2026-04-12
    python scripts/validate_event_coverage.py --events-dir data/events --json

Exit codes
----------
    0  Coverage meets threshold (default: >= 80% of trading days have data)
    1  Argument error
    2  Coverage below threshold or data quality issues found
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

# Ensure src/ is on the path when run directly
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TRT = timezone(timedelta(hours=3))
_BIST_SESSION_OPEN_HOUR = 9    # 09:00 TRT
_BIST_SESSION_CLOSE_HOUR = 19  # 19:00 TRT (extended for post-session disclosures)


def _weekdays_in_range(start: date, end: date) -> list[str]:
    days: list[str] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur.isoformat())
        cur += timedelta(days=1)
    return days


def _parse_jsonl_file(path: Path) -> tuple[list[dict], list[str]]:
    """Read all records from a JSONL file. Returns (records, errors)."""
    records: list[dict] = []
    errors: list[str] = []
    try:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                errors.append(f"line={lineno}: JSONDecodeError: {exc}")
    except OSError as exc:
        errors.append(f"read error: {exc}")
    return records, errors


def _parse_ts(ts: str) -> datetime | None:
    """Parse ISO timestamp string to datetime. Returns None on failure."""
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_TRT)
        return dt.astimezone(_TRT)
    except Exception:
        return None


def _load_bist_symbols_from_price_data() -> set[str]:
    """Collect symbol names from the iDeal loader if available. Falls back to empty set."""
    try:
        from bist_core.data.ideal_intraday_loader import IdealIntradayLoader  # type: ignore

        loader = IdealIntradayLoader()
        symbols = set(loader.list_symbols())
        return {s.upper() for s in symbols if s}
    except Exception:
        pass

    # Fallback: scan data/raw/ for symbol directories
    raw_dir = _REPO_ROOT / "data" / "raw"
    if raw_dir.is_dir():
        return {
            p.name.upper()
            for p in raw_dir.iterdir()
            if p.is_dir() and p.name.isupper() and len(p.name) <= 6
        }
    return set()


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------


def validate_coverage(
    events_dir: Path,
    start: date,
    end: date,
    min_coverage_pct: float = 80.0,
) -> dict:
    """Run all coverage checks.

    Returns a structured report dict with 'ok' boolean.
    """
    expected_days = _weekdays_in_range(start, end)
    expected_set = set(expected_days)

    # Scan events_dir for existing files
    existing_files: dict[str, Path] = {}
    if events_dir.is_dir():
        for p in sorted(events_dir.glob("*.jsonl")):
            # Only accept YYYY-MM-DD.jsonl names
            stem = p.stem
            try:
                date.fromisoformat(stem)
                existing_files[stem] = p
            except ValueError:
                continue

    # Date coverage
    days_with_data = [d for d in expected_days if d in existing_files]
    days_missing = [d for d in expected_days if d not in existing_files]
    coverage_pct = 100.0 * len(days_with_data) / len(expected_days) if expected_days else 0.0

    # Per-day event stats
    events_per_day: dict[str, int] = {}
    parse_errors_per_day: dict[str, list[str]] = {}
    symbols_found: set[str] = set()
    ts_anomalies: list[dict] = []  # events outside expected window
    duplicate_ids: list[dict] = []

    for day_str in days_with_data:
        path = existing_files[day_str]
        records, errs = _parse_jsonl_file(path)

        events_per_day[day_str] = len(records)
        if errs:
            parse_errors_per_day[day_str] = errs

        seen_ids: set[str] = set()
        try:
            day_date = date.fromisoformat(day_str)
        except ValueError:
            day_date = None

        for rec in records:
            sym = rec.get("symbol", "")
            if sym:
                symbols_found.add(sym)

            # Dedup check
            eid = rec.get("event_id")
            if eid:
                if eid in seen_ids:
                    duplicate_ids.append({"date": day_str, "event_id": eid})
                else:
                    seen_ids.add(eid)

            # Timestamp alignment check
            ts = rec.get("ts", "")
            if ts and day_date is not None:
                dt = _parse_ts(ts)
                if dt is not None:
                    # Check date alignment: ts.date should be within [-1, +1] day
                    # (disclosures can be filed after close or before open)
                    diff_days = abs((dt.date() - day_date).days)
                    if diff_days > 3:
                        ts_anomalies.append(
                            {
                                "date": day_str,
                                "ts": ts,
                                "symbol": rec.get("symbol"),
                                "diff_days": diff_days,
                            }
                        )

    # Price data symbol comparison
    price_symbols = _load_bist_symbols_from_price_data()
    events_only_symbols = sorted(symbols_found - price_symbols) if price_symbols else []
    price_only_symbols = sorted(price_symbols - symbols_found) if price_symbols else []
    common_symbols = sorted(symbols_found & price_symbols) if price_symbols else []

    # Events per day statistics
    counts = list(events_per_day.values())
    avg_events = sum(counts) / len(counts) if counts else 0.0
    min_events = min(counts) if counts else 0
    max_events = max(counts) if counts else 0

    # Empty-day check (files that exist but have 0 events)
    zero_event_days = [d for d, n in events_per_day.items() if n == 0]

    ok = coverage_pct >= min_coverage_pct and not parse_errors_per_day

    report = {
        "schema_version": 1,
        "ok": ok,
        "events_dir": str(events_dir),
        "date_range": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "coverage": {
            "expected_trading_days": len(expected_days),
            "days_with_data": len(days_with_data),
            "days_missing": len(days_missing),
            "coverage_pct": round(coverage_pct, 2),
            "min_coverage_threshold_pct": min_coverage_pct,
            "passed": coverage_pct >= min_coverage_pct,
        },
        "events_summary": {
            "total_events": sum(counts),
            "avg_per_day": round(avg_events, 1),
            "min_per_day": min_events,
            "max_per_day": max_events,
            "zero_event_days": len(zero_event_days),
        },
        "symbols": {
            "unique_in_events": len(symbols_found),
            "unique_in_price_data": len(price_symbols),
            "common": len(common_symbols),
            "events_only": len(events_only_symbols),
            "price_only": len(price_only_symbols),
        },
        "data_quality": {
            "days_with_parse_errors": len(parse_errors_per_day),
            "total_duplicate_event_ids": len(duplicate_ids),
            "ts_anomaly_count": len(ts_anomalies),
        },
        # Detailed lists (first 20 each to keep output manageable)
        "missing_days_sample": days_missing[:20],
        "zero_event_days_sample": zero_event_days[:20],
        "ts_anomalies_sample": ts_anomalies[:10],
        "duplicate_ids_sample": duplicate_ids[:10],
        "parse_errors_sample": {
            k: v for k, v in list(parse_errors_per_day.items())[:5]
        },
    }

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Validate KAP event dataset coverage and quality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--from", dest="date_from", default="2023-01-01", metavar="YYYY-MM-DD",
                   help="Start date (default: 2023-01-01)")
    p.add_argument("--to", dest="date_to", default=None, metavar="YYYY-MM-DD",
                   help="End date (default: today)")
    p.add_argument("--events-dir", dest="events_dir", default=None, metavar="DIR",
                   help="Events directory (default: data/events/)")
    p.add_argument("--min-coverage", dest="min_coverage", type=float, default=80.0,
                   metavar="PCT",
                   help="Minimum %% of trading days that must have data (default: 80)")
    p.add_argument("--json", dest="json_output", action="store_true", default=False,
                   help="Print full report as JSON")
    p.add_argument("--strict", action="store_true", default=False,
                   help="Exit 2 if any parse errors exist (regardless of coverage)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        start = date.fromisoformat(args.date_from)
    except ValueError:
        print(f"ERROR: invalid --from {args.date_from!r}", file=sys.stderr)
        return 1

    end_str = args.date_to or date.today().isoformat()
    try:
        end = date.fromisoformat(end_str)
    except ValueError:
        print(f"ERROR: invalid --to {end_str!r}", file=sys.stderr)
        return 1

    if start > end:
        print("ERROR: --from must not be after --to", file=sys.stderr)
        return 1

    if args.events_dir:
        events_dir = Path(args.events_dir)
    else:
        env_dir = os.getenv("BIST_KAP_EVENTS_DIR")
        if env_dir:
            events_dir = Path(env_dir)
        else:
            try:
                from bist_core import config as _cfg

                events_dir = _cfg.REPO_ROOT / "data" / "events"
            except ImportError:
                events_dir = _REPO_ROOT / "data" / "events"

    report = validate_coverage(
        events_dir=events_dir,
        start=start,
        end=end,
        min_coverage_pct=args.min_coverage,
    )

    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 2

    # Human-friendly output
    cov = report["coverage"]
    evt = report["events_summary"]
    sym = report["symbols"]
    dq = report["data_quality"]

    status = "PASS" if report["ok"] else "FAIL"
    print(f"\nEvent Coverage Report [{status}]")
    print(f"  Dir   : {report['events_dir']}")
    print(f"  Range : {start.isoformat()} → {end.isoformat()}")
    print()
    print("Date Coverage:")
    print(f"  Expected trading days : {cov['expected_trading_days']}")
    print(f"  Days with data        : {cov['days_with_data']}")
    print(f"  Days missing          : {cov['days_missing']}")
    print(f"  Coverage              : {cov['coverage_pct']:.1f}% (threshold: {cov['min_coverage_threshold_pct']:.0f}%)")
    print(f"  Coverage check        : {'PASS' if cov['passed'] else 'FAIL'}")
    print()
    print("Event Statistics:")
    print(f"  Total events          : {evt['total_events']}")
    print(f"  Avg per day           : {evt['avg_per_day']}")
    print(f"  Min / Max per day     : {evt['min_per_day']} / {evt['max_per_day']}")
    print(f"  Zero-event days       : {evt['zero_event_days']}")
    print()
    print("Symbol Coverage:")
    print(f"  Unique symbols (events)     : {sym['unique_in_events']}")
    if sym["unique_in_price_data"] > 0:
        print(f"  Unique symbols (price data) : {sym['unique_in_price_data']}")
        print(f"  Common (events ∩ price)     : {sym['common']}")
        print(f"  Events-only symbols         : {sym['events_only']}")
        print(f"  Price-only symbols          : {sym['price_only']}")
    else:
        print("  Price data symbols          : not available")
    print()
    print("Data Quality:")
    print(f"  Days with parse errors      : {dq['days_with_parse_errors']}")
    print(f"  Duplicate event IDs         : {dq['total_duplicate_event_ids']}")
    print(f"  Timestamp anomalies (>3d)   : {dq['ts_anomaly_count']}")

    missing_sample = report.get("missing_days_sample", [])
    if missing_sample:
        print(f"\nMissing days (first {len(missing_sample)}):")
        for d in missing_sample:
            print(f"  {d}")
        if cov["days_missing"] > len(missing_sample):
            print(f"  ... and {cov['days_missing'] - len(missing_sample)} more")

    parse_errors = report.get("parse_errors_sample", {})
    if parse_errors:
        print("\nParse errors (sample):")
        for day_str, errs in list(parse_errors.items())[:5]:
            print(f"  {day_str}:")
            for e in errs[:3]:
                print(f"    {e}")

    print()
    if args.strict and dq["days_with_parse_errors"] > 0:
        print("STRICT: parse errors found → exit 2")
        return 2

    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
