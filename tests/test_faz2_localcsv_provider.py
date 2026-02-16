
from pathlib import Path
import os
import subprocess
import sys

from bist_core.providers import LocalCSVProvider


def test_local_csv_provider_symbols_and_close(tmp_path: Path) -> None:
    """LocalCSVProvider reads symbol and close from snapshot; isolated tmp_path."""
    day = "2025-01-15"
    snap_dir = tmp_path / "snapshots" / day
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.csv").write_text("symbol,close\nTEST,0.0\n", encoding="utf-8")

    prov = LocalCSVProvider(base=tmp_path / "snapshots")
    syms = prov.symbols(day)
    assert "TEST" in syms

    cmap = prov.close_map(day)
    assert cmap["TEST"] == 0.0
