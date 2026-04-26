"""Phase 7D — Bybit snapshot recovery + multi-venue resync parity.

Validates:
1. bybit_adapter.parse_depth_snapshot — parses V5 REST response correctly.
2. BybitSnapshotFetcher — HTTP injection, retCode error, HTTP errors.
3. DeltaBuffer.drain_for_replay(require_strict_contiguous=False) — monotonic
   validation for Bybit; gaps in seq are valid; out-of-order or duplicate seq
   raise SequenceGapError.
4. Bybit recovery wiring in DataIngestor — snapshot emitted, deltas replayed,
   state machine advances to READY, gap in deltas marks FAILED.
5. Multi-cycle buffer reset — no state leakage between recovery cycles.
6. Venue parity proof — Binance strict-contiguous and Bybit monotonic-only both
   function independently in the same DataIngestor instance.

All tests are CI-safe: no real network, no real sleep, deterministic threading.

PRD reference: §4.5 Recovery Protocol (Phase 7D — Bybit recovery closure).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from crypto_core.data.ingestion import bybit_adapter
from crypto_core.data.ingestion.bybit_snapshot_fetcher import BybitSnapshotFetcher
from crypto_core.data.ingestion.data_ingestor import DataIngestor
from crypto_core.data.ingestion.websocket_client import WebSocketClient, WebSocketConfig
from crypto_core.data.models.events import Exchange, OrderBookEvent, OrderBookEventType, OrderBookLevel
from crypto_core.data.models.feed_state import RecoveryState
from crypto_core.data.recovery.delta_buffer import DeltaBuffer, SequenceGapError
from tests.crypto_core.data.fixtures.ws_simulator import WebSocketSimulator

# ── Constants ─────────────────────────────────────────────────────────────────

_SYMBOL = "BTCUSDT"
_TS_NS = 1_700_000_000_000_000_000
_TS_MS = 1_700_000_000_000

# ── Bybit REST response helpers ───────────────────────────────────────────────


def _bybit_rest_result(
    seq: int = 99000,
    u: int = 1000,
    symbol: str = _SYMBOL,
) -> dict[str, Any]:
    """Minimal Bybit V5 REST /v5/market/orderbook 'result' sub-dict."""
    return {
        "s": symbol,
        "b": [["49999.0", "2.5"], ["49998.0", "1.0"]],
        "a": [["50001.0", "3.0"], ["50002.0", "0.5"]],
        "ts": _TS_MS,
        "u": u,
        "seq": seq,
    }


def _bybit_rest_response(
    seq: int = 99000,
    u: int = 1000,
    symbol: str = _SYMBOL,
    ret_code: int = 0,
    ret_msg: str = "OK",
) -> dict[str, Any]:
    """Full Bybit V5 REST response envelope."""
    return {
        "retCode": ret_code,
        "retMsg": ret_msg,
        "result": _bybit_rest_result(seq=seq, u=u, symbol=symbol),
        "retExtInfo": {},
        "time": _TS_MS,
    }


class _MockHTTPResponse:
    """Minimal requests.Response stub for BybitSnapshotFetcher tests."""

    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code}",
                response=MagicMock(status_code=self.status_code),
            )

    def json(self) -> dict[str, Any]:
        return self._payload


def _mock_http_ok(seq: int = 99000):
    """Returns an injectable HTTP GET callable that returns a valid Bybit response."""

    def _http(url: str, *, params: Any, timeout: float) -> _MockHTTPResponse:
        return _MockHTTPResponse(_bybit_rest_response(seq=seq))

    return _http


# ── DeltaBuffer Bybit helpers ─────────────────────────────────────────────────


def _make_bybit_delta(seq: int, symbol: str = _SYMBOL) -> OrderBookEvent:
    """Minimal DELTA event with first_update_id == last_update_id == seq (Bybit model)."""
    return OrderBookEvent(
        symbol=symbol,
        exchange=Exchange.BYBIT,
        event_type=OrderBookEventType.DELTA,
        bids=(OrderBookLevel(price=50000.0, qty=1.0),),
        asks=(OrderBookLevel(price=50001.0, qty=1.0),),
        timestamp_ns=_TS_NS,
        first_update_id=seq,
        last_update_id=seq,
        checksum=None,
    )


def _make_bybit_snapshot(seq: int = 99000) -> OrderBookEvent:
    """Minimal SNAPSHOT event with first_update_id == last_update_id == seq."""
    return OrderBookEvent(
        symbol=_SYMBOL,
        exchange=Exchange.BYBIT,
        event_type=OrderBookEventType.SNAPSHOT,
        bids=(OrderBookLevel(price=49999.0, qty=2.0),),
        asks=(OrderBookLevel(price=50001.0, qty=3.0),),
        timestamp_ns=_TS_NS,
        first_update_id=seq,
        last_update_id=seq,
        checksum=None,
    )


# ── Config helpers ────────────────────────────────────────────────────────────


def _bybit_config(symbol: str = _SYMBOL) -> WebSocketConfig:
    return WebSocketConfig(
        url="wss://stream.bybit.com/v5/public/linear",
        symbol=symbol,
    )


def _binance_config(symbol: str = _SYMBOL) -> WebSocketConfig:
    return WebSocketConfig(
        url=f"wss://fstream.binance.com/stream?streams={symbol.lower()}@depth",
        symbol=symbol,
    )


def _make_bybit_ingestor(
    emitted: list[object],
    snapshot_seq: int = 99000,
) -> tuple[DataIngestor, str]:
    """Helper: ingestor wired with Bybit feed, injectable mock HTTP, no-sleep recovery."""

    def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
        return WebSocketSimulator(config, on_msg, messages=[])

    ingestor = DataIngestor(
        on_event=emitted.append,
        ws_factory=ws_factory,
        recovery_sleep_fn=lambda s: None,
    )
    feed_key = ingestor.register_feed(
        _bybit_config(),
        Exchange.BYBIT,
        snapshot_http_get=_mock_http_ok(snapshot_seq),
    )
    return ingestor, feed_key


# ─────────────────────────────────────────────────────────────────────────────
# 1. bybit_adapter.parse_depth_snapshot
# ─────────────────────────────────────────────────────────────────────────────


class TestBybitAdapterParseDepthSnapshot:
    def test_parse_full_response(self) -> None:
        """parse_depth_snapshot returns OrderBookEvent(SNAPSHOT) from V5 result."""
        result = _bybit_rest_result(seq=99000, u=1000)
        event = bybit_adapter.parse_depth_snapshot(result, _SYMBOL, _TS_NS)

        assert isinstance(event, OrderBookEvent)
        assert event.event_type == OrderBookEventType.SNAPSHOT
        assert event.symbol == _SYMBOL
        assert event.exchange == Exchange.BYBIT
        assert event.timestamp_ns == _TS_NS
        assert event.first_update_id == 99000
        assert event.last_update_id == 99000  # first == last == seq (Bybit model)
        assert len(event.bids) == 2
        assert len(event.asks) == 2

    def test_parse_seq_takes_priority_over_u(self) -> None:
        """seq field is used when both seq and u are present."""
        result = _bybit_rest_result(seq=77777, u=1000)
        event = bybit_adapter.parse_depth_snapshot(result, _SYMBOL, _TS_NS)
        assert event.first_update_id == 77777
        assert event.last_update_id == 77777

    def test_parse_falls_back_to_u_when_no_seq(self) -> None:
        """When seq is absent, u is used as the sequence reference."""
        result = _bybit_rest_result(u=5555)
        del result["seq"]  # simulate older API response without seq
        event = bybit_adapter.parse_depth_snapshot(result, _SYMBOL, _TS_NS)
        assert event.first_update_id == 5555
        assert event.last_update_id == 5555

    def test_parse_empty_bids_and_asks(self) -> None:
        """Empty order book levels are valid (snapshot with no liquidity)."""
        result = {
            "s": _SYMBOL,
            "b": [],
            "a": [],
            "ts": _TS_MS,
            "u": 100,
            "seq": 200,
        }
        event = bybit_adapter.parse_depth_snapshot(result, _SYMBOL, _TS_NS)
        assert event.bids == ()
        assert event.asks == ()

    def test_parse_symbol_preserved(self) -> None:
        """Symbol passed as argument is preserved in the event (not overridden by result['s'])."""
        result = _bybit_rest_result(symbol="ETHUSDT")
        event = bybit_adapter.parse_depth_snapshot(result, "ETHUSDT", _TS_NS)
        assert event.symbol == "ETHUSDT"

    def test_parse_missing_bids_raises(self) -> None:
        """Missing 'b' key raises KeyError (fail-closed)."""
        result = {
            "s": _SYMBOL,
            "a": [["50001.0", "1.0"]],
            "ts": _TS_MS,
            "u": 100,
            "seq": 200,
        }
        with pytest.raises(KeyError):
            bybit_adapter.parse_depth_snapshot(result, _SYMBOL, _TS_NS)


# ─────────────────────────────────────────────────────────────────────────────
# 2. BybitSnapshotFetcher
# ─────────────────────────────────────────────────────────────────────────────


class TestBybitSnapshotFetcher:
    def test_fetch_ok_returns_snapshot_event(self) -> None:
        """Injected HTTP returns valid Bybit V5 response → OrderBookEvent(SNAPSHOT)."""
        fetcher = BybitSnapshotFetcher(_SYMBOL, _http_get=_mock_http_ok(seq=99000))
        event = fetcher.fetch()

        assert isinstance(event, OrderBookEvent)
        assert event.event_type == OrderBookEventType.SNAPSHOT
        assert event.symbol == _SYMBOL
        assert event.first_update_id == 99000
        assert event.last_update_id == 99000

    def test_fetch_event_is_exchange_bybit(self) -> None:
        """Fetched event has exchange=BYBIT."""
        fetcher = BybitSnapshotFetcher(_SYMBOL, _http_get=_mock_http_ok())
        event = fetcher.fetch()
        assert event.exchange == Exchange.BYBIT

    def test_fetch_symbol_uppercase(self) -> None:
        """BybitSnapshotFetcher converts symbol to uppercase on construction."""
        fetcher = BybitSnapshotFetcher("btcusdt", _http_get=_mock_http_ok())
        assert fetcher._symbol == "BTCUSDT"

    def test_fetch_nonzero_ret_code_raises_runtime_error(self) -> None:
        """retCode != 0 from Bybit API → RuntimeError (application-level error)."""

        def mock_http_error(url: str, *, params: Any, timeout: float) -> _MockHTTPResponse:
            return _MockHTTPResponse(_bybit_rest_response(ret_code=10001, ret_msg="params error"), 200)

        fetcher = BybitSnapshotFetcher(_SYMBOL, _http_get=mock_http_error)
        with pytest.raises(RuntimeError, match="retCode=10001"):
            fetcher.fetch()

    def test_fetch_http_4xx_raises_http_error(self) -> None:
        """HTTP 4xx from REST endpoint → requests.HTTPError propagates."""

        def mock_http_4xx(url: str, *, params: Any, timeout: float) -> _MockHTTPResponse:
            return _MockHTTPResponse({}, status_code=429)

        fetcher = BybitSnapshotFetcher(_SYMBOL, _http_get=mock_http_4xx)
        with pytest.raises(requests.HTTPError):
            fetcher.fetch()

    def test_fetch_timeout_propagates(self) -> None:
        """requests.Timeout from injectable HTTP propagates (fail-closed)."""

        def mock_http_timeout(url: str, *, params: Any, timeout: float) -> Any:
            raise requests.Timeout("timed out")

        fetcher = BybitSnapshotFetcher(_SYMBOL, _http_get=mock_http_timeout)
        with pytest.raises(requests.Timeout):
            fetcher.fetch()

    def test_fetch_bids_and_asks_populated(self) -> None:
        """Fetched snapshot contains bid and ask levels from the response."""
        fetcher = BybitSnapshotFetcher(_SYMBOL, _http_get=_mock_http_ok())
        event = fetcher.fetch()
        assert len(event.bids) >= 1
        assert len(event.asks) >= 1

    def test_empty_symbol_raises_value_error(self) -> None:
        """Constructor rejects empty symbol."""
        with pytest.raises(ValueError, match="symbol must be non-empty"):
            BybitSnapshotFetcher("")


# ─────────────────────────────────────────────────────────────────────────────
# 3. DeltaBuffer — Bybit monotonic replay (require_strict_contiguous=False)
# ─────────────────────────────────────────────────────────────────────────────


class TestDeltaBufferBybitMonotonicReplay:
    """drain_for_replay with require_strict_contiguous=False uses monotonic ordering."""

    def _make_active_buf(self, *seqs: int) -> DeltaBuffer:
        buf = DeltaBuffer()
        buf.start_buffering()
        for seq in seqs:
            buf.push(_make_bybit_delta(seq))
        return buf

    def test_contiguous_seq_ok(self) -> None:
        """Contiguous seq values (also valid monotonic) replays successfully."""
        buf = self._make_active_buf(99001, 99002, 99003)
        result = buf.drain_for_replay(99000, require_strict_contiguous=False)
        assert len(result) == 3
        assert [r.first_update_id for r in result] == [99001, 99002, 99003]

    def test_gapped_seq_ok_for_bybit(self) -> None:
        """Non-contiguous (gapped) seq is valid for Bybit monotonic mode."""
        # seq gaps like 99001, 99050, 99200 are legitimate for Bybit's global
        # cross-symbol counter — only monotonic ordering is required.
        buf = self._make_active_buf(99001, 99050, 99200)
        result = buf.drain_for_replay(99000, require_strict_contiguous=False)
        assert len(result) == 3
        assert [r.first_update_id for r in result] == [99001, 99050, 99200]

    def test_stale_deltas_filtered_out(self) -> None:
        """Deltas with seq <= snapshot_seq are filtered before replay."""
        buf = self._make_active_buf(98998, 98999, 99000, 99001, 99002)
        result = buf.drain_for_replay(99000, require_strict_contiguous=False)
        # Only deltas with seq > 99000 are returned.
        assert len(result) == 2
        assert [r.first_update_id for r in result] == [99001, 99002]

    def test_all_stale_returns_empty(self) -> None:
        """All buffered deltas stale → empty list (no error)."""
        buf = self._make_active_buf(98000, 98500, 98999)
        result = buf.drain_for_replay(99000, require_strict_contiguous=False)
        assert result == []

    def test_empty_buffer_returns_empty(self) -> None:
        """Empty buffer returns empty list (no error)."""
        buf = DeltaBuffer()
        buf.start_buffering()
        result = buf.drain_for_replay(99000, require_strict_contiguous=False)
        assert result == []

    def test_single_valid_delta_ok(self) -> None:
        """Single delta with seq > snapshot_seq replays correctly."""
        buf = self._make_active_buf(99100)
        result = buf.drain_for_replay(99000, require_strict_contiguous=False)
        assert len(result) == 1
        assert result[0].first_update_id == 99100

    def test_out_of_order_raises_sequence_gap_error(self) -> None:
        """Non-monotonic (out-of-order) deltas raise SequenceGapError — fail-closed."""
        buf = self._make_active_buf(99001, 99050, 99030)  # 99030 < 99050 → non-monotonic
        with pytest.raises(SequenceGapError):
            buf.drain_for_replay(99000, require_strict_contiguous=False)

    def test_duplicate_seq_raises_sequence_gap_error(self) -> None:
        """Duplicate seq values violate monotonic ordering → SequenceGapError."""
        buf = self._make_active_buf(99001, 99001)  # duplicate
        with pytest.raises(SequenceGapError):
            buf.drain_for_replay(99000, require_strict_contiguous=False)

    def test_bybit_mode_does_not_require_snapshot_plus_one(self) -> None:
        """In Bybit mode, delta[0].seq = snapshot.seq + 5 is valid (no strict +1 needed)."""
        buf = self._make_active_buf(99005)  # gap of 5 from snapshot at 99000
        # strict_contiguous=True would raise; strict_contiguous=False must succeed.
        result = buf.drain_for_replay(99000, require_strict_contiguous=False)
        assert len(result) == 1

    def test_strict_contiguous_still_enforced_by_default(self) -> None:
        """Default require_strict_contiguous=True rejects Bybit-style gaps (Binance mode)."""
        buf = self._make_active_buf(99005)  # gap of 5 from snapshot 99000 → not +1
        # Binance strict mode expects 99001.
        with pytest.raises(SequenceGapError):
            buf.drain_for_replay(99000)  # default: require_strict_contiguous=True


# ─────────────────────────────────────────────────────────────────────────────
# 4. Bybit recovery wiring in DataIngestor
# ─────────────────────────────────────────────────────────────────────────────


class TestBybitRecoveryWiring:
    """Integration tests: DataIngestor + Bybit recovery path."""

    def test_snapshot_request_advances_state_to_ready(self) -> None:
        """on_snapshot_request for Bybit transitions recovery state to READY."""
        emitted: list[object] = []
        ingestor, feed_key = _make_bybit_ingestor(emitted, snapshot_seq=99000)
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.recovery_state = RecoveryState.SNAPSHOTTING

        rm = ingestor._recovery_managers[feed_key]
        rm._on_snapshot_request(_SYMBOL, "bybit")

        assert state.recovery_state == RecoveryState.READY

    def test_snapshot_event_emitted_to_downstream(self) -> None:
        """Snapshot event is forwarded through on_event callback."""
        emitted: list[object] = []
        ingestor, feed_key = _make_bybit_ingestor(emitted, snapshot_seq=99000)
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.recovery_state = RecoveryState.SNAPSHOTTING

        rm = ingestor._recovery_managers[feed_key]
        rm._on_snapshot_request(_SYMBOL, "bybit")

        assert len(emitted) >= 1
        snap = emitted[0]
        assert isinstance(snap, OrderBookEvent)
        assert snap.event_type == OrderBookEventType.SNAPSHOT
        assert snap.symbol == _SYMBOL

    def test_buffered_deltas_replayed_after_snapshot(self) -> None:
        """WS deltas buffered during SNAPSHOTTING are replayed after snapshot (monotonic gaps ok)."""
        emitted: list[object] = []
        snapshot_seq = 99000

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(
            _bybit_config(),
            Exchange.BYBIT,
            snapshot_http_get=_mock_http_ok(snapshot_seq),
        )
        state = ingestor.get_feed_state(feed_key)
        assert state is not None

        # Prime delta buffer manually (simulates WS deltas arriving during REST fetch).
        # Use gapped seq values (valid for Bybit global cross-symbol counter).
        buf = ingestor._delta_buffers[feed_key]
        buf.start_buffering()
        buf.push(_make_bybit_delta(99010))  # gap of 10 from snapshot
        buf.push(_make_bybit_delta(99050))  # gap of 40
        state.recovery_state = RecoveryState.SNAPSHOTTING

        rm = ingestor._recovery_managers[feed_key]
        rm._on_snapshot_request(_SYMBOL, "bybit")

        # snapshot + 2 deltas = 3 events emitted
        assert len(emitted) == 3
        assert emitted[0].event_type == OrderBookEventType.SNAPSHOT  # type: ignore[union-attr]
        assert emitted[1].event_type == OrderBookEventType.DELTA  # type: ignore[union-attr]
        assert emitted[2].event_type == OrderBookEventType.DELTA  # type: ignore[union-attr]
        assert emitted[1].first_update_id == 99010  # type: ignore[union-attr]
        assert emitted[2].first_update_id == 99050  # type: ignore[union-attr]

    def test_stale_deltas_not_replayed(self) -> None:
        """Deltas with seq <= snapshot_seq are filtered; state still advances to READY."""
        emitted: list[object] = []
        snapshot_seq = 99000

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(
            _bybit_config(),
            Exchange.BYBIT,
            snapshot_http_get=_mock_http_ok(snapshot_seq),
        )
        state = ingestor.get_feed_state(feed_key)
        assert state is not None

        buf = ingestor._delta_buffers[feed_key]
        buf.start_buffering()
        buf.push(_make_bybit_delta(98500))  # stale (seq < snapshot_seq)
        buf.push(_make_bybit_delta(99000))  # stale (seq == snapshot_seq)
        state.recovery_state = RecoveryState.SNAPSHOTTING

        rm = ingestor._recovery_managers[feed_key]
        rm._on_snapshot_request(_SYMBOL, "bybit")

        # Only snapshot emitted — stale deltas discarded.
        assert len(emitted) == 1
        assert emitted[0].event_type == OrderBookEventType.SNAPSHOT  # type: ignore[union-attr]
        assert state.recovery_state == RecoveryState.READY

    def test_delta_gap_marks_state_failed(self) -> None:
        """Non-monotonic (out-of-order) delta during replay marks feed FAILED."""
        emitted: list[object] = []
        snapshot_seq = 99000

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(
            _bybit_config(),
            Exchange.BYBIT,
            snapshot_http_get=_mock_http_ok(snapshot_seq),
        )
        state = ingestor.get_feed_state(feed_key)
        assert state is not None

        buf = ingestor._delta_buffers[feed_key]
        buf.start_buffering()
        buf.push(_make_bybit_delta(99050))
        buf.push(_make_bybit_delta(99020))  # out-of-order → gap error
        state.recovery_state = RecoveryState.SNAPSHOTTING

        rm = ingestor._recovery_managers[feed_key]
        with pytest.raises(SequenceGapError):
            rm._on_snapshot_request(_SYMBOL, "bybit")

        assert state.recovery_state == RecoveryState.FAILED

    def test_buffer_cleared_after_successful_recovery(self) -> None:
        """DeltaBuffer is cleared (and deactivated) after successful recovery."""
        emitted: list[object] = []
        ingestor, feed_key = _make_bybit_ingestor(emitted, snapshot_seq=99000)
        state = ingestor.get_feed_state(feed_key)
        assert state is not None

        buf = ingestor._delta_buffers[feed_key]
        buf.start_buffering()
        buf.push(_make_bybit_delta(99001))
        state.recovery_state = RecoveryState.SNAPSHOTTING

        rm = ingestor._recovery_managers[feed_key]
        rm._on_snapshot_request(_SYMBOL, "bybit")

        assert not buf.is_active()
        assert len(buf) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Multi-cycle supervision — no state leakage between recovery cycles
# ─────────────────────────────────────────────────────────────────────────────


class TestBybitMultiCycleSupervision:
    """Verify buffer resets between recovery attempts — no cross-cycle leakage."""

    def test_buffer_reset_between_recovery_cycles(self) -> None:
        """Second recovery cycle starts with clean buffer (no stale data from first cycle)."""
        emitted: list[object] = []
        snapshot_seq = 99000

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )
        feed_key = ingestor.register_feed(
            _bybit_config(),
            Exchange.BYBIT,
            snapshot_http_get=_mock_http_ok(snapshot_seq),
        )
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        buf = ingestor._delta_buffers[feed_key]

        # ── Cycle 1: recovery succeeds ───────────────────────────────────────────
        buf.start_buffering()
        buf.push(_make_bybit_delta(99001))
        state.recovery_state = RecoveryState.SNAPSHOTTING
        rm = ingestor._recovery_managers[feed_key]
        rm._on_snapshot_request(_SYMBOL, "bybit")
        assert state.recovery_state == RecoveryState.READY
        assert len(buf) == 0  # cleared after cycle 1

        # ── Cycle 2: start_buffering resets buffer state ─────────────────────────
        buf.start_buffering()
        assert len(buf) == 0  # no leakage from cycle 1
        assert buf.is_active()

        # Push fresh cycle-2 delta and recover again.
        buf.push(_make_bybit_delta(99100))  # fresh seq (well past cycle-1 range)
        state.recovery_state = RecoveryState.SNAPSHOTTING
        rm._on_snapshot_request(_SYMBOL, "bybit")
        assert state.recovery_state == RecoveryState.READY

    def test_start_buffering_discards_previous_contents(self) -> None:
        """start_buffering() after a failed cycle empties any residual deltas."""
        buf = DeltaBuffer()
        buf.start_buffering()
        buf.push(_make_bybit_delta(99001))
        buf.push(_make_bybit_delta(99050))
        assert len(buf) == 2

        # Simulate a new recovery cycle starting (as _recovery_on_connect does).
        buf.start_buffering()
        assert len(buf) == 0
        assert buf.is_active()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Venue parity proof
# ─────────────────────────────────────────────────────────────────────────────


class TestVenueParityProof:
    """Binance strict-contiguous and Bybit monotonic-only both function side-by-side."""

    def test_binance_strict_contiguous_still_enforced(self) -> None:
        """Binance drain_for_replay still requires strict +1 contiguity after Phase 7D."""
        # Binance uses first_update_id..last_update_id ranges (e.g., 501..502, 503..504)
        from crypto_core.data.models.events import OrderBookLevel

        def _binance_delta(first: int, last: int) -> OrderBookEvent:
            return OrderBookEvent(
                symbol=_SYMBOL,
                exchange=Exchange.BINANCE,
                event_type=OrderBookEventType.DELTA,
                bids=(OrderBookLevel(price=50000.0, qty=1.0),),
                asks=(OrderBookLevel(price=50001.0, qty=1.0),),
                timestamp_ns=_TS_NS,
                first_update_id=first,
                last_update_id=last,
                checksum=None,
            )

        buf = DeltaBuffer()
        buf.start_buffering()
        # Gap: snapshot at 500, first delta at 503 (not 501) → should fail strict mode.
        buf.push(_binance_delta(503, 504))
        with pytest.raises(SequenceGapError):
            buf.drain_for_replay(500, require_strict_contiguous=True)  # default Binance

    def test_binance_and_bybit_both_registered_in_same_ingestor(self) -> None:
        """Binance and Bybit feeds coexist in a single DataIngestor instance."""

        emitted: list[object] = []

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        def binance_http(url: str, *, params: Any, timeout: float) -> Any:
            class _Resp:
                def raise_for_status(self) -> None:
                    pass

                def json(self) -> dict:
                    return {
                        "lastUpdateId": 500,
                        "bids": [["49999.0", "2.0"]],
                        "asks": [["50001.0", "3.0"]],
                    }

            return _Resp()

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )

        binance_key = ingestor.register_feed(
            _binance_config(),
            Exchange.BINANCE,
            snapshot_http_get=binance_http,
        )
        bybit_key = ingestor.register_feed(
            _bybit_config(),
            Exchange.BYBIT,
            snapshot_http_get=_mock_http_ok(99000),
        )

        # Both feeds registered; each has its own DeltaBuffer.
        assert binance_key in ingestor._delta_buffers
        assert bybit_key in ingestor._delta_buffers
        assert ingestor._delta_buffers[binance_key] is not ingestor._delta_buffers[bybit_key]

    def test_bybit_recovery_does_not_interfere_with_binance(self) -> None:
        """Bybit on_snapshot_request does not touch Binance feed state."""
        emitted: list[object] = []

        def ws_factory(config: WebSocketConfig, on_msg: Any) -> WebSocketClient:
            return WebSocketSimulator(config, on_msg, messages=[])

        def binance_http(url: str, *, params: Any, timeout: float) -> Any:
            class _Resp:
                def raise_for_status(self) -> None:
                    pass

                def json(self) -> dict:
                    return {
                        "lastUpdateId": 500,
                        "bids": [["49999.0", "2.0"]],
                        "asks": [["50001.0", "3.0"]],
                    }

            return _Resp()

        ingestor = DataIngestor(
            on_event=emitted.append,
            ws_factory=ws_factory,
            recovery_sleep_fn=lambda s: None,
        )

        binance_key = ingestor.register_feed(
            _binance_config(),
            Exchange.BINANCE,
            snapshot_http_get=binance_http,
        )
        bybit_key = ingestor.register_feed(
            _bybit_config(),
            Exchange.BYBIT,
            snapshot_http_get=_mock_http_ok(99000),
        )

        binance_state = ingestor.get_feed_state(binance_key)
        bybit_state = ingestor.get_feed_state(bybit_key)
        assert binance_state is not None
        assert bybit_state is not None

        # Recover Bybit only.
        bybit_state.recovery_state = RecoveryState.SNAPSHOTTING
        bybit_rm = ingestor._recovery_managers[bybit_key]
        bybit_rm._on_snapshot_request(_SYMBOL, "bybit")

        assert bybit_state.recovery_state == RecoveryState.READY
        # Binance state is untouched.
        assert binance_state.recovery_state == RecoveryState.IDLE
