"""Data loader — load iDeal dataset to OHLCVBar."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from bist_core.models.ohlcv import OHLCVBar

from bist_core.data.ingest import InvalidDataError, ingest_ohlcv_from_file
from bist_core.vendors.ideal_g32 import parse_g32_file


def _g_to_csv(path: Path, out_csv: Path) -> None:
    """Export .G file to ingest-compatible CSV (timestamp, open, high, low, close, volume)."""
    parsed = parse_g32_file(path, strict=False)
    rows = parsed.get("rows", [])
    if not rows:
        raise InvalidDataError("no valid rows")

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        w.writeheader()
        for r in rows:
            w.writerow({
                "timestamp": str(r["raw_date_code"]),
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
                "volume": r["volume"],
            })


def load_ideal_dataset(base_path: str, symbols: list[str]) -> dict[str, list[OHLCVBar]]:
    """Load iDeal .G dataset. Path: base_path/IMKBH'{symbol}.G
    Skip missing files (fail-closed: log and continue).
    """
    base = Path(base_path)
    result: dict[str, list[OHLCVBar]] = {}
    for symbol in sorted(symbols):
        path = base / f"IMKBH'{symbol}.G"
        if not path.exists():
            continue
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
                tmp = Path(f.name)
            try:
                _g_to_csv(path, tmp)
                raw_bars = ingest_ohlcv_from_file(str(tmp))
                bars = [
                    OHLCVBar(timestamp=b.timestamp, symbol=symbol, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume)
                    for b in raw_bars
                ]
                result[symbol] = bars
            finally:
                tmp.unlink(missing_ok=True)
        except (InvalidDataError, ValueError, OSError):
            continue
    return result
