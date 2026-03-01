#!/usr/bin/env python3
"""FAZ577: Weekly rollup — scoreboard + performance + journal. Deterministic. Derived from logs only."""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _week_to_dates(week_str: str) -> tuple[str, str]:
    """Parse YYYY-WW to (monday, sunday) ISO dates. Deterministic."""
    # YYYY-Www e.g. 2025-W03
    m = re.match(r"(\d{4})-W(\d{1,2})$", week_str.strip(), re.IGNORECASE)
    if not m:
        raise ValueError(f"Invalid week format: {week_str}. Use YYYY-WW (e.g. 2025-W03)")
    year = int(m.group(1))
    week = int(m.group(2))
    # Jan 4 is always in week 1
    jan4 = datetime(year, 1, 4)
    monday = jan4 - timedelta(days=jan4.weekday())
    week_monday = monday + timedelta(weeks=week - 1)
    week_sunday = week_monday + timedelta(days=6)
    return week_monday.strftime("%Y-%m-%d"), week_sunday.strftime("%Y-%m-%d")


def _dates_in_range(date_from: str, date_to: str) -> list[str]:
    """List all dates in range inclusive. Deterministic sorted."""
    start = datetime.strptime(date_from, "%Y-%m-%d")
    end = datetime.strptime(date_to, "%Y-%m-%d")
    out: list[str] = []
    d = start
    while d <= end:
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


def _load_scoreboard(reports_dir: Path, day: str) -> dict | None:
    """Load scoreboard.json for day. None if missing."""
    path = reports_dir / day / "scoreboard.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _load_performance(reports_dir: Path, day: str) -> dict | None:
    """Load performance.json for day. None if missing."""
    path = reports_dir / day / "performance.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _load_journal_report(out_root: Path, date_from: str, date_to: str, journal_path: Path | None) -> dict | None:
    """Build journal report for range. None if no journal."""
    if not journal_path or not journal_path.is_file():
        return None
    try:
        from tools.live_journal_report import build_report

        return build_report(journal_path, out_root, date_from, date_to)
    except Exception:
        return None


def build_weekly_report(
    week: str,
    out_root: Path,
    journal_path: Path | None = None,
) -> dict:
    """
    Build weekly rollup from existing logs. Deterministic.
    Returns: schema_version, week, date_from, date_to, scoreboard, performance, journal.
    """
    out_root = Path(out_root)
    reports_dir = out_root / "reports"
    date_from, date_to = _week_to_dates(week)
    days = _dates_in_range(date_from, date_to)

    scoreboard_days: list[dict] = []
    scoreboard_rows: list[dict] = []
    performance_by_day: list[dict] = []
    performance_aggregated = {
        "trade_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate": 0.0,
        "avg_r": 0.0,
        "total_r": 0.0,
        "max_dd": 0.0,
    }

    for day in days:
        sb = _load_scoreboard(reports_dir, day)
        if sb:
            rows = sb.get("rows") or []
            scoreboard_days.append({"day": day, "rows": rows})
            for r in rows:
                row_copy = dict(r)
                row_copy["day"] = day
                scoreboard_rows.append(row_copy)

        perf = _load_performance(reports_dir, day)
        if perf:
            performance_by_day.append(
                {"day": day, **{k: perf.get(k) for k in ("trade_count", "win_rate", "avg_r", "total_r", "max_dd")}}
            )
            performance_aggregated["trade_count"] += int(perf.get("trade_count", 0))
            performance_aggregated["win_count"] += int(perf.get("win_count", 0))
            performance_aggregated["loss_count"] += int(perf.get("loss_count", 0))
            performance_aggregated["total_r"] += float(perf.get("total_r", 0))

    if performance_aggregated["trade_count"] > 0:
        performance_aggregated["win_rate"] = round(
            performance_aggregated["win_count"] / performance_aggregated["trade_count"], 4
        )
        performance_aggregated["avg_r"] = round(
            performance_aggregated["total_r"] / performance_aggregated["trade_count"], 4
        )
    performance_aggregated["total_r"] = round(performance_aggregated["total_r"], 4)

    journal = _load_journal_report(out_root, date_from, date_to, journal_path)

    scoreboard_rows = sorted(scoreboard_rows, key=lambda r: (r.get("day", ""), r.get("symbol", "")))
    performance_by_day = sorted(performance_by_day, key=lambda x: x.get("day", ""))

    return {
        "schema_version": 1,
        "week": week,
        "date_from": date_from,
        "date_to": date_to,
        "scoreboard": {
            "days": scoreboard_days,
            "rows": scoreboard_rows,
        },
        "performance": {
            "aggregated": performance_aggregated,
            "by_day": performance_by_day,
        },
        "journal": journal,
    }


