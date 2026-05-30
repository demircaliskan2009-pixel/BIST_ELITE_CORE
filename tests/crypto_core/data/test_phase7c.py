"""Phase 7C — DeltaBuffer + validated resync closure.

Validates:
1. DeltaBuffer — bounded push/drain/clear, overflow fail-closed, stale filtering,
   sequence-gap detection, lifecycle management.
2. DataIngestor delta routing — depth deltas buffered during SNAPSHOTTING,
   other event types dropped, overflow marks FAILED.
3. Snapshot-aligned replay — contiguous deltas replayed, stale deltas discarded,
   gaps fail recovery, state advances to READY.
4. Buffer reset between cycles — no state leak across recovery attempts.
5. _recovery_on_connect opens buffer — buffer is active before snapshot fetch.
6. Bybit recovery wiring — covered in Phase 7D (test_phase7d.py).
7. Multi-reconnect cycle — buffer cleared and re-opened on each cycle.

All tests are CI-safe: no real network, no real sleep, deterministic threading.

PRD reference: §4.5 Recovery Protocol (Phase 7C — delta buffer closure).
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from crypto_core.data.ingestion.data_ingestor import DataIngestor
from crypto_core.data.ingestion.websocket_client import WebSocketClient, WebSocketConfig
from crypto_core.data.models.events import Exchange, OrderBookEvent, OrderBookEventType, OrderBookLevel
from crypto_core.data.models.feed_state import ConnectionState, RecoveryState
from crypto_core.data.recovery.delta_buffer import DeltaBuffer, SequenceGapError
from tests.crypto_core.data.fixtures.ws_simulator import WebSocketSimulator

# ── Constants ─────────────────────────────────────────────────────────────────

_SYMBOL = "BTCUSDT"
_TS_NS = 1_700_000_000_000_000_000

# ── Fixtures / builders ───────────────────────────────────────────────────────


def _make_delta(
    first_update_id: int,
    last_update_id: int,
    symbol: str = _SYMBOL,
) -> OrderBookEvent:
    """Minimal OrderBookEvent(DELTA) for testing."""
    return OrderBookEvent(
        symbol=symbol,
        exchange=Exchange.BINANCE,
        event_type=OrderBookEventType.DELTA,
        bids=(OrderBookLevel(price=50000.0, qty=1.0),),
        asks=(OrderBookLevel(price=50001.0, qty=1.0),),
        timestamp_ns=_TS_NS,
        first_update_id=first_update_id,
        last_update_id=last_update_id,
        checksum=None,
    )


def _make_snapshot(last_update_id: int = 500) -> OrderBookEvent:
    """Minimal OrderBookEvent(SNAPSHOT) for testing."""
    return OrderBookEvent(
        symbol=_SYMBOL,
        exchange=Exchange.BINANCE,
        event_type=OrderBookEventType.SNAPSHOT,
        bids=(OrderBookLevel(price=49999.0, qty=2.0),),
        asks=(OrderBookLevel(price=50001.0, qty=3.0),),
        timestamp_ns=_TS_NS,
        first_update_id=0,
        last_update_id=last_update_id,
        checksum=None,
    )


class _MockResponse:
    """Minimal requests.Response stub for snapshot HTTP."""

    def __init__(self, last_update_id: int = 500) -> None:
        self._last_update_id = last_update_id

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return {
            "lastUpdateId": self._last_update_id,
            "bids": [["49999.0", "2.0"]],
            "asks": [["50001.0", "3.0"]],
        }


def _mock_http_ok(last_update_id: int = 500):
    """Returns an injectable HTTP GET callable that returns a snapshot."""

    def _http(url: str, *, params: Any, timeout: float) -> _MockResponse:
        return _MockResponse(last_update_id=last_update_id)

    return _http


def _binance_config(symbol: str = _SYMBOL) -> WebSocketConfig:
    return WebSocketConfig(
        url=f"wss://fstream.binance.com/stream?streams={symbol.lower()}@depth",
        symbol=symbol,
    )


def _bybit_config(symbol: str = _SYMBOL) -> WebSocketConfig:
    return WebSocketConfig(
        url="wss://stream.bybit.com/v5/public/linear",
        symbol=symbol,
    )


def _make_ingestor(
    emitted: list[object],
    snapshot_last_update_id: int = 500,
) -> tuple[DataIngestor, str]:
    """Helper: ingestor wired with no-sleep recovery and injectable HTTP."""

    def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
        return WebSocketSimulator(config, on_msg, messages=[])

    ingestor = DataIngestor(
        on_event=emitted.append,
        ws_factory=ws_factory,
        recovery_sleep_fn=lambda s: None,
    )
    feed_key = ingestor.register_feed(
        _binance_config(),
        Exchange.BINANCE,
        snapshot_http_get=_mock_http_ok(snapshot_last_update_id),
    )
    return ingestor, feed_key


# ─────────────────────────────────────────────────────────────────────────────
# 1. DeltaBuffer — unit tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDeltaBufferLifecycle:
    def test_initial_state_inactive(self) -> None:
        """Fresh buffer is inactive and empty."""
        buf = DeltaBuffer()
        assert not buf.is_active()
        assert len(buf) == 0

    def test_start_buffering_activates(self) -> None:
        """start_buffering() makes buffer active."""
        buf = DeltaBuffer()
        buf.start_buffering()
        assert buf.is_active()

    def test_clear_deactivates_and_empties(self) -> None:
        """clear() deactivates buffer and empties it."""
        buf = DeltaBuffer()
        buf.start_buffering()
        buf.push(_make_delta(501, 501))
        buf.clear()
        assert not buf.is_active()
        assert len(buf) == 0

    def test_start_buffering_resets_previous_contents(self) -> None:
        """start_buffering() on a buffer that already has contents resets it."""
        buf = DeltaBuffer()
        buf.start_buffering()
        buf.push(_make_delta(501, 501))
        buf.start_buffering()  # reset
        assert len(buf) == 0
        assert buf.is_active()

    def test_repr(self) -> None:
        """__repr__ is informative."""
        buf = DeltaBuffer(max_deltas=10)
        buf.start_buffering()
        r = repr(buf)
        assert "DeltaBuffer" in r
        assert "active=True" in r
        assert "10" in r


class TestDeltaBufferPush:
    def test_push_single_delta(self) -> None:
        """Push one DELTA event — buffer size is 1."""
        buf = DeltaBuffer()
        buf.start_buffering()
        buf.push(_make_delta(501, 501))
        assert len(buf) == 1

    def test_push_multiple_deltas(self) -> None:
        """Push multiple deltas in sequence — all retained."""
        buf = DeltaBuffer()
        buf.start_buffering()
        for i in range(5):
            buf.push(_make_delta(501 + i, 501 + i))
        assert len(buf) == 5

    def test_push_raises_if_inactive(self) -> None:
        """push() on inactive buffer raises ValueError."""
        buf = DeltaBuffer()
        with pytest.raises(ValueError, match="not active"):
            buf.push(_make_delta(501, 501))

    def test_push_snapshot_raises(self) -> None:
        """push() rejects SNAPSHOT events — only DELTA allowed."""
        buf = DeltaBuffer()
        buf.start_buffering()
        with pytest.raises(ValueError, match="DELTA"):
            buf.push(_make_snapshot())

    def test_push_overflow_raises(self) -> None:
        """Buffer overflow at max_deltas → OverflowError (fail-closed)."""
        buf = DeltaBuffer(max_deltas=3)
        buf.start_buffering()
        buf.push(_make_delta(501, 501))
        buf.push(_make_delta(502, 502))
        buf.push(_make_delta(503, 503))
        with pytest.raises(OverflowError, match="overflow"):
            buf.push(_make_delta(504, 504))


class TestDeltaBufferDrain:
    def test_drain_empty_buffer_returns_empty_list(self) -> None:
        """drain_for_replay on empty active buffer returns []."""
        buf = DeltaBuffer()
        buf.start_buffering()
        result = buf.drain_for_replay(snapshot_last_update_id=500)
        assert result == []

    def test_drain_filters_stale_deltas(self) -> None:
        """Deltas with last_update_id <= snapshot_last_update_id are discarded."""
        buf = DeltaBuffer()
        buf.start_buffering()
        buf.push(_make_delta(400, 450))  # stale: last_update_id=450 <= 500
        buf.push(_make_delta(451, 500))  # stale: last_update_id=500 <= 500
        result = buf.drain_for_replay(snapshot_last_update_id=500)
        assert result == []

    def test_drain_returns_valid_contiguous_deltas(self) -> None:
        """All deltas newer than snapshot are returned if contiguous from snapshot+1."""
        buf = DeltaBuffer()
        buf.start_buffering()
        buf.push(_make_delta(501, 502))  # first_update_id == 500 + 1 = 501 ✓
        buf.push(_make_delta(503, 505))  # first_update_id == 502 + 1 = 503 ✓
        buf.push(_make_delta(506, 510))  # first_update_id == 505 + 1 = 506 ✓
        result = buf.drain_for_replay(snapshot_last_update_id=500)
        assert len(result) == 3
        assert result[0].first_update_id == 501
        assert result[-1].last_update_id == 510

    def test_drain_mix_stale_and_valid(self) -> None:
        """Stale deltas discarded, valid ones retained and contiguity checked."""
        buf = DeltaBuffer()
        buf.start_buffering()
        buf.push(_make_delta(400, 450))  # stale
        buf.push(_make_delta(501, 502))  # valid first
        buf.push(_make_delta(503, 504))  # valid second
        result = buf.drain_for_replay(snapshot_last_update_id=500)
        assert len(result) == 2
        assert result[0].first_update_id == 501

    def test_drain_raises_on_gap_after_snapshot(self) -> None:
        """first relevant delta.first_update_id != snapshot.last_update_id + 1 → SequenceGapError."""
        buf = DeltaBuffer()
        buf.start_buffering()
        buf.push(_make_delta(503, 505))  # gap: expected 501, got 503
        with pytest.raises(SequenceGapError) as exc_info:
            buf.drain_for_replay(snapshot_last_update_id=500)
        assert exc_info.value.expected == 501
        assert exc_info.value.got == 503

    def test_drain_raises_on_inter_delta_gap(self) -> None:
        """Gap between consecutive buffered deltas → SequenceGapError."""
        buf = DeltaBuffer()
        buf.start_buffering()
        buf.push(_make_delta(501, 502))  # ok
        buf.push(_make_delta(504, 505))  # gap: expected 503, got 504
        with pytest.raises(SequenceGapError) as exc_info:
            buf.drain_for_replay(snapshot_last_update_id=500)
        assert exc_info.value.expected == 503
        assert exc_info.value.got == 504

    def test_drain_does_not_clear_buffer(self) -> None:
        """drain_for_replay does not clear the buffer (caller must call clear())."""
        buf = DeltaBuffer()
        buf.start_buffering()
        buf.push(_make_delta(501, 501))
        buf.drain_for_replay(snapshot_last_update_id=500)
        assert len(buf) == 1  # still has the delta
        assert buf.is_active()


# ─────────────────────────────────────────────────────────────────────────────
# 2. DataIngestor delta routing during SNAPSHOTTING
# ─────────────────────────────────────────────────────────────────────────────


class TestDeltaRoutingDuringSnapshotting:
    def _make_ingestor_in_snapshotting(self) -> tuple[DataIngestor, str]:
        """Create ingestor with feed in SNAPSHOTTING state + active buffer."""
        emitted: list[object] = []

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE, snapshot_http_get=_mock_http_ok())
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.connection_state = ConnectionState.CONNECTED
        state.recovery_state = RecoveryState.SNAPSHOTTING
        # Manually open the buffer (as _recovery_on_connect would)
        ingestor._delta_buffers[feed_key].start_buffering()
        return ingestor, feed_key

    def _depth_update_msg(self, first_update_id: int, last_update_id: int) -> dict:
        return {
            "e": "depthUpdate",
            "E": 1700000000000,
            "s": _SYMBOL,
            "U": first_update_id,
            "u": last_update_id,
            "pu": first_update_id - 1,
            "b": [["49999.0", "1.0"]],
            "a": [["50001.0", "2.0"]],
        }

    def test_depth_delta_buffered_during_snapshotting(self) -> None:
        """depthUpdate message during SNAPSHOTTING → stored in DeltaBuffer."""
        ingestor, feed_key = self._make_ingestor_in_snapshotting()
        raw_cb = ingestor._make_raw_callback(_SYMBOL, Exchange.BINANCE)
        raw_cb(self._depth_update_msg(501, 502))

        buf = ingestor._delta_buffers[feed_key]
        assert len(buf) == 1

    def test_multiple_deltas_buffered_during_snapshotting(self) -> None:
        """Multiple depthUpdate messages during SNAPSHOTTING → all buffered."""
        ingestor, feed_key = self._make_ingestor_in_snapshotting()
        raw_cb = ingestor._make_raw_callback(_SYMBOL, Exchange.BINANCE)
        raw_cb(self._depth_update_msg(501, 501))
        raw_cb(self._depth_update_msg(502, 502))
        raw_cb(self._depth_update_msg(503, 503))

        buf = ingestor._delta_buffers[feed_key]
        assert len(buf) == 3

    def test_trade_event_dropped_during_snapshotting(self) -> None:
        """Trade message during SNAPSHOTTING → dropped (not buffered, not emitted)."""
        emitted: list[object] = []

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE, snapshot_http_get=_mock_http_ok())
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.recovery_state = RecoveryState.SNAPSHOTTING
        ingestor._delta_buffers[feed_key].start_buffering()

        raw_cb = ingestor._make_raw_callback(_SYMBOL, Exchange.BINANCE)
        raw_cb(
            {
                "e": "trade",
                "E": 1700000000000,
                "s": _SYMBOL,
                "t": 1,
                "p": "50000.0",
                "q": "0.01",
                "T": 1700000000000,
                "m": False,
                "M": True,
            }
        )

        assert len(emitted) == 0
        assert len(ingestor._delta_buffers[feed_key]) == 0  # trade not buffered

    def test_delta_overflow_marks_feed_failed(self) -> None:
        """DeltaBuffer overflow during SNAPSHOTTING → feed state transitions to FAILED."""
        # DeltaBuffer max is 500 by default; use a tiny test buffer via monkey-patch
        from crypto_core.data.recovery import delta_buffer as db_module

        original_max = db_module.MAX_DELTAS
        db_module.MAX_DELTAS = 2  # temporarily lower the default

        try:
            ingestor, feed_key = self._make_ingestor_in_snapshotting()

            # The buffer was already created with the old max; recreate a small one
            small_buf = DeltaBuffer(max_deltas=2)
            small_buf.start_buffering()
            ingestor._delta_buffers[feed_key] = small_buf

            raw_cb = ingestor._make_raw_callback(_SYMBOL, Exchange.BINANCE)
            raw_cb(self._depth_update_msg(501, 501))
            raw_cb(self._depth_update_msg(502, 502))
            # 3rd push → overflow
            raw_cb(self._depth_update_msg(503, 503))

            state = ingestor.get_feed_state(feed_key)
            assert state is not None
            assert state.recovery_state == RecoveryState.FAILED
        finally:
            db_module.MAX_DELTAS = original_max

    def test_events_passed_through_when_ready(self) -> None:
        """Events during READY state flow to on_event normally."""
        emitted: list[object] = []

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE, snapshot_http_get=_mock_http_ok())
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.connection_state = ConnectionState.CONNECTED
        state.recovery_state = RecoveryState.READY

        raw_cb = ingestor._make_raw_callback(_SYMBOL, Exchange.BINANCE)
        raw_cb(
            {
                "e": "trade",
                "E": 1700000000000,
                "s": _SYMBOL,
                "t": 99,
                "p": "50000.0",
                "q": "0.01",
                "T": 1700000000000,
                "m": False,
                "M": True,
            }
        )
        assert len(emitted) == 1

    def test_events_dropped_during_replaying(self) -> None:
        """Events arriving while REPLAYING are dropped."""
        emitted: list[object] = []

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE, snapshot_http_get=_mock_http_ok())
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.recovery_state = RecoveryState.REPLAYING

        raw_cb = ingestor._make_raw_callback(_SYMBOL, Exchange.BINANCE)
        raw_cb(
            {
                "e": "trade",
                "E": 1700000000000,
                "s": _SYMBOL,
                "t": 99,
                "p": "50000.0",
                "q": "0.01",
                "T": 1700000000000,
                "m": False,
                "M": True,
            }
        )
        assert len(emitted) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. on_snapshot_request — replay integration
# ─────────────────────────────────────────────────────────────────────────────


class TestSnapshotAlignedReplay:
    """Tests for the snapshot fetch + delta replay pipeline in on_snapshot_request."""

    def _depth_update_msg(self, first_update_id: int, last_update_id: int) -> dict:
        return {
            "e": "depthUpdate",
            "E": 1700000000000,
            "s": _SYMBOL,
            "U": first_update_id,
            "u": last_update_id,
            "pu": first_update_id - 1,
            "b": [["49999.0", "1.0"]],
            "a": [["50001.0", "2.0"]],
        }

    def test_empty_buffer_snapshot_only_emitted(self) -> None:
        """No buffered deltas → snapshot event emitted, state → READY."""
        emitted: list[object] = []
        ingestor, feed_key = _make_ingestor(emitted, snapshot_last_update_id=500)

        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.recovery_state = RecoveryState.SNAPSHOTTING

        rm = ingestor._recovery_managers[feed_key]
        rm._on_snapshot_request(_SYMBOL, "binance")

        snapshot_events = [
            e for e in emitted if isinstance(e, OrderBookEvent) and e.event_type == OrderBookEventType.SNAPSHOT
        ]
        assert len(snapshot_events) == 1
        assert state.recovery_state == RecoveryState.READY

    def test_buffered_deltas_replayed_to_downstream(self) -> None:
        """Buffered deltas contiguous with snapshot → emitted in order after snapshot."""
        emitted: list[object] = []
        ingestor, feed_key = _make_ingestor(emitted, snapshot_last_update_id=500)

        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.recovery_state = RecoveryState.SNAPSHOTTING

        # Pre-seed the buffer (simulates deltas arriving during snapshot fetch)
        buf = ingestor._delta_buffers[feed_key]
        buf.start_buffering()
        buf.push(_make_delta(501, 502))
        buf.push(_make_delta(503, 505))

        rm = ingestor._recovery_managers[feed_key]
        rm._on_snapshot_request(_SYMBOL, "binance")

        snapshot_events = [
            e for e in emitted if isinstance(e, OrderBookEvent) and e.event_type == OrderBookEventType.SNAPSHOT
        ]
        delta_events = [
            e for e in emitted if isinstance(e, OrderBookEvent) and e.event_type == OrderBookEventType.DELTA
        ]
        # Snapshot emitted first, then deltas
        assert len(snapshot_events) == 1
        assert len(delta_events) == 2
        assert delta_events[0].first_update_id == 501
        assert delta_events[1].first_update_id == 503
        # Order in emitted: snapshot before deltas
        snapshot_idx = emitted.index(snapshot_events[0])
        delta_idx_0 = emitted.index(delta_events[0])
        assert snapshot_idx < delta_idx_0
        assert state.recovery_state == RecoveryState.READY

    def test_stale_buffered_deltas_not_replayed(self) -> None:
        """Deltas covered by snapshot → filtered, not emitted."""
        emitted: list[object] = []
        ingestor, feed_key = _make_ingestor(emitted, snapshot_last_update_id=500)

        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.recovery_state = RecoveryState.SNAPSHOTTING

        buf = ingestor._delta_buffers[feed_key]
        buf.start_buffering()
        buf.push(_make_delta(400, 450))  # stale: last_update_id 450 <= 500
        buf.push(_make_delta(451, 499))  # stale: last_update_id 499 <= 500

        rm = ingestor._recovery_managers[feed_key]
        rm._on_snapshot_request(_SYMBOL, "binance")

        delta_events = [
            e for e in emitted if isinstance(e, OrderBookEvent) and e.event_type == OrderBookEventType.DELTA
        ]
        assert len(delta_events) == 0
        assert state.recovery_state == RecoveryState.READY

    def test_buffer_cleared_after_successful_replay(self) -> None:
        """DeltaBuffer is cleared and inactive after successful on_snapshot_request."""
        emitted: list[object] = []
        ingestor, feed_key = _make_ingestor(emitted, snapshot_last_update_id=500)

        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.recovery_state = RecoveryState.SNAPSHOTTING

        buf = ingestor._delta_buffers[feed_key]
        buf.start_buffering()
        buf.push(_make_delta(501, 502))

        rm = ingestor._recovery_managers[feed_key]
        rm._on_snapshot_request(_SYMBOL, "binance")

        assert len(buf) == 0
        assert not buf.is_active()

    def test_sequence_gap_triggers_recovery_failed(self) -> None:
        """Gap between snapshot and first delta → state FAILED, exception propagated."""
        emitted: list[object] = []
        ingestor, feed_key = _make_ingestor(emitted, snapshot_last_update_id=500)

        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.recovery_state = RecoveryState.SNAPSHOTTING

        buf = ingestor._delta_buffers[feed_key]
        buf.start_buffering()
        buf.push(_make_delta(503, 505))  # gap: expected 501, got 503

        rm = ingestor._recovery_managers[feed_key]
        with pytest.raises(SequenceGapError):
            rm._on_snapshot_request(_SYMBOL, "binance")

        assert state.recovery_state == RecoveryState.FAILED

    def test_buffer_binance_feed_created(self) -> None:
        """DeltaBuffer is created for Binance feeds."""
        emitted: list[object] = []
        ingestor, feed_key = _make_ingestor(emitted)
        assert feed_key in ingestor._delta_buffers
        assert isinstance(ingestor._delta_buffers[feed_key], DeltaBuffer)

    def test_bybit_feed_now_has_delta_buffer(self) -> None:
        """Phase 7D: DeltaBuffer IS created for Bybit feeds (real recovery wired)."""

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        ingestor = DataIngestor(
            on_event=lambda e: None,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_bybit_config(), Exchange.BYBIT)
        # Phase 7D: Bybit has real recovery — DeltaBuffer is registered.
        assert feed_key in ingestor._delta_buffers


# ─────────────────────────────────────────────────────────────────────────────
# 4. _recovery_on_connect opens buffer
# ─────────────────────────────────────────────────────────────────────────────


class TestRecoveryOnConnectOpensBuffer:
    def test_on_connect_starts_buffering(self) -> None:
        """_recovery_on_connect() opens the DeltaBuffer."""
        emitted: list[object] = []

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE, snapshot_http_get=_mock_http_ok())

        buf = ingestor._delta_buffers[feed_key]
        assert not buf.is_active()

        # Call _recovery_on_connect directly (as RecoveryManager would)
        rm = ingestor._recovery_managers[feed_key]
        rm._on_connect()

        assert buf.is_active()

    def test_on_connect_resets_previous_buffer_state(self) -> None:
        """_recovery_on_connect() clears any leftover deltas from a prior cycle."""
        emitted: list[object] = []

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE, snapshot_http_get=_mock_http_ok())

        # Simulate leftover state in the buffer
        buf = ingestor._delta_buffers[feed_key]
        buf.start_buffering()
        buf.push(_make_delta(100, 100))
        assert len(buf) == 1

        # _recovery_on_connect should reset
        rm = ingestor._recovery_managers[feed_key]
        rm._on_connect()

        assert len(buf) == 0
        assert buf.is_active()


# ─────────────────────────────────────────────────────────────────────────────
# 5. Multi-cycle buffer reset
# ─────────────────────────────────────────────────────────────────────────────


class TestMultiCycleBufferReset:
    """Prove no state leak across multiple recovery cycles."""

    _TIMEOUT_S = 3.0

    class _BlockingSimulator(WebSocketClient):
        def __init__(
            self,
            config: WebSocketConfig,
            on_message: Any,
            ready_event: threading.Event | None = None,
        ) -> None:
            super().__init__(config, on_message)
            self._stop = threading.Event()
            self._ready_event = ready_event

        def connect(self) -> None:
            self._stop.clear()
            if self._ready_event is not None:
                self._ready_event.set()
            self._stop.wait()

        def disconnect(self) -> None:
            self._stop.set()

        def is_connected(self) -> bool:
            return not self._stop.is_set()

        def send(self, msg: dict) -> None:  # noqa: ARG002
            pass

    def _make_ingestor_blocking(
        self,
        ready_events: list[threading.Event],
        snapshot_calls: list[int],
    ) -> tuple[DataIngestor, str]:
        call_count = [0]

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            idx = call_count[0]
            call_count[0] += 1
            ev = ready_events[idx] if idx < len(ready_events) else threading.Event()
            return self._BlockingSimulator(config, on_msg, ready_event=ev)

        def mock_http(url: str, *, params: Any, timeout: float):
            snapshot_calls.append(500)
            return _MockResponse(last_update_id=500)

        ingestor = DataIngestor(
            on_event=lambda e: None,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE, snapshot_http_get=mock_http)
        return ingestor, feed_key

    def test_buffer_reset_on_each_recovery_cycle(self) -> None:
        """Buffer is cleared and re-opened on each recovery (no cross-cycle leakage)."""
        ready = [threading.Event() for _ in range(4)]
        snapshot_calls: list[int] = []

        ingestor, feed_key = self._make_ingestor_blocking(ready, snapshot_calls)

        t = ingestor.start_feed_managed(feed_key)

        # First connection
        assert ready[0].wait(timeout=self._TIMEOUT_S), "Connect #1 timed out"

        buf = ingestor._delta_buffers[feed_key]
        assert not buf.is_active(), "Buffer must be inactive during normal operation"

        # Trigger first recovery
        ingestor._clients[feed_key].disconnect()
        assert ready[1].wait(timeout=self._TIMEOUT_S), "Connect #2 timed out"

        # After recovery: buffer was cleared by on_snapshot_request
        assert not buf.is_active(), "Buffer cleared after recovery"
        assert len(buf) == 0

        # Trigger second recovery
        ingestor._clients[feed_key].disconnect()
        assert ready[2].wait(timeout=self._TIMEOUT_S), "Connect #3 timed out"

        assert len(snapshot_calls) == 2
        assert not buf.is_active()
        assert len(buf) == 0

        ingestor.shutdown(feed_key)
        t.join(timeout=self._TIMEOUT_S)

    def test_stop_feed_clears_buffer(self) -> None:
        """stop_feed() clears any open delta buffer (no leakage on shutdown)."""
        emitted: list[object] = []
        ingestor, feed_key = _make_ingestor(emitted)

        buf = ingestor._delta_buffers[feed_key]
        buf.start_buffering()
        buf.push(_make_delta(501, 501))
        assert len(buf) == 1

        ingestor.stop_feed(feed_key)

        assert not buf.is_active()
        assert len(buf) == 0
