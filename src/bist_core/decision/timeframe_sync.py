"""TimeframeSynchronizer — chronological bar-by-bar event loop for MTF backtest.

Merges bars from all timeframes for a single symbol into a chronological stream.
At each base-timeframe (1-min) bar, provides the current MTFContext by tracking
completed higher-TF bars without lookahead.

NO LOOKAHEAD: a higher-TF bar is only visible AFTER its timestamp has elapsed.
The base-TF bar drives the clock; higher-TF history grows only as bars complete.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Final, Iterator

from bist_core.data.ideal_intraday_loader import SymbolBundle
from bist_core.decision.mtf_context import (
    MTFContext,
    MTFContextEngine,
)
from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# These control how much history each TF builder looks back (max bars).
# Keeps memory bounded while providing enough data for indicators.
_DAILY_HISTORY_CAP: Final[int] = 200
_HOURLY_HISTORY_CAP: Final[int] = 200
_M5_HISTORY_CAP: Final[int] = 100
_M1_HISTORY_CAP: Final[int] = 120

# Daily bars have timestamps at 03:00 TRT (midnight UTC).  A bar for day D
# should only be visible AFTER day D's session ends (~18:00 TRT).  The offset
# from 03:00 to 18:00 is 15 hours = 54 000 seconds.  We use this to shift the
# comparison point so today's daily bar is NOT visible during today's session.
_DAILY_VISIBILITY_OFFSET: Final[int] = 54_000  # 15 hours in seconds


# ---------------------------------------------------------------------------
# Bar-level event emitted by the synchronizer
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MTFBarEvent:
    """A base-timeframe bar with its full MTF context attached."""
    bar: OHLCVBar           # current base-TF bar (e.g., 1-min)
    context: MTFContext      # aggregated multi-TF context at this bar
    daily_completed: bool    # True if a new daily bar just completed
    hourly_completed: bool   # True if a new hourly bar just completed
    m5_completed: bool       # True if a new 5-min bar just completed


# ---------------------------------------------------------------------------
# Per-symbol synchronizer
# ---------------------------------------------------------------------------

class TimeframeSynchronizer:
    """Stream MTFBarEvents for one symbol in chronological order.

    Usage:
        loader = IdealIntradayLoader()
        bundle = loader.load_symbol("AKBNK", ["G", "60", "05", "01"])
        sync = TimeframeSynchronizer("AKBNK", bundle, base_tf="01")
        for event in sync.iter_events():
            # event.bar = current 1-min bar
            # event.context = full MTF context (no lookahead)
            pass

    The synchronizer walks through base_tf bars one by one. Before emitting
    each bar, it advances higher-TF cursors (daily, hourly, 5-min) up to
    the last COMPLETED bar before the current timestamp.
    """

    def __init__(
        self,
        symbol: str,
        bundle: SymbolBundle,
        base_tf: str = "01",
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> None:
        self._symbol = symbol.strip().upper()
        self._engine = MTFContextEngine()

        # Extract and sort bars by timestamp
        self._daily = sorted(bundle.get("G", []), key=lambda b: b.timestamp)
        self._hourly = sorted(bundle.get("60", []), key=lambda b: b.timestamp)
        self._m5 = sorted(bundle.get("05", []), key=lambda b: b.timestamp)
        self._base = sorted(bundle.get(base_tf, []), key=lambda b: b.timestamp)

        # Precompute timestamp arrays for bisect (avoids O(n²))
        self._daily_ts = [b.timestamp for b in self._daily]
        self._hourly_ts = [b.timestamp for b in self._hourly]
        self._m5_ts = [b.timestamp for b in self._m5]
        self._base_ts = [b.timestamp for b in self._base]

        # Date range filter
        self._start_ts = start_ts
        self._end_ts = end_ts

    def _completed_before(
        self,
        ts_array: list[int],
        bars: list[OHLCVBar],
        current_ts: int,
        cap: int,
    ) -> list[OHLCVBar]:
        """Return the last `cap` bars with timestamp < current_ts (NO LOOKAHEAD)."""
        # bisect_left gives index of first ts >= current_ts
        idx = bisect.bisect_left(ts_array, current_ts)
        if idx == 0:
            return []
        start = max(0, idx - cap)
        return bars[start:idx]

    def iter_events(self) -> Iterator[MTFBarEvent]:
        """Yield MTFBarEvent for each base-TF bar in chronological order."""
        # Track absolute bisect indices (NOT capped-history indices)
        # to correctly detect new completions even when history exceeds cap.
        prev_daily_count = 0
        prev_hourly_count = 0
        prev_m5_count = 0

        for bar_i, bar in enumerate(self._base):
            ts = bar.timestamp

            # Date range filter
            if self._start_ts is not None and ts < self._start_ts:
                continue
            if self._end_ts is not None and ts > self._end_ts:
                continue

            # --- Daily: shifted visibility to prevent same-day lookahead ---
            # A daily bar for day D (ts=03:00 TRT) becomes visible only
            # after D's session ends, i.e. when current_ts > bar_ts + offset.
            daily_cutoff = ts - _DAILY_VISIBILITY_OFFSET
            daily_hist = self._completed_before(
                self._daily_ts, self._daily, daily_cutoff, _DAILY_HISTORY_CAP
            )

            # Hourly and M5: standard (no lookahead by design)
            hourly_hist = self._completed_before(
                self._hourly_ts, self._hourly, ts, _HOURLY_HISTORY_CAP
            )
            m5_hist = self._completed_before(
                self._m5_ts, self._m5, ts, _M5_HISTORY_CAP
            )

            # Base TF history (last N bars up to and including current)
            # For MTF context m1 indicators, we need bars BEFORE current
            m1_start = max(0, bar_i - _M1_HISTORY_CAP)
            m1_hist = self._base[m1_start:bar_i]  # excludes current bar

            # Detect new completions using absolute bar counts
            curr_daily_count = bisect.bisect_left(self._daily_ts, daily_cutoff)
            curr_hourly_count = bisect.bisect_left(self._hourly_ts, ts)
            curr_m5_count = bisect.bisect_left(self._m5_ts, ts)

            daily_completed = curr_daily_count > prev_daily_count
            hourly_completed = curr_hourly_count > prev_hourly_count
            m5_completed = curr_m5_count > prev_m5_count

            prev_daily_count = curr_daily_count
            prev_hourly_count = curr_hourly_count
            prev_m5_count = curr_m5_count

            # Build MTF context
            context = self._engine.build_context(
                symbol=self._symbol,
                timestamp=ts,
                daily_bars=daily_hist if daily_hist else None,
                hourly_bars=hourly_hist if hourly_hist else None,
                m5_bars=m5_hist if m5_hist else None,
                m1_bars=m1_hist if m1_hist else None,
            )

            yield MTFBarEvent(
                bar=bar,
                context=context,
                daily_completed=daily_completed,
                hourly_completed=hourly_completed,
                m5_completed=m5_completed,
            )


# ---------------------------------------------------------------------------
# Multi-symbol synchronizer
# ---------------------------------------------------------------------------

class UniverseSynchronizer:
    """Merge bar events from all symbols into a single chronological stream.

    Events from different symbols at the same timestamp are emitted in
    symbol-alphabetical order for determinism.
    """

    def __init__(
        self,
        universe: dict[str, SymbolBundle],
        base_tf: str = "01",
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> None:
        self._syncs: dict[str, TimeframeSynchronizer] = {}
        for sym, bundle in sorted(universe.items()):
            self._syncs[sym] = TimeframeSynchronizer(
                symbol=sym,
                bundle=bundle,
                base_tf=base_tf,
                start_ts=start_ts,
                end_ts=end_ts,
            )

    def iter_events(self) -> Iterator[MTFBarEvent]:
        """Yield events from all symbols in chronological order.

        Uses a merge-sort approach over per-symbol iterators.
        """
        import heapq

        # Priority queue: (timestamp, symbol, event, iterator)
        heap: list[tuple[int, str, MTFBarEvent]] = []
        iters: dict[str, Iterator[MTFBarEvent]] = {}

        for sym, sync in self._syncs.items():
            it = sync.iter_events()
            iters[sym] = it
            try:
                ev = next(it)
                heapq.heappush(heap, (ev.bar.timestamp, sym, ev))
            except StopIteration:
                pass

        while heap:
            ts, sym, event = heapq.heappop(heap)
            yield event
            try:
                ev = next(iters[sym])
                heapq.heappush(heap, (ev.bar.timestamp, sym, ev))
            except StopIteration:
                pass


__all__ = [
    "MTFBarEvent",
    "TimeframeSynchronizer",
    "UniverseSynchronizer",
]
