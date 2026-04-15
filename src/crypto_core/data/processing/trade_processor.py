"""TradeStreamProcessor — deduplication, sequence validation, downstream emission.

Responsibilities:
1. Accept a TradeEvent from EventRouter.
2. Run DataValidator on it (field checks + clock drift + dedup + sequence).
3. On success: call on_validated_trade callback.
4. On failure: log and discard — never propagate corrupt data downstream.

State owned:
- DataValidator (holds SequenceTracker + seen_trade_ids per symbol).

Determinism: same event stream → same validated output sequence.
PRD reference: §4.3 (trade stream dedup, gap detection).
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from crypto_core.data.models.events import TradeEvent
from crypto_core.data.validation.data_validator import DataValidator
from crypto_core.data.validation.errors import ValidationError

logger = logging.getLogger(__name__)

# Downstream callback: receives a fully-validated TradeEvent.
ValidatedTradeCallback = Callable[[TradeEvent], None]


class TradeStreamProcessor:
    """Validates and emits trade events.

    A separate instance should be created per (symbol, exchange) pair to keep
    state boundaries explicit and deterministic.

    Constructor args:
        on_validated_trade: called for every event that passes validation.
        validator: injected DataValidator. Defaults to a new instance with default config.
    """

    def __init__(
        self,
        on_validated_trade: ValidatedTradeCallback,
        validator: Optional[DataValidator] = None,
    ) -> None:
        self._on_validated_trade = on_validated_trade
        self._validator = validator or DataValidator()
        self._accepted_count: int = 0
        self._rejected_count: int = 0

    def process(self, event: TradeEvent) -> None:
        """Validate and emit a single TradeEvent.

        On validation success: calls on_validated_trade(event).
        On validation failure: logs the error with full context and discards the event.
        The feed continues — a single bad event does not halt the stream.
        (Stream-level halts are managed by DataIngestor via FeedState.)
        """
        try:
            self._validator.validate_trade(event)
            self._on_validated_trade(event)
            self._accepted_count += 1
        except ValidationError as exc:
            self._rejected_count += 1
            logger.error(
                "TradeStreamProcessor rejected %s:%s trade_id=%s — %s (context=%s)",
                event.exchange.value,
                event.symbol,
                event.trade_id,
                exc,
                exc.context,
            )

    def reset_stream(self, stream_key: str) -> None:
        """Reset sequence tracking for the given stream (called on reconnect)."""
        self._validator.reset_sequence(stream_key)

    @property
    def accepted_count(self) -> int:
        """Total events accepted since instantiation."""
        return self._accepted_count

    @property
    def rejected_count(self) -> int:
        """Total events rejected since instantiation."""
        return self._rejected_count
