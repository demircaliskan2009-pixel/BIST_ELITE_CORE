"""Feed-to-session runtime bridge — Phase 7F.

Routes typed market events to MarketStateAssembler and drives
PaperLiveSession.process_event() according to the configured trigger policy.

Trigger policies (configured via RuntimeBridgeConfig.trigger_policy):
  MARK_PRICE:  cycle on every MarkPriceEvent (default, ~3-5 s on Binance).
  KLINE_CLOSE: cycle on closed KlineEvent (bar-close driven).
  TRADE_BATCH: cycle after accumulating trade_batch_size trades.
  TOP_OF_BOOK: cycle on every top-of-book price change.

Recovery-aware:
  Cycles are blocked when the feed for a symbol is not READY (i.e. is in
  recovery, disconnected, or failed). Suppressed triggers are recorded.

Determinism:
  same event sequence → same trigger decisions → same session outputs.
  Dedup by (symbol, exchange, reason, trigger_ts_ns) prevents duplicate cycles.

Paper-only:
  Enforced by PaperLiveSession — the bridge does not re-check.

Not thread-safe — all on_event() calls must come from the same thread.

PRD reference: §2 System Orchestration, §4.1-§4.5 Data Layer.
"""

from __future__ import annotations

import logging

from crypto_core.data.models.events import (
    KlineEvent,
    LiquidationEvent,
    MarkPriceEvent,
    OrderBookEvent,
    TradeEvent,
)
from crypto_core.data.models.feed_state import FeedState
from crypto_core.runtime.assembler import MarketStateAssembler
from crypto_core.runtime.models import (
    CycleTrigger,
    RuntimeBridgeConfig,
    TriggerPolicy,
    TriggerReason,
)
from crypto_core.session.engine import PaperLiveSession
from crypto_core.session.models import CycleResult, SessionMode

logger = logging.getLogger(__name__)


