import os, sys
from subprocess import run, PIPE
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # repo root
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}

def _run(*mod_and_args: str):
    # Örn: _run("bist_core.cli.main", "info")
    return run([sys.executable, "-m", *mod_and_args],
               text=True, stdout=PIPE, stderr=PIPE, env=ENV)

def test_cli_info():
    r = _run("bist_core.cli.main", "info")
    assert r.returncode == 0, r.stderr
    assert "symbols:" in r.stdout

def test_cli_eod_creates_snapshot():
    day = "2025-01-15"
    r = _run("bist_core.cli.main", "eod", "--date", day)
    assert r.returncode == 0, r.stderr
    outdir = ROOT / f"data/eod/snapshots/{day}"
    assert outdir.exists(), f"snapshot yok: {outdir}"
    assert any(p.suffix == ".csv" for p in outdir.iterdir())