def write_weekly_json(report: dict, out_dir: Path) -> Path:
    """Write weekly.json. Deterministic keys."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "weekly.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_weekly_csv(report: dict, out_dir: Path) -> Path:
    """Write weekly.csv. Deterministic: metrics first, then scoreboard rows."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "weekly.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["section", "metric", "value"])
        w.writerow(["meta", "week", report.get("week", "")])
        w.writerow(["meta", "date_from", report.get("date_from", "")])
        w.writerow(["meta", "date_to", report.get("date_to", "")])
        perf = report.get("performance", {}).get("aggregated", {})
        for k in ("trade_count", "win_count", "loss_count", "win_rate", "avg_r", "total_r", "max_dd"):
            w.writerow(["performance", k, perf.get(k, "")])
        journal = report.get("journal") or {}
        if journal:
            w.writerow(["journal", "realized_pnl_tl", journal.get("realized_pnl_tl", "")])
        rows = report.get("scoreboard", {}).get("rows") or []
        if rows:
            all_keys = set()
            for r in rows:
                all_keys.update(r.keys())
            ret_cols = sorted(k for k in all_keys if k.startswith("ret_"))
            cols = ["day", "symbol", "decision_raw"] + ret_cols
            w.writerow(["section"] + cols)
            for r in rows:
                w.writerow(["scoreboard"] + [str(r.get(c, "")) for c in cols])
    return path


def write_weekly_html(report: dict, out_dir: Path) -> Path:
    """Write weekly.html. Phone-friendly. Deterministic."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "weekly.html"

    week = report.get("week", "")
    date_from = report.get("date_from", "")
    date_to = report.get("date_to", "")
    perf = report.get("performance", {}).get("aggregated", {})
    journal = report.get("journal") or {}
    rows = report.get("scoreboard", {}).get("rows") or []

    lines = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>Weekly {week}</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:1em;max-width:40em}",
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:.25em}",
        "a{color:#06c}</style></head><body>",
        f"<h1>Weekly {week}</h1>",
        f"<p>{date_from} – {date_to}</p>",
        "<h2>Performance</h2>",
        "<ul>",
        f"<li>trades: {perf.get('trade_count', 0)}</li>",
        f"<li>win_rate: {perf.get('win_rate', 0)}</li>",
        f"<li>avg_r: {perf.get('avg_r', 0)}</li>",
        f"<li>total_r: {perf.get('total_r', 0)}</li>",
        f"<li>max_dd: {perf.get('max_dd', 0)}</li>",
        "</ul>",
        "<h2>Journal</h2>",
        f"<p>realized_pnl_tl: {journal.get('realized_pnl_tl', 'n/a')}</p>",
        "<h2>Scoreboard</h2>",
        "<table><tr><th>day</th><th>symbol</th><th>decision</th></tr>",
    ]
    for r in rows[:50]:
        lines.append(
            f"<tr><td>{r.get('day', '')}</td><td>{r.get('symbol', '')}</td><td>{r.get('decision_raw', '')}</td></tr>"
        )
    if len(rows) > 50:
        lines.append(f"<tr><td colspan='3'>... and {len(rows) - 50} more</td></tr>")
    lines.extend(["</table>", "</body>", "</html>"])

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="FAZ577: Weekly live review (scoreboard+perf+journal)")
    p.add_argument("--week", default=None, help="YYYY-WW (default: current week)")
    p.add_argument("--out-root", default="data/log")
    p.add_argument("--journal", default=None, help="Journal CSV path")
    args = p.parse_args()

    if args.week:
        week = args.week
    else:
        from datetime import date

        today = date.today()
        iso = today.isocalendar()
        week = f"{iso[0]}-W{iso[1]:02d}"

    out_root = Path(args.out_root)
    if not out_root.is_absolute():
        out_root = (_repo_root() / out_root).resolve()
    journal_path = Path(args.journal) if args.journal else None
    if journal_path and not journal_path.is_absolute():
        journal_path = (_repo_root() / journal_path).resolve()

    try:
        report = build_weekly_report(week, out_root, journal_path)
        out_dir = out_root / "reports" / "weekly" / week
        write_weekly_json(report, out_dir)
        write_weekly_csv(report, out_dir)
        write_weekly_html(report, out_dir)
        print(str(out_dir / "weekly.json"))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
