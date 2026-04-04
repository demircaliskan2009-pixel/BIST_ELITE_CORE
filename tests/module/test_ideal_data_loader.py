"""ideal_data_loader delimiter rules."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bist_core.data.ideal_data_loader import load_ideal_bars, split_ideal_line


def test_semicolon_delimited() -> None:
    assert split_ideal_line("a;b;c") == ["a", "b", "c"]


def test_comma_delimited() -> None:
    assert split_ideal_line("a,b,c") == ["a", "b", "c"]


def test_whitespace_delimited() -> None:
    assert split_ideal_line("a b  c") == ["a", "b", "c"]


def test_semicolon_takes_precedence_over_comma() -> None:
    assert split_ideal_line("a;b,c") == ["a", "b,c"]


def test_load_ideal_bars_no_01_file_returns_empty(tmp_path: Path) -> None:
    """No ``.01`` file at env root → []."""
    old = os.environ.get("IDEAL_DATA_PATH")
    try:
        os.environ["IDEAL_DATA_PATH"] = str(tmp_path / "nonexistent_subdir")
        assert load_ideal_bars("ZZZ") == []
    finally:
        if old is None:
            os.environ.pop("IDEAL_DATA_PATH", None)
        else:
            os.environ["IDEAL_DATA_PATH"] = old


def test_load_ideal_bars_reads_01_binary_chunks(tmp_path: Path) -> None:
    """Minimal ``.01`` binary produces OHLCV bars via fixed-step scan."""
    f = tmp_path / "IMKBH'ZZZ.01"
    f.write_bytes(b"\x01\x00\x00\x00" * 40)
    old = os.environ.get("IDEAL_DATA_PATH")
    try:
        os.environ["IDEAL_DATA_PATH"] = str(tmp_path)
        bars = load_ideal_bars("ZZZ")
    finally:
        if old is None:
            os.environ.pop("IDEAL_DATA_PATH", None)
        else:
            os.environ["IDEAL_DATA_PATH"] = old

    assert len(bars) >= 1
    assert bars[0].symbol == "ZZZ"
    assert bars[0].close == pytest.approx(0.01)
    assert bars[0].open == pytest.approx(0.01)
    assert bars[0].high == pytest.approx(0.01)
    assert bars[0].low == pytest.approx(0.01)
    assert bars[0].volume == 1000.0
