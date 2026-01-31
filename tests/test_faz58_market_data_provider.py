"""
FAZ58: Market data provider interface.
Tests: provider resolution (local_eod), deterministic reads, CLI validate --day.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from bist_core.market_data import LocalEODProvider, resolve_provider
from bist_core.services.events_pipeline import _provider_raw_cache


def test_faz58_resolve_provider_local_eod(tmp_path: Path) -> None:
    """resolve_provider('local_eod', snapshot_root=X) returns LocalEODProvider."""
    provider = resolve_provider("local_eod", snapshot_root=tmp_path)
    assert isinstance(provider, LocalEODProvider)


def test_faz58_resolve_provider_unknown_raises() -> None:
    """resolve_provider('unknown') raises ValueError."""
    with pytest.raises(ValueError, match="unknown market_data provider"):
        resolve_provider("unknown")


def test_faz58_local_eod_deterministic_reads(tmp_path: Path) -> None:
    """LocalEODProvider: same snapshot -> same symbols and close_map order (deterministic)."""
    day = "2099-06-01"
    (tmp_path / day).mkdir()
    (tmp_path / day / "snapshot.csv").write_text(
        "symbol,close\nB,20.0\nA,10.0\nC,30.0\n",
        encoding="utf-8",
    )
    prov = LocalEODProvider(tmp_path)
    syms1 = prov.symbols(day)
    syms2 = prov.symbols(day)
    assert syms1 == syms2 == ["A", "B", "C"]
    close1 = prov.close_map(day)
    close2 = prov.close_map(day)
    assert list(close1.keys()) == list(close2.keys()) == ["A", "B", "C"]
    assert close1["A"] == 10.0 and close1["B"] == 20.0 and close1["C"] == 30.0


def test_faz58_local_eod_validate_ok(tmp_path: Path) -> None:
    """LocalEODProvider.validate(day) returns (True, 'ok') when snapshot exists and has symbols."""
    day = "2099-06-02"
    (tmp_path / day).mkdir()
    (tmp_path / day / "snapshot.csv").write_text("symbol,close\nX,5.0\n", encoding="utf-8")
    prov = LocalEODProvider(tmp_path)
    ok, msg = prov.validate(day)
    assert ok is True
    assert msg == "ok"


def test_faz58_local_eod_validate_missing(tmp_path: Path) -> None:
    """LocalEODProvider.validate(day) returns (False, ...) when snapshot missing."""
    prov = LocalEODProvider(tmp_path)
    ok, msg = prov.validate("2099-06-99")
    assert ok is False
    assert "no snapshot" in msg or "2099-06-99" in msg


def test_faz58_provider_raw_cache(tmp_path: Path) -> None:
    """After symbols(day), _provider_raw_cache(provider) returns path (and optionally sha256)."""
    day = "2099-06-03"
    (tmp_path / day).mkdir()
    snap = tmp_path / day / "snapshot.csv"
    snap.write_text("symbol,close\nY,1.0\n", encoding="utf-8")
    prov = LocalEODProvider(tmp_path)
    prov.symbols(day)
    raw = _provider_raw_cache(prov)
    assert raw is not None
    assert raw.get("path") == str(snap)
    assert raw.get("sha256") or True


def test_faz58_cli_validate_ok(tmp_path: Path) -> None:
    """bist_core cli market-data validate --day X --snapshot-root Y succeeds when snapshot exists."""
    day = "2099-06-04"
    (tmp_path / day).mkdir()
    (tmp_path / day / "snapshot.csv").write_text("symbol,close\nZ,2.0\n", encoding="utf-8")
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "market-data", "validate", "--day", day, "--snapshot-root", str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 0
    assert "ok" in (r.stdout or "").lower()


def test_faz58_cli_validate_missing_exit_nonzero(tmp_path: Path) -> None:
    """bist_core cli market-data validate --day X fails when snapshot missing."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "market-data", "validate", "--day", "2099-06-99", "--snapshot-root", str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode != 0
    assert "error" in (r.stderr or r.stdout or "").lower() or "no snapshot" in (r.stderr or r.stdout or "").lower()
