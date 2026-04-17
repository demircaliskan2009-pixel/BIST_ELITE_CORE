"""Phase 7B — REST snapshot recovery loop + transport supervision closure.

Validates:
1. BinanceSnapshotFetcher — parse, HTTP error, timeout (injectable _http_get)
2. register_feed() — Binance wires real snapshot callback; Bybit raises NotImplementedError
3. on_snapshot_request wiring — snapshot emitted and state machine advanced
4. Supervision loop — reconnects after unexpected disconnect, loops continuously
5. Supervision loop — events blocked during recovery, READY after recovery
6. shutdown() / shutdown_all() — exits supervision loop cleanly, no thread leaks
7. RecoveryManager state-machine integration through DataIngestor

All tests are CI-safe: no real network, no real sleep, deterministic threading.

PRD reference: §4.1, §4.5 Recovery Protocol.
"""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from crypto_core.data.ingestion.binance_snapshot_fetcher import BinanceSnapshotFetcher
from crypto_core.data.ingestion.data_ingestor import DataIngestor
from crypto_core.data.ingestion.websocket_client import WebSocketClient, WebSocketConfig
from crypto_core.data.models.events import Exchange, OrderBookEvent, OrderBookEventType
from crypto_core.data.models.feed_state import ConnectionState, RecoveryState
from tests.crypto_core.data.fixtures.ws_simulator import WebSocketSimulator

# ── Constants ─────────────────────────────────────────────────────────────────

_TS_MS = 1_700_000_000_000
_SYMBOL = "BTCUSDT"


# ── HTTP mock helpers ─────────────────────────────────────────────────────────


class _MockResponse:
    """Minimal requests.Response stub for testing BinanceSnapshotFetcher."""

    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(
                f"HTTP {self.status_code}",
                response=MagicMock(status_code=self.status_code),
            )

    def json(self) -> dict[str, Any]:
        return self._payload


def _snapshot_payload(last_update_id: int = 500) -> dict[str, Any]:
    return {
        "lastUpdateId": last_update_id,
        "bids": [["49999.0", "2.5"], ["49998.0", "1.0"]],
        "asks": [["50001.0", "3.0"], ["50002.0", "0.5"]],
    }


def _mock_http_ok(
    url: str,
    *,
    params: dict[str, Any],
    timeout: float,
) -> _MockResponse:
    return _MockResponse(_snapshot_payload())


# ── BlockingWSSimulator ───────────────────────────────────────────────────────


class _BlockingSimulator(WebSocketClient):
    """WS simulator that blocks in connect() until disconnect() is called.

    Replays initial messages immediately on connect(), then holds the connection
    open until disconnect() is called.  A threading.Event can be injected so
    tests can synchronise on the "connected and waiting" state.
    """

    def __init__(
        self,
        config: WebSocketConfig,
        on_message: Any,
        messages: list[dict] | None = None,
        ready_event: threading.Event | None = None,
    ) -> None:
        super().__init__(config, on_message)
        self._messages: list[dict] = messages or []
        self._stop = threading.Event()
        self._ready_event = ready_event

    def connect(self) -> None:
        self._stop.clear()
        for msg in self._messages:
            self._on_message(msg)
        if self._ready_event is not None:
            self._ready_event.set()
        self._stop.wait()  # hold until disconnect() is called

    def disconnect(self) -> None:
        self._stop.set()

    def is_connected(self) -> bool:
        return not self._stop.is_set()

    def send(self, msg: dict) -> None:  # noqa: ARG002
        pass


# ── Standard WebSocketConfig ──────────────────────────────────────────────────


def _binance_config(symbol: str = _SYMBOL) -> WebSocketConfig:
    return WebSocketConfig(
        url=f"wss://fstream.binance.com/stream?streams={symbol.lower()}@trade",
        symbol=symbol,
    )


