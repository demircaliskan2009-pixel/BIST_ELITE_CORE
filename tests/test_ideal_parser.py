"""iDeal 32-byte binary parser — structure-locked, fail-closed."""

from __future__ import annotations

import math
import struct
import time
from pathlib import Path

import pytest

from bist_core.data.ideal_binary_parser import (
    IDEAL_RECORD_DTYPE,
    OHLCVRecord,
    decode_ideal_binary_bytes,
    normalize_timestamp,
    parse_ideal_binary,
    parse_ideal_binary_bytes,
    validate_records,
)


def _pack(
    ts: int,
    o: float,
    h: float,
    l: float,
    c: float,
    v: float,
    extra: float = 0.0,
    flag: int = 0,
) -> bytes:
    return struct.pack("<iffffffi", ts, o, h, l, c, v, extra, flag)


def test_parse_valid_file(tmp_path: Path) -> None:
    buf = bytearray()
    for i in range(50):
        ts = 1_000_000_000 + i * 60
        c = 1.5 + i * 0.001
        buf.extend(_pack(ts, c - 0.01, c + 0.01, c - 0.02, c, 1000.0 + i))
    p = tmp_path / "IMKBH'X.01"
    p.write_bytes(bytes(buf))
    recs = parse_ideal_binary(p)
    assert len(recs) == 50
    assert recs[0].timestamp < recs[-1].timestamp


def test_corrupted_length_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.01"
    p.write_bytes(b"\x00" * 31)
    with pytest.raises(ValueError, match="IDEAL_BINARY_ALIGNMENT"):
        parse_ideal_binary(p)


def test_invalid_nan_skipped_ratio_high_raises() -> None:
    buf = bytearray()
    n = 200
    for i in range(n):
        ts = 1_000_000_000 + i
        c = 1.5 + i * 0.0001
        if i < 5:
            buf.extend(
                struct.pack(
                    "<iffffffi",
                    ts,
                    float("nan"),
                    c,
                    c,
                    c,
                    1.0,
                    0.0,
                    0,
                )
            )
        else:
            buf.extend(_pack(ts, c - 0.01, c + 0.01, c - 0.02, c, 1.0))
    with pytest.raises(ValueError, match="IDEAL_BINARY_TOO_MANY_BAD_RECORDS"):
        parse_ideal_binary_bytes(bytes(buf), validate_ohlc=True)


def test_timestamp_ordering_filter() -> None:
    buf = (
        _pack(1_000_000_000, 1.0, 1.1, 0.9, 1.05, 1.0)
        + _pack(1_000_000_000, 1.0, 1.1, 0.9, 1.06, 1.0)
        + _pack(1_000_000_600, 1.0, 1.1, 0.9, 1.07, 1.0)
    )
    recs = parse_ideal_binary_bytes(buf, validate_ohlc=False)
    assert len(recs) == 2
    assert recs[0].timestamp == 1_000_000_000
    assert recs[1].timestamp == 1_000_000_600


def test_validate_records_high_low() -> None:
    recs = [
        OHLCVRecord(
            timestamp=1_000_000_000 + i,
            open=1.0,
            high=0.5,
            low=1.1,
            close=1.0,
            volume=1.0,
            extra=0.0,
            flag=0,
        )
        for i in range(5)
    ]
    with pytest.raises(ValueError, match="IDEAL_RECORDS_VALIDATION_FAILED"):
        validate_records(recs)


def test_normalize_timestamp_invalid() -> None:
    with pytest.raises(ValueError):
        normalize_timestamp(0)
    with pytest.raises(ValueError):
        normalize_timestamp(3_000_000_000)


def test_performance_decode_1m_rows() -> None:
    """NumPy decode path must stay under 200ms for 1M×32-byte rows (vectorized)."""
    import numpy as np

    n = 1_000_000
    ts0 = 1_000_000_000
    arr = np.zeros(n, dtype=IDEAL_RECORD_DTYPE)
    arr["ts"] = np.arange(ts0, ts0 + n, dtype=np.int32)
    i = np.arange(n, dtype=np.float32)
    c = 1.5 + (i % 1000) * np.float32(0.0001)
    arr["o"] = c - 0.01
    arr["h"] = c + 0.01
    arr["l"] = c - 0.02
    arr["c"] = c
    arr["v"] = 1000.0 + i
    buf = arr.tobytes()
    t0 = time.perf_counter()
    g = decode_ideal_binary_bytes(buf)
    elapsed = time.perf_counter() - t0
    assert len(g) == n
    assert elapsed < 0.2, f"decode took {elapsed:.3f}s, expected <200ms for 1M rows"
    assert math.isfinite(float(g["c"][-1]))
