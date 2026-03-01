#!/usr/bin/env python3
"""FAZ571: Publish deterministic daily HTML summary. Phone-friendly. No network."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def publish_summary(day: str, out_root: Path) -> Path | None:
    """
    Generate summary.html under reports/<DAY>/. Returns path or None on failure.
    Deterministic: symbols sorted.
    """
    out_root = Path(out_root)
    reports_dir = out_root / "reports" / day
    reports_dir.mkdir(parents=True, exist_ok=True)

    scan_path = out_root / "daily_scan" / day / "scan.json"
    ask_dir = out_root / "ask" / day
    symbols: list[str] = []
    if scan_path.is_file():
        try:
            data = json.loads(scan_path.read_text(encoding="utf-8"))
            ranked = data.get("ranked") or []
            symbols = sorted(item["symbol"] for item in ranked if isinstance(item, dict) and item.get("symbol"))
        except (json.JSONDecodeError, OSError):
            pass

    if not symbols and ask_dir.is_dir():
        symbols = sorted(p.stem for p in ask_dir.glob("*.json") if p.stem and not p.name.startswith("."))

    out_path = reports_dir / "summary.html"

    lines: list[str] = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>Live Test {day}</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:1em;max-width:40em}",
        "a{color:#06c}ul{margin:.5em 0}</style>",
        "</head>",
        "<body>",
        f"<h1>Live Test {day}</h1>",
        "<h2>Scan</h2>",
        f"<ul><li><a href='../../daily_scan/{day}/scan.json'>scan.json</a></li></ul>",
        "<h2>Ask artifacts</h2>",
        "<ul>",
    ]

    for sym in symbols:
        lines.append(f"<li><a href='../../ask/{day}/{sym}.json'>{sym}.json</a></li>")

    lines.extend(
        [
            "</ul>",
            "<h2>Performance</h2>",
            "<ul>",
            "<li><a href='performance.json'>performance.json</a></li>",
            "<li><a href='performance.csv'>performance.csv</a></li>",
            "</ul>",
            "</body>",
            "</html>",
        ]
    )

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="FAZ571: Publish daily HTML summary")
    p.add_argument("--day", required=True, help="YYYY-MM-DD")
    p.add_argument("--out-root", default="data/log")
    args = p.parse_args()

    out_root = Path(args.out_root)
    if not out_root.is_absolute():
        out_root = (_repo_root() / out_root).resolve()

    try:
        path = publish_summary(args.day, out_root)
        if path:
            print(str(path))
            return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
