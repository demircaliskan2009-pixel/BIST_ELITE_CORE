"""OHLCV bar model — canonical data structure for market bars."""

from __future__ import annotations

from dataclasses import dataclass


def normalize_timestamp(ts: int | str) -> int:
    """Coerce bar timestamp to Unix seconds (int). Deterministic; numeric strings only."""
    if isinstance(ts, int):
        return ts
    s = str(ts).strip()
    if not s:
        raise ValueError("empty timestamp")
    if s.isdigit():
        return int(s)
    try:
        return int(float(s))
    except ValueError as e:
        raise ValueError(f"invalid timestamp: {ts!r}") from e


@dataclass(frozen=True)
class OHLCVBar:
    timestamp: int  # Unix seconds
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_dummy: bool = False  # True for feed fallback bars only; not real market data


__all__ = ["OHLCVBar", "normalize_timestamp"]
