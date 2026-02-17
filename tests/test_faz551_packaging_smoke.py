"""FAZ551: Packaging smoke test — pack.ps1 / python -m build produces sdist + wheel without network."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz551_pack_builds_artifacts(tmp_path: Path) -> None:
    """python -m build produces dist/ with sdist and wheel when build is installed."""
    pytest = __import__("pytest")
    pytest.importorskip("build", reason="build package required for packaging smoke test")

    root = _repo_root()
    outdir = tmp_path / "dist"
    outdir.mkdir(parents=True, exist_ok=True)

    r = subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(outdir)],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, f"build failed: {r.stderr or r.stdout}"


def test_faz551_dist_has_wheel_and_sdist(tmp_path: Path) -> None:
    """After build, dist/ contains .whl and .tar.gz artifacts."""
    pytest = __import__("pytest")
    pytest.importorskip("build", reason="build package required for packaging smoke test")

    root = _repo_root()
    outdir = tmp_path / "dist"
    outdir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(outdir)],
        cwd=str(root),
        capture_output=True,
        timeout=120,
        check=True,
    )

    files = list(outdir.iterdir())
    whl = [f for f in files if f.suffix == ".whl"]
    sdist = [f for f in files if f.name.endswith(".tar.gz")]

    assert len(whl) >= 1, f"Expected at least one .whl in {outdir}, got {files}"
    assert len(sdist) >= 1, f"Expected at least one .tar.gz in {outdir}, got {files}"
