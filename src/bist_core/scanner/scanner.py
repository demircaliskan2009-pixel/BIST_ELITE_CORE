"""Scanner Engine — scan multiple symbols and produce candidate trade setups."""

from __future__ import annotations

import math
import statistics
from typing import Literal

from bist_core.data.quality import InvalidDataError, basic_checks
from bist_core.models.ohlcv import OHLCVBar

import os as _os
MIN_BARS = int(_os.environ.get("DEBUG_MIN_BARS", "50"))
MOMENTUM_LOOKBACK = 20


def _has_nan(bar: OHLCVBar) -> bool:
    return (
        math.isnan(bar.open)
        or math.isnan(bar.high)
        or math.isnan(bar.low)
        or math.isnan(bar.close)
        or math.isnan(bar.volume)
    )


def _is_valid(bars: list[OHLCVBar]) -> bool:
    if len(bars) < MIN_BARS:
        return False
    if any(_has_nan(b) for b in bars):
        return False
    try:
        basic_checks(bars)
    except InvalidDataError:
        return False
    return True


def _momentum(bars: list[OHLCVBar]) -> float:
    if len(bars) < MOMENTUM_LOOKBACK + 1:
        return bars[-1].close - bars[0].close
    return bars[-1].close - bars[-(MOMENTUM_LOOKBACK + 1)].close


def _volatility(bars: list[OHLCVBar]) -> float:
    returns = []
    for i in range(1, len(bars)):
        prev = bars[i - 1].close
        if prev <= 0:
            return 0.0
        ret = (bars[i].close - prev) / prev
        returns.append(ret)
    if len(returns) < 2:
        return 0.0
    return statistics.stdev(returns)


def _trend(momentum: float) -> Literal["up", "down", "neutral"]:
    if momentum > 0:
        return "up"
    if momentum < 0:
        return "down"
    return "neutral"


def _normalize(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.5
    return (x - lo) / (hi - lo)


class Scanner:
    """Scan multiple symbols and produce ranked candidate trade setups.

    Deterministic, fail-closed, no randomness.
    """

    def scan(self, data: dict[str, list[OHLCVBar]]) -> list[dict]:
        """Scan symbols and return ranked candidates.

        Filters: skip symbol if len(bars) < 50, any NaN, invalid OHLC.
        Sorts by score descending.
        """
        valid: list[tuple[str, float, float, Literal["up", "down", "neutral"]]] = []
        for symbol in sorted(data.keys()):
            bars = data[symbol]
            if not _is_valid(bars):
                continue
            mom = _momentum(bars)
            vol = _volatility(bars)
            trend_val = _trend(mom)
            valid.append((symbol, mom, vol, trend_val))

        if not valid:
            return []

        moms = [v[1] for v in valid]
        vols = [v[2] for v in valid]
        mom_lo, mom_hi = min(moms), max(moms)
        vol_lo, vol_hi = min(vols), max(vols)

        results: list[dict] = []
        for symbol, mom, vol, trend_val in valid:
            norm_mom = _normalize(mom, mom_lo, mom_hi)
            norm_vol = _normalize(vol, vol_lo, vol_hi)
            score = norm_mom + norm_vol
            signal_strength = _normalize(abs(mom), 0, max(abs(m) for m in moms) or 1.0)
            results.append({
                "symbol": symbol,
                "score": score,
                "signal_strength": signal_strength,
                "volatility": vol,
                "trend": trend_val,
            })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results
