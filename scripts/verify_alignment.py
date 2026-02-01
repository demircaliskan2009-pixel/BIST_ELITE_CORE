"""
FAZ83: Alignment gate — exit 2 if checklist in docs/target_robot_alignment.md is incomplete.
Run from repo root: python scripts/verify_alignment.py [path]
Path defaults to docs/target_robot_alignment.md relative to script's repo root.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _checklist_complete(md_path: Path) -> bool:
    """Return True if all checklist items in the Checklist section are checked ([x])."""
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_section = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"^##\s+", stripped):
            if "checklist" in stripped.lower():
                in_section = True
                continue
            in_section = False
            continue
        if not in_section:
            continue
        if stripped.startswith("- [ ]"):
            return False
    return True


def main(args: list[str] | None = None) -> int:
    argv = args if args is not None else sys.argv[1:]
    root = _repo_root()
    if argv:
        md_path = Path(argv[0])
        if not md_path.is_absolute():
            md_path = root / md_path
    else:
        md_path = root / "docs" / "target_robot_alignment.md"
    if not md_path.is_file():
        print(f"Alignment doc not found: {md_path}", file=sys.stderr)
        return 2
    if _checklist_complete(md_path):
        return 0
    print("Checklist incomplete: at least one unchecked item in docs/target_robot_alignment.md", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
