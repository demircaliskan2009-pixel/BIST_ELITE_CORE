#!/usr/bin/env python3
"""FAZ397: Append changelog entry. Usage: python tools/changelog_append.py fazNNN 'summary'."""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Append [fazNNN] entry to CHANGELOG.md")
    parser.add_argument("phase", metavar="fazNNN", help="Phase id (e.g. faz397)")
    parser.add_argument("summary", nargs="?", default="", help="One-line summary")
    args = parser.parse_args()

    phase = args.phase.strip().lower()
    if not re.match(r"^faz\d+$", phase):
        print(f"Invalid phase: {phase}. Use fazNNN format.", file=sys.stderr)
        return 1

    changelog = _repo_root() / "CHANGELOG.md"
    if not changelog.is_file():
        print(f"CHANGELOG.md not found at {changelog}", file=sys.stderr)
        return 1

    today = date.today().isoformat()
    entry = f"- [{phase}] {today} — {args.summary}\n"

    text = changelog.read_text(encoding="utf-8")
    if f"[{phase}]" in text:
        print(f"Phase [{phase}] already in CHANGELOG.md", file=sys.stderr)
        return 1

    # Append at end of phases list
    new_text = text.rstrip()
    if not new_text.endswith("\n"):
        new_text += "\n"
    new_text += entry

    changelog.write_text(new_text, encoding="utf-8")
    print(f"Appended: {entry.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
