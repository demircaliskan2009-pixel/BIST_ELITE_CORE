"""FAZ547: Snapshots use normalize_symbol on read — uppercase, trim, deterministic."""
from __future__ import annotations

from pathlib import Path

import pytest

from bist_core.market_data.local_eod import LocalEODProvider


@pytest.fixture
def snapshot_dir(tmp_path: Path) -> Path:
    """Minimal snapshot with mixed-case and trimmed symbols."""
    day_dir = tmp_path / "2025-01-15"
    day_dir.mkdir()
    snap = day_dir / "snapshot.csv"
    snap.write_text(
        "symbol,close\nakbnk,50.0\n  GARAN  ,100.0\nTHYAO.E,25.5\n",
        encoding="utf-8",
    )
    return tmp_path


def test_faz547_snapshot_symbol_uppercase(snapshot_dir: Path) -> None:
    """Symbols from snapshot are returned uppercase."""
    prov = LocalEODProvider(snapshot_dir)
    syms = prov.symbols("2025-01-15")
    assert "AKBNK" in syms
    assert "akbnk" not in syms
    assert all(s == s.upper() for s in syms)


def test_faz547_snapshot_symbol_normalized(snapshot_dir: Path) -> None:
    """Symbols with whitespace and .E suffix are normalized."""
    prov = LocalEODProvider(snapshot_dir)
    syms = prov.symbols("2025-01-15")
    assert "GARAN" in syms  # trimmed
    assert "THYAO" in syms  # .E suffix removed
    close = prov.close_map("2025-01-15")
    assert close["AKBNK"] == 50.0
    assert close["GARAN"] == 100.0
    assert close["THYAO"] == 25.5
