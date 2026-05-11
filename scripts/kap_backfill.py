#!/usr/bin/env python3
"""KAP historical disclosure backfill CLI.

Fetches and stores KAP disclosures for a date range.
Output: data/events/{date}.jsonl  (one JSON event per line, one file per trading day)

Usage
-----
    # Typical 3-year backfill
    $env:BIST_CORE_ALLOW_NETWORK = "1"
    $env:BIST_KAP_EVENTS_URL_TEMPLATE = "/your/kap/endpoint/{day}"
    python scripts/kap_backfill.py --from 2023-01-01 --to 2026-04-12

    # Resume interrupted run (default: skip already-written dates)
    python scripts/kap_backfill.py --from 2023-01-01 --to 2026-04-12

    # Cache-only (parse local HTML files, no network)
    python scripts/kap_backfill.py --from 2023-01-01 --to 2026-04-12 --cache-only

    # Custom output dir
    python scripts/kap_backfill.py --from 2023-01-01 --to 2026-04-12 --output-dir /path/to/events

Required env vars
-----------------
    BIST_CORE_ALLOW_NETWORK=1           enable network requests (default OFF)
    BIST_KAP_EVENTS_URL_TEMPLATE        URL path template containing {day}
                                        Example: /kap/events/{day}

Exit codes
----------
    0  All trading days processed (fetched or skipped) without fatal error
    1  Argument error
    2  Fatal error (e.g. import failure)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

# Ensure src/ is on the path when run directly
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill KAP disclosures to data/events/{date}.jsonl",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--from", dest="date_from", required=True, metavar="YYYY-MM-DD",
                   help="Start date (inclusive)")
    p.add_argument("--to", dest="date_to", required=True, metavar="YYYY-MM-DD",
                   help="End date (inclusive)")
    p.add_argument("--output-dir", dest="output_dir", default=None, metavar="DIR",
                   help="Output directory (default: data/events/)")
    p.add_argument("--delay", dest="delay", type=float, default=0.5, metavar="SECONDS",
                   help="Minimum seconds between requests (default: 0.5)")
    p.add_argument("--timeout", dest="timeout", type=int, default=20, metavar="SECONDS",
                   help="Per-request HTTP timeout (default: 20)")
    p.add_argument("--no-resume", dest="resume", action="store_false", default=True,
                   help="Re-fetch dates that already have output files")
    p.add_argument("--cache-only", dest="cache_only", action="store_true", default=False,
                   help="Use local cache only; never issue network requests")
    p.add_argument("--legacy-html", dest="legacy_html", action="store_true", default=False,
                   help="Use legacy HTML scraper instead of KAP JSON API")
    p.add_argument("--base-url", dest="base_url", default="https://www.kap.org.tr",
                   metavar="URL", help="KAP base URL (default: https://www.kap.org.tr)")
    p.add_argument("--url-template", dest="url_template", default=None, metavar="TEMPLATE",
                   help="URL path template with {day} (legacy HTML mode only)")
    p.add_argument("--max-consecutive-empty", dest="max_consecutive_empty", type=int,
                   default=5, metavar="N",
                   help="Abort after N consecutive 0-event fetches (rate-limit guard, default: 5, 0=off)")
    p.add_argument("--json", dest="json_output", action="store_true", default=False,
                   help="Print final summary as JSON")
    return p.parse_args(argv)


def _validate_date(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        print(f"ERROR: invalid {name} format {value!r} — use YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    start = _validate_date(args.date_from, "--from")
    end = _validate_date(args.date_to, "--to")
    if start > end:
        print("ERROR: --from must not be after --to", file=sys.stderr)
        return 1

    # Honour --cache-only flag by setting env var before imports that check it
    if args.cache_only:
        os.environ["BIST_KAP_CACHE_ONLY"] = "1"

    try:
        from bist_core.env import network_allowed
        from bist_core.events.kap_backfill import backfill_range
    except ImportError as exc:
        print(f"ERROR: import failed — {exc}", file=sys.stderr)
        return 2

    # Safety check: warn if network disabled and not cache-only
    if not network_allowed() and not args.cache_only:
        print(
            "WARNING: BIST_CORE_ALLOW_NETWORK is not set — fetching from local cache only.\n"
            "         Set BIST_CORE_ALLOW_NETWORK=1 to enable live fetching.",
            file=sys.stderr,
        )

    use_json_api = not args.legacy_html

    output_dir_path = Path(args.output_dir) if args.output_dir else None

    # Compute trading day count for progress display
    from datetime import timedelta

    trading_days: list[str] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            trading_days.append(cur.isoformat())
        cur += timedelta(days=1)
    total = len(trading_days)

    print(
        f"Backfill: {start.isoformat()} → {end.isoformat()}"
        f" | {total} trading days | resume={args.resume} | delay={args.delay}s"
    )
    if output_dir_path:
        print(f"Output dir: {output_dir_path}")
    else:
        from bist_core import config as _cfg
        out = Path(os.getenv("BIST_KAP_EVENTS_DIR", "")) or _cfg.REPO_ROOT / "data" / "events"
        print(f"Output dir: {out}")

    results = backfill_range(
        start=start,
        end=end,
        output_dir=output_dir_path,
        resume=args.resume,
        min_delay_s=args.delay,
        base_url=args.base_url,
        url_template=args.url_template,
        timeout_s=args.timeout,
        use_json_api=use_json_api,
        max_consecutive_empty=args.max_consecutive_empty,
    )

    # Progress summary
    fetched = [r for r in results if not r.skipped]
    skipped = [r for r in results if r.skipped]
    error_days = [r for r in fetched if r.errors > 0]
    total_events = sum(r.events_written for r in fetched)

    print(
        f"\nDone: {len(fetched)} fetched, {len(skipped)} skipped (resume), "
        f"{len(error_days)} days with parse errors"
    )
    print(f"Total events written: {total_events}")

    if error_days:
        print("\nDays with errors:")
        for r in error_days[:20]:
            print(f"  {r.date_str}: {r.errors} errors, {r.events_written} events written")
        if len(error_days) > 20:
            print(f"  ... and {len(error_days) - 20} more")

    if args.json_output:
        summary = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "trading_days": total,
            "fetched": len(fetched),
            "skipped": len(skipped),
            "error_days": len(error_days),
            "total_events": total_events,
            "results": [r.to_dict() for r in results],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