class FeedSessionBridge:
    """Connects typed event stream to PaperLiveSession with a trigger policy.

    Responsibilities:
    - Accept typed events from DataIngestor via on_event().
    - Route events to MarketStateAssembler per symbol.
    - Evaluate the trigger policy; fire a session cycle when policy fires.
    - Deduplicate triggers by (symbol, exchange, reason, trigger_ts_ns).
    - Block cycles if the feed is in recovery or the session is not RUNNING.
    - Record a CycleTrigger audit record for every trigger decision.

    Not thread-safe — all on_event() calls must come from the same thread.
    """

    def __init__(
        self,
        session: PaperLiveSession,
        assembler: MarketStateAssembler,
        config: RuntimeBridgeConfig,
        feed_states: dict[str, FeedState] | None = None,
    ) -> None:
        """Construct the bridge.

        Args:
            session:     PaperLiveSession to drive.
            assembler:   MarketStateAssembler that accumulates market state.
            config:      RuntimeBridgeConfig with trigger policy and limits.
            feed_states: Optional dict mapping feed_key → FeedState from the
                         DataIngestor.  When provided, recovery-state gating is
                         active.  When None (replay/test mode), gating is skipped.
        """
        self._session = session
        self._assembler = assembler
        self._config = config
        self._feed_states: dict[str, FeedState] | None = feed_states

        # Audit trail of every trigger decision.
        self._triggers: list[CycleTrigger] = []

        # Aggregate counters.
        self._event_count: int = 0
        self._trigger_count: int = 0
        self._suppressed_count: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_event(self, event: object) -> CycleResult | None:
        """Process one typed event.

        Routes the event to the assembler and evaluates the trigger policy.

        Returns:
            CycleResult if a session cycle was fired; None otherwise.
        """
        self._event_count += 1

        if isinstance(event, OrderBookEvent):
            self._assembler.on_order_book_event(event)
            self._sync_feed_state(event.symbol, event.exchange.value)
            if self._config.trigger_policy == TriggerPolicy.TOP_OF_BOOK:
                return self._maybe_trigger_top_of_book(event.symbol, event.exchange.value, event.timestamp_ns)

        elif isinstance(event, TradeEvent):
            self._assembler.on_trade_event(event)
            if self._config.trigger_policy == TriggerPolicy.TRADE_BATCH:
                state = self._assembler.get_state(event.symbol, event.exchange.value)
                if state is not None and state.trade_batch_count >= self._config.trade_batch_size:
                    return self._maybe_trigger(
                        event.symbol,
                        event.exchange.value,
                        event.timestamp_ns,
                        TriggerReason.TRADE_BATCH,
                    )

        elif isinstance(event, MarkPriceEvent):
            self._assembler.on_mark_price_event(event)
            self._sync_feed_state(event.symbol, event.exchange.value)
            if self._config.trigger_policy == TriggerPolicy.MARK_PRICE:
                return self._maybe_trigger(
                    event.symbol,
                    event.exchange.value,
                    event.timestamp_ns,
                    TriggerReason.MARK_PRICE,
                )

        elif isinstance(event, LiquidationEvent):
            self._assembler.on_liquidation_event(event)

        elif isinstance(event, KlineEvent):
            self._assembler.on_kline_event(event)
            if self._config.trigger_policy == TriggerPolicy.KLINE_CLOSE and event.is_closed:
                return self._maybe_trigger(
                    event.symbol,
                    event.exchange.value,
                    event.open_time_ns,  # deterministic: use bar open time as key
                    TriggerReason.KLINE_CLOSE,
                )

        return None

    @property
    def trigger_log(self) -> list[CycleTrigger]:
        """Snapshot of the full trigger audit trail (copy)."""
        return list(self._triggers)

    @property
    def event_count(self) -> int:
        """Total events processed."""
        return self._event_count

    @property
    def trigger_count(self) -> int:
        """Total session cycles fired."""
        return self._trigger_count

    @property
    def suppressed_count(self) -> int:
        """Total trigger decisions that were suppressed."""
        return self._suppressed_count

    # ------------------------------------------------------------------
    # Internal trigger logic
    # ------------------------------------------------------------------

    def _maybe_trigger(
        self,
        symbol: str,
        exchange: str,
        trigger_ts_ns: int,
        reason: TriggerReason,
    ) -> CycleResult | None:
        """Evaluate whether to fire a session cycle.

        Steps (in order):
        1. Recovery check — block if feed is not READY.
        2. Session mode check — block if not RUNNING.
        3. Dedup — skip if this exact (reason, trigger_ts_ns) was already seen.
        4. Assemble MarketDataInput — fail-closed if symbol not registered.
        5. Fire cycle.
        6. Drain accumulators.
        7. Record dedup marker.
        8. Record CycleTrigger audit record.
        """
        # 1. Recovery check.
        if not self._is_feed_ready(symbol, exchange):
            self._record_suppressed(symbol, exchange, trigger_ts_ns, TriggerReason.RECOVERY_BLOCKED)
            return None

        # 2. Session mode check.
        if self._session.mode != SessionMode.RUNNING:
            self._record_suppressed(symbol, exchange, trigger_ts_ns, TriggerReason.SESSION_BLOCKED)
            return None

        # 3. Dedup.
        dedup_key = reason.value  # dedup per (symbol, exchange, reason) → last ts
        state = self._assembler.get_state(symbol, exchange)
        if state is not None and state.last_trigger_ts_ns.get(dedup_key) == trigger_ts_ns:
            self._record_suppressed(symbol, exchange, trigger_ts_ns, TriggerReason.DEDUP_SUPPRESSED)
            return None

        # 4. Assemble MarketDataInput.
        market_data = self._assembler.assemble(symbol, exchange, timestamp_ns=trigger_ts_ns)
        if market_data is None:
            self._record_suppressed(symbol, exchange, trigger_ts_ns, TriggerReason.ASSEMBLER_INCOMPLETE)
            return None

        # 5. Fire the cycle.
        cycle_result = self._session.process_event(market_data)

        # 6. Drain accumulators (consume pending events from this cycle window).
        self._assembler.drain_trades(symbol, exchange)
        self._assembler.drain_liquidations(symbol, exchange)

        # 7. Record dedup marker.
        if state is not None:
            state.last_trigger_ts_ns[dedup_key] = trigger_ts_ns

        # 8. Audit record.
        self._trigger_count += 1
        self._triggers.append(
            CycleTrigger(
                symbol=symbol,
                exchange=exchange,
                trigger_ts_ns=trigger_ts_ns,
                reason=reason,
                cycle_number=cycle_result.cycle_number,
                suppressed=False,
                suppression_reason=None,
            )
        )

        return cycle_result

    def _maybe_trigger_top_of_book(
        self,
        symbol: str,
        exchange: str,
        trigger_ts_ns: int,
    ) -> CycleResult | None:
        """TOP_OF_BOOK policy: only trigger when best bid or ask changes."""
        state = self._assembler.get_state(symbol, exchange)
        if state is None:
            return None

        # Suppress if top-of-book hasn't changed since the last cycle.
        if state.book_bid_price == state.last_top_bid and state.book_ask_price == state.last_top_ask:
            self._record_suppressed(symbol, exchange, trigger_ts_ns, TriggerReason.DEDUP_SUPPRESSED)
            return None

        # Record the new top before triggering to detect future no-ops.
        state.last_top_bid = state.book_bid_price
        state.last_top_ask = state.book_ask_price

        return self._maybe_trigger(symbol, exchange, trigger_ts_ns, TriggerReason.TOP_OF_BOOK)

    # ------------------------------------------------------------------
    # Feed-state helpers
    # ------------------------------------------------------------------

    def _sync_feed_state(self, symbol: str, exchange: str) -> None:
        """Mirror feed connection/recovery strings into the assembler state."""
        conn = self._get_feed_connection(symbol, exchange)
        rec = self._get_feed_recovery(symbol, exchange)
        self._assembler.update_feed_state(symbol, exchange, conn, rec)

    def _is_feed_ready(self, symbol: str, exchange: str) -> bool:
        """Returns True if the feed is live (CONNECTED + READY).

        If feed_states is None (replay/test mode), always returns True.
        """
        if self._feed_states is None:
            return True  # replay / test mode — skip recovery gating
        feed_key = f"{exchange}:{symbol}"
        state = self._feed_states.get(feed_key)
        if state is None:
            return False  # unknown feed → block
        return state.is_live()

    def _get_feed_connection(self, symbol: str, exchange: str) -> str:
        if self._feed_states is None:
            return "connected"
        feed_key = f"{exchange}:{symbol}"
        state = self._feed_states.get(feed_key)
        return state.connection_state.value if state is not None else "disconnected"

    def _get_feed_recovery(self, symbol: str, exchange: str) -> str:
        if self._feed_states is None:
            return "ready"
        feed_key = f"{exchange}:{symbol}"
        state = self._feed_states.get(feed_key)
        return state.recovery_state.value if state is not None else "idle"

    def _record_suppressed(
        self,
        symbol: str,
        exchange: str,
        trigger_ts_ns: int,
        reason: TriggerReason,
    ) -> None:
        self._suppressed_count += 1
        self._triggers.append(
            CycleTrigger(
                symbol=symbol,
                exchange=exchange,
                trigger_ts_ns=trigger_ts_ns,
                reason=reason,
                cycle_number=0,
                suppressed=True,
                suppression_reason=reason.value,
            )
        )
        logger.debug(
            "Cycle suppressed %s:%s reason=%s ts=%d",
            exchange,
            symbol,
            reason.value,
            trigger_ts_ns,
        )
