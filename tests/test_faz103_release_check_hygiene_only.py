"""FAZ103: Release check --hygiene-only gate."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_faz103_release_check_hygiene_only() -> None:
    """python tools/release_check.py --hygiene-only must exit 0."""
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "tools" / "release_check.py"
    r = subprocess.run(
        [sys.executable, str(script), "--hygiene-only"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr or r.stdout or f"exit {r.returncode}"
