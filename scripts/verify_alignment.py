"""
FAZ83/FAZ100: Alignment gate — exit 2 if checklist in docs/target_robot_alignment.md is incomplete.
Run from repo root: python scripts/verify_alignment.py [path]
Path defaults to docs/target_robot_alignment.md relative to script's repo root.
Uses single source-of-truth sentinel from bist_core.alignment.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Single source-of-truth for core-complete sentinel
_root = Path(__file__).resolve().parents[1]
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))
from bist_core.alignment import CORE_COMPLETE_SENTINEL


def _repo_root() -> Path:
    return _root


def _has_checklist_section(text: str) -> bool:
    """Return True if doc has a ## Checklist section."""
    return bool(re.search(r"^##\s+checklist\s*$", text, re.MULTILINE | re.IGNORECASE))


def _checklist_complete(md_path: Path) -> bool:
    """Return True if doc has Checklist section and all checklist items are checked ([x])."""
    text = md_path.read_text(encoding="utf-8")
    if not _has_checklist_section(text):
        return False
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
    if not _checklist_complete(md_path):
        print("Checklist incomplete: at least one unchecked item in docs/target_robot_alignment.md", file=sys.stderr)
        return 2
    print(CORE_COMPLETE_SENTINEL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
