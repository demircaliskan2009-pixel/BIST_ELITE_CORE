"""FAZ58: Market data provider interface. Default: local_eod (reads snapshots); registry for custom providers."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from bist_core.market_data.base import MarketDataProvider
from bist_core.market_data.local_eod import LocalEODProvider
from bist_core.market_data.registry import get_market_data_provider


def resolve_provider(
    name: str = "local_eod",
    snapshot_root: Optional[Path | str] = None,
    **kwargs: Any,
) -> MarketDataProvider:
    """Resolve market data provider by name. Default local_eod requires snapshot_root; else registry."""
    if name == "local_eod":
        if snapshot_root is None:
            import os
            snapshot_root = os.environ.get("BIST_CORE_SNAPSHOT_DIR")
            if not snapshot_root:
                raise ValueError("local_eod requires snapshot_root or BIST_CORE_SNAPSHOT_DIR")
        return LocalEODProvider(snapshot_root=Path(snapshot_root))
    factory = get_market_data_provider(name)
    if factory is not None:
        return factory(snapshot_root=snapshot_root, **kwargs)
    raise ValueError(f"unknown market_data provider: {name}")


__all__ = [
    "MarketDataProvider",
    "LocalEODProvider",
    "resolve_provider",
]
