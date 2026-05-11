"""Market-state assembler — Phase 7F.

Aggregates per-symbol typed events into MarketDataInput for the pipeline.

Design rules:
- Uses OrderBookManager per symbol for correct level tracking (handles
  snapshot, delta, level removes).
- Accumulates trades and liquidations in bounded FIFOs.
- Mirrors latest MarkPriceEvent for funding family activation.
- Tracks feed connection/recovery strings from DataIngestor feed states.
- assemble() always produces a valid MarketDataInput when the symbol is
  registered; unavailable fields remain 0.0 / None (not invented).
- ValidationError from OrderBookManager is logged and skipped (graceful
  degradation — the pipeline will see stale book data but not crash).

Determinism: same event sequence → same accumulated state → same MarketDataInput.
Not thread-safe: all calls must come from the same thread.

PRD reference: §4.2 Order Book, §4.3 Trade Stream, §4.1 WebSocket Streams.
"""

from __future__ import annotations

import logging
import time

from crypto_core.data.models.events import (
    KlineEvent,
    LiquidationEvent,
    MarkPriceEvent,
    OrderBookEvent,
    TradeEvent,
)
from crypto_core.data.models.order_book import OrderBook
from crypto_core.data.processing.book_manager import OrderBookManager
from crypto_core.data.validation.errors import ValidationError
from crypto_core.orchestrator.models import MarketDataInput
from crypto_core.runtime.models import RuntimeBridgeConfig, SymbolRuntimeState

logger = logging.getLogger(__name__)


