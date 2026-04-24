"""Phase 2 — Event Alpha Study.

Joins KAP event data with BIST price data to measure forward returns
per event kind. Outputs cohort statistics and edge classification.

Methodology (conservative, no look-ahead):
  - T0 = first trading day >= event calendar date
  - Entry price = close(T0)
  - T+N = Nth trading day after T0
  - Return(N) = close(T0+N) / close(T0) - 1
  - Events for symbols without price data are excluded

Edge classification:
  - PF > 1.1 and AVG_RET > 0 → POSITIVE EDGE
  - PF < 0.9 → NEGATIVE EDGE (ANTI-EDGE)
  - else → NO EDGE
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class EventRecord:
    kind: str
    symbol: str
    event_date: str  # YYYY-MM-DD


@dataclass
class CohortStats:
    kind: str
    n: int = 0
    n_matched: int = 0  # events with full forward return data
    returns_1d: list = field(default_factory=list)
    returns_3d: list = field(default_factory=list)
    returns_5d: list = field(default_factory=list)


def load_price_data(
    price_path: str,
) -> tuple[dict[str, dict[str, float]], dict[str, list[str]]]:
    """Load price CSV → {symbol: {date: close}}, {symbol: [sorted_dates]}."""
    prices: dict[str, dict[str, float]] = defaultdict(dict)
    with open(price_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row["symbol"]
            dt = row["date"]
            close = float(row["close"])
            if close > 0:
                prices[sym][dt] = close

    # Build sorted trading day lists per symbol
    trading_days: dict[str, list[str]] = {}
    for sym, date_map in prices.items():
        trading_days[sym] = sorted(date_map.keys())

    return dict(prices), trading_days


def load_events(events_dir: str) -> list[EventRecord]:
    """Load all events from JSONL files."""
    events = []
    for fname in sorted(os.listdir(events_dir)):
        if not fname.endswith(".jsonl"):
            continue
        fpath = os.path.join(events_dir, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ev = json.loads(line)
                # Extract date from ts (e.g. "2024-11-11T23:59:36+03:00")
                ts_str = ev.get("ts", "")
                if ts_str:
                    event_date = ts_str[:10]
                else:
                    # Fallback: use filename date
                    event_date = fname.replace(".jsonl", "")
                events.append(
                    EventRecord(
                        kind=ev.get("kind", "unknown"),
                        symbol=ev.get("symbol", ""),
                        event_date=event_date,
                    )
                )
    return events


def find_trading_day_offset(
    trading_days_list: list[str], from_date: str, offset: int
) -> str | None:
    """Find the trading day at 'offset' positions from 'from_date'.

    offset=0 → first trading day >= from_date
    offset=N → Nth trading day after T0
    """
    import bisect

    idx = bisect.bisect_left(trading_days_list, from_date)
    target = idx + offset
    if 0 <= target < len(trading_days_list):
        return trading_days_list[target]
    return None


def compute_cohort_stats(
    events: list[EventRecord],
    prices: dict[str, dict[str, float]],
    trading_days: dict[str, list[str]],
) -> dict[str, CohortStats]:
    """Compute forward return statistics per event kind."""
    cohorts: dict[str, CohortStats] = {}

    for ev in events:
        if ev.kind not in cohorts:
            cohorts[ev.kind] = CohortStats(kind=ev.kind)
        cohort = cohorts[ev.kind]
        cohort.n += 1

        # Skip if no price data for symbol
        if ev.symbol not in prices:
            continue
        sym_days = trading_days[ev.symbol]
        sym_prices = prices[ev.symbol]

        # T0 = first trading day >= event_date
        t0_date = find_trading_day_offset(sym_days, ev.event_date, 0)
        if t0_date is None:
            continue
        t0_close = sym_prices.get(t0_date)
        if t0_close is None or t0_close <= 0:
            continue

        # T+1, T+3, T+5
        t0_idx_in_list = None
        import bisect

        t0_idx_in_list = bisect.bisect_left(sym_days, t0_date)
        if t0_idx_in_list >= len(sym_days) or sym_days[t0_idx_in_list] != t0_date:
            continue

        matched = True
        for offset, ret_list in [
            (1, cohort.returns_1d),
            (3, cohort.returns_3d),
            (5, cohort.returns_5d),
        ]:
            tn_idx = t0_idx_in_list + offset
            if tn_idx >= len(sym_days):
                matched = False
                break
            tn_date = sym_days[tn_idx]
            tn_close = sym_prices.get(tn_date)
            if tn_close is None or tn_close <= 0:
                matched = False
                break
            ret = (tn_close / t0_close) - 1.0
            ret_list.append(ret)

        if matched:
            cohort.n_matched += 1

    return cohorts


def profit_factor(returns: list[float]) -> float:
    """PF = sum(wins) / abs(sum(losses)). Returns inf if no losses."""
    wins = sum(r for r in returns if r > 0)
    losses = abs(sum(r for r in returns if r < 0))
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return wins / losses


def winrate(returns: list[float]) -> float:
    """Fraction of positive returns."""
    if not returns:
        return 0.0
    return sum(1 for r in returns if r > 0) / len(returns)


def avg_ret(returns: list[float]) -> float:
    if not returns:
        return 0.0
    return sum(returns) / len(returns)


def classify_edge(pf: float, avg_r: float) -> str:
    if pf > 1.1 and avg_r > 0:
        return "POSITIVE EDGE"
    if pf < 0.9:
        return "NEGATIVE EDGE"
    return "NO EDGE"


def main():
    parser = argparse.ArgumentParser(description="Event Alpha Study")
    parser.add_argument(
        "--events-dir",
        default="data/events",
        help="Directory with event JSONL files",
    )
    parser.add_argument(
        "--price-file",
        default="data/vendor/datastore_normalized.csv",
        help="Normalized price CSV",
    )
    parser.add_argument(
        "--output",
        default="tmp/event_alpha_report.json",
        help="Output JSON report path",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    args = parser.parse_args()

    # Validate inputs
    if not os.path.isdir(args.events_dir):
        print(f"FAIL: events dir not found: {args.events_dir}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(args.price_file):
        print(f"FAIL: price file not found: {args.price_file}", file=sys.stderr)
        sys.exit(1)

    print("Loading price data...", file=sys.stderr)
    prices, trading_days = load_price_data(args.price_file)
    print(f"  {len(prices)} symbols, {sum(len(v) for v in prices.values())} price rows", file=sys.stderr)

    print("Loading events...", file=sys.stderr)
    events = load_events(args.events_dir)
    print(f"  {len(events)} total events", file=sys.stderr)

    # Filter to symbols with price data
    events_with_prices = [e for e in events if e.symbol in prices]
    print(f"  {len(events_with_prices)} events with price data ({len(events) - len(events_with_prices)} excluded)", file=sys.stderr)

    print("Computing forward returns...", file=sys.stderr)
    cohorts = compute_cohort_stats(events_with_prices, prices, trading_days)

    # Build results
    results = []
    for kind in sorted(cohorts.keys(), key=lambda k: cohorts[k].n, reverse=True):
        c = cohorts[kind]
        if c.n_matched < 10:
            verdict = "INSUFFICIENT SAMPLE"
        else:
            # Use 1D returns for primary edge classification
            pf_1d = profit_factor(c.returns_1d)
            ar_1d = avg_ret(c.returns_1d)
            verdict = classify_edge(pf_1d, ar_1d)

        row = {
            "kind": kind,
            "n_total": c.n,
            "n_matched": c.n_matched,
            "avg_ret_1d": round(avg_ret(c.returns_1d) * 100, 4) if c.returns_1d else None,
            "avg_ret_3d": round(avg_ret(c.returns_3d) * 100, 4) if c.returns_3d else None,
            "avg_ret_5d": round(avg_ret(c.returns_5d) * 100, 4) if c.returns_5d else None,
            "winrate_1d": round(winrate(c.returns_1d) * 100, 2) if c.returns_1d else None,
            "winrate_3d": round(winrate(c.returns_3d) * 100, 2) if c.returns_3d else None,
            "winrate_5d": round(winrate(c.returns_5d) * 100, 2) if c.returns_5d else None,
            "pf_1d": round(profit_factor(c.returns_1d), 4) if c.returns_1d else None,
            "pf_3d": round(profit_factor(c.returns_3d), 4) if c.returns_3d else None,
            "pf_5d": round(profit_factor(c.returns_5d), 4) if c.returns_5d else None,
            "verdict": verdict,
        }
        results.append(row)

    # Summary
    report = {
        "methodology": {
            "T0": "first trading day >= event calendar date",
            "entry": "close(T0)",
            "forward_returns": "close(T+N)/close(T0) - 1",
            "edge_positive": "PF > 1.1 AND avg_ret > 0",
            "edge_negative": "PF < 0.9",
            "min_sample": 10,
        },
        "data_summary": {
            "total_events": len(events),
            "events_with_prices": len(events_with_prices),
            "price_symbols": len(prices),
            "event_symbols_matched": len({e.symbol for e in events_with_prices}),
        },
        "cohorts": results,
    }

    # Print table to stderr
    print("\n" + "=" * 120, file=sys.stderr)
    print(f"{'EVENT KIND':<25} {'N':>7} {'MATCH':>7} {'AVG1D%':>8} {'AVG3D%':>8} {'AVG5D%':>8} {'WR1D%':>7} {'PF_1D':>7} {'PF_3D':>7} {'PF_5D':>7} {'VERDICT':<18}", file=sys.stderr)
    print("=" * 120, file=sys.stderr)
    for r in results:
        def fmt(v, w=8):
            return f"{v:>{w}.4f}" if v is not None else f"{'N/A':>{w}}"
        def fmtp(v, w=7):
            return f"{v:>{w}.2f}" if v is not None else f"{'N/A':>{w}}"
        print(
            f"{r['kind']:<25} {r['n_total']:>7} {r['n_matched']:>7} "
            f"{fmt(r['avg_ret_1d'])} {fmt(r['avg_ret_3d'])} {fmt(r['avg_ret_5d'])} "
            f"{fmtp(r['winrate_1d'])} {fmtp(r['pf_1d'])} {fmtp(r['pf_3d'])} {fmtp(r['pf_5d'])} "
            f"{r['verdict']:<18}",
            file=sys.stderr,
        )
    print("=" * 120, file=sys.stderr)

    # Save report
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nReport saved to {args.output}", file=sys.stderr)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
