"""Deterministic OHLCV CSV ingest — stdlib only, no pandas.

Reads CSV with required columns: timestamp, open, high, low, close, volume.
Converts to list[OHLCVBar]. Fail-closed on any validation issue.

Also re-exports read_csv, register_dataset, load_registered_dataset from local_csv.
"""

from __future__ import annotations

import csv
from pathlib import Path

from bist_core.backtest.backtest_engine import OHLCVBar

from .local_csv import (
    load_registered_dataset,
    read_csv,
    register_dataset,
)


REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


class InvalidDataError(Exception):
    """Raised when CSV data fails validation (schema, values, or ordering)."""

    pass


def _parse_timestamp(s: str) -> int:
    """Parse timestamp string to int (Unix epoch)."""
    v = str(s).strip().replace(",", ".")
    if not v:
        raise InvalidDataError("empty timestamp")
    try:
        f = float(v)
        i = int(f)
        if i != f and abs(f - i) > 1e-9:
            raise InvalidDataError("timestamp must be integer")
        return i
    except (ValueError, OverflowError) as e:
        raise InvalidDataError(f"invalid timestamp: {s!r}") from e


def _parse_float(s: str, name: str) -> float:
    """Parse string to float."""
    v = str(s).strip().replace(",", ".")
    if v == "":
        raise InvalidDataError(f"empty {name}")
    try:
        return float(v)
    except ValueError as e:
        raise InvalidDataError(f"invalid {name}: {s!r}") from e


def ingest_ohlcv_from_file(path: str) -> list[OHLCVBar]:
    """Read OHLCV CSV and return sorted list of OHLCVBar.

    Requirements:
    - Required columns: timestamp, open, high, low, close, volume
    - timestamp -> int (Unix epoch)
    - open, high, low, close, volume -> float
    - Non-empty
    - Strictly increasing timestamps
    - All prices > 0
    - volume >= 0

    Raises InvalidDataError on any issue.
    """
    p = Path(path)
    if not p.exists():
        raise InvalidDataError(f"file not found: {path}")

    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise InvalidDataError("CSV has no header")

        cols = [c.strip() for c in reader.fieldnames if c]
        missing = [c for c in REQUIRED_COLUMNS if c not in cols]
        if missing:
            raise InvalidDataError(f"missing required columns: {missing}")

        rows: list[dict[str, str]] = []
        for row in reader:
            rows.append(dict(row))

    if not rows:
        raise InvalidDataError("empty file")

    bars: list[tuple[int, OHLCVBar]] = []
    for i, row in enumerate(rows):
        try:
            ts = _parse_timestamp(row.get("timestamp", ""))
            o = _parse_float(row.get("open", ""), "open")
            h = _parse_float(row.get("high", ""), "high")
            lo = _parse_float(row.get("low", ""), "low")
            c = _parse_float(row.get("close", ""), "close")
            v = _parse_float(row.get("volume", ""), "volume")
        except InvalidDataError:
            raise
        except Exception as e:
            raise InvalidDataError(f"row {i + 2}: {e}") from e

        if o <= 0 or h <= 0 or lo <= 0 or c <= 0:
            raise InvalidDataError(f"row {i + 2}: all prices must be > 0")
        if v < 0:
            raise InvalidDataError(f"row {i + 2}: volume must be >= 0")

        bar = OHLCVBar(
            timestamp=str(ts),
            symbol="",
            open=o,
            high=h,
            low=lo,
            close=c,
            volume=v,
        )
        bars.append((ts, bar))

    bars.sort(key=lambda x: x[0])

    for i in range(1, len(bars)):
        if bars[i][0] <= bars[i - 1][0]:
            raise InvalidDataError(
                f"timestamps must be strictly increasing: {bars[i - 1][0]} then {bars[i][0]}"
            )

    return [b for _, b in bars]


__all__ = [
    "InvalidDataError",
    "ingest_ohlcv_from_file",
    "load_registered_dataset",
    "read_csv",
    "register_dataset",
]
