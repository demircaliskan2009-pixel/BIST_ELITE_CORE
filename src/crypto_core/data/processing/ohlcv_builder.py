"""OHLCVBuilder — multi-timeframe OHLCV construction from trade stream.

Builds OHLCV bars for multiple intervals simultaneously from tick data.
Emits a completed OHLCVBar when a bar period closes.
Maintains one in-progress bar per interval until bar close.

Design:
- Stateful: one OHLCVBuilder instance per (symbol, exchange).
- All intervals share the same trade input stream.
- Bar boundaries are computed from timestamp_ns using INTERVAL_NS (UTC-aligned).
- No clock dependency: bar boundaries derived from event timestamps only.

Determinism: same trade stream → identical bars for all intervals.

Edge cases:
- Burst traffic: all trades in a burst are bucketed correctly by timestamp_ns.
- Clock drift: bar boundaries use event timestamps, not wall clock.
  (DataValidator rejects events with extreme clock drift upstream.)

PRD reference: §4.3 (OHLCV construction from trades), §4.6 (timeframe hierarchy).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

from crypto_core.data.models.events import TradeEvent
from crypto_core.data.models.ohlcv import INTERVAL_NS, VALID_INTERVALS, OHLCVBar, OHLCVSeries

logger = logging.getLogger(__name__)

# Downstream callback: called when a bar closes.
BarClosedCallback = Callable[[OHLCVBar], None]


@dataclass
class _InProgressBar:
    """Mutable accumulator for a single in-progress OHLCV bar."""

    symbol: str
    exchange: str
    interval: str
    open_time_ns: int
    close_time_ns: int  # exclusive end of the period
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    quote_volume: float
    trade_count: int

    def to_bar(self, is_closed: bool) -> OHLCVBar:
        return OHLCVBar(
            symbol=self.symbol,
            exchange=self.exchange,
            interval=self.interval,
            open_time_ns=self.open_time_ns,
            close_time_ns=self.close_time_ns,
            open_price=self.open_price,
            high_price=self.high_price,
            low_price=self.low_price,
            close_price=self.close_price,
            volume=self.volume,
            quote_volume=self.quote_volume,
            trade_count=self.trade_count,
            is_closed=is_closed,
        )


class OHLCVBuilder:
    """Builds multi-timeframe OHLCV bars from a validated trade stream.

    Usage:
        builder = OHLCVBuilder(
            symbol="BTCUSDT",
            exchange="binance",
            intervals=["1m", "5m", "1h"],
            on_bar_closed=lambda bar: print(bar),
        )
        builder.on_trade(trade_event)  # called for each validated trade

    on_bar_closed is called synchronously when a bar period closes.
    Bar is emitted with is_closed=True.

    OHLCVSeries is maintained per interval for historical access.
    """

    def __init__(
        self,
        symbol: str,
        exchange: str,
        intervals: Optional[List[str]] = None,
        on_bar_closed: Optional[BarClosedCallback] = None,
    ) -> None:
        self._symbol = symbol
        self._exchange = exchange
        self._on_bar_closed = on_bar_closed

        # Default to all supported intervals if not specified.
        effective_intervals: List[str] = intervals if intervals is not None else list(VALID_INTERVALS)
        invalid = set(effective_intervals) - VALID_INTERVALS
        if invalid:
            raise ValueError(f"OHLCVBuilder: unsupported intervals {invalid}. Valid: {VALID_INTERVALS}")

        self._intervals: List[str] = sorted(effective_intervals)
        # in-progress bars: interval → _InProgressBar or None
        self._current: Dict[str, Optional[_InProgressBar]] = {iv: None for iv in self._intervals}
        # completed series: interval → OHLCVSeries
        self._series: Dict[str, OHLCVSeries] = {
            iv: OHLCVSeries(symbol=symbol, exchange=exchange, interval=iv) for iv in self._intervals
        }

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    def on_trade(self, trade: TradeEvent) -> None:
        """Process a validated trade event — update all in-progress bars.

        Called by TradeStreamProcessor after validation passes.
        """
        for interval in self._intervals:
            self._process_trade_for_interval(trade, interval)

    def get_series(self, interval: str) -> OHLCVSeries:
        """Returns the completed bar series for the given interval."""
        if interval not in self._series:
            raise KeyError(f"Interval '{interval}' not tracked by this builder")
        return self._series[interval]

    def current_bar(self, interval: str) -> Optional[OHLCVBar]:
        """Returns the in-progress (not yet closed) bar for the given interval, or None."""
        bar = self._current.get(interval)
        if bar is None:
            return None
        return bar.to_bar(is_closed=False)

    # ──────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────

    def _process_trade_for_interval(self, trade: TradeEvent, interval: str) -> None:
        """Update (or close and open) the bar for a single interval."""
        interval_ns = INTERVAL_NS[interval]
        bar_open_ns = _bar_open_time(trade.timestamp_ns, interval_ns)
        bar_close_ns = bar_open_ns + interval_ns

        current = self._current[interval]

        if current is None:
            # First trade ever for this interval.
            self._current[interval] = _open_bar(trade, interval, bar_open_ns, bar_close_ns)
            return

        if trade.timestamp_ns >= current.close_time_ns:
            # Trade falls in a new bar period — close the current bar first.
            closed_bar = current.to_bar(is_closed=True)
            self._series[interval].append_bar(closed_bar)
            if self._on_bar_closed is not None:
                self._on_bar_closed(closed_bar)
            logger.debug(
                "Bar closed: %s %s %s  open=%.2f close=%.2f vol=%.4f",
                self._exchange,
                self._symbol,
                interval,
                closed_bar.open_price,
                closed_bar.close_price,
                closed_bar.volume,
            )
            # Open the new bar.
            self._current[interval] = _open_bar(trade, interval, bar_open_ns, bar_close_ns)
        else:
            # Trade falls within the current bar — update it.
            _update_bar(current, trade)

    @property
    def intervals(self) -> List[str]:
        """List of intervals this builder tracks."""
        return list(self._intervals)


# ──────────────────────────────────────────────────────────────────────
# Module-level pure helpers (easily unit-testable)
# ──────────────────────────────────────────────────────────────────────

def _bar_open_time(timestamp_ns: int, interval_ns: int) -> int:
    """Compute the UTC-aligned bar open time for a given timestamp.

    Bars are aligned to UTC midnight boundaries.
    Example: for 1m bars, bar_open = floor(timestamp / 60s) * 60s.
    """
    return (timestamp_ns // interval_ns) * interval_ns


def _open_bar(
    trade: TradeEvent,
    interval: str,
    bar_open_ns: int,
    bar_close_ns: int,
) -> _InProgressBar:
    """Create a new in-progress bar from the first trade."""
    return _InProgressBar(
        symbol=trade.symbol,
        exchange=trade.exchange.value,
        interval=interval,
        open_time_ns=bar_open_ns,
        close_time_ns=bar_close_ns,
        open_price=trade.price,
        high_price=trade.price,
        low_price=trade.price,
        close_price=trade.price,
        volume=trade.qty,
        quote_volume=trade.price * trade.qty,
        trade_count=1,
    )


def _update_bar(bar: _InProgressBar, trade: TradeEvent) -> None:
    """Update an in-progress bar with a new trade (mutates in place)."""
    if trade.price > bar.high_price:
        bar.high_price = trade.price
    if trade.price < bar.low_price:
        bar.low_price = trade.price
    bar.close_price = trade.price
    bar.volume += trade.qty
    bar.quote_volume += trade.price * trade.qty
    bar.trade_count += 1
