"""Re-export portfolio v2 allocator for ``bist_core.portfolio.portfolio_engine_v2``."""

from __future__ import annotations

from bist_core.portfolio_engine_v2 import apply_portfolio_v2_to_trades

__all__ = ["apply_portfolio_v2_to_trades"]
