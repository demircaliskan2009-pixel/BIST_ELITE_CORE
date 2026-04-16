"""Funding Rate edge family (Family B) — v1 paper signal.

Signal logic (v1 — from MarkPriceEvent funding_rate field):
  If mark_price_event is not provided  → is_valid=False, status="unavailable".
  If |funding_rate| < rate_threshold   → NEUTRAL (no meaningful deviation).
  If funding_rate  >  rate_threshold   → SELL (longs overpaying → bearish).
  If funding_rate  < -rate_threshold   → BUY  (shorts overpaying → bullish).

Confidence is scaled linearly from threshold to 10× threshold (capped at 1.0).

Activation requirement:
  Caller (EdgeEngine via ActivationMatrix) must block this family when
  mark_price_event is None; the evaluator also returns is_valid=False as a
  belt-and-suspenders check.

PRD reference: §1.2 Family B — Funding Rate Arbitrage / §1.9 Funding Rate MR.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from crypto_core.data.models.events import MarkPriceEvent, TradeEvent
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection

logger = logging.getLogger(__name__)

#: Default threshold: 0.05% per 8-hour settlement period.
_DEFAULT_RATE_THRESHOLD: float = 0.0005


@dataclass
class FundingConfig:
    """Configuration for the FundingRateEdge v1 signal."""

    #: Minimum |funding_rate| to generate a non-neutral signal.
    rate_threshold: float = _DEFAULT_RATE_THRESHOLD


class FundingRateEdge:
    """Funding rate edge family (Family B) — deterministic v1 paper signal.

    Requires a MarkPriceEvent from the current evaluation cycle.
    Returns is_valid=False when the event is absent (fail-closed, not neutral).

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
        mark_price_event: MarkPriceEvent | None = None,
    ) -> EdgeSignal:
        """Evaluate funding rate signal.

        Args:
            trades: current trade stream (used for symbol/exchange context only).
            symbol: market symbol.
            exchange: exchange identifier.
            timestamp_ns: evaluation timestamp.
            mark_price_event: current MarkPriceEvent containing funding_rate.
                              If None, returns is_valid=False (unavailable).

        Returns:
            EdgeSignal with explicit status in evidence.
        """
        cfg = self._cfg
        family = EdgeFamily.FUNDING_RATE

        # Belt-and-suspenders: should be blocked by ActivationMatrix before here.
        if mark_price_event is None:
            return EdgeSignal(
                family=family,
                symbol=symbol,
                exchange=exchange,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                score=0.0,
                evidence={
                    "status": "unavailable",
                    "reason": "mark_price_event_not_provided",
                    "missing_inputs": ["mark_price_event"],
                },
                timestamp_ns=timestamp_ns,
                is_valid=False,
                block_reason="funding_feed_unavailable",
            )

        rate = mark_price_event.funding_rate
        abs_rate = abs(rate)

        evidence: dict[str, object] = {
            "status": "active",
            "funding_rate": rate,
            "rate_threshold": cfg.rate_threshold,
            "mark_price": mark_price_event.mark_price,
            "index_price": mark_price_event.index_price,
            "next_funding_time_ns": mark_price_event.next_funding_time_ns,
        }

        if abs_rate < cfg.rate_threshold:
            return EdgeSignal(
                family=family,
                symbol=symbol,
                exchange=exchange,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                score=rate,
                evidence=evidence,
                timestamp_ns=timestamp_ns,
                is_valid=True,
                block_reason=None,
            )

        # Scale confidence: 0 at threshold, 1.0 at 10× threshold
        confidence = min(1.0, (abs_rate - cfg.rate_threshold) / (cfg.rate_threshold * 9))

        # Positive funding → longs overpaying → bearish pressure → SELL.
        # Negative funding → shorts overpaying → bullish pressure → BUY.
        direction = SignalDirection.SELL if rate > 0 else SignalDirection.BUY

        return EdgeSignal(
            family=family,
            symbol=symbol,
            exchange=exchange,
            direction=direction,
            confidence=confidence,
            score=rate,
            evidence=evidence,
            timestamp_ns=timestamp_ns,
            is_valid=True,
            block_reason=None,
        )
