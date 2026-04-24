"""iDeal multi-timeframe binary loader — production-grade, deterministic.

Loads .G (daily), .60 (hourly), .05 (5-min), .01 (1-min) from iDeal ChartData
using the verified epoch (1987-05-30 00:00 TRT) and per-timeframe unit mapping.

Binary layout: 32-byte records, struct ``<iffffffi``
  (int32 ts, float32 O, H, L, C, Volume, Turnover, int32 Flag)

Usage:
    loader = IdealIntradayLoader(chart_root=Path(r"C:\\iDeal\\ChartData\\IMKBH"))
    bundle = loader.load_symbol("AKBNK", timeframes=["G", "60", "05", "01"])
    bars_60 = bundle["60"]  # list[OHLCVBar] with correct unix timestamps
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Sequence

import numpy as np

from bist_core.data.ideal_timestamp_codec import (
    DAILY_EPOCH_UNIX,
    INTRADAY_EPOCH_UNIX,
)
from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RECORD_STRUCT: Final[struct.Struct] = struct.Struct("<iffffffi")
_RECORD_SIZE: Final[int] = _RECORD_STRUCT.size  # 32

_NUMPY_DTYPE: Final[np.dtype] = np.dtype(
    [
        ("ts", "<i4"),
        ("o", "<f4"),
        ("h", "<f4"),
        ("l", "<f4"),
        ("c", "<f4"),
        ("v", "<f4"),
        ("turnover", "<f4"),
        ("flag", "<i4"),
    ]
)

# Timeframe → per-unit seconds for timestamp conversion
_TF_SECONDS: Final[dict[str, int]] = {
    "01": 60,
    "05": 60,      # same unit as .01 (minutes), bars increment by 5
    "60": 3600,
    "G": 86400,
}

# Default iDeal chart root
_DEFAULT_CHART_ROOT: Final[str] = r"C:\iDeal\ChartData\IMKBH"

# Maximum bad-record ratio before fail-closed
_MAX_BAD_RATIO: Final[float] = 0.02

# OHLCV sanity bounds (BIST stocks can have very low pre-split prices)
_MIN_PRICE: Final[float] = 0.001
_MAX_PRICE: Final[float] = 100_000.0


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class IntradayBar:
    """Raw parsed bar with original and decoded timestamps."""
    raw_ts: int
    unix_ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float


SymbolBundle = dict[str, list[OHLCVBar]]


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _resolve_chart_root() -> Path:
    """Resolve iDeal chart root from env or default."""
    root = os.environ.get("BIST_IDEAL_CHART_ROOT", "").strip()
    if root:
        return Path(root)
    return Path(_DEFAULT_CHART_ROOT)


def resolve_ideal_path(
    symbol: str,
    timeframe: str,
    chart_root: Path | None = None,
) -> Path:
    """Build path: ``<root>/<tf>/IMKBH'<SYMBOL>.<tf>``."""
    root = chart_root or _resolve_chart_root()
    sym = symbol.strip().upper()
    tf = timeframe.strip().lstrip(".").upper()
    return root / tf / f"IMKBH'{sym}.{tf}"


# ---------------------------------------------------------------------------
# Core parsing (numpy vectorized)
# ---------------------------------------------------------------------------

def parse_ideal_binary(
    data: bytes,
    timeframe: str,
    symbol: str = "",
) -> list[OHLCVBar]:
    """
    Parse raw bytes into OHLCVBar list with correct unix timestamps.

    Fail-closed: raises on alignment error or excessive bad records.
    Deterministic: no randomness, no heuristics.
    """
    tf = timeframe.strip().lstrip(".").upper()

    if len(data) % _RECORD_SIZE != 0:
        raise ValueError(
            f"IDEAL_BINARY_ALIGNMENT: len={len(data)} "
            f"not divisible by {_RECORD_SIZE}"
        )

    total = len(data) // _RECORD_SIZE
    if total == 0:
        return []

    # Fast numpy decode
    arr = np.frombuffer(data, dtype=_NUMPY_DTYPE, count=total)

    # Filter: finite OHLCV
    o, h, l, c, v = arr["o"], arr["h"], arr["l"], arr["c"], arr["v"]
    finite = (
        np.isfinite(o) & np.isfinite(h) & np.isfinite(l)
        & np.isfinite(c) & np.isfinite(v)
    )

    # Filter: positive prices, h >= l
    valid_ohlc = (
        (o > _MIN_PRICE) & (h > _MIN_PRICE) & (l > _MIN_PRICE) & (c > _MIN_PRICE)
        & (o < _MAX_PRICE) & (h < _MAX_PRICE) & (l < _MAX_PRICE) & (c < _MAX_PRICE)
        & (h >= l) & (v >= 0)
    )

    mask = finite & valid_ohlc
    bad_count = int(total - int(mask.sum()))

    # For daily (.G) files, early records often have zero OHLC (pre-electronic era).
    # Only enforce strict bad-ratio for intraday data where all records should be valid.
    if tf != "G" and total > 0 and bad_count / total > _MAX_BAD_RATIO:
        raise ValueError(
            f"IDEAL_BINARY_TOO_MANY_BAD: bad={bad_count} total={total} "
            f"ratio={bad_count/total:.4f}"
        )

    good = arr[mask]
    if len(good) == 0:
        return []

    # Convert timestamps
    raw_ts = good["ts"].astype(np.int64)

    if tf == "G":
        epoch = DAILY_EPOCH_UNIX
        unit_sec = 86400
    else:
        epoch = INTRADAY_EPOCH_UNIX
        unit_sec = _TF_SECONDS.get(tf, 60)

    unix_ts = epoch + raw_ts * unit_sec

    # Sanity filter: 1986–2035
    ts_valid = (unix_ts >= 504_921_600) & (unix_ts <= 2_051_222_400)
    good = good[ts_valid]
    unix_ts = unix_ts[ts_valid]

    if len(good) == 0:
        return []

    # Strictly increasing timestamps (deduplicate)
    if len(unix_ts) > 1:
        mono = np.concatenate(([True], unix_ts[1:] > unix_ts[:-1]))
        good = good[mono]
        unix_ts = unix_ts[mono]

    # Build OHLCVBar list
    sym = symbol.strip().upper()
    bars: list[OHLCVBar] = []
    g_o = good["o"].astype(np.float64)
    g_h = good["h"].astype(np.float64)
    g_l = good["l"].astype(np.float64)
    g_c = good["c"].astype(np.float64)
    g_v = good["v"].astype(np.float64)

    for i in range(len(good)):
        bars.append(
            OHLCVBar(
                timestamp=int(unix_ts[i]),
                symbol=sym,
                open=float(g_o[i]),
                high=float(g_h[i]),
                low=float(g_l[i]),
                close=float(g_c[i]),
                volume=float(g_v[i]),
            )
        )

    return bars


