"""Tests for OrderBookManager — snapshot/delta application, CRC32, crossed-book detection.

Covers:
- Snapshot initialises the book
- Deltas update the book in sequence
- Delta before snapshot raises BOOK_NO_SNAPSHOT
- Sequence gap in deltas raises SEQ_GAP
- Crossed book raises BOOK_CROSSED
- Level removal (qty=0) works correctly
- Stale detection
"""

from __future__ import annotations

import pytest

from crypto_core.data.processing.book_manager import OrderBookManager
from crypto_core.data.validation.errors import ValidationError, ValidationErrorCode
from tests.crypto_core.data.fixtures.book_replay import (
    make_delta,
    make_delta_sequence,
    make_snapshot,
)
from tests.crypto_core.data.fixtures.deterministic_clock import DeterministicClock

# ──────────────────────────────────────────────────────────────────
# Snapshot application
# ──────────────────────────────────────────────────────────────────


class TestSnapshot:
    def _mgr(self):
        return OrderBookManager("BTCUSDT", "binance")

    def test_snapshot_initialises_book(self):
        mgr = self._mgr()
        snap = make_snapshot(last_update_id=100)
        mgr.apply(snap)
        assert mgr.has_snapshot()
        assert mgr.book().best_bid() == 49_999.0
        assert mgr.book().best_ask() == 50_001.0

    def test_snapshot_clears_previous_state(self):
        mgr = self._mgr()
        snap1 = make_snapshot(bids=[(48_000.0, 1.0)], asks=[(48_001.0, 1.0)], last_update_id=50)
        snap2 = make_snapshot(bids=[(49_000.0, 2.0)], asks=[(49_001.0, 2.0)], last_update_id=100)
        mgr.apply(snap1)
        mgr.apply(snap2)
        assert mgr.book().best_bid() == 49_000.0
        assert mgr.book().best_ask() == 49_001.0
        # Levels from snap1 must be gone.
        assert 48_000.0 not in mgr.book().bids

    def test_callback_called_on_snapshot(self):
        received = []
        mgr = OrderBookManager("BTCUSDT", "binance", on_book_update=received.append)
        mgr.apply(make_snapshot())
        assert len(received) == 1


# ──────────────────────────────────────────────────────────────────
# Delta application
# ──────────────────────────────────────────────────────────────────


class TestDelta:
    def _mgr_with_snapshot(self):
        mgr = OrderBookManager("BTCUSDT", "binance")
        mgr.apply(make_snapshot(last_update_id=100))
        return mgr

    def test_delta_updates_bid_level(self):
        mgr = self._mgr_with_snapshot()
        delta = make_delta(bids=[(49_999.0, 5.0)], first_update_id=101, last_update_id=101)
        mgr.apply(delta)
        assert mgr.book().bids[49_999.0] == 5.0

    def test_delta_removes_bid_level_on_zero_qty(self):
        mgr = self._mgr_with_snapshot()
        assert 49_999.0 in mgr.book().bids
        delta = make_delta(bids=[(49_999.0, 0.0)], first_update_id=101, last_update_id=101)
        mgr.apply(delta)
        assert 49_999.0 not in mgr.book().bids

    def test_gap_free_sequence_accepted(self):
        mgr = self._mgr_with_snapshot()
        deltas = make_delta_sequence(count=5, base_update_id=101)
        for d in deltas:
            mgr.apply(d)
        assert mgr.book().last_update_id == 105

    def test_delta_before_snapshot_raises(self):
        mgr = OrderBookManager("BTCUSDT", "binance")
        delta = make_delta(first_update_id=101, last_update_id=101)
        with pytest.raises(ValidationError) as exc_info:
            mgr.apply(delta)
        assert exc_info.value.code == ValidationErrorCode.BOOK_NO_SNAPSHOT

    def test_sequence_gap_raises(self):
        mgr = self._mgr_with_snapshot()
        # Jump from 100 to 103 — gap
        delta = make_delta(first_update_id=103, last_update_id=103)
        with pytest.raises(ValidationError) as exc_info:
            mgr.apply(delta)
        assert exc_info.value.code == ValidationErrorCode.SEQ_GAP


# ──────────────────────────────────────────────────────────────────
# Crossed book
# ──────────────────────────────────────────────────────────────────


class TestCrossedBook:
    def test_crossed_book_after_snapshot_raises(self):
        mgr = OrderBookManager("BTCUSDT", "binance")
        # best_bid > best_ask → crossed
        snap = make_snapshot(
            bids=[(50_002.0, 1.0)],  # bid above ask → crossed
            asks=[(50_001.0, 1.0)],
            last_update_id=100,
        )
        with pytest.raises(ValidationError) as exc_info:
            mgr.apply(snap)
        assert exc_info.value.code == ValidationErrorCode.BOOK_CROSSED

    def test_valid_book_not_crossed(self):
        mgr = OrderBookManager("BTCUSDT", "binance")
        snap = make_snapshot()  # bid=49_999, ask=50_001 — normal
        mgr.apply(snap)  # must not raise
        assert not mgr.book().is_crossed()


# ──────────────────────────────────────────────────────────────────
# Reset
# ──────────────────────────────────────────────────────────────────


class TestReset:
    def test_reset_clears_snapshot_flag(self):
        mgr = OrderBookManager("BTCUSDT", "binance")
        mgr.apply(make_snapshot())
        assert mgr.has_snapshot()
        mgr.reset()
        assert not mgr.has_snapshot()

    def test_delta_after_reset_raises_no_snapshot(self):
        mgr = OrderBookManager("BTCUSDT", "binance")
        mgr.apply(make_snapshot(last_update_id=100))
        mgr.reset()
        delta = make_delta(first_update_id=101, last_update_id=101)
        with pytest.raises(ValidationError) as exc_info:
            mgr.apply(delta)
        assert exc_info.value.code == ValidationErrorCode.BOOK_NO_SNAPSHOT


# ──────────────────────────────────────────────────────────────────
# Stale detection
# ──────────────────────────────────────────────────────────────────


class TestStale:
    def test_stale_raises_after_threshold(self):
        clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
        mgr = OrderBookManager("BTCUSDT", "binance", stale_threshold_ns=10_000_000_000)
        snap = make_snapshot(timestamp_ns=clock() - 15_000_000_000)
        mgr.apply(snap)
        with pytest.raises(ValidationError) as exc_info:
            mgr.check_stale(clock())
        assert exc_info.value.code == ValidationErrorCode.STALE_DATA

    def test_fresh_book_not_stale(self):
        clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
        mgr = OrderBookManager("BTCUSDT", "binance", stale_threshold_ns=10_000_000_000)
        snap = make_snapshot(timestamp_ns=clock() - 5_000_000_000)
        mgr.apply(snap)
        mgr.check_stale(clock())  # must not raise
