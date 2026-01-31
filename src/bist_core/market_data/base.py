"""
FAZ58: Market data provider interface.
Protocol: symbols(day), close_map(day), validate(day).
Optional: raw_path, raw_sha256 for pipeline provenance.
"""
from __future__ import annotations

from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class MarketDataProvider(Protocol):
    """Interface for EOD market data (snapshots). Deterministic: same day -> same symbols/close_map order."""

    def symbols(self, day: str) -> List[str]:
        """Return symbol list for day (deterministic order, e.g. sorted)."""
        ...

    def close_map(self, day: str) -> Dict[str, float]:
        """Return symbol -> close price for day. Deterministic key order."""
        ...

    def validate(self, day: str) -> tuple[bool, str]:
        """Return (ok, message). ok True iff data for day is available and usable."""
        ...