class MarketStateAssembler:
    """Per-symbol market state accumulator.

    Accepts typed events and produces MarketDataInput snapshots on demand.

    All fields default to safe/empty values when no data is available.
    Unavailable fields are explicitly kept None or 0 — never invented.

    Usage::

        assembler = MarketStateAssembler(config)
        assembler.on_order_book_event(ob_event)
        assembler.on_trade_event(trade_event)
        assembler.on_mark_price_event(mp_event)

        market_input = assembler.assemble("BTCUSDT", "binance", timestamp_ns)
    """

    def __init__(self, config: RuntimeBridgeConfig) -> None:
        self._config = config
        # Per-symbol mutable runtime state
        self._states: dict[tuple[str, str], SymbolRuntimeState] = {}
        # Per-symbol OrderBookManager (proper level tracking)
        self._book_managers: dict[tuple[str, str], OrderBookManager] = {}

    # ------------------------------------------------------------------
    # Event handlers — called by FeedSessionBridge.on_event()
    # ------------------------------------------------------------------

    def on_order_book_event(self, event: OrderBookEvent) -> None:
        """Apply an OrderBookEvent to the per-symbol book manager and update state."""
        state = self._get_or_create_state(event.symbol, event.exchange.value)
        book_mgr = self._get_or_create_book_manager(event.symbol, event.exchange.value)

        try:
            book_mgr.apply(event)
        except ValidationError as exc:
            logger.warning(
                "OrderBookManager rejected event for %s:%s — %s",
                event.exchange.value,
                event.symbol,
                exc,
            )
            # Do not update state from a rejected event; keep last known values.
            return

        # Extract best bid/ask from the managed book.
        book: OrderBook = book_mgr.book()
        best_bid = book.best_bid()
        best_ask = book.best_ask()

        state.book_has_snapshot = book_mgr.has_snapshot()
        state.book_last_update_ns = event.timestamp_ns
        state.book_bid_count = len(book.bids)
        state.book_ask_count = len(book.asks)

        if best_bid is not None:
            state.book_bid_price = best_bid
            state.book_bid_size = book.bids.get(best_bid)
        if best_ask is not None:
            state.book_ask_price = best_ask
            state.book_ask_size = book.asks.get(best_ask)

    def on_trade_event(self, event: TradeEvent) -> None:
        """Append a trade event to the pending accumulator."""
        state = self._get_or_create_state(event.symbol, event.exchange.value)
        state.pending_trades.append(event)
        # Bound to 2× max_trades_per_cycle to prevent unbounded growth.
        max_stored = self._config.max_trades_per_cycle * 2
        if len(state.pending_trades) > max_stored:
            state.pending_trades = state.pending_trades[-max_stored:]
        state.trade_batch_count += 1

    def on_mark_price_event(self, event: MarkPriceEvent) -> None:
        """Store the latest MarkPriceEvent for this symbol."""
        state = self._get_or_create_state(event.symbol, event.exchange.value)
        state.mark_price_event = event
        state.last_mark_price_ts_ns = event.timestamp_ns

    def on_liquidation_event(self, event: LiquidationEvent) -> None:
        """Append a liquidation event and mark the feed as wired."""
        state = self._get_or_create_state(event.symbol, event.exchange.value)
        state.pending_liquidations.append(event)
        state.liquidation_feed_wired = True
        max_stored = self._config.max_liquidations_per_cycle * 2
        if len(state.pending_liquidations) > max_stored:
            state.pending_liquidations = state.pending_liquidations[-max_stored:]

    def on_kline_event(self, event: KlineEvent) -> None:
        """Acknowledge a kline event — no book update, used only as trigger."""
        # Ensure the state entry exists so the symbol is registered.
        self._get_or_create_state(event.symbol, event.exchange.value)

    def update_feed_state(
        self,
        symbol: str,
        exchange: str,
        connection_state: str,
        recovery_state: str,
    ) -> None:
        """Mirror FeedState strings into per-symbol runtime state."""
        state = self._get_or_create_state(symbol, exchange)
        state.feed_connection_state = connection_state
        state.feed_recovery_state = recovery_state

    def mark_liquidation_wired(self, symbol: str, exchange: str) -> None:
        """Explicitly mark the liquidation feed as wired for this symbol.

        Call this when a liquidation stream subscription is established so
        that empty liquidation_events tuples are passed to the pipeline
        (rather than None, which means 'feed not present').
        """
        state = self._get_or_create_state(symbol, exchange)
        state.liquidation_feed_wired = True

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    def assemble(
        self,
        symbol: str,
        exchange: str,
        timestamp_ns: int | None = None,
    ) -> MarketDataInput | None:
        """Produce a MarketDataInput from current accumulated state.

        Returns None if no state has been registered for this symbol (fail-closed:
        the bridge must not trigger a cycle for an unregistered symbol).

        Unavailable fields are kept at their zero/None defaults — never invented.
        """
        key = (symbol, exchange)
        if key not in self._states:
            return None

        state = self._states[key]
        ts = timestamp_ns if timestamp_ns is not None else time.time_ns()

        # Collect most recent trades (bounded to max_trades_per_cycle).
        trades = tuple(state.pending_trades[-self._config.max_trades_per_cycle :])

        # Liquidation events: None = feed not wired, tuple = feed present (may be empty).
        liquidations: tuple[LiquidationEvent, ...] | None
        if state.liquidation_feed_wired:
            liquidations = tuple(state.pending_liquidations[-self._config.max_liquidations_per_cycle :])
        else:
            liquidations = None

        return MarketDataInput(
            symbol=symbol,
            exchange=exchange,
            timestamp_ns=ts,
            trades=trades,
            book_last_update_ns=state.book_last_update_ns,
            book_has_snapshot=state.book_has_snapshot,
            book_bid_count=state.book_bid_count,
            book_ask_count=state.book_ask_count,
            feed_connection_state=state.feed_connection_state,
            feed_recovery_state=state.feed_recovery_state,
            book_bid_price=state.book_bid_price,
            book_ask_price=state.book_ask_price,
            book_bid_size=state.book_bid_size,
            book_ask_size=state.book_ask_size,
            mark_price_event=state.mark_price_event,
            liquidation_events=liquidations,
        )

    # ------------------------------------------------------------------
    # Post-cycle drains
    # ------------------------------------------------------------------

    def drain_trades(self, symbol: str, exchange: str) -> None:
        """Clear pending trade accumulator after a cycle."""
        state = self._states.get((symbol, exchange))
        if state is not None:
            state.pending_trades = []
            state.trade_batch_count = 0

    def drain_liquidations(self, symbol: str, exchange: str) -> None:
        """Clear pending liquidation accumulator after a cycle."""
        state = self._states.get((symbol, exchange))
        if state is not None:
            state.pending_liquidations = []

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_state(self, symbol: str, exchange: str) -> SymbolRuntimeState | None:
        """Return the mutable state for a symbol, or None if not registered."""
        return self._states.get((symbol, exchange))

    def registered_symbols(self) -> list[tuple[str, str]]:
        """Return all (symbol, exchange) pairs registered with this assembler."""
        return list(self._states.keys())

    def reset_book(self, symbol: str, exchange: str) -> None:
        """Reset the order book for a symbol (called on feed reconnect)."""
        mgr = self._book_managers.get((symbol, exchange))
        if mgr is not None:
            mgr.reset()
        state = self._states.get((symbol, exchange))
        if state is not None:
            state.book_has_snapshot = False
            state.book_bid_price = 0.0
            state.book_ask_price = 0.0
            state.book_bid_size = None
            state.book_ask_size = None
            state.book_bid_count = 0
            state.book_ask_count = 0
            state.book_last_update_ns = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_state(self, symbol: str, exchange: str) -> SymbolRuntimeState:
        key = (symbol, exchange)
        if key not in self._states:
            self._states[key] = SymbolRuntimeState(symbol=symbol, exchange=exchange)
        return self._states[key]

    def _get_or_create_book_manager(self, symbol: str, exchange: str) -> OrderBookManager:
        key = (symbol, exchange)
        if key not in self._book_managers:
            self._book_managers[key] = OrderBookManager(
                symbol=symbol,
                exchange=exchange,
            )
        return self._book_managers[key]
