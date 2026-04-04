"""Tests for deterministic OHLCV CSV ingest."""

from __future__ import annotations

from pathlib import Path

import pytest

from bist_core.data.ingest import InvalidDataError, ingest_ohlcv_from_file


def _write_valid_ohlcv(tmp_path: Path) -> Path:
    """Write a valid OHLCV CSV fixture."""
    p = tmp_path / "sample.csv"
    p.write_text(
        "timestamp,open,high,low,close,volume\n"
        "1704067200,100.0,101.0,99.0,100.5,1000\n"
        "1704153600,100.5,102.0,100.0,101.0,1500\n"
        "1704240000,101.0,103.0,100.5,102.0,2000\n",
        encoding="utf-8",
    )
    return p


def test_determinism(tmp_path: Path) -> None:
    """Call ingest_ohlcv_from_file twice on same fixture -> identical output."""
    path = _write_valid_ohlcv(tmp_path)
    a = ingest_ohlcv_from_file(str(path))
    b = ingest_ohlcv_from_file(str(path))
    assert len(a) == len(b) == 3
    for i, (bar_a, bar_b) in enumerate(zip(a, b)):
        assert bar_a.timestamp == bar_b.timestamp
        assert bar_a.open == bar_b.open
        assert bar_a.high == bar_b.high
        assert bar_a.low == bar_b.low
        assert bar_a.close == bar_b.close
        assert bar_a.volume == bar_b.volume


def test_invalid_input(tmp_path: Path) -> None:
    """Malformed CSV -> InvalidDataError."""
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "timestamp,open,high,low\n"
        "1704067200,100,101,99\n",
        encoding="utf-8",
    )
    with pytest.raises(InvalidDataError) as exc_info:
        ingest_ohlcv_from_file(str(bad))
    assert "missing required columns" in str(exc_info.value)


def test_edge_case_non_contiguous_timestamps(tmp_path: Path) -> None:
    """Non-contiguous / non-increasing timestamps -> InvalidDataError."""
    p = tmp_path / "edge.csv"
    p.write_text(
        "timestamp,open,high,low,close,volume\n"
        "1704067200,100.0,101.0,99.0,100.5,1000\n"
        "1704153600,100.5,102.0,100.0,101.0,1500\n"
        "1704067200,101.0,103.0,100.5,102.0,2000\n",
        encoding="utf-8",
    )
    with pytest.raises(InvalidDataError) as exc_info:
        ingest_ohlcv_from_file(str(p))
    assert "strictly increasing" in str(exc_info.value)


def test_empty_file(tmp_path: Path) -> None:
    """Empty CSV -> InvalidDataError."""
    p = tmp_path / "empty.csv"
    p.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
    with pytest.raises(InvalidDataError) as exc_info:
        ingest_ohlcv_from_file(str(p))
    assert "empty" in str(exc_info.value).lower()


def test_invalid_numeric(tmp_path: Path) -> None:
    """Invalid numeric values -> InvalidDataError."""
    p = tmp_path / "bad_numeric.csv"
    p.write_text(
        "timestamp,open,high,low,close,volume\n"
        "1704067200,100.0,101.0,99.0,100.5,1000\n"
        "1704153600,abc,102.0,100.0,101.0,1500\n",
        encoding="utf-8",
    )
    with pytest.raises(InvalidDataError) as exc_info:
        ingest_ohlcv_from_file(str(p))
    assert "invalid" in str(exc_info.value).lower()


def test_negative_price_raises(tmp_path: Path) -> None:
    """Negative price -> InvalidDataError."""
    p = tmp_path / "neg.csv"
    p.write_text(
        "timestamp,open,high,low,close,volume\n"
        "1704067200,-100.0,101.0,99.0,100.5,1000\n",
        encoding="utf-8",
    )
    with pytest.raises(InvalidDataError) as exc_info:
        ingest_ohlcv_from_file(str(p))
    assert "prices must be > 0" in str(exc_info.value)


def test_negative_volume_raises(tmp_path: Path) -> None:
    """Negative volume -> InvalidDataError."""
    p = tmp_path / "neg_vol.csv"
    p.write_text(
        "timestamp,open,high,low,close,volume\n"
        "1704067200,100.0,101.0,99.0,100.5,-100\n",
        encoding="utf-8",
    )
    with pytest.raises(InvalidDataError) as exc_info:
        ingest_ohlcv_from_file(str(p))
    assert "volume" in str(exc_info.value).lower()


def test_file_not_found_raises() -> None:
    """Non-existent file -> InvalidDataError."""
    with pytest.raises(InvalidDataError) as exc_info:
        ingest_ohlcv_from_file("/nonexistent/path/ohlcv.csv")
    assert "not found" in str(exc_info.value).lower()


def test_sorted_ascending_by_timestamp(tmp_path: Path) -> None:
    """Output is sorted ascending by timestamp even if CSV is unsorted."""
    p = tmp_path / "unsorted.csv"
    p.write_text(
        "timestamp,open,high,low,close,volume\n"
        "1704240000,101.0,103.0,100.5,102.0,2000\n"
        "1704067200,100.0,101.0,99.0,100.5,1000\n"
        "1704153600,100.5,102.0,100.0,101.0,1500\n",
        encoding="utf-8",
    )
    bars = ingest_ohlcv_from_file(str(p))
    assert [b.timestamp for b in bars] == ["1704067200", "1704153600", "1704240000"]
