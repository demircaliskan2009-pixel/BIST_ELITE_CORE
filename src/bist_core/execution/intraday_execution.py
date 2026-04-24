"""Intraday Execution Realism — extends execution_realism for intraday bar resolution.

Adds:
- Bar-volume-based fill constraints (no filling > bar volume)
- Intraday slippage scaling (wider at open/close, tighter mid-session)
- BIST tick rounding on all prices
- Session boundary enforcement
- Next-bar execution enforcement (order at bar N → fill at bar N+1 open)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Sequence

from bist_core.decision.intraday_edges import IntradaySignal
from bist_core.execution.execution_realism import (
    apply_slippage,
    compute_fill_ratio,
    compute_slippage_bps,
    compute_total_cost_bps,
)
from bist_core.execution.tick_size import round_to_tick
from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# BIST session hours (seconds-of-day in TRT = UTC+3)
_SESSION_OPEN: Final[int] = 9 * 3600
_SESSION_CLOSE: Final[int] = 18 * 3600

# Slippage multiplier by session phase
_OPEN_SLIPPAGE_MULT: Final[float] = 1.8    # first 15 min: wider spread
_CLOSE_SLIPPAGE_MULT: Final[float] = 1.5   # last 15 min: wider spread
_MID_SLIPPAGE_MULT: Final[float] = 1.0     # mid-session: normal

# Bar volume cap: cannot fill more than this fraction of bar volume
_MAX_FILL_FRACTION_OF_BAR_VOL: Final[float] = 0.10  # 10% of bar volume

# Minimum volume for valid bar fill
_MIN_BAR_VOL_FOR_FILL: Final[int] = 100

# Intraday ADV lookback (in bars)
_INTRADAY_ADV_LOOKBACK: Final[int] = 120


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class IntradayFill:
    """Represents a realized fill from an intraday signal."""
    timestamp: int          # fill bar timestamp (next-bar)
    symbol: str
    edge: str
    direction: str          # "LONG"
    fill_price: float       # after slippage + tick rounding
    fill_size: int          # actual filled shares
    original_size: int      # requested size
    stop_price: float       # tick-rounded
    target_price: float     # tick-rounded
    slippage_bps: float
    total_cost_bps: float
    fill_ratio: float
    rejected: bool
    reject_reason: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _time_of_day_sec(unix_ts: int) -> int:
    return (unix_ts + 3 * 3600) % 86400


def _session_slippage_mult(unix_ts: int) -> float:
    """Intraday slippage multiplier based on session timing."""
    tod = _time_of_day_sec(unix_ts)
    if tod < _SESSION_OPEN + 15 * 60:
        return _OPEN_SLIPPAGE_MULT
    if tod > _SESSION_CLOSE - 15 * 60:
        return _CLOSE_SLIPPAGE_MULT
    return _MID_SLIPPAGE_MULT


def _avg_bar_volume(bars: Sequence[OHLCVBar], lookback: int) -> float:
    if not bars:
        return 0.0
    window = bars[-lookback:]
    vols = [float(b.volume) for b in window]
    return sum(vols) / len(vols) if vols else 0.0


def _recent_close_volatility(bars: Sequence[OHLCVBar], lookback: int = 60) -> float:
    """Return stddev of 1-bar returns."""
    if len(bars) < lookback + 1:
        lookback = len(bars) - 1
    if lookback < 2:
        return 0.02

    closes = [float(b.close) for b in bars[-(lookback + 1):]]
    rets: list[float] = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            rets.append((closes[i] - closes[i - 1]) / closes[i - 1])
    if len(rets) < 2:
        return 0.02
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return max(0.005, var ** 0.5)


# ---------------------------------------------------------------------------
# Main execution function
# ---------------------------------------------------------------------------

def execute_intraday_signal(
    signal: IntradaySignal,
    fill_bar: OHLCVBar,
    recent_bars: Sequence[OHLCVBar],
) -> IntradayFill:
    """Simulate realistic execution of an intraday signal.

    NEXT-BAR EXECUTION: signal generated at bar N, filled at bar N+1 open.
    The fill_bar is the NEXT bar after signal generation.

    Args:
        signal: The intraday signal to execute.
        fill_bar: The next bar (where execution happens at open).
        recent_bars: Recent history for volatility/volume estimation.

    Returns:
        IntradayFill with realized execution details.
    """
    sym = signal.symbol
    edge = signal.edge
    direction = signal.direction
    requested_size = signal.position_size

    # 1. Session check
    tod = _time_of_day_sec(fill_bar.timestamp)
    if tod < _SESSION_OPEN or tod > _SESSION_CLOSE:
        return IntradayFill(
            timestamp=fill_bar.timestamp, symbol=sym, edge=edge,
            direction=direction, fill_price=0.0, fill_size=0,
            original_size=requested_size, stop_price=signal.stop_price,
            target_price=signal.target_price, slippage_bps=0.0,
            total_cost_bps=0.0, fill_ratio=0.0, rejected=True,
            reject_reason="OUTSIDE_SESSION",
        )

    # 2. Bar volume check
    bar_vol = float(fill_bar.volume)
    if bar_vol < _MIN_BAR_VOL_FOR_FILL:
        return IntradayFill(
            timestamp=fill_bar.timestamp, symbol=sym, edge=edge,
            direction=direction, fill_price=0.0, fill_size=0,
            original_size=requested_size, stop_price=signal.stop_price,
            target_price=signal.target_price, slippage_bps=0.0,
            total_cost_bps=0.0, fill_ratio=0.0, rejected=True,
            reject_reason="INSUFFICIENT_BAR_VOLUME",
        )

    # 3. Compute slippage
    vol = _recent_close_volatility(recent_bars, lookback=60)
    avg_vol = _avg_bar_volume(recent_bars, _INTRADAY_ADV_LOOKBACK)
    entry_price = float(fill_bar.open)  # fill at next-bar open

    base_slippage = compute_slippage_bps(
        daily_vol=vol,
        order_size=requested_size,
        avg_volume=avg_vol,
        price=entry_price,
    )

    # Apply session timing multiplier
    session_mult = _session_slippage_mult(fill_bar.timestamp)
    effective_slippage = base_slippage * session_mult

    # 4. Fill size constraint
    # Cannot fill more than 10% of bar volume in shares
    max_shares_from_bar = int(bar_vol * _MAX_FILL_FRACTION_OF_BAR_VOL)

    # Also check ADV-based fill ratio
    adv_fill_ratio = compute_fill_ratio(
        order_size=requested_size,
        avg_volume=avg_vol,
        price=entry_price,
    )

    if adv_fill_ratio == 0.0:
        return IntradayFill(
            timestamp=fill_bar.timestamp, symbol=sym, edge=edge,
            direction=direction, fill_price=0.0, fill_size=0,
            original_size=requested_size, stop_price=signal.stop_price,
            target_price=signal.target_price, slippage_bps=effective_slippage,
            total_cost_bps=0.0, fill_ratio=0.0, rejected=True,
            reject_reason="ORDER_TOO_LARGE_FOR_ADV",
        )

    # Effective fill size
    adv_limited_size = int(requested_size * adv_fill_ratio)
    bar_limited_size = max_shares_from_bar
    fill_size = max(1, min(adv_limited_size, bar_limited_size, requested_size))

    # 5. Apply slippage to fill price
    fill_price = apply_slippage(
        price=entry_price,
        slippage_bps=effective_slippage,
        side="buy" if direction == "LONG" else "sell",
    )

    # 6. Verify fill price within bar range
    if fill_price > float(fill_bar.high) or fill_price < float(fill_bar.low):
        # Price moved too fast — fill at bar's worst available price
        if direction == "LONG":
            fill_price = round_to_tick(min(fill_price, float(fill_bar.high)))
        else:
            fill_price = round_to_tick(max(fill_price, float(fill_bar.low)))

    # 7. Tick-round stops and targets
    stop_price = round_to_tick(signal.stop_price)
    target_price = round_to_tick(signal.target_price)

    # 8. Total cost
    total_cost = compute_total_cost_bps()

    actual_fill_ratio = fill_size / requested_size if requested_size > 0 else 0.0

    return IntradayFill(
        timestamp=fill_bar.timestamp,
        symbol=sym,
        edge=edge,
        direction=direction,
        fill_price=fill_price,
        fill_size=fill_size,
        original_size=requested_size,
        stop_price=stop_price,
        target_price=target_price,
        slippage_bps=round(effective_slippage, 2),
        total_cost_bps=round(total_cost, 2),
        fill_ratio=round(actual_fill_ratio, 4),
        rejected=False,
        reject_reason="",
    )


__all__ = [
    "IntradayFill",
    "execute_intraday_signal",
]
