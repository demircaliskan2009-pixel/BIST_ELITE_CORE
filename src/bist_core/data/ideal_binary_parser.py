"""
Deterministic iDeal binary parser — 32-byte records, little-endian (production-locked).

Layout: int32 ts, float32 o,h,l,c,v,extra, int32 flag — struct ``<iffffffi``.
"""

from __future__ import annotations

import json
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Sequence

import numpy as np

RECORD_STRUCT: Final[struct.Struct] = struct.Struct("<iffffffi")
RECORD_SIZE: Final[int] = RECORD_STRUCT.size  # 32

_IDEAL_DTYPE: Final[np.dtype[Any]] = np.dtype(
    [
        ("ts", "<i4"),
        ("o", "<f4"),
        ("h", "<f4"),
        ("l", "<f4"),
        ("c", "<f4"),
        ("v", "<f4"),
        ("extra", "<f4"),
        ("flag", "<i4"),
    ]
)

IDEAL_RECORD_DTYPE = _IDEAL_DTYPE

# Plausible int32 Unix seconds (inclusive). No heuristic conversion — identity mapping.
_TS_MIN: Final[int] = 1
_TS_MAX: Final[int] = 2_147_483_647

_BAD_RECORD_RATIO_MAX: Final[float] = 0.01
_VALIDATE_FAIL_RATIO_MAX: Final[float] = 0.01


@dataclass(frozen=True, slots=True)
class OHLCVRecord:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    extra: float
    flag: int


def normalize_timestamp(ts: int) -> int:
    """
    Validate iDeal time field as Unix seconds (int32 range). Identity mapping — no guessing.

    Raises:
        TypeError: not int
        ValueError: out of int32 / non-positive
    """
    if not isinstance(ts, int):
        raise TypeError(f"IDEAL_TIMESTAMP_TYPE: expected int, got {type(ts).__name__}")
    if ts < _TS_MIN or ts > _TS_MAX:
        raise ValueError(f"IDEAL_TIMESTAMP_OUT_OF_RANGE: {ts}")
    return ts


