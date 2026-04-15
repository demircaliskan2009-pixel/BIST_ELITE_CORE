"""Funding Rate edge family (Family B) — placeholder v1.

Full funding rate signal requires a dedicated funding rate feed (§4.6).
This v1 is a stub that always returns NEUTRAL with a placeholder evidence
dict. It is structurally complete and will be replaced when the funding
rate adapter is wired in.

Signal logic (v1 placeholder):
  Returns NEUTRAL unconditionally.
  Evidence records the placeholder status.

PRD reference: §1.2 Family B — Funding Rate Arbitrage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from crypto_core.data.models.events import TradeEvent
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection

logger = logging.getLogger(__name__)


@dataclass
class FundingConfig:
    """Reserved for future funding rate adapter configuration."""

    # Will hold: funding_threshold, lookback_hours, min_funding_samples, etc.
    pass


class FundingRateEdge:
    """Funding rate edge — v1 placeholder (always returns NEUTRAL).

    Replace `evaluate()` body when funding rate feed is available.
    The class name, interface, and family tag are final.
    """

    def __init__(self, config: FundingConfig | None = None) -> None:
        self._cfg = config or FundingConfig()

    def evaluate(
        self,
        trades: list[TradeEvent] | tuple[TradeEvent, ...],
        symbol: str,
        exchange: str,
        timestamp_ns: int,
    ) -> EdgeSignal:
        # v1 stub: funding rate feed not yet wired in
        return EdgeSignal(
            family=EdgeFamily.FUNDING_RATE,
            symbol=symbol,
            exchange=exchange,
            direction=SignalDirection.NEUTRAL,
            confidence=0.0,
            score=0.0,
            evidence={
                "status": "placeholder_v1",
                "reason": "funding_rate_feed_not_connected",
            },
            timestamp_ns=timestamp_ns,
            is_valid=True,  # Structurally valid, just no signal
            block_reason=None,
        )
