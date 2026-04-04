"""Tests for iDeal dataset loader."""

from __future__ import annotations

from pathlib import Path
from struct import Struct

import pytest

from bist_core.data.loader import load_ideal_dataset
from bist_core.models.ohlcv import OHLCVBar


REC = Struct("<I7f")


def _pack_bar(date_code: int, o: float, h: float, l: float, c: float, v: float, t: float = 1000.0, r: float = 0.0) -> bytes:
    return REC.pack(date_code, float(o), float(h), float(l), float(c), float(v), float(t), float(r))


def test_load_valid_dataset(tmp_path: Path) -> None:
    """Load valid .G files returns bars."""
    g_dir = tmp_path / "G"
    g_dir.mkdir()
    (g_dir / "IMKBH'ASELS.G").write_bytes(
        b"".join([
            _pack_bar(1704067200, 98, 99, 97, 98.5, 1000),
            _pack_bar(1704153600, 98.5, 100, 98, 99.5, 1100),
            _pack_bar(1704240000, 99.5, 101, 99, 100.5, 1200),
            _pack_bar(1704326400, 100.5, 102, 100, 101.5, 1300),
        ])
    )
    result = load_ideal_dataset(str(g_dir), ["ASELS"])
    assert "ASELS" in result
    bars = result["ASELS"]
    assert len(bars) == 4
    assert all(isinstance(b, OHLCVBar) for b in bars)
    assert bars[0].close == 98.5
    assert bars[-1].close == 101.5


def test_missing_file_skipped(tmp_path: Path) -> None:
    """Missing files are skipped."""
    g_dir = tmp_path / "G"
    g_dir.mkdir()
    (g_dir / "IMKBH'ASELS.G").write_bytes(
        b"".join([
            _pack_bar(1704067200, 98, 99, 97, 98.5, 1000),
            _pack_bar(1704153600, 98.5, 100, 98, 99.5, 1100),
        ])
    )
    result = load_ideal_dataset(str(g_dir), ["ASELS", "MISSING"])
    assert "ASELS" in result
    assert "MISSING" not in result


def test_determinism(tmp_path: Path) -> None:
    """Same input produces same output."""
    g_dir = tmp_path / "G"
    g_dir.mkdir()
    (g_dir / "IMKBH'GARAN.G").write_bytes(
        b"".join([
            _pack_bar(1704067200, 100, 101, 99, 100.5, 5000),
            _pack_bar(1704153600, 100.5, 102, 100, 101.5, 6000),
            _pack_bar(1704240000, 101.5, 103, 101, 102.5, 7000),
        ])
    )
    a = load_ideal_dataset(str(g_dir), ["GARAN"])
    b = load_ideal_dataset(str(g_dir), ["GARAN"])
    assert a["GARAN"] == b["GARAN"]
