"""Tests for RecoveryManager — reconnect, backoff, snapshot protocol.

Covers:
- on_disconnect triggers reconnect loop
- Successful reconnect calls on_connect and on_snapshot_request
- Recovery state transitions are correct
- Max recovery time exhaustion → FAILED state + on_recovery_failed callback
"""

from __future__ import annotations

from typing import List

import pytest

from crypto_core.data.models.feed_state import ConnectionState, FeedState, RecoveryState
from crypto_core.data.recovery.recovery_manager import RecoveryManager


def _make_state() -> FeedState:
    return FeedState(symbol="BTCUSDT", exchange="binance", stream_type="multi")


def _no_sleep(seconds: float) -> None:
    """Test sleep — do nothing."""
    pass


class TestSuccessfulRecovery:
    def test_on_disconnect_calls_connect_and_snapshot(self):
        state = _make_state()
        state.connection_state = ConnectionState.CONNECTED
        state.recovery_state = RecoveryState.READY

        connect_calls: List[None] = []
        snapshot_calls: List[tuple] = []
        success_calls: List[FeedState] = []

        def on_connect():
            connect_calls.append(None)

        def on_snapshot_request(symbol, exchange):
            snapshot_calls.append((symbol, exchange))

        def on_success(fs):
            success_calls.append(fs)

        mgr = RecoveryManager(
            feed_state=state,
            on_connect=on_connect,
            on_snapshot_request=on_snapshot_request,
            on_recovery_success=on_success,
            sleep_fn=_no_sleep,
        )

        mgr.on_disconnect()

        assert len(connect_calls) == 1
        assert len(snapshot_calls) == 1
        assert snapshot_calls[0] == ("BTCUSDT", "binance")
        assert state.connection_state == ConnectionState.CONNECTED
        assert state.recovery_state == RecoveryState.SNAPSHOTTING

    def test_full_recovery_sequence(self):
        state = _make_state()
        success_calls: List[FeedState] = []

        mgr = RecoveryManager(
            feed_state=state,
            on_connect=lambda: None,
            on_snapshot_request=lambda s, e: None,
            on_recovery_success=success_calls.append,
            sleep_fn=_no_sleep,
        )

        mgr.on_disconnect()
        assert state.recovery_state == RecoveryState.SNAPSHOTTING

        mgr.on_snapshot_received()
        assert state.recovery_state == RecoveryState.REPLAYING

        mgr.on_stream_caught_up()
        assert state.recovery_state == RecoveryState.VALIDATING

        mgr.on_validation_passed()
        assert state.recovery_state == RecoveryState.READY
        assert state.reconnect_attempt == 0
        assert len(success_calls) == 1


class TestRecoveryFailure:
    def test_exhausted_recovery_sets_failed_state(self):
        state = _make_state()
        failed_calls: List[tuple] = []

        connect_attempts = 0

        def on_connect():
            nonlocal connect_attempts
            connect_attempts += 1
            raise ConnectionError("simulated network failure")

        def on_failed(fs, reason):
            failed_calls.append((fs, reason))

        mgr = RecoveryManager(
            feed_state=state,
            on_connect=on_connect,
            on_snapshot_request=lambda s, e: None,
            on_recovery_failed=on_failed,
            sleep_fn=_no_sleep,
            max_recovery_seconds=0.001,  # near-zero so it fails immediately
        )

        mgr.on_disconnect()

        assert state.connection_state == ConnectionState.FAILED
        assert state.recovery_state == RecoveryState.FAILED
        assert len(failed_calls) == 1


class TestStateTransitions:
    def test_disconnected_state_on_disconnect(self):
        state = _make_state()
        state.connection_state = ConnectionState.CONNECTED

        mgr = RecoveryManager(
            feed_state=state,
            on_connect=lambda: None,
            on_snapshot_request=lambda s, e: None,
            sleep_fn=_no_sleep,
        )

        # After on_disconnect is called (and connect succeeds), state is CONNECTED again.
        mgr.on_disconnect()
        assert state.connection_state == ConnectionState.CONNECTED
