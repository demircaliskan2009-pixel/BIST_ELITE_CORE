"""Tests for TradeStreamProcessor — dedup + sequence validation + emission.

Covers:
- Valid trades are emitted downstream
- Duplicate trades are rejected and not emitted
- Sequence gap stops emission
- Accepted/rejected counters are correct
- reset_stream allows post-reconnect restart
"""

from __future__ import annotations

from crypto_core.data.models.events import TradeEvent
from crypto_core.data.processing.trade_processor import TradeStreamProcessor
from crypto_core.data.validation.data_validator import DataValidator
from tests.crypto_core.data.fixtures.deterministic_clock import DeterministicClock
from tests.crypto_core.data.fixtures.trade_replay import make_trade, make_trade_sequence


def _processor(received: list[TradeEvent]) -> TradeStreamProcessor:
    clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
    validator = DataValidator(wall_clock=clock, clock_drift_threshold_ns=5_000_000_000)
    return TradeStreamProcessor(on_validated_trade=received.append, validator=validator)


class TestEmission:
    def test_valid_trade_emitted(self):
        received: list[TradeEvent] = []
        proc = _processor(received)
        t = make_trade("1")
        proc.process(t)
        assert len(received) == 1
        assert received[0].trade_id == "1"

    def test_sequence_of_trades_all_emitted(self):
        received: list[TradeEvent] = []
        proc = _processor(received)
        trades = make_trade_sequence(10, start_ns=1_700_000_000_000_000_000)
        for t in trades:
            proc.process(t)
        assert len(received) == 10

    def test_duplicate_not_emitted(self):
        received: list[TradeEvent] = []
        proc = _processor(received)
        t = make_trade("1")
        proc.process(t)
        proc.process(t)  # duplicate — must be rejected
        assert len(received) == 1

    def test_gap_event_not_emitted(self):
        received: list[TradeEvent] = []
        proc = _processor(received)
        t1 = make_trade("1", sequence_no=1)
        t3 = make_trade("3", sequence_no=3, timestamp_ns=1_700_000_000_200_000_000)
        proc.process(t1)
        proc.process(t3)  # gap at seq 2 — rejected
        assert len(received) == 1


class TestCounters:
    def test_accepted_count(self):
        proc = _processor([])
        trades = make_trade_sequence(5, start_ns=1_700_000_000_000_000_000)
        for t in trades:
            proc.process(t)
        assert proc.accepted_count == 5

    def test_rejected_count(self):
        proc = _processor([])
        t = make_trade("1")
        proc.process(t)
        proc.process(t)  # duplicate
        assert proc.rejected_count == 1

    def test_zero_counters_initially(self):
        proc = _processor([])
        assert proc.accepted_count == 0
        assert proc.rejected_count == 0


class TestReset:
    def test_reset_allows_new_sequence(self):
        received: list[TradeEvent] = []
        proc = _processor(received)
        t1 = make_trade("1", sequence_no=1)
        proc.process(t1)
        proc.reset_stream("binance:BTCUSDT:trade")
        # After reset, a new first trade is accepted regardless of trade_id.
        t_new = make_trade("99", sequence_no=1, timestamp_ns=1_700_000_001_000_000_000)
        proc.process(t_new)
        assert proc.accepted_count == 2
