"""OHLCV bar and series models.

OHLCVBar: immutable completed or in-progress bar.
OHLCVSeries: ordered mutable container for a single symbol/exchange/interval combination.

Determinism: OHLCVBuilder with identical trade stream produces identical bars.
PRD reference: §4.3 (OHLCV construction), §4.6 (timeframe hierarchy).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# All intervals the system supports per PRD §4.1 and §4.6.
VALID_INTERVALS = frozenset({"1s", "1m", "5m", "15m", "1h", "4h", "1d"})

# Interval duration in nanoseconds — used by OHLCVBuilder for bar boundary calculations.
INTERVAL_NS: dict = {
    "1s": 1_000_000_000,
    "1m": 60_000_000_000,
    "5m": 300_000_000_000,
    "15m": 900_000_000_000,
    "1h": 3_600_000_000_000,
    "4h": 14_400_000_000_000,
    "1d": 86_400_000_000_000,
}


@dataclass(frozen=True)
class OHLCVBar:
    """Immutable OHLCV bar.

    Determinism: two bars built from the same ordered trade sequence are identical.
    is_closed: True when the bar period has ended and no more trades can modify it.
    """

    symbol: str
    exchange: str
    interval: str
    open_time_ns: int  # bar period start (inclusive), ns since epoch UTC
    close_time_ns: int  # bar period end (exclusive), ns since epoch UTC
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float  # base asset volume
    quote_volume: float  # quote asset volume (price × qty)
    trade_count: int
    is_closed: bool


@dataclass
class OHLCVSeries:
    """Ordered sequence of OHLCVBar for a given symbol/exchange/interval.

    Invariant: bars are strictly chronologically ordered (open_time_ns ascending).
    All mutations via append_bar() only — direct list mutation is prohibited.

    max_bars: maximum number of bars retained. Oldest bars are evicted when exceeded.
              Default 10 000 ≈ ~7 days of 1m bars. Set 0 for unlimited (testing only).
    """

    symbol: str
    exchange: str
    interval: str
    bars: list[OHLCVBar] = field(default_factory=list)
    max_bars: int = 10_000

    def append_bar(self, bar: OHLCVBar) -> None:
        """Append a bar in chronological order.

        Raises ValueError on out-of-order append (determinism guard).
        Evicts oldest bars when max_bars is exceeded.
        """
        if self.bars and bar.open_time_ns <= self.bars[-1].open_time_ns:
            raise ValueError(
                f"OHLCVSeries out-of-order append for {self.symbol}/{self.interval}: "
                f"new open_time_ns={bar.open_time_ns} <= last open_time_ns={self.bars[-1].open_time_ns}"
            )
        self.bars.append(bar)
        if self.max_bars > 0 and len(self.bars) > self.max_bars:
            self.bars = self.bars[-self.max_bars :]

    def latest(self) -> OHLCVBar | None:
        """Returns most recent bar, or None if series is empty."""
        return self.bars[-1] if self.bars else None

    def __len__(self) -> int:
        return len(self.bars)