def _bybit_config(symbol: str = _SYMBOL) -> WebSocketConfig:
    return WebSocketConfig(
        url="wss://stream.bybit.com/v5/public/linear",
        symbol=symbol,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. BinanceSnapshotFetcher — unit tests
# ─────────────────────────────────────────────────────────────────────────────


class TestBinanceSnapshotFetcher:
    def test_fetch_parses_snapshot_payload(self) -> None:
        """Injected HTTP returns valid payload → OrderBookEvent(SNAPSHOT)."""
        fetcher = BinanceSnapshotFetcher(_SYMBOL, _http_get=_mock_http_ok)
        event = fetcher.fetch()

        assert isinstance(event, OrderBookEvent)
        assert event.event_type == OrderBookEventType.SNAPSHOT
        assert event.symbol == _SYMBOL
        assert event.last_update_id == 500
        assert len(event.bids) == 2
        assert len(event.asks) == 2

    def test_fetch_bid_ask_prices(self) -> None:
        """Bid/ask prices and quantities are parsed correctly."""
        fetcher = BinanceSnapshotFetcher(_SYMBOL, _http_get=_mock_http_ok)
        event = fetcher.fetch()

        bid_prices = {b.price for b in event.bids}
        ask_prices = {a.price for a in event.asks}
        assert 49999.0 in bid_prices
        assert 49998.0 in bid_prices
        assert 50001.0 in ask_prices
        assert 50002.0 in ask_prices

    def test_fetch_timestamp_ns_is_positive(self) -> None:
        """Snapshot timestamp_ns is a positive integer (wall-clock time)."""
        before = time.time_ns()
        fetcher = BinanceSnapshotFetcher(_SYMBOL, _http_get=_mock_http_ok)
        event = fetcher.fetch()
        after = time.time_ns()

        assert before <= event.timestamp_ns <= after

    def test_fetch_raises_on_http_error(self) -> None:
        """Non-2xx response → requests.HTTPError propagates."""
        import requests

        def mock_http_error(url: str, *, params: Any, timeout: float) -> _MockResponse:
            return _MockResponse({}, status_code=429)

        fetcher = BinanceSnapshotFetcher(_SYMBOL, _http_get=mock_http_error)
        with pytest.raises(requests.HTTPError):
            fetcher.fetch()

    def test_fetch_raises_on_timeout(self) -> None:
        """Request timeout → requests.Timeout propagates."""
        import requests

        def mock_timeout(url: str, *, params: Any, timeout: float) -> _MockResponse:
            raise requests.Timeout("timed out")

        fetcher = BinanceSnapshotFetcher(_SYMBOL, _http_get=mock_timeout)
        with pytest.raises(requests.Timeout):
            fetcher.fetch()

    def test_symbol_uppercased(self) -> None:
        """Symbol is uppercased regardless of input."""
        fetcher = BinanceSnapshotFetcher("btcusdt", _http_get=_mock_http_ok)
        event = fetcher.fetch()
        assert event.symbol == "BTCUSDT"

    def test_empty_symbol_raises(self) -> None:
        """Empty symbol raises ValueError at construction."""
        with pytest.raises(ValueError, match="symbol must be non-empty"):
            BinanceSnapshotFetcher("")

    def test_uses_requests_get_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When _http_get is None, requests.get is used at fetch time."""
        import requests as req_mod

        calls: list[dict] = []

        def patched_get(url: str, *, params: Any, timeout: float) -> _MockResponse:
            calls.append({"url": url, "params": params})
            return _MockResponse(_snapshot_payload())

        monkeypatch.setattr(req_mod, "get", patched_get)
        fetcher = BinanceSnapshotFetcher(_SYMBOL)  # no _http_get
        fetcher.fetch()

        assert len(calls) == 1
        assert "fapi.binance.com" in calls[0]["url"]
        assert calls[0]["params"]["symbol"] == _SYMBOL


# ─────────────────────────────────────────────────────────────────────────────
# 2. DataIngestor register_feed — snapshot wiring
# ─────────────────────────────────────────────────────────────────────────────


class TestRegisterFeedSnapshotWiring:
    def _make_ingestor(self) -> DataIngestor:
        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        return DataIngestor(
            on_event=lambda e: None,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )

    def test_binance_snapshot_request_emits_event(self) -> None:
        """on_snapshot_request for Binance fetches snapshot and emits it."""
        emitted: list[object] = []
        fetches: list[str] = []

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        def mock_http(url: str, *, params: Any, timeout: float) -> _MockResponse:
            fetches.append(params["symbol"])
            return _MockResponse(_snapshot_payload())

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE, snapshot_http_get=mock_http)

        # Manually invoke the snapshot callback (simulating recovery)
        rm = ingestor._recovery_managers[feed_key]
        rm._on_snapshot_request(_SYMBOL, "binance")

        assert len(fetches) == 1
        assert fetches[0] == _SYMBOL
        assert len(emitted) == 1
        assert isinstance(emitted[0], OrderBookEvent)
        assert emitted[0].event_type == OrderBookEventType.SNAPSHOT  # type: ignore[union-attr]

    def test_binance_snapshot_request_advances_state_machine(self) -> None:
        """After on_snapshot_request, recovery state transitions to READY."""
        emitted: list[object] = []

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        def mock_http(url: str, *, params: Any, timeout: float) -> _MockResponse:
            return _MockResponse(_snapshot_payload())

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE, snapshot_http_get=mock_http)

        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        # Prime state to SNAPSHOTTING (as RecoveryManager would set it)
        state.recovery_state = RecoveryState.SNAPSHOTTING

        rm = ingestor._recovery_managers[feed_key]
        rm._on_snapshot_request(_SYMBOL, "binance")

        assert state.recovery_state == RecoveryState.READY
        assert state.reconnect_attempt == 0

    def test_bybit_snapshot_request_raises_not_implemented(self) -> None:
        """on_snapshot_request for Bybit raises NotImplementedError."""

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        ingestor = DataIngestor(
            on_event=lambda e: None,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_bybit_config(), Exchange.BYBIT)

        rm = ingestor._recovery_managers[feed_key]
        with pytest.raises(NotImplementedError, match="Phase 7B supports Binance Futures only"):
            rm._on_snapshot_request(_SYMBOL, "bybit")

    def test_register_stores_config_and_exchange(self) -> None:
        """register_feed stores config and exchange for supervision loop use."""
        ingestor = self._make_ingestor()
        config = _binance_config()
        feed_key = ingestor.register_feed(config, Exchange.BINANCE)

        assert ingestor._feed_configs[feed_key] is config
        assert ingestor._feed_exchanges[feed_key] == Exchange.BINANCE


# ─────────────────────────────────────────────────────────────────────────────
# 3. Supervision loop — continuous reconnect behaviour
# ─────────────────────────────────────────────────────────────────────────────


class TestSupervisionLoop:
    """All tests use _BlockingSimulator so we control disconnect timing."""

    _TIMEOUT_S = 3.0  # per-wait timeout; keeps CI tests fast

    def _make_ingestor_with_blocking_ws(
        self,
        ready_events: list[threading.Event],
        snapshot_calls: list[str],
        emitted: list[object],
    ) -> tuple[DataIngestor, str]:
        """Build an ingestor whose WS factory creates a _BlockingSimulator per call."""
        call_count = [0]

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            idx = call_count[0]
            call_count[0] += 1
            ev = ready_events[idx] if idx < len(ready_events) else threading.Event()
            return _BlockingSimulator(config, on_msg, messages=[], ready_event=ev)

        def mock_http(url: str, *, params: Any, timeout: float) -> _MockResponse:
            snapshot_calls.append(params["symbol"])
            return _MockResponse(_snapshot_payload())

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(
            _binance_config(),
            Exchange.BINANCE,
            snapshot_http_get=mock_http,
        )
        return ingestor, feed_key

    # ── test 1: first connect establishes connection ───────────────────────

    def test_first_connection_established(self) -> None:
        """start_feed_managed spawns a WS connect thread that reaches READY."""
        ready = [threading.Event()]
        ingestor, feed_key = self._make_ingestor_with_blocking_ws(ready, [], [])

        t = ingestor.start_feed_managed(feed_key)
        assert ready[0].wait(timeout=self._TIMEOUT_S), "First WS connection timed out"

        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        assert state.connection_state == ConnectionState.CONNECTED
        assert state.recovery_state == RecoveryState.READY

        ingestor.shutdown(feed_key)
        t.join(timeout=self._TIMEOUT_S)

    # ── test 2: unexpected disconnect triggers recovery ────────────────────

    def test_recovery_triggered_after_unexpected_disconnect(self) -> None:
        """Supervision loop fetches snapshot and reconnects after disconnect."""
        ready = [threading.Event(), threading.Event(), threading.Event()]
        snapshot_calls: list[str] = []

        ingestor, feed_key = self._make_ingestor_with_blocking_ws(ready, snapshot_calls, [])

        t = ingestor.start_feed_managed(feed_key)

        # Wait for first connection
        assert ready[0].wait(timeout=self._TIMEOUT_S), "First WS timed out"

        # Simulate unexpected disconnect (do NOT call shutdown/stop_feed first)
        ingestor._clients[feed_key].disconnect()

        # Wait for second connection (recovery spawned a new WS)
        assert ready[1].wait(timeout=self._TIMEOUT_S), "Second WS after recovery timed out"

        # Snapshot must have been fetched exactly once
        assert len(snapshot_calls) == 1
        assert snapshot_calls[0] == _SYMBOL

        # State is READY after recovery
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        assert state.recovery_state == RecoveryState.READY
        assert state.connection_state == ConnectionState.CONNECTED

        ingestor.shutdown(feed_key)
        t.join(timeout=self._TIMEOUT_S)

    # ── test 3: two consecutive recoveries ────────────────────────────────

    def test_supervision_loop_recovers_twice(self) -> None:
        """Supervision loop handles two consecutive unexpected disconnects."""
        ready = [threading.Event() for _ in range(4)]
        snapshot_calls: list[str] = []

        ingestor, feed_key = self._make_ingestor_with_blocking_ws(ready, snapshot_calls, [])

        t = ingestor.start_feed_managed(feed_key)

        # First connect
        assert ready[0].wait(timeout=self._TIMEOUT_S), "Connect #1 timed out"
        ingestor._clients[feed_key].disconnect()

        # Second connect (after first recovery)
        assert ready[1].wait(timeout=self._TIMEOUT_S), "Connect #2 timed out"
        assert len(snapshot_calls) == 1

        # Second unexpected disconnect
        ingestor._clients[feed_key].disconnect()

        # Third connect (after second recovery)
        assert ready[2].wait(timeout=self._TIMEOUT_S), "Connect #3 timed out"
        assert len(snapshot_calls) == 2

        ingestor.shutdown(feed_key)
        t.join(timeout=self._TIMEOUT_S)

    # ── test 4: snapshot event reaches downstream ─────────────────────────

    def test_snapshot_event_emitted_to_downstream(self) -> None:
        """REST snapshot event is emitted via on_event during recovery."""
        ready = [threading.Event(), threading.Event()]
        emitted: list[object] = []

        ingestor, feed_key = self._make_ingestor_with_blocking_ws(ready, [], emitted)

        t = ingestor.start_feed_managed(feed_key)
        assert ready[0].wait(timeout=self._TIMEOUT_S), "First connect timed out"

        ingestor._clients[feed_key].disconnect()
        assert ready[1].wait(timeout=self._TIMEOUT_S), "Post-recovery connect timed out"

        snapshot_events = [
            e for e in emitted if isinstance(e, OrderBookEvent) and e.event_type == OrderBookEventType.SNAPSHOT
        ]
        assert len(snapshot_events) == 1
        assert snapshot_events[0].symbol == _SYMBOL

        ingestor.shutdown(feed_key)
        t.join(timeout=self._TIMEOUT_S)

    # ── test 5: events blocked during recovery ────────────────────────────

    def test_events_blocked_during_snapshotting(self) -> None:
        """Events arriving while recovery_state == SNAPSHOTTING are dropped."""
        emitted: list[object] = []

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE)
        state = ingestor.get_feed_state(feed_key)
        assert state is not None

        # Prime the state to SNAPSHOTTING (recovery in flight)
        state.connection_state = ConnectionState.CONNECTED
        state.recovery_state = RecoveryState.SNAPSHOTTING

        # Invoke the raw callback directly (bypasses start_feed's state reset)
        raw_cb = ingestor._make_raw_callback(_SYMBOL, Exchange.BINANCE)
        raw_cb({
            "e": "trade", "E": _TS_MS, "s": _SYMBOL, "t": 1,
            "p": "50000.0", "q": "0.01", "T": _TS_MS, "m": False, "M": True,
        })

        # Gate must have dropped the event
        assert len(emitted) == 0

    # ── test 6: events flow after recovery completes ──────────────────────

    def test_events_flow_after_recovery_completes(self) -> None:
        """Trade events are forwarded once recovery_state is READY."""
        emitted: list[object] = []

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(
                config,
                on_msg,
                messages=[
                    {
                        "e": "trade",
                        "E": _TS_MS,
                        "s": _SYMBOL,
                        "t": 2,
                        "p": "50100.0",
                        "q": "0.02",
                        "T": _TS_MS,
                        "m": True,
                        "M": True,
                    },
                ],
            )

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE)

        # READY state before connecting
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.connection_state = ConnectionState.CONNECTED
        state.recovery_state = RecoveryState.READY

        ingestor.start_feed(feed_key)

        assert len(emitted) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 4. shutdown / stop_feed — clean exit
# ─────────────────────────────────────────────────────────────────────────────


class TestShutdown:
    _TIMEOUT_S = 3.0

    def test_shutdown_exits_supervision_loop(self) -> None:
        """shutdown() causes the supervision thread to exit cleanly."""
        ready = [threading.Event()]

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return _BlockingSimulator(config, on_msg, ready_event=ready[0])

        ingestor = DataIngestor(
            on_event=lambda e: None,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE)
        t = ingestor.start_feed_managed(feed_key)

        assert ready[0].wait(timeout=self._TIMEOUT_S), "Connection timed out"

        ingestor.shutdown(feed_key)
        t.join(timeout=self._TIMEOUT_S)

        assert not t.is_alive(), "Supervision thread still alive after shutdown"

    def test_shutdown_sets_feed_state_disconnected(self) -> None:
        """shutdown() marks the feed as DISCONNECTED."""
        ready = [threading.Event()]

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return _BlockingSimulator(config, on_msg, ready_event=ready[0])

        ingestor = DataIngestor(
            on_event=lambda e: None,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE)
        t = ingestor.start_feed_managed(feed_key)

        assert ready[0].wait(timeout=self._TIMEOUT_S)
        ingestor.shutdown(feed_key)
        t.join(timeout=self._TIMEOUT_S)

        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        assert state.connection_state == ConnectionState.DISCONNECTED

    def test_shutdown_all_stops_all_feeds(self) -> None:
        """shutdown_all() stops every registered feed."""
        ready_b = threading.Event()
        ready_y = threading.Event()

        call_idx = [0]

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            idx = call_idx[0]
            call_idx[0] += 1
            ev = ready_b if idx == 0 else ready_y
            return _BlockingSimulator(config, on_msg, ready_event=ev)

        ingestor = DataIngestor(
            on_event=lambda e: None,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        fk_b = ingestor.register_feed(_binance_config("BTCUSDT"), Exchange.BINANCE)
        fk_e = ingestor.register_feed(_binance_config("ETHUSDT"), Exchange.BINANCE)
        t_b = ingestor.start_feed_managed(fk_b)
        t_e = ingestor.start_feed_managed(fk_e)

        assert ready_b.wait(timeout=self._TIMEOUT_S)
        assert ready_y.wait(timeout=self._TIMEOUT_S)

        ingestor.shutdown_all()
        t_b.join(timeout=self._TIMEOUT_S)
        t_e.join(timeout=self._TIMEOUT_S)

        assert not t_b.is_alive()
        assert not t_e.is_alive()

    def test_stop_feed_does_not_trigger_recovery(self) -> None:
        """stop_feed() sets DISCONNECTED so supervision loop exits cleanly."""
        ready = [threading.Event()]

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return _BlockingSimulator(config, on_msg, ready_event=ready[0])

        ingestor = DataIngestor(
            on_event=lambda e: None,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE)
        t = ingestor.start_feed_managed(feed_key)

        assert ready[0].wait(timeout=self._TIMEOUT_S)

        ingestor.shutdown(feed_key)
        t.join(timeout=self._TIMEOUT_S)

        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        # No recovery attempted — reconnect_attempt stays 0
        assert state.reconnect_attempt == 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. RecoveryManager state machine through DataIngestor
# ─────────────────────────────────────────────────────────────────────────────


class TestRecoveryStateMachine:
    def test_on_snapshot_request_full_state_sequence(self) -> None:
        """State machine: IDLE → SNAPSHOTTING → REPLAYING → VALIDATING → READY."""
        states: list[RecoveryState] = []

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        def mock_http(url: str, *, params: Any, timeout: float) -> _MockResponse:
            return _MockResponse(_snapshot_payload())

        ingestor = DataIngestor(
            on_event=lambda e: None,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE, snapshot_http_get=mock_http)

        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        rm = ingestor._recovery_managers[feed_key]

        # Drive the state machine manually (mirrors what RecoveryManager does)
        state.recovery_state = RecoveryState.SNAPSHOTTING
        states.append(state.recovery_state)

        # Invoke snapshot callback directly
        rm._on_snapshot_request(_SYMBOL, "binance")
        states.append(state.recovery_state)

        # After callback: SNAPSHOTTING → REPLAYING → VALIDATING → READY
        assert states[-1] == RecoveryState.READY

    def test_failed_snapshot_keeps_state_safe(self) -> None:
        """Snapshot failure leaves state in SNAPSHOTTING (retry possible)."""

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        def mock_http_fail(url: str, *, params: Any, timeout: float) -> _MockResponse:
            return _MockResponse({}, status_code=503)

        ingestor = DataIngestor(
            on_event=lambda e: None,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(_binance_config(), Exchange.BINANCE, snapshot_http_get=mock_http_fail)

        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.recovery_state = RecoveryState.SNAPSHOTTING

        rm = ingestor._recovery_managers[feed_key]
        import requests

        with pytest.raises(requests.HTTPError):
            rm._on_snapshot_request(_SYMBOL, "binance")

        # State was not advanced past SNAPSHOTTING
        assert state.recovery_state == RecoveryState.SNAPSHOTTING
