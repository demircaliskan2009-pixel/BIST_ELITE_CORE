"""Markets package — multi-market architecture boundary.

Provides market-specific modules:
- ``bist``: BIST (Istanbul Stock Exchange) — production market
- ``crypto``: Crypto — placeholder (empty)

Market-agnostic core logic stays in ``bist_core.backtest``,
``bist_core.execution``, ``bist_core.risk``, ``bist_core.models``.
"""

from __future__ import annotations

SUPPORTED_MARKETS = ("bist", "crypto")

__all__ = ["SUPPORTED_MARKETS"]
