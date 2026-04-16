"""Tests for the Phase 6C edge-health tracker."""

from __future__ import annotations

from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.edge_health.models import EdgeFSMState, EdgeSignalRecord
from crypto_core.edge_health.tracker import EdgeHealthTracker, _classify_fsm, _compute_ehs


def _signal(
    *,
    confidence: float,
    score: float,
    valid: bool = True,
    timestamp_ns: int,
    family: EdgeFamily = EdgeFamily.ORDER_FLOW_IMBALANCE,
) -> EdgeSignal:
    if not valid:
        return EdgeSignal.invalid(
            family=family,
            symbol="BTCUSDT",
            exchange="binance",
            reason="blocked",
            timestamp_ns=timestamp_ns,
        )
    return EdgeSignal(
        family=family,
        symbol="BTCUSDT",
        exchange="binance",
        direction=SignalDirection.BUY,
        confidence=confidence,
        score=score,
        evidence={},
        timestamp_ns=timestamp_ns,
        is_valid=True,
        block_reason=None,
    )


def test_compute_ehs_returns_none_for_insufficient_observations() -> None:
    records = [
        EdgeSignalRecord(
            family=EdgeFamily.ORDER_FLOW_IMBALANCE,
            symbol="BTCUSDT",
            exchange="binance",
            is_valid=True,
            confidence=0.8,
            timestamp_ns=1_000,
            score=0.6,
        ),
        EdgeSignalRecord(
            family=EdgeFamily.ORDER_FLOW_IMBALANCE,
            symbol="BTCUSDT",
            exchange="binance",
            is_valid=True,
            confidence=0.75,
            timestamp_ns=2_000,
            score=0.5,
        ),
    ]
    assert _compute_ehs(records, min_observations=5) is None


def test_classify_fsm_maps_new_warning_band() -> None:
    assert _classify_fsm(None) == EdgeFSMState.WARNING
    assert _classify_fsm(0.88) == EdgeFSMState.ACTIVE
    assert _classify_fsm(0.60) == EdgeFSMState.WARNING
    assert _classify_fsm(0.29) == EdgeFSMState.DISABLED


def test_tracker_exposes_active_edge_with_full_allocation() -> None:
    tracker = EdgeHealthTracker(min_observations=5)
    signals = [
        _signal(confidence=0.82, score=0.70, timestamp_ns=1_000),
        _signal(confidence=0.80, score=0.68, timestamp_ns=2_000),
        _signal(confidence=0.85, score=0.74, timestamp_ns=3_000),
        _signal(confidence=0.81, score=0.72, timestamp_ns=4_000),
        _signal(confidence=0.84, score=0.75, timestamp_ns=5_000),
    ]

    tracker.record_signals(signals)
    snapshot = tracker.snapshot_for_key(EdgeFamily.ORDER_FLOW_IMBALANCE, "BTCUSDT", "binance", 5_000)

    assert snapshot is not None
    assert snapshot.fsm_state == EdgeFSMState.ACTIVE
    assert snapshot.ehs_score is not None and snapshot.ehs_score > 0.8
    assert snapshot.allocation_factor == 1.0
    assert snapshot.component_availability_ratio == 1.0
    assert len(snapshot.ehs_components) == 4


def test_tracker_enters_warning_with_reduced_capacity() -> None:
    tracker = EdgeHealthTracker(min_observations=6)
    signals = [
        _signal(confidence=0.50, score=0.20, timestamp_ns=1_000),
        _signal(confidence=0.45, score=0.15, timestamp_ns=2_000),
        _signal(confidence=0.40, score=0.10, timestamp_ns=3_000),
        _signal(confidence=0.0, score=0.0, valid=False, timestamp_ns=4_000),
        _signal(confidence=0.0, score=0.0, valid=False, timestamp_ns=5_000),
        _signal(confidence=0.0, score=0.0, valid=False, timestamp_ns=6_000),
    ]

    tracker.record_signals(signals)
    snapshot = tracker.snapshot_for_key(EdgeFamily.ORDER_FLOW_IMBALANCE, "BTCUSDT", "binance", 6_000)

    assert snapshot is not None
    assert snapshot.fsm_state == EdgeFSMState.WARNING
    assert snapshot.ehs_score is not None and 0.4 <= snapshot.ehs_score < 0.8
    assert snapshot.allocation_factor is not None and 0.25 < snapshot.allocation_factor < 1.0
    edge_input = tracker.to_edge_health_input("BTCUSDT", "binance", 6_000)
    assert edge_input is not None
    assert edge_input.edge_fsm_state == EdgeFSMState.WARNING
    assert edge_input.edge_health_score == snapshot.ehs_score


