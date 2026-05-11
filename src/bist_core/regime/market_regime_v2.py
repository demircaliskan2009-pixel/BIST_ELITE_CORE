"""Market Regime Engine V2 — deterministic 5-state regime classifier for BIST.

Classifies the broad market into one of 5 states using an equal-weight
proxy index computed from the validated symbol universe:

    SUPER_BULL — strong trend + high breadth + controlled vol
    BULL       — positive trend
    NEUTRAL    — no clear direction
    BEAR       — negative trend
    CHAOS      — extreme volatility (any direction)

All computations are deterministic, lag-safe (no lookahead), and use only
completed daily bars.

Inputs: dict[str, list[OHLCVBar]] mapping symbol → sorted daily bars.
Output: list[RegimeSnapshot] — one per trading day with all intermediate values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Sequence

from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SMA_SHORT: Final[int] = 20
_SMA_LONG: Final[int] = 50
_MOMENTUM_LOOKBACK: Final[int] = 20
_VOL_LOOKBACK: Final[int] = 20
_BREADTH_LOOKBACK: Final[int] = 5
_MIN_SYMBOLS: Final[int] = 3
_MIN_HISTORY: Final[int] = _SMA_LONG + 5  # need SMA_LONG + warm-up

# Regime thresholds
_CHAOS_VOL_THRESHOLD: Final[float] = 0.035  # daily realized vol > 3.5%
_SUPER_BULL_MOMENTUM: Final[float] = 0.04   # 4% over 20 days
_SUPER_BULL_BREADTH: Final[float] = 0.65    # 65%+ symbols trending up
_BEAR_MOMENTUM: Final[float] = -0.02        # -2% over 20 days

# Hysteresis: regime must persist for N days to flip (prevents noise flipping)
_REGIME_PERSISTENCE: Final[int] = 3


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RegimeSnapshot:
    """Market regime at a specific point in time."""
    timestamp: int          # unix ts of daily bar
    regime: str             # SUPER_BULL, BULL, NEUTRAL, BEAR, CHAOS
    sma_short: float        # proxy index SMA short
    sma_long: float         # proxy index SMA long
    momentum: float         # 20-day return of proxy index
    realized_vol: float     # 20-day realized vol
    breadth: float          # fraction of symbols with positive 5-day return
    index_level: float      # proxy index value


# ---------------------------------------------------------------------------
# Proxy index construction
# ---------------------------------------------------------------------------

def _build_proxy_index(
    daily_by_symbol: dict[str, list[OHLCVBar]],
) -> list[tuple[int, float]]:
    """Build equal-weight proxy index from aligned daily bars.

    Returns sorted list of (timestamp, index_level) starting at 100.0.
    Only includes timestamps where at least _MIN_SYMBOLS have bars.
    """
    # Collect all daily closes by timestamp
    ts_closes: dict[int, list[float]] = {}
    for sym, bars in daily_by_symbol.items():
        for b in bars:
            ts_closes.setdefault(b.timestamp, []).append(float(b.close))

    # Filter timestamps with enough symbols
    valid_ts = sorted(
        ts for ts, closes in ts_closes.items()
        if len(closes) >= _MIN_SYMBOLS
    )

    if len(valid_ts) < 2:
        return []

    # Build index from equal-weight daily returns
    index: list[tuple[int, float]] = [(valid_ts[0], 100.0)]

    for i in range(1, len(valid_ts)):
        ts_prev, ts_curr = valid_ts[i - 1], valid_ts[i]
        curr_closes = ts_closes[ts_curr]
        prev_closes = ts_closes[ts_prev]

        # Match only symbols present in both days
        # Use average return across all available symbols
        if not curr_closes or not prev_closes:
            index.append((ts_curr, index[-1][1]))
            continue

        avg_curr = sum(curr_closes) / len(curr_closes)
        avg_prev = sum(prev_closes) / len(prev_closes)
        if avg_prev <= 0:
            index.append((ts_curr, index[-1][1]))
            continue

        daily_return = (avg_curr - avg_prev) / avg_prev
        new_level = index[-1][1] * (1.0 + daily_return)
        index.append((ts_curr, new_level))

    return index


# ---------------------------------------------------------------------------
# SMA / Statistics helpers
# ---------------------------------------------------------------------------

def _sma(values: Sequence[float], period: int) -> float:
    """Simple moving average of last `period` values."""
    if len(values) < period:
        return 0.0
    return sum(values[-period:]) / period


def _realized_vol(returns: Sequence[float], lookback: int) -> float:
    """Annualized realized volatility from daily returns."""
    if len(returns) < lookback:
        return 0.0
    recent = list(returns[-lookback:])
    mean = sum(recent) / len(recent)
    var = sum((r - mean) ** 2 for r in recent) / len(recent)
    return math.sqrt(var) if var > 0 else 0.0


def _breadth(
    daily_by_symbol: dict[str, list[OHLCVBar]],
    current_ts: int,
    lookback: int,
) -> float:
    """Fraction of symbols with positive N-day return at current_ts."""
    positive = 0
    total = 0

    for sym, bars in daily_by_symbol.items():
        # Find bars at or before current_ts
        relevant = [b for b in bars if b.timestamp <= current_ts]
        if len(relevant) < lookback + 1:
            continue
        total += 1

        close_now = float(relevant[-1].close)
        close_ago = float(relevant[-lookback - 1].close)
        if close_ago > 0 and close_now > close_ago:
            positive += 1

    return positive / total if total > 0 else 0.5


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

def classify_regime_series(
    daily_by_symbol: dict[str, list[OHLCVBar]],
) -> list[RegimeSnapshot]:
    """Classify market regime for every trading day in the dataset.

    Returns a list of RegimeSnapshot sorted by timestamp.
    """
    # 1. Build proxy index
    index_series = _build_proxy_index(daily_by_symbol)
    if len(index_series) < _MIN_HISTORY:
        return []

    timestamps = [t for t, _ in index_series]
    levels = [v for _, v in index_series]

    # 2. Compute daily returns
    returns: list[float] = [0.0]
    for i in range(1, len(levels)):
        if levels[i - 1] > 0:
            returns.append((levels[i] - levels[i - 1]) / levels[i - 1])
        else:
            returns.append(0.0)

    # 3. Classify each day
    snapshots: list[RegimeSnapshot] = []
    pending_regime = "NEUTRAL"
    persistence_count = 0

    for i in range(_MIN_HISTORY, len(levels)):
        ts = timestamps[i]
        level = levels[i]

        sma_s = _sma(levels[: i + 1], _SMA_SHORT)
        sma_l = _sma(levels[: i + 1], _SMA_LONG)
        momentum = (levels[i] - levels[max(0, i - _MOMENTUM_LOOKBACK)]) / levels[max(0, i - _MOMENTUM_LOOKBACK)] if levels[max(0, i - _MOMENTUM_LOOKBACK)] > 0 else 0.0
        rvol = _realized_vol(returns[: i + 1], _VOL_LOOKBACK)
        brd = _breadth(daily_by_symbol, ts, _BREADTH_LOOKBACK)

        # Raw regime classification
        if rvol > _CHAOS_VOL_THRESHOLD:
            raw_regime = "CHAOS"
        elif sma_s > sma_l and momentum > _SUPER_BULL_MOMENTUM and brd > _SUPER_BULL_BREADTH:
            raw_regime = "SUPER_BULL"
        elif sma_s > sma_l and momentum > 0:
            raw_regime = "BULL"
        elif sma_s < sma_l and momentum < _BEAR_MOMENTUM:
            raw_regime = "BEAR"
        else:
            raw_regime = "NEUTRAL"

        # Hysteresis: require persistence to flip regime
        if raw_regime == pending_regime:
            persistence_count += 1
        else:
            pending_regime = raw_regime
            persistence_count = 1

        # Use previous regime until persistence threshold met
        if persistence_count >= _REGIME_PERSISTENCE:
            confirmed_regime = pending_regime
        elif snapshots:
            confirmed_regime = snapshots[-1].regime
        else:
            confirmed_regime = "NEUTRAL"

        snapshots.append(RegimeSnapshot(
            timestamp=ts,
            regime=confirmed_regime,
            sma_short=round(sma_s, 4),
            sma_long=round(sma_l, 4),
            momentum=round(momentum, 6),
            realized_vol=round(rvol, 6),
            breadth=round(brd, 4),
            index_level=round(level, 4),
        ))

    return snapshots


def get_regime_at(
    snapshots: list[RegimeSnapshot],
    timestamp: int,
) -> RegimeSnapshot | None:
    """Get the latest regime snapshot at or before the given timestamp.

    Uses binary search for efficiency on large datasets.
    """
    if not snapshots:
        return None

    lo, hi = 0, len(snapshots) - 1
    result: RegimeSnapshot | None = None

    while lo <= hi:
        mid = (lo + hi) // 2
        if snapshots[mid].timestamp <= timestamp:
            result = snapshots[mid]
            lo = mid + 1
        else:
            hi = mid - 1

    return result


__all__ = [
    "RegimeSnapshot",
    "classify_regime_series",
    "get_regime_at",
]
