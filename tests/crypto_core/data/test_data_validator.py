"""Tests for DataValidator — fail-closed validation enforcement.

Covers:
- Field validation (price, qty, trade_id)
- Deduplication (same trade_id rejected)
- Sequence gaps / out-of-order / duplicates
- Clock drift detection
- Stale data detection
- Symbol whitelist enforcement
"""

from __future__ import annotations

import pytest

from crypto_core.data.models.events import Exchange, TradeSide, TradeEvent
from crypto_core.data.validation.data_validator import DataValidator
from crypto_core.data.validation.errors import ValidationError, ValidationErrorCode
from tests.crypto_core.data.fixtures.deterministic_clock import DeterministicClock
from tests.crypto_core.data.fixtures.trade_replay import make_trade, make_trade_sequence


# ──────────────────────────────────────────────────────────────────
# Field validation rules
# ──────────────────────────────────────────────────────────────────

class TestFieldValidation:
    def _validator(self):
        clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
        return DataValidator(wall_clock=clock, clock_drift_threshold_ns=5_000_000_000)

    def test_valid_trade_accepted(self):
        v = self._validator()
        trade = make_trade("1")
        v.validate_trade(trade)  # must not raise

    def test_empty_trade_id_rejected(self):
        v = self._validator()
        trade = make_trade("")
        with pytest.raises(ValidationError) as exc_info:
            v.validate_trade(trade)
        assert exc_info.value.code == ValidationErrorCode.MISSING_FIELD

    def test_zero_price_rejected(self):
        v = self._validator()
        trade = make_trade("1", price=0.0)
        with pytest.raises(ValidationError) as exc_info:
            v.validate_trade(trade)
        assert exc_info.value.code == ValidationErrorCode.INVALID_PRICE

    def test_negative_price_rejected(self):
        v = self._validator()
        trade = make_trade("1", price=-1.0)
        with pytest.raises(ValidationError) as exc_info:
            v.validate_trade(trade)
        assert exc_info.value.code == ValidationErrorCode.INVALID_PRICE

    def test_negative_qty_rejected(self):
        v = self._validator()
        trade = make_trade("1", qty=-0.01)
        with pytest.raises(ValidationError) as exc_info:
            v.validate_trade(trade)
        assert exc_info.value.code == ValidationErrorCode.INVALID_QTY

    def test_zero_qty_accepted(self):
        # qty == 0.0 is a valid (zero-volume) trade; only < 0 is rejected.
        v = self._validator()
        trade = make_trade("1", qty=0.0)
        v.validate_trade(trade)  # must not raise


# ──────────────────────────────────────────────────────────────────
# Deduplication
# ──────────────────────────────────────────────────────────────────

class TestDeduplication:
    def _validator(self):
        clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
        return DataValidator(wall_clock=clock, clock_drift_threshold_ns=5_000_000_000)

    def test_first_trade_accepted(self):
        v = self._validator()
        trade = make_trade("42")
        v.validate_trade(trade)  # must not raise

    def test_duplicate_trade_id_rejected(self):
        v = self._validator()
        trade = make_trade("42")
        v.validate_trade(trade)
        with pytest.raises(ValidationError) as exc_info:
            v.validate_trade(trade)  # same trade_id → DUPLICATE
        assert exc_info.value.code == ValidationErrorCode.DUPLICATE_EVENT

    def test_different_trade_ids_accepted(self):
        v = self._validator()
        t1 = make_trade("1")
        t2 = make_trade("2", sequence_no=2, timestamp_ns=1_700_000_000_100_000_000)
        v.validate_trade(t1)
        v.validate_trade(t2)  # must not raise


# ──────────────────────────────────────────────────────────────────
# Sequence tracking
# ──────────────────────────────────────────────────────────────────

