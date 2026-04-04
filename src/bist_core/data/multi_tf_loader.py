"""Load all standard timeframes via :class:`MatriksHistorical` (fail-closed per TF)."""

from __future__ import annotations

from datetime import date

from bist_core.data.matriks_historical import MatriksHistorical
from bist_core.models.ohlcv import OHLCVBar


class MultiTFLoader:
    """Returns ``symbol_data`` shape: ``1m`` / ``5m`` / ``60m`` / ``1d`` → bars."""

    def __init__(self) -> None:
        self.mh = MatriksHistorical()

    def load(
        self,
        symbol: str,
        *,
        start: date | str | None = None,
        end: date | str | None = None,
    ) -> dict[str, list[OHLCVBar]]:
        return {
            "1m": self.mh.fetch(symbol, start=start, end=end, period="1m"),
            "5m": self.mh.fetch(symbol, start=start, end=end, period="5m"),
            "60m": self.mh.fetch(symbol, start=start, end=end, period="60m"),
            "1d": self.mh.fetch(symbol, start=start, end=end, period="1d"),
        }


__all__ = ["MultiTFLoader"]