def load_ideal_file(
    symbol: str,
    timeframe: str,
    chart_root: Path | None = None,
) -> list[OHLCVBar]:
    """
    Load and parse a single iDeal binary file.

    Returns empty list if file not found (fail-closed for other errors).
    """
    path = resolve_ideal_path(symbol, timeframe, chart_root)
    if not path.is_file():
        return []
    data = path.read_bytes()
    if not data:
        return []
    return parse_ideal_binary(data, timeframe, symbol)


# ---------------------------------------------------------------------------
# Multi-timeframe loader
# ---------------------------------------------------------------------------

class IdealIntradayLoader:
    """Load multi-timeframe iDeal data for one or more symbols."""

    def __init__(self, chart_root: Path | str | None = None) -> None:
        if chart_root is not None:
            self._root = Path(chart_root)
        else:
            self._root = _resolve_chart_root()

    def load_symbol(
        self,
        symbol: str,
        timeframes: Sequence[str] = ("G", "60", "05", "01"),
    ) -> SymbolBundle:
        """
        Load all requested timeframes for a symbol.

        Returns dict mapping timeframe → list[OHLCVBar].
        Missing files produce empty lists (fail-closed for corrupt data).
        """
        bundle: SymbolBundle = {}
        for tf in timeframes:
            tf_key = tf.strip().lstrip(".").upper()
            bars = load_ideal_file(symbol, tf_key, self._root)
            bundle[tf_key] = bars
        return bundle

    def load_universe(
        self,
        symbols: Sequence[str],
        timeframes: Sequence[str] = ("G", "60", "05", "01"),
    ) -> dict[str, SymbolBundle]:
        """Load all timeframes for all symbols in the universe."""
        universe: dict[str, SymbolBundle] = {}
        for sym in symbols:
            sym_key = sym.strip().upper()
            universe[sym_key] = self.load_symbol(sym_key, timeframes)
        return universe

    def available_symbols(self, timeframe: str = "G") -> list[str]:
        """List symbols available for a given timeframe."""
        tf = timeframe.strip().lstrip(".").upper()
        tf_dir = self._root / tf
        if not tf_dir.is_dir():
            return []
        symbols = []
        prefix = "IMKBH'"
        suffix = f".{tf}"
        for f in tf_dir.iterdir():
            name = f.name
            if name.startswith(prefix) and name.endswith(suffix):
                sym = name[len(prefix):-len(suffix)]
                if sym:
                    symbols.append(sym)
        return sorted(symbols)


# ---------------------------------------------------------------------------
# Timeframe alignment (no lookahead)
# ---------------------------------------------------------------------------

def align_bars_to_base(
    base_bars: list[OHLCVBar],
    higher_bars: list[OHLCVBar],
) -> list[OHLCVBar | None]:
    """
    For each base bar, find the most recent completed higher-TF bar.

    NO LOOKAHEAD: uses only bars with timestamp < base_bar.timestamp.
    Returns list parallel to base_bars; None where no prior higher bar exists.
    """
    if not higher_bars:
        return [None] * len(base_bars)

    result: list[OHLCVBar | None] = []
    h_idx = 0
    h_len = len(higher_bars)

    for base in base_bars:
        # Advance to last higher bar that completed BEFORE this base bar
        while h_idx < h_len - 1 and higher_bars[h_idx + 1].timestamp < base.timestamp:
            h_idx += 1

        if h_idx < h_len and higher_bars[h_idx].timestamp < base.timestamp:
            result.append(higher_bars[h_idx])
        else:
            result.append(None)

    return result


def filter_bars_by_date_range(
    bars: list[OHLCVBar],
    start_unix: int | None = None,
    end_unix: int | None = None,
) -> list[OHLCVBar]:
    """Filter bars to [start_unix, end_unix] inclusive. None = no bound."""
    out = bars
    if start_unix is not None:
        out = [b for b in out if b.timestamp >= start_unix]
    if end_unix is not None:
        out = [b for b in out if b.timestamp <= end_unix]
    return out


__all__ = [
    "IdealIntradayLoader",
    "IntradayBar",
    "SymbolBundle",
    "align_bars_to_base",
    "filter_bars_by_date_range",
    "load_ideal_file",
    "parse_ideal_binary",
    "resolve_ideal_path",
]
