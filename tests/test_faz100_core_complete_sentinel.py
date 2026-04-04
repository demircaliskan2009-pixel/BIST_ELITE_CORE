"""FAZ100: verify_alignment.py — when all checklist items complete, prints CORE_COMPLETE_NO_INTEGRATION."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SENTINEL = "CORE_COMPLETE_NO_INTEGRATION"


def _run_verify(align_doc_path: Path | None = None) -> tuple[int, str, str]:
    """Run verify_alignment.py; return (returncode, stdout, stderr)."""
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "verify_alignment.py"
    argv = [sys.executable, str(script)]
    if align_doc_path is not None:
        argv.append(str(align_doc_path))
    proc = subprocess.run(
        argv,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def test_faz100_complete_prints_sentinel(tmp_path: Path) -> None:
    """When checklist is complete, script prints CORE_COMPLETE_NO_INTEGRATION and exits 0."""
    md = tmp_path / "target_robot_alignment.md"
    md.write_text(
        "# Alignment\n\n## Checklist\n\n- [x] Item one\n- [x] Item two\n\n## DoD\n\nDone.\n",
        encoding="utf-8",
    )
    rc, stdout, stderr = _run_verify(md)
    assert rc == 0, stderr
    assert SENTINEL in stdout
    assert stdout.strip() == SENTINEL


def test_faz100_incomplete_no_sentinel(tmp_path: Path) -> None:
    """When checklist is incomplete, script does not print sentinel and exits 2."""
    md = tmp_path / "target_robot_alignment.md"
    md.write_text(
        "# Alignment\n\n## Checklist\n\n- [ ] Unchecked\n- [x] Checked\n\n## DoD\n\nDone.\n",
        encoding="utf-8",
    )
    rc, stdout, stderr = _run_verify(md)
    assert rc == 2
    assert SENTINEL not in stdout


def test_faz100_default_doc_prints_sentinel() -> None:
    """Repo docs/target_robot_alignment.md complete -> script prints CORE_COMPLETE_NO_INTEGRATION."""
    rc, stdout, stderr = _run_verify(None)
    assert rc == 0, stderr
    assert SENTINEL in stdout