def test_tracker_transitions_to_quarantine_after_repeated_disabled_cycles() -> None:
    tracker = EdgeHealthTracker(window_size=5, min_observations=5)
    weak_cycle = [
        _signal(confidence=0.0, score=0.0, valid=False, timestamp_ns=1_000),
        _signal(confidence=0.0, score=0.0, valid=False, timestamp_ns=2_000),
        _signal(confidence=0.0, score=0.0, valid=False, timestamp_ns=3_000),
        _signal(confidence=0.0, score=0.0, valid=False, timestamp_ns=4_000),
        _signal(confidence=0.0, score=0.0, valid=False, timestamp_ns=5_000),
    ]
    recovery_cycle = [_signal(confidence=0.82, score=0.70, timestamp_ns=6_000 + idx) for idx in range(5)]
    second_weak_cycle = [
        _signal(confidence=0.0, score=0.0, valid=False, timestamp_ns=7_000),
        _signal(confidence=0.0, score=0.0, valid=False, timestamp_ns=7_001),
        _signal(confidence=0.0, score=0.0, valid=False, timestamp_ns=7_002),
        _signal(confidence=0.0, score=0.0, valid=False, timestamp_ns=7_003),
        _signal(confidence=0.0, score=0.0, valid=False, timestamp_ns=7_004),
    ]

    tracker.record_signals(weak_cycle)
    tracker.record_signals(recovery_cycle)
    tracker.record_signals(second_weak_cycle)

    snapshot = tracker.snapshot_for_key(EdgeFamily.ORDER_FLOW_IMBALANCE, "BTCUSDT", "binance", 8_000)

    assert snapshot is not None
    assert snapshot.fsm_state == EdgeFSMState.QUARANTINE
    assert snapshot.quarantine_until_ns is not None
    assert snapshot.allocation_factor == 0.0


def test_tracker_snapshot_counts_warning_and_quarantine_edges() -> None:
    tracker = EdgeHealthTracker(window_size=5, min_observations=5)
    active = [_signal(confidence=0.85, score=0.70, timestamp_ns=10_000 + idx) for idx in range(5)]
    warning = [
        _signal(
            confidence=0.50 - idx * 0.05,
            score=0.20 - idx * 0.05,
            timestamp_ns=20_000 + idx,
            family=EdgeFamily.FUNDING_RATE,
        )
        for idx in range(3)
    ]
    warning.append(
        _signal(
            confidence=0.0,
            score=0.0,
            valid=False,
            timestamp_ns=20_003,
            family=EdgeFamily.FUNDING_RATE,
        )
    )
    warning.append(
        _signal(
            confidence=0.0,
            score=0.0,
            valid=False,
            timestamp_ns=20_004,
            family=EdgeFamily.FUNDING_RATE,
        )
    )
    disabled = [
        _signal(
            confidence=0.0,
            score=0.0,
            valid=False,
            timestamp_ns=30_000 + idx,
            family=EdgeFamily.LIQUIDATION_SIGNAL,
        )
        for idx in range(5)
    ]

    tracker.record_signals(active)
    tracker.record_signals(warning)
    tracker.record_signals(disabled)
    tracker.record_signals(
        [
            _signal(
                confidence=0.84,
                score=0.70,
                timestamp_ns=35_000 + idx,
                family=EdgeFamily.LIQUIDATION_SIGNAL,
            )
            for idx in range(5)
        ]
    )
    tracker.record_signals(
        [
            _signal(
                confidence=0.0,
                score=0.0,
                valid=False,
                timestamp_ns=40_000 + idx,
                family=EdgeFamily.LIQUIDATION_SIGNAL,
            )
            for idx in range(5)
        ]
    )

    summary = tracker.tracker_snapshot(45_000)

    assert len(summary.family_snapshots) == 3
    assert summary.active_edge_count == 2
    assert summary.warning_edge_count == 1
    assert summary.quarantine_edge_count == 1
    assert summary.capacity_red_count == 0