class TestSequenceTracking:
    def _validator(self):
        clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
        return DataValidator(wall_clock=clock, clock_drift_threshold_ns=5_000_000_000)

    def test_sequential_trades_accepted(self):
        v = self._validator()
        trades = make_trade_sequence(5, start_ns=1_700_000_000_000_000_000)
        for t in trades:
            v.validate_trade(t)

    def test_sequence_gap_rejected(self):
        v = self._validator()
        t1 = make_trade("1", sequence_no=1)
        # sequence 2 is skipped — gap
        t3 = make_trade("3", sequence_no=3, timestamp_ns=1_700_000_000_200_000_000)
        v.validate_trade(t1)
        with pytest.raises(ValidationError) as exc_info:
            v.validate_trade(t3)
        assert exc_info.value.code == ValidationErrorCode.SEQ_GAP

    def test_out_of_order_rejected(self):
        v = self._validator()
        t2 = make_trade("2", sequence_no=2, timestamp_ns=1_700_000_000_100_000_000)
        t1 = make_trade("1", sequence_no=1)
        v.validate_trade(t2)
        with pytest.raises(ValidationError) as exc_info:
            v.validate_trade(t1)
        assert exc_info.value.code == ValidationErrorCode.OUT_OF_ORDER

    def test_reset_sequence_allows_restart(self):
        v = self._validator()
        t1 = make_trade("1", sequence_no=1)
        v.validate_trade(t1)
        stream_key = "binance:BTCUSDT:trade"
        v.reset_sequence(stream_key)
        # After reset, sequence 1 is accepted again (first-event semantics).
        t1b = make_trade("99", sequence_no=1, timestamp_ns=1_700_000_000_500_000_000)
        v.validate_trade(t1b)


# ──────────────────────────────────────────────────────────────────
# Clock drift
# ──────────────────────────────────────────────────────────────────

class TestClockDrift:
    def test_within_threshold_accepted(self):
        clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
        v = DataValidator(wall_clock=clock, clock_drift_threshold_ns=5_000_000_000)
        # event 2 seconds ahead of clock — within 5s threshold
        trade = make_trade("1", timestamp_ns=clock() + 2_000_000_000)
        v.validate_trade(trade)

    def test_exceeds_threshold_rejected(self):
        clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
        v = DataValidator(wall_clock=clock, clock_drift_threshold_ns=5_000_000_000)
        # event 10 seconds ahead — exceeds 5s threshold
        trade = make_trade("1", timestamp_ns=clock() + 10_000_000_000)
        with pytest.raises(ValidationError) as exc_info:
            v.validate_trade(trade)
        assert exc_info.value.code == ValidationErrorCode.CLOCK_DRIFT


# ──────────────────────────────────────────────────────────────────
# Stale data
# ──────────────────────────────────────────────────────────────────

class TestStaleData:
    def test_fresh_stream_not_stale(self):
        clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
        v = DataValidator(wall_clock=clock, stale_threshold_ns=10_000_000_000)
        last_ts = clock() - 5_000_000_000  # 5 seconds ago
        v.check_stale("binance:BTCUSDT:trade", last_ts)  # must not raise

    def test_stale_stream_raises(self):
        clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
        v = DataValidator(wall_clock=clock, stale_threshold_ns=10_000_000_000)
        last_ts = clock() - 15_000_000_000  # 15 seconds ago — exceeds 10s threshold
        with pytest.raises(ValidationError) as exc_info:
            v.check_stale("binance:BTCUSDT:trade", last_ts)
        assert exc_info.value.code == ValidationErrorCode.STALE_DATA

    def test_zero_last_ts_not_stale(self):
        clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
        v = DataValidator(wall_clock=clock)
        v.check_stale("binance:BTCUSDT:trade", last_event_ts_ns=0)  # must not raise


# ──────────────────────────────────────────────────────────────────
# Symbol whitelist
# ──────────────────────────────────────────────────────────────────

class TestSymbolWhitelist:
    def test_whitelisted_symbol_accepted(self):
        clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
        v = DataValidator(wall_clock=clock, active_symbols={"BTCUSDT", "ETHUSDT"})
        trade = make_trade("1")  # BTCUSDT
        v.validate_trade(trade)

    def test_unknown_symbol_rejected(self):
        clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
        v = DataValidator(wall_clock=clock, active_symbols={"ETHUSDT"})
        trade = make_trade("1")  # BTCUSDT — not in whitelist
        with pytest.raises(ValidationError) as exc_info:
            v.validate_trade(trade)
        assert exc_info.value.code == ValidationErrorCode.INVALID_SYMBOL

    def test_no_whitelist_accepts_all(self):
        clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
        v = DataValidator(wall_clock=clock, active_symbols=None)
        trade = make_trade("1", symbol="XYZUSDT")
        v.validate_trade(trade)
