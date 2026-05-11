"""Tests for Phase 8A — Managed continuous paper-live service + async-safe event bridge.

Covers:
  1. EventQueueBridge — enqueue / get / drain / bounded overflow / pressure zones.
  2. EventQueueBridge — thread-safe concurrent enqueue from multiple producers.
  3. EventQueueBridge — queue snapshot accuracy.
  4. EventQueueBridge — backpressure zone transitions (NORMAL → WARNING → CRITICAL → OVERFLOW).
  5. PaperLiveService — lifecycle (start / stop / idempotent).
  6. PaperLiveService — pause / resume.
  7. PaperLiveService — restart.
  8. PaperLiveService — consumer loop drains queue → runner.on_event.
  9. PaperLiveService — overflow → FAILED transition.
  10. PaperLiveService — consumer crash → FAILED transition.
  11. PaperLiveService — stall detection via watchdog.
  12. PaperLiveService — symbol health reporting.
  13. PaperLiveService — ServiceStatus snapshot accuracy.
  14. ServiceConfig defaults.
  15. ServiceMode transitions.
  16. Integration: multi-threaded producers → queue → consumer → runner.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from crypto_core.data.models.events import (
    Exchange,
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
from crypto_core.orchestrator.pipeline import PipelineConfig, PipelineOrchestrator
from crypto_core.portfolio.tracker import PositionTracker
from crypto_core.runtime.assembler import MarketStateAssembler
from crypto_core.runtime.bridge import FeedSessionBridge
from crypto_core.runtime.models import RuntimeBridgeConfig, TriggerPolicy
from crypto_core.runtime.runner import PaperLiveRunner
from crypto_core.service.models import (
    QueuePressure,
    QueueSnapshot,
    ServiceConfig,
    ServiceMode,
    SymbolHealth,
    WatchdogStatus,
)
from crypto_core.service.paper_live_service import PaperLiveService
from crypto_core.service.queue_bridge import EventQueueBridge
from crypto_core.session.engine import PaperLiveSession
from crypto_core.session.models import PaperSessionConfig

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
    timestamp_ns: int = _T0_NS,
    seq: int = 1,
    symbol: str = _SYMBOL,
    exchange: Exchange = _EXCHANGE,
) -> TradeEvent:
    return TradeEvent(
        trade_id=f"t-{seq}-{price}",
        symbol=symbol,
        exchange=exchange,
        side=TradeSide.BUY,
        price=price,
        qty=0.1,
        timestamp_ns=timestamp_ns,
        sequence_no=seq,
        is_maker=False,
    )


def _mark_price(
    price: float = 50_000.0,
    timestamp_ns: int = _T0_NS,
    symbol: str = _SYMBOL,
    exchange: Exchange = _EXCHANGE,
) -> MarkPriceEvent:
    return MarkPriceEvent(
        symbol=symbol,
        exchange=exchange,
        mark_price=price,
        index_price=price,
        funding_rate=0.0001,
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


def _live_feed_state(symbol: str = _SYMBOL) -> FeedState:
    state = FeedState(symbol=symbol, exchange=_EXCHANGE_STR, stream_type="multi")
    state.connection_state = ConnectionState.CONNECTED
    state.recovery_state = RecoveryState.READY
    return state


# ---------------------------------------------------------------------------
# Pipeline / session helpers
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
    session_id: str = "test-8a",
    initial_nav: float = 10_000.0,
) -> PaperLiveSession:
    cfg = _pipeline_config()
    tracker = PositionTracker(initial_nav_usd=initial_nav)
    lifecycle = ExecutionLifecycleEngine(cfg.execution_lifecycle)
    orch = PipelineOrchestrator(
        config=cfg,
        position_tracker=tracker,
        lifecycle_engine=lifecycle,
    )
    session_cfg = PaperSessionConfig(
        session_id=session_id,
        initial_nav_usd=initial_nav,
        persist_every_fill=True,
    )
    return PaperLiveSession(
        config=session_cfg,
        orchestrator=orch,
        position_tracker=tracker,
        lifecycle_engine=lifecycle,
    )


def _make_runner(
    tmp_path: Path,
    policy: TriggerPolicy = TriggerPolicy.MARK_PRICE,
    feed_states: dict[str, FeedState] | None = None,
) -> PaperLiveRunner:
    session = _make_session(tmp_path)
    config = RuntimeBridgeConfig(trigger_policy=policy, trade_batch_size=3)
    assembler = MarketStateAssembler(config)
    bridge = FeedSessionBridge(
        session=session,
        assembler=assembler,
        config=config,
        feed_states=feed_states,
    )
    return PaperLiveRunner(session=session, bridge=bridge)


def _make_service(
    tmp_path: Path,
    *,
    queue_max_size: int = 100,
    stall_threshold_s: float = 60.0,
    consumer_poll_timeout_s: float = 0.1,
    feed_states: dict[str, FeedState] | None = None,
) -> PaperLiveService:
    """Create a PaperLiveService with a mock ingestor."""
    runner = _make_runner(tmp_path, feed_states=feed_states)
    ingestor = MagicMock()
    ingestor.get_feed_state = MagicMock(return_value=None)
    ingestor.shutdown_all = MagicMock()
    config = ServiceConfig(
        queue_max_size=queue_max_size,
        stall_threshold_s=stall_threshold_s,
        consumer_poll_timeout_s=consumer_poll_timeout_s,
    )
    return PaperLiveService(runner=runner, ingestor=ingestor, config=config)


# ===========================================================================
# 1 · EventQueueBridge — basic operations
# ===========================================================================


class TestEventQueueBridgeBasic:
    """Basic enqueue / get / drain operations."""

    def test_enqueue_and_get(self) -> None:
        config = ServiceConfig(queue_max_size=10)
        bridge = EventQueueBridge(config)
        event = _trade()
        assert bridge.enqueue(event)
        result = bridge.get(timeout=1.0)
        assert result is event

    def test_get_returns_none_on_timeout(self) -> None:
        config = ServiceConfig(queue_max_size=10)
        bridge = EventQueueBridge(config)
        result = bridge.get(timeout=0.01)
        assert result is None

    def test_drain_returns_all_events(self) -> None:
        config = ServiceConfig(queue_max_size=100)
        bridge = EventQueueBridge(config)
        events = [_trade(seq=i) for i in range(5)]
        for e in events:
            bridge.enqueue(e)
        drained = bridge.drain()
        assert len(drained) == 5
        # FIFO order preserved.
        for i, e in enumerate(drained):
            assert e is events[i]

    def test_drain_with_max_events(self) -> None:
        config = ServiceConfig(queue_max_size=100)
        bridge = EventQueueBridge(config)
        for i in range(10):
            bridge.enqueue(_trade(seq=i))
        drained = bridge.drain(max_events=3)
        assert len(drained) == 3
        # Remaining events still in queue.
        assert bridge.depth == 7

    def test_drain_empty_queue(self) -> None:
        config = ServiceConfig(queue_max_size=10)
        bridge = EventQueueBridge(config)
        drained = bridge.drain()
        assert drained == []

    def test_is_empty(self) -> None:
        config = ServiceConfig(queue_max_size=10)
        bridge = EventQueueBridge(config)
        assert bridge.is_empty()
        bridge.enqueue(_trade())
        assert not bridge.is_empty()

    def test_clear(self) -> None:
        config = ServiceConfig(queue_max_size=10)
        bridge = EventQueueBridge(config)
        for i in range(5):
            bridge.enqueue(_trade(seq=i))
        cleared = bridge.clear()
        assert cleared == 5
        assert bridge.is_empty()

    def test_depth(self) -> None:
        config = ServiceConfig(queue_max_size=10)
        bridge = EventQueueBridge(config)
        for i in range(3):
            bridge.enqueue(_trade(seq=i))
        assert bridge.depth == 3
        bridge.get(timeout=0.01)
        assert bridge.depth == 2


# ===========================================================================
# 2 · EventQueueBridge — overflow / bounded
# ===========================================================================


class TestEventQueueBridgeOverflow:
    """Bounded queue overflow behavior."""

    def test_overflow_returns_false(self) -> None:
        config = ServiceConfig(queue_max_size=3)
        bridge = EventQueueBridge(config)
        for i in range(3):
            assert bridge.enqueue(_trade(seq=i))
        # 4th event overflows.
        assert not bridge.enqueue(_trade(seq=100))

    def test_overflow_counts(self) -> None:
        config = ServiceConfig(queue_max_size=2)
        bridge = EventQueueBridge(config)
        bridge.enqueue(_trade(seq=1))
        bridge.enqueue(_trade(seq=2))
        bridge.enqueue(_trade(seq=3))
        bridge.enqueue(_trade(seq=4))
        assert bridge.total_dropped == 2

    def test_overflow_does_not_corrupt_queue(self) -> None:
        config = ServiceConfig(queue_max_size=2)
        bridge = EventQueueBridge(config)
        e1 = _trade(seq=1)
        e2 = _trade(seq=2)
        bridge.enqueue(e1)
        bridge.enqueue(e2)
        bridge.enqueue(_trade(seq=3))  # overflow
        assert bridge.get(timeout=0.01) is e1
        assert bridge.get(timeout=0.01) is e2
        assert bridge.get(timeout=0.01) is None  # overflow event was not queued


# ===========================================================================
# 3 · EventQueueBridge — queue snapshot
# ===========================================================================


class TestEventQueueBridgeSnapshot:
    """Queue snapshot accuracy."""

    def test_snapshot_empty(self) -> None:
        config = ServiceConfig(queue_max_size=100)
        bridge = EventQueueBridge(config)
        snap = bridge.queue_snapshot()
        assert snap.current_depth == 0
        assert snap.max_size == 100
        assert snap.pressure == QueuePressure.NORMAL
        assert snap.total_enqueued == 0
        assert snap.total_dropped == 0
        assert snap.total_processed == 0

    def test_snapshot_after_enqueue(self) -> None:
        config = ServiceConfig(queue_max_size=10)
        bridge = EventQueueBridge(config)
        bridge.enqueue(_trade(seq=1))
        bridge.enqueue(_trade(seq=2))
        snap = bridge.queue_snapshot()
        assert snap.current_depth == 2
        assert snap.total_enqueued == 2

    def test_snapshot_after_get(self) -> None:
        config = ServiceConfig(queue_max_size=10)
        bridge = EventQueueBridge(config)
        bridge.enqueue(_trade(seq=1))
        bridge.get(timeout=0.01)
        snap = bridge.queue_snapshot()
        assert snap.current_depth == 0
        assert snap.total_enqueued == 1
        assert snap.total_processed == 1

    def test_snapshot_with_overflow(self) -> None:
        config = ServiceConfig(queue_max_size=1)
        bridge = EventQueueBridge(config)
        bridge.enqueue(_trade(seq=1))
        bridge.enqueue(_trade(seq=2))  # overflow
        snap = bridge.queue_snapshot()
        assert snap.total_enqueued == 1
        assert snap.total_dropped == 1


# ===========================================================================
# 4 · EventQueueBridge — pressure zones
# ===========================================================================


class TestEventQueueBridgePressure:
    """Backpressure zone transitions."""

    def test_normal_zone(self) -> None:
        config = ServiceConfig(queue_max_size=100, queue_warning_pct=50.0, queue_critical_pct=80.0)
        bridge = EventQueueBridge(config)
        # 10% occupancy = NORMAL.
        for i in range(10):
            bridge.enqueue(_trade(seq=i))
        assert bridge.queue_snapshot().pressure == QueuePressure.NORMAL

    def test_warning_zone(self) -> None:
        config = ServiceConfig(queue_max_size=100, queue_warning_pct=50.0, queue_critical_pct=80.0)
        bridge = EventQueueBridge(config)
        # 55% occupancy = WARNING.
        for i in range(55):
            bridge.enqueue(_trade(seq=i))
        assert bridge.queue_snapshot().pressure == QueuePressure.WARNING

    def test_critical_zone(self) -> None:
        config = ServiceConfig(queue_max_size=100, queue_warning_pct=50.0, queue_critical_pct=80.0)
        bridge = EventQueueBridge(config)
        # 85% occupancy = CRITICAL.
        for i in range(85):
            bridge.enqueue(_trade(seq=i))
        assert bridge.queue_snapshot().pressure == QueuePressure.CRITICAL

    def test_overflow_zone(self) -> None:
        config = ServiceConfig(queue_max_size=10, queue_warning_pct=50.0, queue_critical_pct=80.0)
        bridge = EventQueueBridge(config)
        # Fill to capacity → OVERFLOW detection at boundary.
        for i in range(10):
            bridge.enqueue(_trade(seq=i))
        assert bridge.queue_snapshot().pressure == QueuePressure.OVERFLOW


# ===========================================================================
# 5 · EventQueueBridge — thread-safe concurrent producers
# ===========================================================================


class TestEventQueueBridgeConcurrency:
    """Multiple producer threads enqueue concurrently."""

    def test_concurrent_enqueue(self) -> None:
        config = ServiceConfig(queue_max_size=10_000)
        bridge = EventQueueBridge(config)
        n_threads = 4
        events_per_thread = 100
        barrier = threading.Barrier(n_threads)

        def producer(tid: int) -> None:
            barrier.wait()
            for i in range(events_per_thread):
                bridge.enqueue(_trade(seq=tid * 1000 + i))

        threads = [threading.Thread(target=producer, args=(tid,)) for tid in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        snap = bridge.queue_snapshot()
        assert snap.total_enqueued == n_threads * events_per_thread
        assert snap.current_depth == n_threads * events_per_thread
        assert snap.total_dropped == 0

    def test_concurrent_enqueue_with_overflow(self) -> None:
        config = ServiceConfig(queue_max_size=50)
        bridge = EventQueueBridge(config)
        n_threads = 4
        events_per_thread = 25  # 100 total, max_size=50

        def producer(tid: int) -> None:
            for i in range(events_per_thread):
                bridge.enqueue(_trade(seq=tid * 1000 + i))

        threads = [threading.Thread(target=producer, args=(tid,)) for tid in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        snap = bridge.queue_snapshot()
        assert snap.total_enqueued + snap.total_dropped == n_threads * events_per_thread
        assert snap.total_enqueued <= 50


# ===========================================================================
# 6 · ServiceConfig defaults
# ===========================================================================


class TestServiceConfig:
    """ServiceConfig frozen defaults."""

    def test_defaults(self) -> None:
        cfg = ServiceConfig()
        assert cfg.queue_max_size == 10_000
        assert cfg.queue_warning_pct == 50.0
        assert cfg.queue_critical_pct == 80.0
        assert cfg.stall_threshold_s == 60.0
        assert cfg.consumer_poll_timeout_s == 1.0

    def test_custom(self) -> None:
        cfg = ServiceConfig(queue_max_size=500, stall_threshold_s=30.0)
        assert cfg.queue_max_size == 500
        assert cfg.stall_threshold_s == 30.0


# ===========================================================================
# 7 · ServiceMode enum
# ===========================================================================


class TestServiceMode:
    """ServiceMode string enum values."""

    def test_values(self) -> None:
        expected = {"created", "starting", "running", "paused", "stopping", "stopped", "failed"}
        assert {m.value for m in ServiceMode} == expected


# ===========================================================================
# 8 · QueuePressure enum
# ===========================================================================


class TestQueuePressure:
    """QueuePressure string enum values."""

    def test_values(self) -> None:
        expected = {"normal", "warning", "critical", "overflow"}
        assert {p.value for p in QueuePressure} == expected


# ===========================================================================
# 9 · Service models frozen
# ===========================================================================


class TestServiceModels:
    """Model immutability and construction."""

    def test_watchdog_status_frozen(self) -> None:
        ws = WatchdogStatus(
            consumer_alive=True,
            last_event_time_ns=0,
            last_cycle_time_ns=0,
            seconds_since_event=0.0,
            seconds_since_cycle=0.0,
            stall_detected=False,
            stall_threshold_s=60.0,
        )
        with pytest.raises(AttributeError):
            ws.consumer_alive = False  # type: ignore[misc]

    def test_symbol_health_frozen(self) -> None:
        sh = SymbolHealth(
            symbol="BTCUSDT",
            exchange="binance",
            feed_connected=True,
            feed_ready=True,
            feed_key="binance:BTCUSDT",
            last_event_time_ns=0,
            blocked=False,
            block_reason=None,
        )
        with pytest.raises(AttributeError):
            sh.blocked = True  # type: ignore[misc]

    def test_queue_snapshot_frozen(self) -> None:
        qs = QueueSnapshot(
            current_depth=0,
            max_size=100,
            pressure=QueuePressure.NORMAL,
            total_enqueued=0,
            total_dropped=0,
            total_processed=0,
        )
        with pytest.raises(AttributeError):
            qs.current_depth = 10  # type: ignore[misc]

    def test_service_config_frozen(self) -> None:
        cfg = ServiceConfig()
        with pytest.raises(AttributeError):
            cfg.queue_max_size = 500  # type: ignore[misc]


# ===========================================================================
# 10 · PaperLiveService — lifecycle
# ===========================================================================


class TestPaperLiveServiceLifecycle:
    """Service start / stop lifecycle."""

    def test_initial_mode_created(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        assert svc.mode == ServiceMode.CREATED

    def test_start_transitions_to_running(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        svc.start()
        try:
            assert svc.mode == ServiceMode.RUNNING
        finally:
            svc.stop()

    def test_stop_transitions_to_stopped(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        svc.start()
        svc.stop()
        assert svc.mode == ServiceMode.STOPPED

    def test_double_start_idempotent(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        svc.start()
        try:
            svc.start()  # should not crash
            assert svc.mode == ServiceMode.RUNNING
        finally:
            svc.stop()

    def test_double_stop_idempotent(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        svc.start()
        svc.stop()
        svc.stop()  # should not crash
        assert svc.mode == ServiceMode.STOPPED

    def test_stop_calls_ingestor_shutdown_all(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        svc.start()
        svc.stop()
        svc.ingestor.shutdown_all.assert_called_once()


# ===========================================================================
# 11 · PaperLiveService — pause / resume
# ===========================================================================


class TestPaperLiveServicePauseResume:
    """Pause and resume lifecycle transitions."""

    def test_pause_from_running(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        svc.start()
        try:
            svc.pause()
            assert svc.mode == ServiceMode.PAUSED
        finally:
            svc.stop()

    def test_resume_from_paused(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        svc.start()
        try:
            svc.pause()
            svc.resume()
            assert svc.mode == ServiceMode.RUNNING
        finally:
            svc.stop()

    def test_pause_not_running_ignored(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        svc.pause()  # not started yet
        assert svc.mode == ServiceMode.CREATED

    def test_resume_not_paused_ignored(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        svc.start()
        try:
            svc.resume()  # not paused
            assert svc.mode == ServiceMode.RUNNING
        finally:
            svc.stop()


# ===========================================================================
# 12 · PaperLiveService — restart
# ===========================================================================


class TestPaperLiveServiceRestart:
    """Full restart: stop → clear → start."""

    def test_restart_from_running(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        svc.start()
        try:
            svc.restart()
            assert svc.mode == ServiceMode.RUNNING
        finally:
            svc.stop()

    def test_restart_increments_counter(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        svc.start()
        try:
            svc.restart()
            status = svc.status()
            assert status.total_service_restarts == 1
        finally:
            svc.stop()

    def test_restart_clears_queue(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        # Enqueue some events before start.
        for i in range(5):
            svc.queue_bridge.enqueue(_trade(seq=i))
        svc.start()
        try:
            svc.restart()
            assert svc.queue_bridge.depth == 0
        finally:
            svc.stop()


# ===========================================================================
# 13 · PaperLiveService — consumer loop
# ===========================================================================


class TestPaperLiveServiceConsumer:
    """Consumer loop drains queue into runner."""

    def test_consumer_processes_events(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path, consumer_poll_timeout_s=0.05)
        svc.start()
        try:
            # Enqueue events via the service callback.
            for i in range(5):
                svc.enqueue_event(_trade(seq=i))

            # Give consumer thread time to process.
            time.sleep(0.3)
            snap = svc.queue_bridge.queue_snapshot()
            assert snap.total_processed >= 5
        finally:
            svc.stop()

    def test_consumer_alive_in_status(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path, consumer_poll_timeout_s=0.05)
        svc.start()
        try:
            time.sleep(0.1)
            status = svc.status()
            assert status.watchdog.consumer_alive
        finally:
            svc.stop()

    def test_consumer_dead_after_stop(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path, consumer_poll_timeout_s=0.05)
        svc.start()
        time.sleep(0.1)
        svc.stop()
        status = svc.status()
        assert not status.watchdog.consumer_alive


# ===========================================================================
# 14 · PaperLiveService — enqueue_event gating
# ===========================================================================


class TestPaperLiveServiceEnqueueGating:
    """Events are dropped when service is STOPPED/STOPPING."""

    def test_enqueue_before_start(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        # CREATED — events are accepted (queued for when consumer starts).
        svc.enqueue_event(_trade())
        assert svc.queue_bridge.depth == 1

    def test_enqueue_after_stop(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        svc.start()
        svc.stop()
        svc.enqueue_event(_trade())
        assert svc.queue_bridge.depth == 0  # dropped


# ===========================================================================
# 15 · PaperLiveService — overflow → FAILED
# ===========================================================================


class TestPaperLiveServiceOverflow:
    """Queue overflow transitions service to FAILED."""

    def test_overflow_transitions_to_failed(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path, queue_max_size=3, consumer_poll_timeout_s=0.05)
        svc.start()
        try:
            # Fill queue faster than consumer can drain.
            for i in range(10):
                svc.enqueue_event(_trade(seq=i))
            # Some events should overflow.
            assert svc.queue_bridge.total_dropped > 0
            assert svc.mode == ServiceMode.FAILED
        finally:
            svc.stop()


# ===========================================================================
# 16 · PaperLiveService — stall detection
# ===========================================================================


class TestPaperLiveServiceStall:
    """Watchdog stall detection."""

    def test_no_stall_initially(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path, stall_threshold_s=0.1)
        svc.start()
        try:
            status = svc.status()
            # No cycles yet → stall not reported (last_cycle_ns == 0).
            assert not status.watchdog.stall_detected
        finally:
            svc.stop()

    def test_stall_detected_after_threshold(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path, stall_threshold_s=0.05, consumer_poll_timeout_s=0.01)
        svc.start()
        try:
            # Enqueue one event so consumer processes it (sets last_cycle_time_ns).
            svc.enqueue_event(_trade())
            time.sleep(0.05)  # let consumer process
            # Wait longer than stall_threshold.
            time.sleep(0.15)
            status = svc.status()
            assert status.watchdog.stall_detected
        finally:
            svc.stop()


# ===========================================================================
# 17 · PaperLiveService — symbol health
# ===========================================================================


class TestPaperLiveServiceSymbolHealth:
    """Per-symbol health in status snapshot."""

    def test_no_symbols_registered(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        status = svc.status()
        assert status.symbol_count == 0
        assert status.symbol_health == ()

    def test_symbol_health_with_live_feed(self, tmp_path: Path) -> None:
        fs = _live_feed_state()
        svc = _make_service(tmp_path)
        svc.register_symbol("binance:BTCUSDT", "BTCUSDT", "binance")
        svc.ingestor.get_feed_state.return_value = fs
        status = svc.status()
        assert status.symbol_count == 1
        sh = status.symbol_health[0]
        assert sh.symbol == "BTCUSDT"
        assert sh.exchange == "binance"
        assert sh.feed_connected
        assert sh.feed_ready
        assert not sh.blocked
        assert sh.block_reason is None

    def test_symbol_health_disconnected(self, tmp_path: Path) -> None:
        fs = FeedState(symbol=_SYMBOL, exchange=_EXCHANGE_STR, stream_type="multi")
        fs.connection_state = ConnectionState.DISCONNECTED
        fs.recovery_state = RecoveryState.IDLE
        svc = _make_service(tmp_path)
        svc.register_symbol("binance:BTCUSDT", "BTCUSDT", "binance")
        svc.ingestor.get_feed_state.return_value = fs
        status = svc.status()
        sh = status.symbol_health[0]
        assert not sh.feed_connected
        assert sh.blocked
        assert sh.block_reason == "feed_disconnected"


# ===========================================================================
# 18 · PaperLiveService — ServiceStatus snapshot
# ===========================================================================


class TestPaperLiveServiceStatus:
    """Top-level status snapshot accuracy."""

    def test_status_before_start(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        status = svc.status()
        assert status.service_mode == "created"
        assert not status.trading_enabled
        assert status.blocked_reason is not None
        assert "service_mode" in status.blocked_reason

    def test_status_while_running(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path, consumer_poll_timeout_s=0.05)
        svc.start()
        try:
            time.sleep(0.05)
            status = svc.status()
            assert status.service_mode == "running"
            assert status.trading_enabled
            assert status.blocked_reason is None
            assert status.last_error is None
            assert status.runtime_status is not None
        finally:
            svc.stop()

    def test_status_while_paused(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path, consumer_poll_timeout_s=0.05)
        svc.start()
        try:
            svc.pause()
            status = svc.status()
            assert status.service_mode == "paused"
            assert not status.trading_enabled
            assert "paused" in status.blocked_reason
        finally:
            svc.stop()

    def test_status_after_stop(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        svc.start()
        svc.stop()
        status = svc.status()
        assert status.service_mode == "stopped"
        assert not status.trading_enabled


# ===========================================================================
# 19 · PaperLiveService — trading_enabled logic
# ===========================================================================


class TestPaperLiveServiceTradingEnabled:
    """Trading enabled only when RUNNING + queue healthy."""

    def test_trading_disabled_in_critical(self, tmp_path: Path) -> None:
        # Use a tiny queue so we can push into CRITICAL zone easily.
        svc = _make_service(
            tmp_path,
            queue_max_size=10,
            consumer_poll_timeout_s=10.0,  # slow consumer → events pile up
        )
        svc.start()
        try:
            # Fill 9/10 = 90% → CRITICAL zone.
            for i in range(9):
                svc.queue_bridge.enqueue(_trade(seq=i))
            status = svc.status()
            assert status.queue.pressure == QueuePressure.CRITICAL
            assert not status.trading_enabled
        finally:
            svc.stop()


# ===========================================================================
# 20 · Integration — multi-threaded enqueue → consumer → runner
# ===========================================================================


class TestPaperLiveServiceIntegration:
    """Integration test: concurrent producers + consumer + runner."""

    def test_concurrent_producers_through_service(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path, queue_max_size=10_000, consumer_poll_timeout_s=0.01)
        svc.start()
        try:
            n_threads = 4
            events_per_thread = 25
            barrier = threading.Barrier(n_threads)

            def producer(tid: int) -> None:
                barrier.wait()
                for i in range(events_per_thread):
                    svc.enqueue_event(_trade(seq=tid * 1000 + i))

            threads = [threading.Thread(target=producer, args=(tid,)) for tid in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Wait for consumer to drain.
            time.sleep(0.5)
            snap = svc.queue_bridge.queue_snapshot()
            total = n_threads * events_per_thread
            # All events should be enqueued (queue_max_size >> total).
            assert snap.total_enqueued == total
            # Consumer should have processed all.
            assert snap.total_processed == total
            assert snap.current_depth == 0
        finally:
            svc.stop()


# ===========================================================================
# 21 · PaperLiveService — enqueue_event as DataIngestor callback
# ===========================================================================


class TestPaperLiveServiceCallback:
    """enqueue_event works as a DataIngestor on_event callback."""

    def test_enqueue_event_callable(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        # enqueue_event is callable with a single event argument.
        svc.enqueue_event(_trade())
        assert svc.queue_bridge.depth == 1

    def test_enqueue_event_returns_none(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        result = svc.enqueue_event(_trade())
        assert result is None  # void callback


# ===========================================================================
# 22 · PaperLiveService — consumer handles runner error
# ===========================================================================


class TestPaperLiveServiceConsumerError:
    """Consumer transitions to FAILED on runner.on_event() exception."""

    def test_runner_error_fails_service(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path, consumer_poll_timeout_s=0.01)
        # Patch runner.on_event to raise.
        original_on_event = svc.runner.on_event
        call_count = 0

        def exploding_on_event(event: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise RuntimeError("boom")
            original_on_event(event)

        svc.runner.on_event = exploding_on_event  # type: ignore[assignment]
        svc.start()
        try:
            svc.enqueue_event(_trade(seq=1))
            svc.enqueue_event(_trade(seq=2))
            time.sleep(0.3)
            assert svc.mode == ServiceMode.FAILED
            assert svc.status().last_error is not None
            assert "boom" in svc.status().last_error
        finally:
            svc.stop()


# ===========================================================================
# 23 · Properties
# ===========================================================================


class TestPaperLiveServiceProperties:
    """Property accessors."""

    def test_queue_bridge_property(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        assert isinstance(svc.queue_bridge, EventQueueBridge)

    def test_runner_property(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        assert isinstance(svc.runner, PaperLiveRunner)

    def test_ingestor_property(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        assert svc.ingestor is not None
