"""FAZ102: Repo hygiene — .gitignore has patterns; no tracked __pycache__/, .pyc, .pyo, .bak*, .broken*, proof_*.txt."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _repo_root() -> Path:
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "src").is_dir():
            return p
        p = p.parent
    return p


def test_faz102_repo_hygiene_no_build_artifacts() -> None:
    """Assert .gitignore contains required patterns; fail if any tracked path is a build/backup artifact."""
    root = _repo_root()
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    required = ["__pycache__/", "*.pyc", "*.pyo", "*.bak*", "*.broken*", "proof_*.txt"]
    for pat in required:
        assert pat in gitignore, f".gitignore missing pattern: {pat!r}"

    r = subprocess.run(
        ["git", "ls-files", "--cached"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=10,
    )
    if r.returncode != 0:
        return
    offending: list[str] = []
    for line in (r.stdout or "").strip().splitlines():
        path = line.strip().replace("\\", "/")
        if not path:
            continue
        if "__pycache__/" in path:
            offending.append(path)
            continue
        if path.endswith(".pyc") or path.endswith(".pyo"):
            offending.append(path)
            continue
        if ".bak" in path or ".broken" in path:
            offending.append(path)
            continue
        name = path.split("/")[-1]
        if name.startswith("proof_") and name.endswith(".txt"):
            offending.append(path)
    offending.sort()
    assert not offending, f"Build/backup artifacts tracked in repo: {offending}"
