
from pathlib import Path
from subprocess import run, PIPE
from bist_core.providers import LocalCSVProvider

def _run(mod: str, *args: str):
    return run(["python", "-m", mod, *args], stdout=PIPE, stderr=PIPE, text=True)

def test_local_csv_provider_symbols_and_close():
    day = "2025-01-15"
    # Snapshot yoksa üret (CLI eod komutu)
    r = _run("bist_core.cli.main", "eod", "--date", day)
    assert r.returncode == 0, r.stderr

    prov = LocalCSVProvider(base=Path("data/eod/snapshots"))
    syms = prov.symbols(day)
    assert "TEST" in syms

    cmap = prov.close_map(day)
    assert cmap["TEST"] == 0.0
