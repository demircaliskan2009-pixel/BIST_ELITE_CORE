"""Portfolio subsystem — public API.

Exports the position/portfolio models, tracker engine, and fill factory.
Phase 6A: SyntheticFillFactory bridges execution decision → portfolio tracking.
"""

from __future__ import annotations

from crypto_core.portfolio.fills import FillValidationError, SyntheticFill, SyntheticFillFactory
from crypto_core.portfolio.models import PortfolioSnapshot, Position, PositionSide
from crypto_core.portfolio.tracker import PositionTracker

__all__ = [
    "FillValidationError",
    "SyntheticFill",
    "SyntheticFillFactory",
    "Position",
    "PortfolioSnapshot",
    "PositionSide",
    "PositionTracker",
]
