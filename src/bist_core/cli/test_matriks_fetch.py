"""CLI smoke test: Matriks historical bars (requires ``MATRIKS_ENABLED=1`` + ``MATRIKS_TOKEN``)."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta

from bist_core.data.matriks_historical import MatriksHistorical


def _parse_ymd(s: str) -> date:
    return datetime.strptime(s.strip()[:10], "%Y-%m-%d").date()


def main() -> None:
    parser = argparse.ArgumentParser(description="Matriks historical bar fetch (test env)")
    parser.add_argument("--symbol", default="ASELS", help="BIST symbol, e.g. ASELS")
    parser.add_argument(
        "--start",
        default=None,
        help="YYYY-MM-DD inclusive (default: end minus 120 calendar days)",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="YYYY-MM-DD inclusive (default: today local date)",
    )
    args = parser.parse_args()

    end = date.today()
    if args.end:
        end = _parse_ymd(args.end)
    start = end - timedelta(days=120)
    if args.start:
        start = _parse_ymd(args.start)

    mh = MatriksHistorical()
    bars = mh.fetch_bars(args.symbol, start, end)
    print(len(bars))
    if bars:
        print(float(bars[-1].close))


if __name__ == "__main__":
    main()
