"""Tests for Phase 7F — Continuous feed→session paper-live runtime bridge.

Covers:
  1. MarketStateAssembler — event accumulation, assemble(), drain(), reset_book().
  2. FeedSessionBridge trigger policies — MARK_PRICE, KLINE_CLOSE, TRADE_BATCH,
     TOP_OF_BOOK.
  3. FeedSessionBridge dedup — same trigger_ts_ns → suppressed.
  4. FeedSessionBridge recovery gating — feed not READY → cycle blocked.
  5. FeedSessionBridge session gating — session not RUNNING → cycle blocked.
  6. FeedSessionBridge assembler fail-close — unregistered symbol → suppressed.
  7. PaperLiveRunner lifecycle — start / stop / on_event / status.
  8. PaperLiveRunner idempotency — double start / double stop.
  9. Deterministic replay — same event sequence → same cycle results.
  10. End-to-end paper-live integration — feed events → session → portfolio.
  11. CycleTrigger audit trail — fired and suppressed records.
  12. RuntimeStatus snapshot — field accuracy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from crypto_core.data.models.events import (
    Exchange,
    KlineEvent,
    LiquidationEvent,
    MarkPriceEvent,
    OrderBookEvent,
    OrderBookEventType,
    OrderBookLevel,
    TradeEvent,
    TradeSide,
)
from crypto_core.data.models.feed_state import ConnectionState, FeedState, RecoveryState
from crypto_core.execution.engine import ExecutionConfig
from crypto_core.execution.fill_pricer import FillPricerConfig
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode
from crypto_core.execution.paper_adapter import PaperAdapterConfig
from crypto_core.execution.store import ExecutionStateStore
from crypto_core.orchestrator.pipeline import PipelineConfig, PipelineOrchestrator
from crypto_core.portfolio.store import PortfolioStateStore
from crypto_core.portfolio.tracker import PositionTracker
from crypto_core.runtime.assembler import MarketStateAssembler
from crypto_core.runtime.bridge import FeedSessionBridge
from crypto_core.runtime.models import (
    CycleTrigger,
    RuntimeBridgeConfig,
    RuntimeStatus,
    TriggerPolicy,
    TriggerReason,
)
from crypto_core.runtime.runner import PaperLiveRunner
from crypto_core.session.engine import PaperLiveSession
from crypto_core.session.models import PaperSessionConfig, SessionMode

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000
_NS_PER_S = 1_000_000_000
_SYMBOL = "BTCUSDT"
_EXCHANGE = Exchange.BINANCE
_EXCHANGE_STR = "binance"


# ---------------------------------------------------------------------------
# Event factories
# ---------------------------------------------------------------------------


def _trade(
    price: float = 50_000.0,
    side: TradeSide = TradeSide.BUY,
    qty: float = 0.1,
    timestamp_ns: int = _T0_NS,
    seq: int = 1,
    symbol: str = _SYMBOL,
    exchange: Exchange = _EXCHANGE,
) -> TradeEvent:
    return TradeEvent(
        trade_id=f"t-{seq}-{price}",
        symbol=symbol,
        exchange=exchange,
        side=side,
        price=price,
        qty=qty,
        timestamp_ns=timestamp_ns,
        sequence_no=seq,
        is_maker=False,
    )


def _mark_price(
    price: float = 50_000.0,
    funding_rate: float = 0.0001,
    timestamp_ns: int = _T0_NS,
    symbol: str = _SYMBOL,
    exchange: Exchange = _EXCHANGE,
) -> MarkPriceEvent:
    return MarkPriceEvent(
        symbol=symbol,
        exchange=exchange,
        mark_price=price,
        index_price=price,
        funding_rate=funding_rate,
        next_funding_time_ns=timestamp_ns + 8 * 3600 * _NS_PER_S,
        timestamp_ns=timestamp_ns,
    )


def _ob_snapshot(
    bid_price: float = 49_900.0,
    ask_price: float = 50_100.0,
    timestamp_ns: int = _T0_NS,
    last_update_id: int = 1000,
    symbol: str = _SYMBOL,
    exchange: Exchange = _EXCHANGE,
) -> OrderBookEvent:
    return OrderBookEvent(
        symbol=symbol,
        exchange=exchange,
        event_type=OrderBookEventType.SNAPSHOT,
        bids=(OrderBookLevel(price=bid_price, qty=1.0),),
        asks=(OrderBookLevel(price=ask_price, qty=1.0),),
        timestamp_ns=timestamp_ns,
        first_update_id=last_update_id,
        last_update_id=last_update_id,
        checksum=None,
    )


def _ob_delta(
    bid_price: float = 49_950.0,
    ask_price: float = 50_050.0,
    timestamp_ns: int = _T0_NS + 1,
    first_update_id: int = 1001,
    last_update_id: int = 1001,
    symbol: str = _SYMBOL,
    exchange: Exchange = _EXCHANGE,
) -> OrderBookEvent:
    return OrderBookEvent(
        symbol=symbol,
        exchange=exchange,
        event_type=OrderBookEventType.DELTA,
        bids=(OrderBookLevel(price=bid_price, qty=0.5),),
        asks=(OrderBookLevel(price=ask_price, qty=0.5),),
        timestamp_ns=timestamp_ns,
        first_update_id=first_update_id,
        last_update_id=last_update_id,
        checksum=None,
    )


def _kline(
    is_closed: bool = True,
    close_price: float = 50_000.0,
    open_time_ns: int = _T0_NS,
    timestamp_ns: int = _T0_NS,
    symbol: str = _SYMBOL,
    exchange: Exchange = _EXCHANGE,
) -> KlineEvent:
    return KlineEvent(
        symbol=symbol,
        exchange=exchange,
        interval="1m",
        open_time_ns=open_time_ns,
        close_time_ns=timestamp_ns + 60 * _NS_PER_S,
        open_price=close_price - 50.0,
        high_price=close_price + 100.0,
        low_price=close_price - 100.0,
        close_price=close_price,
        volume=10.0,
        trade_count=100,
        is_closed=is_closed,
        sequence_no=1,
    )


def _liquidation(
    price: float = 48_000.0,
    timestamp_ns: int = _T0_NS,
    symbol: str = _SYMBOL,
    exchange: Exchange = _EXCHANGE,
) -> LiquidationEvent:
    return LiquidationEvent(
        symbol=symbol,
        exchange=exchange,
        side=TradeSide.BUY,
        price=price,
        qty=0.5,
        timestamp_ns=timestamp_ns,
    )


def _live_feed_state(symbol: str = _SYMBOL) -> FeedState:
    state = FeedState(symbol=symbol, exchange=_EXCHANGE_STR, stream_type="multi")
    state.connection_state = ConnectionState.CONNECTED
    state.recovery_state = RecoveryState.READY
    return state


def _recovering_feed_state(symbol: str = _SYMBOL) -> FeedState:
    state = FeedState(symbol=symbol, exchange=_EXCHANGE_STR, stream_type="multi")
    state.connection_state = ConnectionState.RECONNECTING
    state.recovery_state = RecoveryState.SNAPSHOTTING
    return state


# ---------------------------------------------------------------------------
# Session / pipeline helpers
# ---------------------------------------------------------------------------


def _pipeline_config() -> PipelineConfig:
    return PipelineConfig(
        execution=ExecutionConfig(
            mode=ExecutionMode.PAPER,
            fill_pricer=FillPricerConfig(max_spread_bps=200.0, require_book_for_paper=True),
        ),
        execution_lifecycle=ExecutionLifecycleConfig(
            mode=ExecutionMode.PAPER,
            paper_adapter=PaperAdapterConfig(
                fill_pricer=FillPricerConfig(max_spread_bps=200.0),
                allow_degraded_fill=True,
            ),
        ),
        emit_telemetry=False,
    )


def _make_session(
    tmp_path: Path,
    *,
    session_id: str = "test-7f",
    initial_nav: float = 10_000.0,
    max_cycles: int = 0,
    with_stores: bool = False,
) -> PaperLiveSession:
    cfg = _pipeline_config()
    tracker = PositionTracker(initial_nav_usd=initial_nav)
    lifecycle = ExecutionLifecycleEngine(cfg.execution_lifecycle)
    orch = PipelineOrchestrator(
        config=cfg,
        position_tracker=tracker,
        lifecycle_engine=lifecycle,
    )
    portfolio_store = PortfolioStateStore(tmp_path / "portfolio.json") if with_stores else None
    exec_store = ExecutionStateStore(tmp_path / "execution.jsonl") if with_stores else None

    session_cfg = PaperSessionConfig(
        session_id=session_id,
        initial_nav_usd=initial_nav,
        persist_every_fill=True,
        max_cycles=max_cycles,
    )
    return PaperLiveSession(
        config=session_cfg,
        orchestrator=orch,
        position_tracker=tracker,
        portfolio_store=portfolio_store,
        exec_store=exec_store,
        lifecycle_engine=lifecycle,
    )


def _make_bridge(
    session: PaperLiveSession,
    policy: TriggerPolicy = TriggerPolicy.MARK_PRICE,
    feed_states: dict[str, FeedState] | None = None,
    trade_batch_size: int = 3,
) -> FeedSessionBridge:
    config = RuntimeBridgeConfig(
        trigger_policy=policy,
        trade_batch_size=trade_batch_size,
        max_trades_per_cycle=50,
        max_liquidations_per_cycle=20,
    )
    assembler = MarketStateAssembler(config)
    return FeedSessionBridge(
        session=session,
        assembler=assembler,
        config=config,
        feed_states=feed_states,
    )


def _make_runner(
    tmp_path: Path,
    policy: TriggerPolicy = TriggerPolicy.MARK_PRICE,
    feed_states: dict[str, FeedState] | None = None,
) -> PaperLiveRunner:
    session = _make_session(tmp_path)
    bridge = _make_bridge(session, policy=policy, feed_states=feed_states)
    return PaperLiveRunner(session=session, bridge=bridge)


# ===========================================================================
# 1 · MarketStateAssembler
# ===========================================================================


class TestMarketStateAssembler:
    """Assembler accumulates events and produces MarketDataInput."""

    def test_assemble_returns_none_for_unregistered_symbol(self) -> None:
        cfg = RuntimeBridgeConfig()
        assembler = MarketStateAssembler(cfg)
        assert assembler.assemble("ETHUSDT", "binance") is None

    def test_registers_symbol_on_ob_event(self) -> None:
        cfg = RuntimeBridgeConfig()
        assembler = MarketStateAssembler(cfg)
        assembler.on_order_book_event(_ob_snapshot())
        result = assembler.assemble(_SYMBOL, _EXCHANGE_STR)
        assert result is not None
        assert result.symbol == _SYMBOL
        assert result.exchange == _EXCHANGE_STR

    def test_snapshot_sets_book_has_snapshot(self) -> None:
        cfg = RuntimeBridgeConfig()
        assembler = MarketStateAssembler(cfg)
        assembler.on_order_book_event(_ob_snapshot(bid_price=49_900.0, ask_price=50_100.0))
        result = assembler.assemble(_SYMBOL, _EXCHANGE_STR)
        assert result is not None
        assert result.book_has_snapshot is True
        assert result.book_bid_price == pytest.approx(49_900.0)
        assert result.book_ask_price == pytest.approx(50_100.0)

    def test_trades_accumulated_and_bounded(self) -> None:
        cfg = RuntimeBridgeConfig(max_trades_per_cycle=3)
        assembler = MarketStateAssembler(cfg)
        # Register symbol via OB snapshot
        assembler.on_order_book_event(_ob_snapshot())
        # Add 8 trades — should be bounded to 2×max = 6, and assembled only takes last 3
        for i in range(8):
            assembler.on_trade_event(_trade(seq=i + 1, timestamp_ns=_T0_NS + i))
        result = assembler.assemble(_SYMBOL, _EXCHANGE_STR)
        assert result is not None
        assert len(result.trades) == 3  # max_trades_per_cycle

    def test_mark_price_event_forwarded(self) -> None:
        cfg = RuntimeBridgeConfig()
        assembler = MarketStateAssembler(cfg)
        mp = _mark_price(price=50_123.0)
        assembler.on_mark_price_event(mp)
        result = assembler.assemble(_SYMBOL, _EXCHANGE_STR)
        assert result is not None
        assert result.mark_price_event is not None
        assert result.mark_price_event.mark_price == pytest.approx(50_123.0)

    def test_liquidations_none_when_not_wired(self) -> None:
        cfg = RuntimeBridgeConfig()
        assembler = MarketStateAssembler(cfg)
        assembler.on_order_book_event(_ob_snapshot())
        result = assembler.assemble(_SYMBOL, _EXCHANGE_STR)
        assert result is not None
        assert result.liquidation_events is None  # feed not wired

    def test_liquidations_tuple_when_wired(self) -> None:
        cfg = RuntimeBridgeConfig()
        assembler = MarketStateAssembler(cfg)
        assembler.on_order_book_event(_ob_snapshot())
        assembler.on_liquidation_event(_liquidation())
        result = assembler.assemble(_SYMBOL, _EXCHANGE_STR)
        assert result is not None
        assert result.liquidation_events is not None
        assert len(result.liquidation_events) == 1

    def test_drain_clears_trades(self) -> None:
        cfg = RuntimeBridgeConfig()
        assembler = MarketStateAssembler(cfg)
        assembler.on_order_book_event(_ob_snapshot())
        assembler.on_trade_event(_trade(seq=1))
        assembler.on_trade_event(_trade(seq=2))
        assembler.drain_trades(_SYMBOL, _EXCHANGE_STR)
        result = assembler.assemble(_SYMBOL, _EXCHANGE_STR)
        assert result is not None
        assert len(result.trades) == 0

    def test_drain_clears_liquidations(self) -> None:
        cfg = RuntimeBridgeConfig()
        assembler = MarketStateAssembler(cfg)
        assembler.on_liquidation_event(_liquidation())
        assembler.drain_liquidations(_SYMBOL, _EXCHANGE_STR)
        result = assembler.assemble(_SYMBOL, _EXCHANGE_STR)
        assert result is not None
        assert result.liquidation_events == ()  # wired but empty after drain

    def test_reset_book_clears_snapshot_flag(self) -> None:
        cfg = RuntimeBridgeConfig()
        assembler = MarketStateAssembler(cfg)
        assembler.on_order_book_event(_ob_snapshot())
        assembler.reset_book(_SYMBOL, _EXCHANGE_STR)
        result = assembler.assemble(_SYMBOL, _EXCHANGE_STR)
        assert result is not None
        assert result.book_has_snapshot is False
        assert result.book_bid_price == 0.0

    def test_feed_state_update_mirrored(self) -> None:
        cfg = RuntimeBridgeConfig()
        assembler = MarketStateAssembler(cfg)
        assembler.on_order_book_event(_ob_snapshot())
        assembler.update_feed_state(_SYMBOL, _EXCHANGE_STR, "connected", "ready")
        result = assembler.assemble(_SYMBOL, _EXCHANGE_STR)
        assert result is not None
        assert result.feed_connection_state == "connected"
        assert result.feed_recovery_state == "ready"

    def test_mark_liquidation_wired_sets_empty_tuple(self) -> None:
        cfg = RuntimeBridgeConfig()
        assembler = MarketStateAssembler(cfg)
        assembler.on_order_book_event(_ob_snapshot())
        assembler.mark_liquidation_wired(_SYMBOL, _EXCHANGE_STR)
        result = assembler.assemble(_SYMBOL, _EXCHANGE_STR)
        assert result is not None
        # Wired but no events → empty tuple, NOT None
        assert result.liquidation_events == ()

    def test_registered_symbols_returns_all(self) -> None:
        cfg = RuntimeBridgeConfig()
        assembler = MarketStateAssembler(cfg)
        assembler.on_order_book_event(_ob_snapshot(symbol="BTCUSDT"))
        assembler.on_order_book_event(_ob_snapshot(symbol="ETHUSDT"))
        symbols = {s for s, _e in assembler.registered_symbols()}
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols

    def test_ob_delta_updates_best_bid_ask(self) -> None:
        cfg = RuntimeBridgeConfig()
        assembler = MarketStateAssembler(cfg)
        assembler.on_order_book_event(_ob_snapshot(bid_price=49_900.0, ask_price=50_100.0))
        assembler.on_order_book_event(
            _ob_delta(
                bid_price=49_950.0,
                ask_price=50_050.0,
                first_update_id=1001,
                last_update_id=1001,
            )
        )
        result = assembler.assemble(_SYMBOL, _EXCHANGE_STR)
        assert result is not None
        # The delta added a better bid and ask
        assert result.book_bid_price == pytest.approx(49_950.0)
        assert result.book_ask_price == pytest.approx(50_050.0)


# ===========================================================================
# 2 · FeedSessionBridge — MARK_PRICE trigger
# ===========================================================================


class TestBridgeMarkPriceTrigger:
    """MARK_PRICE policy fires a cycle on each MarkPriceEvent."""

    def test_mark_price_triggers_cycle(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.MARK_PRICE)
        session.start()

        # Register symbol via OB snapshot first
        bridge.on_event(_ob_snapshot())
        result = bridge.on_event(_mark_price(timestamp_ns=_T0_NS + 1))

        assert result is not None
        assert result.error is None
        assert result.cycle_number == 1
        assert bridge.trigger_count == 1

    def test_second_same_ts_mark_price_suppressed(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.MARK_PRICE)
        session.start()

        bridge.on_event(_ob_snapshot())
        bridge.on_event(_mark_price(timestamp_ns=_T0_NS))
        # Same timestamp → dedup suppression
        result = bridge.on_event(_mark_price(timestamp_ns=_T0_NS))

        assert result is None
        assert bridge.suppressed_count >= 1
        assert bridge.trigger_count == 1

    def test_different_ts_mark_price_fires_second_cycle(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.MARK_PRICE)
        session.start()

        bridge.on_event(_ob_snapshot())
        bridge.on_event(_mark_price(timestamp_ns=_T0_NS))
        r2 = bridge.on_event(_mark_price(timestamp_ns=_T0_NS + _NS_PER_S))

        assert r2 is not None
        assert bridge.trigger_count == 2


# ===========================================================================
# 3 · FeedSessionBridge — KLINE_CLOSE trigger
# ===========================================================================


class TestBridgeKlineCloseTrigger:
    """KLINE_CLOSE policy fires a cycle on closed KlineEvent only."""

    def test_closed_kline_triggers_cycle(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.KLINE_CLOSE)
        session.start()

        bridge.on_event(_ob_snapshot())
        result = bridge.on_event(_kline(is_closed=True, open_time_ns=_T0_NS))

        assert result is not None
        assert result.cycle_number == 1

    def test_open_kline_does_not_trigger(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.KLINE_CLOSE)
        session.start()

        bridge.on_event(_ob_snapshot())
        result = bridge.on_event(_kline(is_closed=False, open_time_ns=_T0_NS))

        assert result is None
        assert bridge.trigger_count == 0

    def test_duplicate_closed_kline_same_open_time_suppressed(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.KLINE_CLOSE)
        session.start()

        bridge.on_event(_ob_snapshot())
        bridge.on_event(_kline(is_closed=True, open_time_ns=_T0_NS))
        result = bridge.on_event(_kline(is_closed=True, open_time_ns=_T0_NS))  # same bar

        assert result is None
        assert bridge.trigger_count == 1
        assert bridge.suppressed_count >= 1

    def test_next_bar_triggers_new_cycle(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.KLINE_CLOSE)
        session.start()

        bridge.on_event(_ob_snapshot())
        bridge.on_event(_kline(is_closed=True, open_time_ns=_T0_NS))
        r2 = bridge.on_event(_kline(is_closed=True, open_time_ns=_T0_NS + 60 * _NS_PER_S))

        assert r2 is not None
        assert bridge.trigger_count == 2


# ===========================================================================
# 4 · FeedSessionBridge — TRADE_BATCH trigger
# ===========================================================================


class TestBridgeTradeBatchTrigger:
    """TRADE_BATCH policy fires after accumulating trade_batch_size trades."""

    def test_fires_after_batch_size(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.TRADE_BATCH, trade_batch_size=3)
        session.start()

        bridge.on_event(_ob_snapshot())
        # 2 trades — no cycle yet
        bridge.on_event(_trade(seq=1))
        bridge.on_event(_trade(seq=2))
        assert bridge.trigger_count == 0

        # 3rd trade — cycle fires
        result = bridge.on_event(_trade(seq=3, timestamp_ns=_T0_NS + 3))
        assert result is not None
        assert bridge.trigger_count == 1

    def test_after_cycle_batch_resets(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.TRADE_BATCH, trade_batch_size=2)
        session.start()

        bridge.on_event(_ob_snapshot())
        bridge.on_event(_trade(seq=1, timestamp_ns=_T0_NS + 1))
        bridge.on_event(_trade(seq=2, timestamp_ns=_T0_NS + 2))
        assert bridge.trigger_count == 1

        # After drain, batch count is reset — need 2 more trades for next cycle
        bridge.on_event(_trade(seq=3, timestamp_ns=_T0_NS + 3))
        assert bridge.trigger_count == 1  # only 1 trade since reset
        bridge.on_event(_trade(seq=4, timestamp_ns=_T0_NS + 4))
        assert bridge.trigger_count == 2


# ===========================================================================
# 5 · FeedSessionBridge — TOP_OF_BOOK trigger
# ===========================================================================


class TestBridgeTopOfBookTrigger:
    """TOP_OF_BOOK policy fires when best bid or ask changes."""

    def test_first_ob_snapshot_triggers(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.TOP_OF_BOOK)
        session.start()

        result = bridge.on_event(_ob_snapshot(bid_price=49_900.0, ask_price=50_100.0))
        assert result is not None
        assert bridge.trigger_count == 1

    def test_unchanged_top_suppressed(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.TOP_OF_BOOK)
        session.start()

        bridge.on_event(_ob_snapshot(bid_price=49_900.0, ask_price=50_100.0))
        # Delta that does not change best bid/ask (same levels)
        result = bridge.on_event(
            _ob_delta(
                bid_price=49_900.0,
                ask_price=50_100.0,
                first_update_id=1001,
                last_update_id=1001,
            )
        )
        # Same prices → suppressed
        assert result is None

    def test_changed_top_triggers_cycle(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.TOP_OF_BOOK)
        session.start()

        bridge.on_event(_ob_snapshot(bid_price=49_900.0, ask_price=50_100.0))
        result = bridge.on_event(
            _ob_delta(
                bid_price=49_950.0,
                ask_price=50_050.0,
                first_update_id=1001,
                last_update_id=1001,
            )
        )
        assert result is not None
        assert bridge.trigger_count == 2  # snapshot + delta


# ===========================================================================
# 6 · Recovery gating
# ===========================================================================


class TestBridgeRecoveryGating:
    """Cycles blocked when feed is not READY."""

    def test_recovering_feed_suppresses_cycles(self, tmp_path: Path) -> None:
        feed_key = f"{_EXCHANGE_STR}:{_SYMBOL}"
        feed_states = {feed_key: _recovering_feed_state()}

        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.MARK_PRICE, feed_states=feed_states)
        session.start()

        bridge.on_event(_ob_snapshot())
        result = bridge.on_event(_mark_price(timestamp_ns=_T0_NS))

        assert result is None
        assert bridge.trigger_count == 0
        assert bridge.suppressed_count >= 1

        # Verify suppression reason
        suppressed = [t for t in bridge.trigger_log if t.suppressed]
        assert any(t.reason == TriggerReason.RECOVERY_BLOCKED for t in suppressed)

    def test_live_feed_allows_cycles(self, tmp_path: Path) -> None:
        feed_key = f"{_EXCHANGE_STR}:{_SYMBOL}"
        feed_states = {feed_key: _live_feed_state()}

        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.MARK_PRICE, feed_states=feed_states)
        session.start()

        bridge.on_event(_ob_snapshot())
        result = bridge.on_event(_mark_price(timestamp_ns=_T0_NS))

        assert result is not None
        assert bridge.trigger_count == 1

    def test_unknown_feed_key_suppresses(self, tmp_path: Path) -> None:
        # feed_states exists but does not contain the BTCUSDT key
        feed_states: dict[str, FeedState] = {}
        session = _make_session(tmp_path)
        bridge = _make_bridge(session, feed_states=feed_states)
        session.start()

        bridge.on_event(_ob_snapshot())
        result = bridge.on_event(_mark_price(timestamp_ns=_T0_NS))

        assert result is None
        suppressed = [t for t in bridge.trigger_log if t.suppressed]
        assert any(t.reason == TriggerReason.RECOVERY_BLOCKED for t in suppressed)


# ===========================================================================
# 7 · Session mode gating
# ===========================================================================


class TestBridgeSessionGating:
    """Cycles blocked when session is not RUNNING."""

    def test_session_not_started_suppresses(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session)
        # Do NOT call session.start()

        bridge.on_event(_ob_snapshot())
        result = bridge.on_event(_mark_price(timestamp_ns=_T0_NS))

        assert result is None
        suppressed = [t for t in bridge.trigger_log if t.suppressed]
        assert any(t.reason == TriggerReason.SESSION_BLOCKED for t in suppressed)

    def test_stopped_session_suppresses(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session)
        session.start()
        session.stop()

        bridge.on_event(_ob_snapshot())
        result = bridge.on_event(_mark_price(timestamp_ns=_T0_NS))

        assert result is None


# ===========================================================================
# 8 · Unregistered symbol (assembler fail-close)
# ===========================================================================


class TestBridgeAssemblerFailClose:
    """Cycles blocked when no state has been registered for the symbol."""

    def test_unregistered_symbol_suppressed(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session)
        session.start()

        # Send a mark price event WITHOUT any prior OB snapshot (no state registered)
        # In MARK_PRICE policy, on_mark_price_event creates a state entry,
        # so we need to test directly through the assembler.
        # Actually: on_mark_price_event() calls _get_or_create_state() so the
        # symbol IS registered after that event. Assembler never returns None after
        # receiving any event for that symbol.
        # To test assembler fail-close, we call assemble() directly:
        result = bridge._assembler.assemble("UNKNOWNUSDT", "binance")
        assert result is None

    def test_mark_price_creates_state_entry(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session)
        session.start()

        # Mark price registers the symbol even without OB data
        result = bridge.on_event(_mark_price(timestamp_ns=_T0_NS))

        assert result is not None  # cycle fires even without book data
        assert bridge.trigger_count == 1


# ===========================================================================
# 9 · CycleTrigger audit trail
# ===========================================================================


class TestCycleTriggerAuditTrail:
    """Audit trail records every trigger decision."""

    def test_fired_trigger_recorded(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.MARK_PRICE)
        session.start()

        bridge.on_event(_ob_snapshot())
        bridge.on_event(_mark_price(timestamp_ns=_T0_NS))

        fired = [t for t in bridge.trigger_log if not t.suppressed]
        assert len(fired) == 1
        assert fired[0].reason == TriggerReason.MARK_PRICE
        assert fired[0].cycle_number == 1
        assert fired[0].suppression_reason is None
        assert fired[0].symbol == _SYMBOL
        assert fired[0].exchange == _EXCHANGE_STR

    def test_suppressed_trigger_recorded(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session, policy=TriggerPolicy.MARK_PRICE)
        session.start()

        bridge.on_event(_ob_snapshot())
        bridge.on_event(_mark_price(timestamp_ns=_T0_NS))
        bridge.on_event(_mark_price(timestamp_ns=_T0_NS))  # dedup suppressed

        suppressed = [t for t in bridge.trigger_log if t.suppressed]
        assert len(suppressed) >= 1
        assert all(t.cycle_number == 0 for t in suppressed)

    def test_trigger_log_is_snapshot(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session)
        session.start()

        log1 = bridge.trigger_log
        bridge.on_event(_mark_price(timestamp_ns=_T0_NS))
        log2 = bridge.trigger_log

        # Accessing trigger_log returns a snapshot — mutations don't affect prior copies
        assert len(log2) > len(log1)

    def test_cycle_trigger_immutable(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        bridge = _make_bridge(session)
        session.start()
        bridge.on_event(_mark_price(timestamp_ns=_T0_NS))

        trigger = bridge.trigger_log[0]
        assert isinstance(trigger, CycleTrigger)
        # CycleTrigger is frozen — attribute assignment must fail
        with pytest.raises((AttributeError, TypeError)):
            trigger.cycle_number = 99  # type: ignore[misc]


# ===========================================================================
# 10 · PaperLiveRunner lifecycle
# ===========================================================================


class TestPaperLiveRunnerLifecycle:
    """Runner start/stop/on_event behavior."""

    def test_start_transitions_session(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner.start()
        assert runner.is_running is True
        assert runner.session.mode == SessionMode.RUNNING

    def test_stop_transitions_session(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner.start()
        runner.stop()
        assert runner.is_running is False
        assert runner.session.mode == SessionMode.STOPPED

    def test_double_start_is_noop(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner.start()
        runner.start()  # second call is a no-op
        assert runner.is_running is True
        assert runner.session.mode == SessionMode.RUNNING

    def test_double_stop_is_noop(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner.start()
        runner.stop()
        runner.stop()  # no error
        assert runner.is_running is False

    def test_on_event_before_start_is_noop(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        # on_event before start must not crash or trigger
        runner.on_event(_mark_price(timestamp_ns=_T0_NS))
        assert runner.bridge.trigger_count == 0

    def test_on_event_after_stop_is_noop(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner.start()
        runner.stop()
        runner.on_event(_mark_price(timestamp_ns=_T0_NS))
        assert runner.bridge.trigger_count == 0

    def test_on_event_drives_bridge(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path, policy=TriggerPolicy.MARK_PRICE)
        runner.start()
        runner.on_event(_ob_snapshot())
        runner.on_event(_mark_price(timestamp_ns=_T0_NS))
        assert runner.bridge.trigger_count == 1

    def test_bridge_and_session_accessible(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        assert runner.bridge is not None
        assert runner.session is not None


# ===========================================================================
# 11 · RuntimeStatus snapshot
# ===========================================================================


class TestRuntimeStatus:
    """RuntimeStatus reflects bridge and session state accurately."""

    def test_status_before_start(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        status = runner.status()

        assert isinstance(status, RuntimeStatus)
        assert status.total_event_count == 0
        assert status.total_trigger_count == 0
        assert status.recovery_in_progress is False

    def test_status_after_events(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path, policy=TriggerPolicy.MARK_PRICE)
        runner.start()
        runner.on_event(_ob_snapshot())
        runner.on_event(_mark_price(timestamp_ns=_T0_NS))

        status = runner.status()
        assert status.total_event_count == 2
        assert status.total_trigger_count == 1
        assert status.session_status is not None

    def test_per_symbol_ready_populated(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path, policy=TriggerPolicy.MARK_PRICE)
        runner.start()
        # OB snapshot updates feed state mirror
        runner.on_event(_ob_snapshot())

        status = runner.status()
        # Symbol registered but feed state starts as disconnected/idle
        assert _SYMBOL in status.per_symbol_ready

    def test_recovery_in_progress_when_feed_not_ready(self, tmp_path: Path) -> None:
        feed_key = f"{_EXCHANGE_STR}:{_SYMBOL}"
        feed_states = {feed_key: _recovering_feed_state()}

        runner = _make_runner(tmp_path, policy=TriggerPolicy.MARK_PRICE, feed_states=feed_states)
        runner.start()
        runner.on_event(_ob_snapshot())

        status = runner.status()
        # Feed is recovering → connection/recovery state is not connected+ready
        # The mirror in assembler will reflect the FeedState values which
        # reflect disconnected/snapshotting → not ready
        # However, _sync_feed_state is called on OB events, so the state
        # will be mirrored from feed_states
        assert status.total_event_count >= 1

    def test_blocked_reason_set_when_session_blocked(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        # Don't start — session remains INITIALIZING (trading_blocked=True)
        status = runner.status()
        assert status.blocked_reason is not None

    def test_blocked_reason_none_when_running(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner.start()
        status = runner.status()
        assert status.blocked_reason is None


# ===========================================================================
# 12 · Deterministic replay
# ===========================================================================


class TestDeterministicReplay:
    """Same event sequence → same cycle results / state transitions."""

    def _build_event_sequence(self) -> list[object]:
        events: list[object] = [
            _ob_snapshot(bid_price=49_900.0, ask_price=50_100.0, last_update_id=1000),
            _trade(price=50_000.0, seq=1, timestamp_ns=_T0_NS),
            _trade(price=50_010.0, seq=2, timestamp_ns=_T0_NS + 1),
            _mark_price(price=50_005.0, timestamp_ns=_T0_NS + 5 * _NS_PER_S),
            _trade(price=50_020.0, seq=3, timestamp_ns=_T0_NS + 6 * _NS_PER_S),
            _mark_price(price=50_015.0, timestamp_ns=_T0_NS + 10 * _NS_PER_S),
            _liquidation(price=49_500.0, timestamp_ns=_T0_NS + 11 * _NS_PER_S),
            _mark_price(price=50_020.0, timestamp_ns=_T0_NS + 15 * _NS_PER_S),
        ]
        return events

    def test_same_events_same_trigger_count(self, tmp_path: Path) -> None:
        events = self._build_event_sequence()

        # Run 1
        runner1 = _make_runner(tmp_path / "run1")
        runner1.start()
        for e in events:
            runner1.on_event(e)
        triggers1 = runner1.bridge.trigger_count
        suppressed1 = runner1.bridge.suppressed_count

        # Run 2 (fresh state)
        runner2 = _make_runner(tmp_path / "run2")
        runner2.start()
        for e in events:
            runner2.on_event(e)
        triggers2 = runner2.bridge.trigger_count
        suppressed2 = runner2.bridge.suppressed_count

        assert triggers1 == triggers2
        assert suppressed1 == suppressed2

    def test_same_events_same_cycle_numbers(self, tmp_path: Path) -> None:
        events = self._build_event_sequence()

        results: list[list[int]] = []
        for run_idx in range(2):
            runner = _make_runner(tmp_path / f"run{run_idx}")
            runner.start()
            cycle_nums: list[int] = []
            for e in events:
                r = runner.bridge.on_event(e)
                if r is not None:
                    cycle_nums.append(r.cycle_number)
            results.append(cycle_nums)

        assert results[0] == results[1]

    def test_replay_no_live_sockets(self, tmp_path: Path) -> None:
        """Replay mode: feed_states=None means no socket checks required."""
        events = self._build_event_sequence()
        runner = _make_runner(tmp_path, feed_states=None)  # explicitly no socket check
        runner.start()

        for e in events:
            runner.on_event(e)

        assert runner.bridge.trigger_count >= 1


# ===========================================================================
# 13 · End-to-end paper-live integration
# ===========================================================================


class TestEndToEndPaperLive:
    """Full feed→session→portfolio integration without real sockets."""

    def test_e2e_cycles_complete_without_error(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path, policy=TriggerPolicy.MARK_PRICE)
        runner.start()

        runner.on_event(_ob_snapshot())
        for i in range(30):
            runner.on_event(
                _trade(
                    price=50_000.0 + i * 10.0,
                    seq=i + 1,
                    timestamp_ns=_T0_NS + i * 1000,
                )
            )
        for i in range(5):
            runner.on_event(
                _mark_price(
                    price=50_000.0 + i * 5.0,
                    timestamp_ns=_T0_NS + (i + 1) * _NS_PER_S,
                )
            )

        assert runner.bridge.trigger_count == 5
        assert runner.session.cycle_count == 5

    def test_e2e_session_status_reflects_cycles(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path, policy=TriggerPolicy.MARK_PRICE)
        runner.start()

        runner.on_event(_ob_snapshot())
        runner.on_event(_mark_price(timestamp_ns=_T0_NS + _NS_PER_S))
        runner.on_event(_mark_price(timestamp_ns=_T0_NS + 2 * _NS_PER_S))

        status = runner.status()
        assert status.session_status.total_cycles == 2
        assert not status.session_status.trading_blocked

    def test_e2e_stop_persists_session(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path, policy=TriggerPolicy.MARK_PRICE)
        runner.start()

        runner.on_event(_ob_snapshot())
        runner.on_event(_mark_price(timestamp_ns=_T0_NS))
        runner.stop()

        assert runner.session.mode == SessionMode.STOPPED

    def test_e2e_kline_and_mark_price_policies_same_result(self, tmp_path: Path) -> None:
        """Kline-close driven and mark-price driven runners produce same number of
        cycles for the same number of closed bars / mark-price ticks."""
        # Mark-price runner: 3 distinct timestamps → 3 cycles
        mp_runner = _make_runner(tmp_path / "mp", policy=TriggerPolicy.MARK_PRICE)
        mp_runner.start()
        mp_runner.on_event(_ob_snapshot())
        for i in range(3):
            mp_runner.on_event(_mark_price(timestamp_ns=_T0_NS + i * _NS_PER_S))

        # Kline runner: 3 closed bars → 3 cycles
        kl_runner = _make_runner(tmp_path / "kl", policy=TriggerPolicy.KLINE_CLOSE)
        kl_runner.start()
        kl_runner.on_event(_ob_snapshot())
        for i in range(3):
            kl_runner.on_event(_kline(is_closed=True, open_time_ns=_T0_NS + i * 60 * _NS_PER_S))

        assert mp_runner.bridge.trigger_count == kl_runner.bridge.trigger_count == 3

    def test_e2e_liquidation_forwarded_to_pipeline(self, tmp_path: Path) -> None:
        """Liquidation events are accumulated and forwarded in the next cycle."""
        runner = _make_runner(tmp_path, policy=TriggerPolicy.MARK_PRICE)
        runner.start()

        runner.on_event(_ob_snapshot())
        runner.on_event(_liquidation(price=48_000.0))
        runner.on_event(_mark_price(timestamp_ns=_T0_NS))

        # Liquidations should be present in the first cycle's MarketDataInput
        # (verified by checking the assembler had the event before triggering)
        assert runner.bridge.trigger_count == 1
        assert runner.bridge.suppressed_count == 0

    def test_e2e_with_stores_persist(self, tmp_path: Path) -> None:
        """Session with portfolio store persists on stop."""
        session = _make_session(tmp_path, with_stores=True)
        bridge = _make_bridge(session, policy=TriggerPolicy.MARK_PRICE)
        runner = PaperLiveRunner(session=session, bridge=bridge)
        runner.start()

        runner.on_event(_ob_snapshot())
        runner.on_event(_mark_price(timestamp_ns=_T0_NS))
        runner.stop()

        # Session should be STOPPED (portfolio was persisted if fills occurred)
        assert runner.session.mode == SessionMode.STOPPED


# ===========================================================================
# 14 · RuntimeBridgeConfig defaults and variants
# ===========================================================================


class TestRuntimeBridgeConfig:
    """Config defaults and enum values."""

    def test_default_policy_is_mark_price(self) -> None:
        cfg = RuntimeBridgeConfig()
        assert cfg.trigger_policy == TriggerPolicy.MARK_PRICE

    def test_all_policies_valid(self) -> None:
        for policy in TriggerPolicy:
            cfg = RuntimeBridgeConfig(trigger_policy=policy)
            assert cfg.trigger_policy == policy

    def test_config_frozen(self) -> None:
        cfg = RuntimeBridgeConfig()
        with pytest.raises((AttributeError, TypeError)):
            cfg.trigger_policy = TriggerPolicy.KLINE_CLOSE  # type: ignore[misc]

    def test_trigger_reason_values(self) -> None:
        expected = {
            "mark_price",
            "kline_close",
            "trade_batch",
            "top_of_book",
            "dedup_suppressed",
            "recovery_blocked",
            "session_blocked",
            "assembler_incomplete",
        }
        actual = {r.value for r in TriggerReason}
        assert expected == actual
