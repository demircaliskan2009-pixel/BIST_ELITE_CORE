"""iDeal local data fetcher — primary data source for live paper trading."""

from __future__ import annotations

import os
from typing import Callable

from bist_core.models.ohlcv import OHLCVBar

from bist_core.data.loader import load_ideal_dataset

MIN_BARS_PER_SYMBOL = 50
_DEFAULT_BASE_PATH = r"C:/iDeal/ChartData/IMKBH/G"
_ENV_BASE_PATH = "BIST_IDEAL_BASE_PATH"


def ideal_fetcher(
    symbols: list[str],
    base_path: str | None = None,
) -> dict[str, list[OHLCVBar]]:
    """Load iDeal .G dataset. Only symbols with >= 50 bars. Fail-closed: skip invalid."""
    path = base_path or os.environ.get(_ENV_BASE_PATH, _DEFAULT_BASE_PATH)
    raw = load_ideal_dataset(path, symbols)
    result: dict[str, list[OHLCVBar]] = {}
    for sym in sorted(raw.keys()):
        bars = raw[sym]
        if len(bars) >= MIN_BARS_PER_SYMBOL:
            result[sym] = bars
    return result


def make_ideal_fetcher(base_path: str | None = None) -> Callable[[list[str]], dict[str, list[OHLCVBar]]]:
    """Factory: returns fetcher with fixed base_path."""
    path = base_path or os.environ.get(_ENV_BASE_PATH, _DEFAULT_BASE_PATH)

    def fetcher(symbols: list[str]) -> dict[str, list[OHLCVBar]]:
        return ideal_fetcher(symbols, base_path=path)

    return fetcher


__all__ = ["ideal_fetcher", "make_ideal_fetcher"]