def _ideal_debug_enabled() -> bool:
    return os.environ.get("BIST_IDEAL_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def _maybe_debug(total: int, invalid: int, first_rows: list[OHLCVRecord]) -> None:
    if not _ideal_debug_enabled():
        return
    print(
        json.dumps(
            {
                "BIST_IDEAL_DEBUG": {
                    "total_records": total,
                    "invalid_or_skipped": invalid,
                    "first_rows": [
                        {
                            "timestamp": r.timestamp,
                            "open": r.open,
                            "high": r.high,
                            "low": r.low,
                            "close": r.close,
                            "volume": r.volume,
                            "extra": r.extra,
                            "flag": r.flag,
                        }
                        for r in first_rows[:3]
                    ],
                }
            },
            sort_keys=True,
        ),
        flush=True,
    )


def decode_ideal_binary_bytes(data: bytes) -> np.ndarray:
    """
    Fast path: return filtered structured numpy array (same dtype as on-disk layout).

    No Python OHLCVRecord objects — used by live feed for throughput.
    Raises on alignment / bad-record ratio (same rules as parse_ideal_binary_bytes).
    """
    if len(data) % RECORD_SIZE != 0:
        raise ValueError(
            f"IDEAL_BINARY_ALIGNMENT: len={len(data)} not divisible by {RECORD_SIZE}"
        )
    total_slots = len(data) // RECORD_SIZE
    if total_slots == 0:
        return np.array([], dtype=_IDEAL_DTYPE)

    mv = memoryview(data)
    arr = np.frombuffer(mv, dtype=_IDEAL_DTYPE, count=total_slots)

    o = arr["o"]
    h = arr["h"]
    l = arr["l"]
    c = arr["c"]
    v = arr["v"]
    ex = arr["extra"]
    finite = (
        np.isfinite(o)
        & np.isfinite(h)
        & np.isfinite(l)
        & np.isfinite(c)
        & np.isfinite(v)
        & np.isfinite(ex)
    )
    bad = int(total_slots - int(finite.sum()))
    if total_slots > 0 and (bad / float(total_slots)) > _BAD_RECORD_RATIO_MAX:
        raise ValueError(
            f"IDEAL_BINARY_TOO_MANY_BAD_RECORDS: bad={bad} total_slots={total_slots} "
            f"ratio={bad / float(total_slots):.6f}"
        )

    good = arr[finite]
    ts = good["ts"].astype(np.int64)
    rng = (ts >= _TS_MIN) & (ts <= _TS_MAX)
    good = good[rng]
    ts = good["ts"].astype(np.int64)
    mono = _strictly_increasing_ts_mask(ts)
    return good[mono]


def _strictly_increasing_ts_mask(ts: np.ndarray) -> np.ndarray:
    """
    Keep rows with strictly increasing timestamps in file order.

    If timestamps are non-decreasing (typical iDeal chronological file), use O(n)
    vectorized diff. Otherwise fall back to sequential scan (rare).
    """
    n = int(ts.shape[0])
    if n == 0:
        return np.zeros(0, dtype=bool)
    if n > 1 and bool(np.any(ts[1:] < ts[:-1])):
        out = np.zeros(n, dtype=bool)
        last = -1
        for i in range(n):
            t = int(ts[i])
            if t > last:
                out[i] = True
                last = t
        return out
    return np.concatenate(([True], ts[1:] > ts[:-1]))


def _good_numpy_to_records(good: np.ndarray) -> list[OHLCVRecord]:
    if len(good) == 0:
        return []
    ts_a = good["ts"].astype(np.int64)
    o_a = good["o"].astype(np.float64)
    h_a = good["h"].astype(np.float64)
    l_a = good["l"].astype(np.float64)
    c_a = good["c"].astype(np.float64)
    v_a = good["v"].astype(np.float64)
    ex_a = good["extra"].astype(np.float64)
    fl_a = good["flag"].astype(np.int64)
    m = int(ts_a.shape[0])
    return [
        OHLCVRecord(
            timestamp=int(ts_a[i]),
            open=float(o_a[i]),
            high=float(h_a[i]),
            low=float(l_a[i]),
            close=float(c_a[i]),
            volume=float(v_a[i]),
            extra=float(ex_a[i]),
            flag=int(fl_a[i]),
        )
        for i in range(m)
    ]


def validate_numpy_ohlc_or_raise(good: np.ndarray) -> dict[str, Any]:
    """Vectorized OHLC/volume checks; raises if invalid_ratio > 1%."""
    if len(good) == 0:
        return {"valid": True, "total": 0, "invalid": 0, "invalid_ratio": 0.0}
    o = good["o"].astype(np.float64)
    h = good["h"].astype(np.float64)
    l_ = good["l"].astype(np.float64)
    c = good["c"].astype(np.float64)
    v = good["v"].astype(np.float64)
    bad = (
        (o <= 0.0)
        | (h <= 0.0)
        | (l_ <= 0.0)
        | (c <= 0.0)
        | (h < l_)
        | (v < 0.0)
    )
    invalid = int(np.sum(bad))
    total = int(len(good))
    invalid_ratio = invalid / float(total) if total else 0.0
    if invalid_ratio > _VALIDATE_FAIL_RATIO_MAX:
        raise ValueError(
            f"IDEAL_RECORDS_VALIDATION_FAILED: invalid_ratio={invalid_ratio:.6f} "
            f"invalid={invalid} total={total}"
        )
    return {
        "valid": True,
        "total": total,
        "invalid": invalid,
        "invalid_ratio": round(invalid_ratio, 8),
    }


def parse_ideal_binary_bytes(
    data: bytes,
    *,
    validate_ohlc: bool = True,
) -> list[OHLCVRecord]:
    """
    Parse raw bytes into OHLCVRecord list. Fail-closed if len(data) % 32 != 0.

    Skips records with NaN/inf in any float field; if bad/total > 1%, raises.
    Applies normalize_timestamp (skip on ValueError) and strict monotonic timestamp filter.

    Uses NumPy ``frombuffer`` + vectorized finite checks; monotonic filter is O(n).
    """
    total_slots = len(data) // RECORD_SIZE if data else 0
    good = decode_ideal_binary_bytes(data)
    if validate_ohlc:
        validate_numpy_ohlc_or_raise(good)
    raw = _good_numpy_to_records(good)

    dropped = max(0, total_slots - len(raw))
    _maybe_debug(total_slots, dropped, raw)

    return raw


def parse_ideal_binary(path: str | Path) -> list[OHLCVRecord]:
    """Read file as bytes; fail if empty or misaligned."""
    p = Path(path)
    data = p.read_bytes()
    if len(data) == 0:
        raise ValueError(f"IDEAL_BINARY_EMPTY_FILE: {p}")
    return parse_ideal_binary_bytes(data, validate_ohlc=True)


def validate_records(records: Sequence[OHLCVRecord]) -> dict[str, Any]:
    """
    OHLC/volume plausibility + strictly increasing timestamps.

    Raises:
        ValueError: if invalid_ratio > 1%
    """
    if not records:
        return {
            "valid": True,
            "total": 0,
            "invalid": 0,
            "invalid_ratio": 0.0,
        }

    invalid = 0
    for r in records:
        ok = True
        if not (
            r.open > 0.0
            and r.high > 0.0
            and r.low > 0.0
            and r.close > 0.0
        ):
            ok = False
        elif r.high < r.low:
            ok = False
        elif r.volume < 0.0:
            ok = False
        if not ok:
            invalid += 1

    total = len(records)
    invalid_ratio = invalid / float(total) if total else 0.0
    result = {
        "valid": invalid_ratio <= _VALIDATE_FAIL_RATIO_MAX,
        "total": total,
        "invalid": invalid,
        "invalid_ratio": round(invalid_ratio, 8),
    }
    if invalid_ratio > _VALIDATE_FAIL_RATIO_MAX:
        raise ValueError(
            f"IDEAL_RECORDS_VALIDATION_FAILED: invalid_ratio={invalid_ratio:.6f} "
            f"invalid={invalid} total={total}"
        )
    return result


def emit_parser_ready_report(records_loaded: int, invalid_ratio: float) -> None:
    """Structured status + final line (call after successful full load)."""
    print(
        json.dumps(
            {
                "IDEAL_PARSER": "READY",
                "records_loaded": int(records_loaded),
                "invalid_ratio": float(invalid_ratio),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    print("IDEAL BINARY PARSER ACTIVE — DATA PIPELINE UNLOCKED", flush=True)


__all__ = [
    "IDEAL_RECORD_DTYPE",
    "OHLCVRecord",
    "RECORD_SIZE",
    "RECORD_STRUCT",
    "decode_ideal_binary_bytes",
    "emit_parser_ready_report",
    "normalize_timestamp",
    "parse_ideal_binary",
    "parse_ideal_binary_bytes",
    "validate_numpy_ohlc_or_raise",
    "validate_records",
]
