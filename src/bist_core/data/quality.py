"""Data quality validation and liquidity metrics for OHLCV bars."""

from __future__ import annotations

from bist_core.models.ohlcv import OHLCVBar


class InvalidDataError(Exception):
    """Raised when OHLCV data fails validation."""

    pass


def _ts_float(ts: str) -> float:
    """Parse timestamp to float for comparison; raise on invalid."""
    try:
        return float(str(ts).strip())
    except (ValueError, TypeError) as e:
        raise InvalidDataError(f"invalid timestamp: {ts!r}") from e


def basic_checks(bars: list[OHLCVBar]) -> bool:
    """Validate OHLCV bars. Raise InvalidDataError if any rule fails.

    Rules:
    - bars must not be empty
    - timestamps strictly increasing
    - no duplicate timestamps
    - prices > 0 (open, high, low, close)
    - volume >= 0

    Returns True if valid.
    """
    if not bars:
        raise InvalidDataError("bars must not be empty")

    prev_ts: float | None = None
    seen: set[float] = set()

    for i, bar in enumerate(bars):
        ts = _ts_float(bar.timestamp)
        if ts in seen:
            raise InvalidDataError(f"duplicate timestamp: {bar.timestamp}")
        seen.add(ts)
        if prev_ts is not None and ts <= prev_ts:
            raise InvalidDataError(
                f"timestamps must be strictly increasing: bar {i} has ts {bar.timestamp}"
            )
        prev_ts = ts

        if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
            raise InvalidDataError(f"bar {i}: all prices must be > 0")
        if bar.volume < 0:
            raise InvalidDataError(f"bar {i}: volume must be >= 0")

    return True


def compute_liquidity_metrics(bars: list[OHLCVBar]) -> dict:
    """Compute liquidity metrics from OHLCV bars.

    Returns:
        {
            "avg_volume": float,
            "bar_count": int,
            "turnover_proxy": float
        }

    avg_volume = mean(volume)
    bar_count = len(bars)
    turnover_proxy = mean(close * volume)

    Raises InvalidDataError on empty input or invalid values.
    """
    if not bars:
        raise InvalidDataError("bars must not be empty")

    basic_checks(bars)

    total_vol = 0.0
    total_turnover = 0.0
    n = len(bars)
    for bar in bars:
        total_vol += bar.volume
        total_turnover += bar.close * bar.volume

    return {
        "avg_volume": total_vol / n,
        "bar_count": n,
        "turnover_proxy": total_turnover / n,
    }
