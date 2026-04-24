"""Matriks vendor data adapter — PRD §7 data layer.

Converts Matriks bar responses to the internal OHLCVBar format used by
BacktestEngine.  Handles symbol normalization, validation of malformed
bars, deterministic ordering, and batch conversion.
Pure stdlib, no network.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

from bist_core.backtest.backtest_engine import OHLCVBar

# ---------------------------------------------------------------------------
# Symbol normalization
# ---------------------------------------------------------------------------

_VENDOR_SUFFIX_STRIP = (".E", ".IS", ".TI", ".BIST")


def normalize_symbol(raw: str) -> str:
    """Normalize vendor symbol to internal BIST format (uppercase, stripped suffixes)."""
    token = str(raw or "").strip().upper()
    for suffix in _VENDOR_SUFFIX_STRIP:
        if token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    return token.strip()


# ---------------------------------------------------------------------------
# Single bar conversion
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_timestamp(raw: Dict[str, Any]) -> str | None:
    date_part = str(raw.get("date") or "").strip()
    if not date_part:
        ts = str(raw.get("timestamp") or raw.get("ts") or "").strip()
        return ts if ts else None
    time_part = raw.get("time")
    if time_part is not None:
        return f"{date_part}T{time_part}"
    return date_part


def convert_bar(
    raw: Dict[str, Any],
    *,
    default_symbol: str = "",
    reject_zero_volume: bool = False,
) -> OHLCVBar | None:
    """Convert a single Matriks bar dict to OHLCVBar. Returns None for invalid bars."""
    symbol = normalize_symbol(
        raw.get("symbol") or raw.get("ticker") or default_symbol
    )
    if not symbol:
        return None

    timestamp = _build_timestamp(raw)
    if not timestamp:
        return None

    o = _safe_float(raw.get("open") or raw.get("o"))
    h = _safe_float(raw.get("high") or raw.get("h"))
    lo = _safe_float(raw.get("low") or raw.get("l"))
    c = _safe_float(raw.get("close") or raw.get("c"))
    v = _safe_float(raw.get("volume") or raw.get("vol") or raw.get("v"))

    if o is None or h is None or lo is None or c is None:
        return None
    if o < 0 or h < 0 or lo < 0 or c < 0:
        return None
    if v is None:
        v = 0.0
    if v < 0:
        return None
    if reject_zero_volume and v == 0:
        return None

    return OHLCVBar(
        timestamp=timestamp,
        symbol=symbol,
        open=round(o, 6),
        high=round(h, 6),
        low=round(lo, 6),
        close=round(c, 6),
        volume=round(v, 6),
    )


# ---------------------------------------------------------------------------
# Batch conversion
# ---------------------------------------------------------------------------

def convert_bars(
    raw_bars: Sequence[Dict[str, Any]],
    *,
    default_symbol: str = "",
    reject_zero_volume: bool = False,
) -> list[OHLCVBar]:
    """Convert a list of Matriks bar dicts to sorted OHLCVBar list. Invalid bars are skipped."""
    bars: list[OHLCVBar] = []
    for raw in raw_bars:
        if not isinstance(raw, dict):
            continue
        bar = convert_bar(raw, default_symbol=default_symbol, reject_zero_volume=reject_zero_volume)
        if bar is not None:
            bars.append(bar)
    bars.sort(key=lambda b: (b.timestamp, b.symbol))
    return bars


# ---------------------------------------------------------------------------
# Integration helper
# ---------------------------------------------------------------------------

def prepare_bars_for_backtest(
    raw_bars: Sequence[Dict[str, Any]],
    *,
    symbol: str = "",
    reject_zero_volume: bool = False,
) -> list[OHLCVBar]:
    """Convert vendor bars and prepare for BacktestEngine.run(). Deterministic sort by (timestamp, symbol)."""
    return convert_bars(
        raw_bars,
        default_symbol=symbol,
        reject_zero_volume=reject_zero_volume,
    )
