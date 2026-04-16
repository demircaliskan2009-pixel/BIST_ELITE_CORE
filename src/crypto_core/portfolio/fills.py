"""Synthetic fill model for paper / dry-run position tracking.

Only PAPER and DRY_RUN modes generate SyntheticFills.  LIVE fills are not
supported and will not be added here — they require a broker adapter layer.

PRD reference: §7 Execution Engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from crypto_core.execution.models import ExecutionMode, OrderIntent


@dataclass(frozen=True)
class SyntheticFill:
    """Represents one paper / dry-run fill produced from an approved execution.

    Produced by SyntheticFillFactory from an allowed ExecutionDecision.
    Used as input to PositionTracker to update position state.

    Fields:
      symbol        — trading symbol (e.g. "BTCUSDT")
      exchange      — exchange identifier
      intent        — BUY (open long / close short) or SELL (open short / close long)
      quantity      — base-currency fill size (> 0)
      fill_price    — simulated fill price in USD (price_hint from ExecutionRequest)
      leverage      — leverage at fill time [1.0, 3.0]; default 1.0 for paper
      mode          — PAPER or DRY_RUN
      order_id      — execution engine order_id (from ExecutionDecision)
      timestamp_ns  — fill wall-clock in ns
    """

    symbol: str
    exchange: str
    intent: OrderIntent
    quantity: float  # base-currency size, > 0
    fill_price: float  # USD
    leverage: float  # [1.0, 3.0]
    mode: ExecutionMode
    order_id: str
    timestamp_ns: int


class FillValidationError(Exception):
    """Raised by PositionTracker when a fill is rejected as malformed."""

    pass
