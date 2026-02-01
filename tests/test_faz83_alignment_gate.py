"""FAZ83: Alignment gate — checklist incomplete -> exit 2, complete -> exit 0."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def _run_verify(align_doc_path: Path) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "verify_alignment.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(align_doc_path)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    return proc.returncode


def test_faz83_alignment_incomplete_exit_2(tmp_path: Path) -> None:
    """When checklist has an unchecked item, verify_alignment.py exits 2."""
    md = tmp_path / "target_robot_alignment.md"
    md.write_text(
        "# Alignment\n\n## Checklist\n\n- [ ] Unchecked item\n- [x] Checked item\n\n## DoD\n\nDone.\n",
        encoding="utf-8",
    )
    rc = _run_verify(md)
    assert rc == 2


def test_faz83_alignment_complete_exit_0(tmp_path: Path) -> None:
    """When all checklist items are checked, verify_alignment.py exits 0."""
    md = tmp_path / "target_robot_alignment.md"
    md.write_text(
        "# Alignment\n\n## Checklist\n\n- [x] Item one\n- [x] Item two\n\n## DoD\n\nDone.\n",
        encoding="utf-8",
    )
    rc = _run_verify(md)
    assert rc == 0


def test_faz83_alignment_default_doc_exit_0() -> None:
    """Repo docs/target_robot_alignment.md has all items checked -> exit 0."""
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "verify_alignment.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
