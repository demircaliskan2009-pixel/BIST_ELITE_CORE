"""Comprehensive tests for the Phase 5F EdgeHealthTracker subsystem.

Coverage targets:
  1. Model construction and validation (enums, frozen dataclasses)
  2. EHS proxy score computation (mean confidence formula)
  3. FSM state transitions (ACTIVE → DEGRADED → DISABLED)
  4. Explicit disable / enable operations
  5. Utilization band classification (SAFE / WARNING / RED)
  6. Valid edge count aggregation (NT-E04 logic)
  7. Bounded rolling history (window overflow)
  8. Fail-closed malformed record rejection
  9. Deterministic replay (identical inputs → identical outputs)
  10. to_edge_health_input aggregation (worst-case semantics)
  11. NT-E01: guard blocks on low EHS
  12. NT-E02: guard blocks on DISABLED edge
  13. NT-E03: guard blocks on RED utilization
  14. NT-E04: guard blocks on zero valid edges
  15. Orchestrator integration (tracker wired, telemetry enriched)
  16. First-cycle safety (no history → NT-E family disabled)
  17. record_signals() from EdgeSignal objects
  18. reset() test isolation contract
"""

from __future__ import annotations

import pytest

from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.edge_health.models import (
    EdgeFSMState,
    EdgeHealthSnapshot,
    EdgeHealthTrackerSnapshot,
    EdgeSignalRecord,
    UtilizationBand,
)
from crypto_core.edge_health.tracker import (
    EdgeHealthTracker,
    EdgeSignalRecordError,
    _classify_fsm,
    _classify_utilization,
    _compute_ehs,
)
from crypto_core.guard.models import EdgeHealthInput

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SYM = "BTCUSDT"
EX = "binance"
FAM = "order_flow_imbalance"
FAM2 = "funding_rate"
TS = 1_700_000_000_000_000_000  # nanoseconds


def make_record(
    *,
    family: str = FAM,
    symbol: str = SYM,
    exchange: str = EX,
    is_valid: bool = True,
    confidence: float = 0.8,
    timestamp_ns: int = TS,
    utilization_pct: float | None = None,
) -> EdgeSignalRecord:
    return EdgeSignalRecord(
        family=family,
        symbol=symbol,
        exchange=exchange,
        is_valid=is_valid,
        confidence=confidence,
        timestamp_ns=timestamp_ns,
        utilization_pct=utilization_pct,
    )


def make_invalid_record(**kwargs) -> EdgeSignalRecord:
    return make_record(is_valid=False, confidence=0.0, **kwargs)


def make_edge_signal(
    *,
    family: str = FAM,
    symbol: str = SYM,
    exchange: str = EX,
    is_valid: bool = True,
    confidence: float = 0.8,
    timestamp_ns: int = TS,
) -> EdgeSignal:
    if is_valid:
        return EdgeSignal(
            family=EdgeFamily(family),
            symbol=symbol,
            exchange=exchange,
            direction=SignalDirection.BUY,
            confidence=confidence,
            score=0.5,
            evidence={},
            timestamp_ns=timestamp_ns,
            is_valid=True,
            block_reason=None,
        )
    return EdgeSignal.invalid(
        family=EdgeFamily(family),
        symbol=symbol,
        exchange=exchange,
        reason="test_block",
        timestamp_ns=timestamp_ns,
    )


# ---------------------------------------------------------------------------
# 1. Model construction
# ---------------------------------------------------------------------------


class TestEdgeFSMState:
    def test_enum_values(self):
        assert EdgeFSMState.ACTIVE == "ACTIVE"
        assert EdgeFSMState.DEGRADED == "DEGRADED"
        assert EdgeFSMState.DISABLED == "DISABLED"

    def test_is_str(self):
        assert isinstance(EdgeFSMState.ACTIVE, str)

    def test_str_upper_guard_compat(self):
        """Guard evaluates edge_fsm_state.upper() == 'DISABLED'."""
        # .value is used in to_edge_health_input() to produce plain string for guard.
        assert EdgeFSMState.DISABLED.value.upper() == "DISABLED"


class TestUtilizationBand:
    def test_enum_values(self):
        assert UtilizationBand.SAFE == "safe"
        assert UtilizationBand.WARNING == "warning"
        assert UtilizationBand.RED == "red"


class TestEdgeSignalRecord:
    def test_frozen(self):
        r = make_record()
        with pytest.raises(Exception):
            r.confidence = 0.5  # type: ignore[misc]

    def test_default_utilization_none(self):
        r = make_record()
        assert r.utilization_pct is None

    def test_with_utilization(self):
        r = make_record(utilization_pct=42.0)
        assert r.utilization_pct == 42.0


class TestEdgeHealthSnapshot:
    def test_frozen(self):
        snap = EdgeHealthSnapshot(
            family=FAM,
            symbol=SYM,
            exchange=EX,
            ehs_score=0.8,
            fsm_state=EdgeFSMState.ACTIVE,
            utilization_pct=None,
            utilization_band=None,
            observation_count=10,
            is_valid_edge=True,
            snapshot_ns=TS,
        )
        with pytest.raises(Exception):
            snap.ehs_score = 0.5  # type: ignore[misc]


class TestEdgeHealthTrackerSnapshot:
    def test_frozen(self):
        snap = EdgeHealthTrackerSnapshot(
            valid_edge_count=1,
            disabled_edge_count=0,
            active_edge_count=1,
            min_ehs=0.8,
            max_ehs=0.9,
            capacity_red_count=0,
            snapshot_ns=TS,
            family_snapshots=(),
        )
        with pytest.raises(Exception):
            snap.valid_edge_count = 2  # type: ignore[misc]

    def test_hashable(self):
        snap = EdgeHealthTrackerSnapshot(
            valid_edge_count=1,
            disabled_edge_count=0,
            active_edge_count=1,
            min_ehs=0.8,
            max_ehs=0.9,
            capacity_red_count=0,
            snapshot_ns=TS,
            family_snapshots=(),
        )
        # Should be hashable (tuple field, all frozen members)
        assert hash(snap) == hash(snap)


# ---------------------------------------------------------------------------
# 2. EHS proxy score computation
# ---------------------------------------------------------------------------


class TestComputeEHS:
    def test_none_below_min_observations(self):
        records = [make_record(confidence=0.9) for _ in range(4)]
        assert _compute_ehs(records, 5) is None

    def test_none_empty(self):
        assert _compute_ehs([], 5) is None

    def test_all_valid_high_confidence(self):
        records = [make_record(confidence=1.0) for _ in range(5)]
        assert _compute_ehs(records, 5) == pytest.approx(1.0)

    def test_all_invalid_zero_confidence(self):
        records = [make_invalid_record() for _ in range(5)]
        assert _compute_ehs(records, 5) == pytest.approx(0.0)

    def test_mixed_mean(self):
        # 5 records: 3 valid @1.0, 2 invalid @0.0 → mean = 3/5 = 0.6
        records = [make_record(confidence=1.0)] * 3 + [make_invalid_record()] * 2
        assert _compute_ehs(records, 5) == pytest.approx(0.6)

    def test_exactly_at_min_observations(self):
        records = [make_record(confidence=0.5) for _ in range(5)]
        result = _compute_ehs(records, 5)
        assert result == pytest.approx(0.5)

    def test_more_than_min_observations(self):
        records = [make_record(confidence=0.7) for _ in range(10)]
        assert _compute_ehs(records, 5) == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# 3. FSM state transitions
# ---------------------------------------------------------------------------


class TestClassifyFSM:
    def test_none_returns_active(self):
        """Insufficient history → optimistic ACTIVE (cannot claim disabled)."""
        assert _classify_fsm(None) == EdgeFSMState.ACTIVE

    def test_high_ehs_active(self):
        assert _classify_fsm(0.30) == EdgeFSMState.ACTIVE
        assert _classify_fsm(0.80) == EdgeFSMState.ACTIVE
        assert _classify_fsm(1.0) == EdgeFSMState.ACTIVE

    def test_degraded_band(self):
        assert _classify_fsm(0.10) == EdgeFSMState.DEGRADED
        assert _classify_fsm(0.20) == EdgeFSMState.DEGRADED
        assert _classify_fsm(0.299) == EdgeFSMState.DEGRADED

    def test_disabled_below_floor(self):
        assert _classify_fsm(0.09) == EdgeFSMState.DISABLED
        assert _classify_fsm(0.0) == EdgeFSMState.DISABLED

    def test_boundary_at_degraded_threshold_is_active(self):
        assert _classify_fsm(0.30) == EdgeFSMState.ACTIVE

    def test_boundary_at_disable_threshold_is_degraded(self):
        assert _classify_fsm(0.10) == EdgeFSMState.DEGRADED


# ---------------------------------------------------------------------------
# 4. Utilization band classification
# ---------------------------------------------------------------------------


class TestClassifyUtilization:
    def test_none_returns_none(self):
        assert _classify_utilization(None) is None

    def test_safe_low(self):
        assert _classify_utilization(0.0) == UtilizationBand.SAFE
        assert _classify_utilization(49.9) == UtilizationBand.SAFE

    def test_warning_band(self):
        assert _classify_utilization(50.0) == UtilizationBand.WARNING
        assert _classify_utilization(79.9) == UtilizationBand.WARNING

    def test_red_band(self):
        assert _classify_utilization(80.0) == UtilizationBand.RED
        assert _classify_utilization(100.0) == UtilizationBand.RED

    def test_boundary_50_is_warning(self):
        assert _classify_utilization(50.0) == UtilizationBand.WARNING

    def test_boundary_80_is_red(self):
        assert _classify_utilization(80.0) == UtilizationBand.RED


# ---------------------------------------------------------------------------
# 5. Tracker construction
# ---------------------------------------------------------------------------


class TestTrackerConstruction:
    def test_default_construction(self):
        t = EdgeHealthTracker()
        assert t.window_size == 50
        assert t.min_observations == 5
        assert t.tracked_key_count == 0

    def test_custom_parameters(self):
        t = EdgeHealthTracker(window_size=20, min_observations=3)
        assert t.window_size == 20
        assert t.min_observations == 3

    def test_invalid_window_too_small(self):
        with pytest.raises(ValueError, match="window_size"):
            EdgeHealthTracker(window_size=1)

    def test_invalid_min_observations_zero(self):
        with pytest.raises(ValueError, match="min_observations"):
            EdgeHealthTracker(min_observations=0)

    def test_min_observations_exceeds_window(self):
        with pytest.raises(ValueError, match="min_observations"):
            EdgeHealthTracker(window_size=5, min_observations=10)


# ---------------------------------------------------------------------------
# 6. Fail-closed malformed record rejection
# ---------------------------------------------------------------------------


class TestRecordValidation:
    def test_valid_record_accepted(self):
        t = EdgeHealthTracker()
        t.record_signal(make_record())  # no exception

    def test_rejects_empty_family(self):
        with pytest.raises(EdgeSignalRecordError, match="family"):
            t = EdgeHealthTracker()
            t.record_signal(make_record(family=""))

    def test_rejects_empty_symbol(self):
        with pytest.raises(EdgeSignalRecordError, match="symbol"):
            t = EdgeHealthTracker()
            t.record_signal(make_record(symbol=""))

    def test_rejects_empty_exchange(self):
        with pytest.raises(EdgeSignalRecordError, match="exchange"):
            t = EdgeHealthTracker()
            t.record_signal(make_record(exchange=""))

    def test_rejects_confidence_above_one(self):
        with pytest.raises(EdgeSignalRecordError, match="confidence"):
            t = EdgeHealthTracker()
            t.record_signal(make_record(confidence=1.001))

    def test_rejects_confidence_below_zero(self):
        with pytest.raises(EdgeSignalRecordError, match="confidence"):
            t = EdgeHealthTracker()
            t.record_signal(make_record(confidence=-0.001))

    def test_rejects_negative_utilization(self):
        with pytest.raises(EdgeSignalRecordError, match="utilization_pct"):
            t = EdgeHealthTracker()
            t.record_signal(make_record(utilization_pct=-1.0))

    def test_accepts_zero_confidence(self):
        t = EdgeHealthTracker()
        t.record_signal(make_record(confidence=0.0))  # valid (invalid signal)

    def test_accepts_zero_utilization(self):
        t = EdgeHealthTracker()
        t.record_signal(make_record(utilization_pct=0.0))

    def test_accepts_max_utilization(self):
        t = EdgeHealthTracker()
        t.record_signal(make_record(utilization_pct=100.0))

    def test_multiple_errors_reported(self):
        """All errors collected and reported in one exception."""
        with pytest.raises(EdgeSignalRecordError) as exc:
            t = EdgeHealthTracker()
            t.record_signal(make_record(family="", confidence=2.0))
        assert "family" in str(exc.value)
        assert "confidence" in str(exc.value)


# ---------------------------------------------------------------------------
# 7. Snapshot computation — healthy edge
# ---------------------------------------------------------------------------


class TestSnapshotHealthyEdge:
    def test_no_history_returns_none_ehs(self):
        t = EdgeHealthTracker()
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.ehs_score is None
        assert snap.fsm_state == EdgeFSMState.ACTIVE
        assert snap.is_valid_edge is False
        assert snap.observation_count == 0

    def test_insufficient_history_returns_none_ehs(self):
        t = EdgeHealthTracker()
        for _ in range(4):  # need 5
            t.record_signal(make_record())
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.ehs_score is None
        assert snap.observation_count == 4

    def test_sufficient_history_valid_edge(self):
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record(confidence=0.8))
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.ehs_score == pytest.approx(0.8)
        assert snap.fsm_state == EdgeFSMState.ACTIVE
        assert snap.is_valid_edge is True  # 0.8 >= 0.50 threshold

    def test_utilization_propagates_from_last_record(self):
        t = EdgeHealthTracker()
        for i in range(5):
            t.record_signal(make_record(utilization_pct=float(i * 10)))
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.utilization_pct == pytest.approx(40.0)  # last record
        assert snap.utilization_band == UtilizationBand.SAFE

    def test_utilization_red_band(self):
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record(utilization_pct=90.0))
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.utilization_band == UtilizationBand.RED


# ---------------------------------------------------------------------------
# 8. Explicit disable / enable
# ---------------------------------------------------------------------------


class TestExplicitDisable:
    def test_disable_sets_disabled_state(self):
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record(confidence=0.9))
        t.disable_edge(FAM, SYM, EX)
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.fsm_state == EdgeFSMState.DISABLED
        assert snap.is_valid_edge is False

    def test_enable_removes_explicit_disable(self):
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record(confidence=0.9))
        t.disable_edge(FAM, SYM, EX)
        t.enable_edge(FAM, SYM, EX)
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.fsm_state == EdgeFSMState.ACTIVE
        assert snap.is_valid_edge is True

    def test_disable_key_with_no_history(self):
        t = EdgeHealthTracker()
        t.disable_edge(FAM, SYM, EX)
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.fsm_state == EdgeFSMState.DISABLED
        assert snap.ehs_score is None  # no history
        assert snap.is_valid_edge is False

    def test_disable_included_in_to_edge_health_input(self):
        """Disabled key with no history must appear in to_edge_health_input."""
        t = EdgeHealthTracker()
        t.disable_edge(FAM, SYM, EX)
        inp = t.to_edge_health_input(SYM, EX, TS)
        assert inp is not None
        assert inp.edge_fsm_state == "DISABLED"


# ---------------------------------------------------------------------------
# 9. Low-health and degraded edge
# ---------------------------------------------------------------------------


class TestLowHealthEdge:
    def test_ehs_below_degraded_threshold(self):
        t = EdgeHealthTracker()
        # 5 invalid signals → confidence=0.0 → ehs=0.0 → DISABLED
        for _ in range(5):
            t.record_signal(make_invalid_record())
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.ehs_score == pytest.approx(0.0)
        assert snap.fsm_state == EdgeFSMState.DISABLED
        assert snap.is_valid_edge is False

    def test_ehs_in_degraded_band(self):
        t = EdgeHealthTracker()
        # EHS = 0.20 (in degraded band 0.10–0.30)
        for _ in range(5):
            t.record_signal(make_record(confidence=0.20))
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.ehs_score == pytest.approx(0.20)
        assert snap.fsm_state == EdgeFSMState.DEGRADED
        assert snap.is_valid_edge is False  # 0.20 < 0.50 threshold

    def test_is_not_valid_below_ehs_threshold(self):
        t = EdgeHealthTracker()
        # EHS = 0.49 — above ACTIVE threshold but below valid threshold
        for _ in range(5):
            t.record_signal(make_record(confidence=0.49))
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.fsm_state == EdgeFSMState.ACTIVE
        assert snap.is_valid_edge is False  # 0.49 < 0.50

    def test_is_valid_at_ehs_valid_threshold(self):
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record(confidence=0.50))
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.is_valid_edge is True


# ---------------------------------------------------------------------------
# 10. Bounded rolling history
# ---------------------------------------------------------------------------


class TestBoundedHistory:
    def test_window_overflow_drops_oldest(self):
        t = EdgeHealthTracker(window_size=5, min_observations=3)
        for i in range(5):
            t.record_signal(make_record(confidence=1.0))
        # Add one more invalid — oldest valid is dropped
        t.record_signal(make_invalid_record())
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        # Window: [1.0, 1.0, 1.0, 1.0, 0.0] → mean = 4/5 = 0.8
        assert snap.observation_count == 5
        assert snap.ehs_score == pytest.approx(0.8)

    def test_many_signals_stays_bounded(self):
        t = EdgeHealthTracker(window_size=10, min_observations=5)
        for i in range(100):
            t.record_signal(make_record(confidence=0.7))
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.observation_count == 10

    def test_window_state_is_rolling_not_cumulative(self):
        t = EdgeHealthTracker(window_size=5, min_observations=5)
        # Fill with invalid signals
        for _ in range(5):
            t.record_signal(make_invalid_record())
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.ehs_score == pytest.approx(0.0)
        # Now push 5 valid signals — should fully replace
        for _ in range(5):
            t.record_signal(make_record(confidence=0.9))
        snap2 = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap2.ehs_score == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# 11. Deterministic replay
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    def test_identical_inputs_produce_identical_output(self):
        def run() -> EdgeHealthSnapshot:
            t = EdgeHealthTracker(window_size=10, min_observations=5)
            for i in range(8):
                t.record_signal(make_record(confidence=0.6))
            for i in range(2):
                t.record_signal(make_invalid_record())
            return t.snapshot_for_key(FAM, SYM, EX, TS)

        s1 = run()
        s2 = run()
        assert s1 == s2

    def test_identical_inputs_to_edge_health_input(self):
        def run() -> EdgeHealthInput | None:
            t = EdgeHealthTracker(window_size=10, min_observations=5)
            for _ in range(6):
                t.record_signal(make_record(confidence=0.75))
            return t.to_edge_health_input(SYM, EX, TS)

        r1 = run()
        r2 = run()
        assert r1 == r2


# ---------------------------------------------------------------------------
# 12. to_edge_health_input — aggregation
# ---------------------------------------------------------------------------


class TestToEdgeHealthInput:
    def test_no_history_returns_none(self):
        t = EdgeHealthTracker()
        assert t.to_edge_health_input(SYM, EX, TS) is None

    def test_first_cycle_returns_none(self):
        """Before any signals recorded, NT-E family must be disabled."""
        t = EdgeHealthTracker()
        result = t.to_edge_health_input(SYM, EX, TS)
        assert result is None

    def test_returns_input_after_sufficient_records(self):
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record(confidence=0.8))
        result = t.to_edge_health_input(SYM, EX, TS)
        assert result is not None
        assert isinstance(result, EdgeHealthInput)

    def test_min_ehs_across_families(self):
        """NT-E01: worst-case (minimum) EHS across families."""
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record(family=FAM, confidence=0.9))
        for _ in range(5):
            t.record_signal(make_record(family=FAM2, confidence=0.4))
        result = t.to_edge_health_input(SYM, EX, TS)
        assert result is not None
        assert result.edge_health_score == pytest.approx(0.4)

    def test_worst_fsm_state_across_families(self):
        """NT-E02: worst FSM state (DISABLED > DEGRADED > ACTIVE)."""
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record(family=FAM, confidence=0.9))
        t.disable_edge(FAM2, SYM, EX)  # explicitly disabled with no history
        result = t.to_edge_health_input(SYM, EX, TS)
        assert result is not None
        assert result.edge_fsm_state == "DISABLED"

    def test_max_utilization_across_families(self):
        """NT-E03: maximum utilization across families."""
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record(family=FAM, confidence=0.8, utilization_pct=30.0))
        for _ in range(5):
            t.record_signal(make_record(family=FAM2, confidence=0.8, utilization_pct=85.0))
        result = t.to_edge_health_input(SYM, EX, TS)
        assert result is not None
        assert result.edge_utilization_pct == pytest.approx(85.0)

    def test_valid_edge_count_none_when_no_history(self):
        """NT-E04: valid_count=None if no family has sufficient history."""
        t = EdgeHealthTracker()
        # Only 3 records (below min_observations=5)
        for _ in range(3):
            t.record_signal(make_record(confidence=0.9))
        result = t.to_edge_health_input(SYM, EX, TS)
        assert result is not None
        assert result.valid_edge_count is None

    def test_valid_edge_count_zero_when_all_degraded(self):
        """NT-E04: valid_count=0 when all families are below EHS threshold."""
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record(confidence=0.3))  # below 0.50 valid threshold
        result = t.to_edge_health_input(SYM, EX, TS)
        assert result is not None
        assert result.valid_edge_count == 0

    def test_valid_edge_count_correct(self):
        """NT-E04: correct count of valid families."""
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record(family=FAM, confidence=0.9))  # valid
        for _ in range(5):
            t.record_signal(make_record(family=FAM2, confidence=0.3))  # not valid
        result = t.to_edge_health_input(SYM, EX, TS)
        assert result is not None
        assert result.valid_edge_count == 1  # only FAM is valid

    def test_different_exchange_not_mixed(self):
        """Tracker does not mix symbols/exchanges."""
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record(exchange="bybit", confidence=0.1))
        result = t.to_edge_health_input(SYM, EX, TS)
        assert result is None  # binance has no history

    def test_ehs_none_when_all_families_insufficient_history(self):
        """If all families have < min_obs, edge_health_score should be None."""
        t = EdgeHealthTracker()
        for _ in range(3):  # below min_obs=5
            t.record_signal(make_record(confidence=0.9))
        result = t.to_edge_health_input(SYM, EX, TS)
        assert result is not None
        assert result.edge_health_score is None


# ---------------------------------------------------------------------------
# 13. NT-E01: guard blocks on low EHS
# ---------------------------------------------------------------------------


class TestNTE01_LowEHS:
    """Integration test: NT-E01 fires when EHS is below guard threshold."""

    def test_low_ehs_guard_fires(self):
        from crypto_core.guard.models import NoTradeContext, NoTradeReason, RiskGuardInput
        from crypto_core.guard.no_trade_guard import NoTradeConfig, NoTradeGuard

        t = EdgeHealthTracker()
        # Drive EHS to near 0 (all signals blocked)
        for _ in range(10):
            t.record_signal(make_invalid_record())
        edge_inp = t.to_edge_health_input(SYM, EX, TS)
        assert edge_inp is not None

        ctx = NoTradeContext(
            symbol=SYM,
            exchange=EX,
            current_ns=TS,
            book_last_update_ns=TS - 100,
            book_has_snapshot=True,
            book_bid_count=10,
            book_ask_count=10,
            feed_connection_state="connected",
            feed_recovery_state="idle",
            system_state="NORMAL",
            risk=RiskGuardInput(),
            market=None,
            edge=edge_inp,
        )
        guard = NoTradeGuard(NoTradeConfig())
        result = guard.evaluate(ctx)

        # NT-E01 should block (ehs < threshold)
        assert not result.allowed
        assert result.reason == NoTradeReason.EDGE_HEALTH_LOW


# ---------------------------------------------------------------------------
# 14. NT-E02: guard blocks on DISABLED edge
# ---------------------------------------------------------------------------


class TestNTE02_DisabledEdge:
    def test_disabled_fsm_guard_fires(self):
        from crypto_core.guard.models import NoTradeContext, NoTradeReason, RiskGuardInput
        from crypto_core.guard.no_trade_guard import NoTradeConfig, NoTradeGuard

        t = EdgeHealthTracker()
        for _ in range(10):
            t.record_signal(make_record(confidence=0.9))
        t.disable_edge(FAM, SYM, EX)
        edge_inp = t.to_edge_health_input(SYM, EX, TS)
        assert edge_inp is not None
        assert edge_inp.edge_fsm_state == "DISABLED"

        ctx = NoTradeContext(
            symbol=SYM,
            exchange=EX,
            current_ns=TS,
            book_last_update_ns=TS - 100,
            book_has_snapshot=True,
            book_bid_count=10,
            book_ask_count=10,
            feed_connection_state="connected",
            feed_recovery_state="idle",
            system_state="NORMAL",
            risk=RiskGuardInput(),
            market=None,
            edge=edge_inp,
        )
        guard = NoTradeGuard(NoTradeConfig())
        result = guard.evaluate(ctx)
        assert not result.allowed
        assert result.reason == NoTradeReason.EDGE_DISABLED


# ---------------------------------------------------------------------------
# 15. NT-E03: guard blocks on RED utilization
# ---------------------------------------------------------------------------


class TestNTE03_RedUtilization:
    def test_red_utilization_guard_fires(self):
        from crypto_core.guard.models import NoTradeContext, NoTradeReason, RiskGuardInput
        from crypto_core.guard.no_trade_guard import NoTradeConfig, NoTradeGuard

        t = EdgeHealthTracker()
        for _ in range(10):
            t.record_signal(make_record(confidence=0.9, utilization_pct=95.0))
        edge_inp = t.to_edge_health_input(SYM, EX, TS)
        assert edge_inp is not None
        assert edge_inp.edge_utilization_pct == pytest.approx(95.0)

        ctx = NoTradeContext(
            symbol=SYM,
            exchange=EX,
            current_ns=TS,
            book_last_update_ns=TS - 100,
            book_has_snapshot=True,
            book_bid_count=10,
            book_ask_count=10,
            feed_connection_state="connected",
            feed_recovery_state="idle",
            system_state="NORMAL",
            risk=RiskGuardInput(),
            market=None,
            edge=edge_inp,
        )
        guard = NoTradeGuard(NoTradeConfig())
        result = guard.evaluate(ctx)
        assert not result.allowed
        assert result.reason == NoTradeReason.EDGE_CAPACITY_RED


# ---------------------------------------------------------------------------
# 16. NT-E04: guard blocks on zero valid edges
# ---------------------------------------------------------------------------


class TestNTE04_ZeroValidEdges:
    def test_zero_valid_edges_guard_fires(self):
        from crypto_core.guard.models import NoTradeContext, NoTradeReason, RiskGuardInput
        from crypto_core.guard.no_trade_guard import NoTradeConfig, NoTradeGuard

        t = EdgeHealthTracker()
        # All signals produce low EHS (below valid threshold 0.50)
        for _ in range(10):
            t.record_signal(make_record(confidence=0.3))
        edge_inp = t.to_edge_health_input(SYM, EX, TS)
        assert edge_inp is not None
        assert edge_inp.valid_edge_count == 0

        ctx = NoTradeContext(
            symbol=SYM,
            exchange=EX,
            current_ns=TS,
            book_last_update_ns=TS - 100,
            book_has_snapshot=True,
            book_bid_count=10,
            book_ask_count=10,
            feed_connection_state="connected",
            feed_recovery_state="idle",
            system_state="NORMAL",
            risk=RiskGuardInput(),
            market=None,
            edge=edge_inp,
        )
        guard = NoTradeGuard(NoTradeConfig())
        result = guard.evaluate(ctx)
        assert not result.allowed
        assert result.reason == NoTradeReason.NO_VALID_EDGE


# ---------------------------------------------------------------------------
# 17. Orchestrator integration
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
    """Tests that the orchestrator correctly wires EdgeHealthTracker."""

    def _make_market_data(self):
        from crypto_core.orchestrator.models import MarketDataInput

        return MarketDataInput(
            symbol=SYM,
            exchange=EX,
            timestamp_ns=TS,
            trades=[],
            book_last_update_ns=TS - 1_000_000,
            book_has_snapshot=True,
            book_bid_count=10,
            book_ask_count=10,
            feed_connection_state="connected",
            feed_recovery_state="idle",
        )

    def test_orchestrator_accepts_edge_health_tracker(self):
        from crypto_core.orchestrator.pipeline import PipelineOrchestrator

        t = EdgeHealthTracker()
        orch = PipelineOrchestrator(edge_health_tracker=t)
        assert orch._edge_health_tracker is t

    def test_first_cycle_edge_input_is_none(self):
        """Before any signals are recorded, NT-E family stays disabled."""
        from crypto_core.orchestrator.pipeline import PipelineOrchestrator

        t = EdgeHealthTracker()
        orch = PipelineOrchestrator(edge_health_tracker=t)
        data = self._make_market_data()
        result = orch.process(data)
        # First cycle: no history → NT-E should not block
        # (guard should receive edge=None → NT-E family skipped)
        assert result is not None

    def test_tracker_updated_after_edge_stage(self):
        """Tracker has records after first pipeline cycle."""
        from crypto_core.orchestrator.pipeline import PipelineOrchestrator

        t = EdgeHealthTracker()
        orch = PipelineOrchestrator(edge_health_tracker=t)
        data = self._make_market_data()
        orch.process(data)
        # Tracker should now have at least one key recorded
        assert t.tracked_key_count >= 1

    def test_no_tracker_pipeline_still_works(self):
        """Pipeline without tracker must not regress — NT-E skipped."""
        from crypto_core.orchestrator.pipeline import PipelineOrchestrator

        orch = PipelineOrchestrator(edge_health_tracker=None)
        data = self._make_market_data()
        result = orch.process(data)
        assert result is not None

    def test_deterministic_two_cycle_replay(self):
        """Two calls with identical state must produce identical guard decision."""
        from crypto_core.orchestrator.pipeline import PipelineOrchestrator

        def run_two_cycles():
            t = EdgeHealthTracker()
            orch = PipelineOrchestrator(edge_health_tracker=t)
            data = self._make_market_data()
            orch.process(data)
            return orch.process(data)

        r1 = run_two_cycles()
        r2 = run_two_cycles()
        assert r1.no_trade_decision.allowed == r2.no_trade_decision.allowed
        assert r1.no_trade_decision.reason == r2.no_trade_decision.reason


# ---------------------------------------------------------------------------
# 18. record_signals from EdgeSignal objects
# ---------------------------------------------------------------------------


class TestRecordSignals:
    def test_valid_edge_signal_recorded(self):
        t = EdgeHealthTracker()
        sig = make_edge_signal(is_valid=True, confidence=0.8)
        t.record_signals([sig])
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.observation_count == 1

    def test_invalid_edge_signal_confidence_zero(self):
        t = EdgeHealthTracker()
        t.record_signals([make_edge_signal(is_valid=False)])
        snap = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap.observation_count == 1

    def test_multiple_signals_from_different_families(self):
        t = EdgeHealthTracker()
        sigs = [
            make_edge_signal(family=FAM, confidence=0.8),
            make_edge_signal(family=FAM2, confidence=0.6),
        ]
        t.record_signals(sigs)
        assert t.tracked_key_count == 2

    def test_empty_signals_list_is_noop(self):
        t = EdgeHealthTracker()
        t.record_signals([])
        assert t.tracked_key_count == 0


# ---------------------------------------------------------------------------
# 19. tracker_snapshot aggregation
# ---------------------------------------------------------------------------


class TestTrackerSnapshot:
    def test_empty_tracker_snapshot(self):
        t = EdgeHealthTracker()
        snap = t.tracker_snapshot(TS)
        assert snap.valid_edge_count is None
        assert snap.disabled_edge_count == 0
        assert snap.active_edge_count == 0
        assert snap.min_ehs is None
        assert snap.max_ehs is None
        assert snap.capacity_red_count == 0

    def test_snapshot_with_one_active_family(self):
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record(confidence=0.8))
        snap = t.tracker_snapshot(TS)
        assert snap.valid_edge_count == 1
        assert snap.active_edge_count == 1
        assert snap.disabled_edge_count == 0
        assert snap.min_ehs == pytest.approx(0.8)
        assert snap.max_ehs == pytest.approx(0.8)

    def test_snapshot_counts_disabled(self):
        t = EdgeHealthTracker()
        t.disable_edge(FAM, SYM, EX)
        snap = t.tracker_snapshot(TS)
        assert snap.disabled_edge_count == 1
        assert snap.active_edge_count == 0

    def test_snapshot_capacity_red_count(self):
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record(utilization_pct=90.0))
        snap = t.tracker_snapshot(TS)
        assert snap.capacity_red_count == 1

    def test_family_snapshots_populated(self):
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record(family=FAM, confidence=0.8))
        for _ in range(5):
            t.record_signal(make_record(family=FAM2, confidence=0.6))
        snap = t.tracker_snapshot(TS)
        assert len(snap.family_snapshots) == 2


# ---------------------------------------------------------------------------
# 20. reset() test isolation contract
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_clears_history(self):
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_record())
        t.reset()
        assert t.tracked_key_count == 0
        assert t.to_edge_health_input(SYM, EX, TS) is None

    def test_reset_clears_disabled_set(self):
        t = EdgeHealthTracker()
        t.disable_edge(FAM, SYM, EX)
        t.reset()
        assert t.tracked_key_count == 0
        assert t.to_edge_health_input(SYM, EX, TS) is None

    def test_reset_allows_fresh_start(self):
        t = EdgeHealthTracker()
        for _ in range(5):
            t.record_signal(make_invalid_record())
        snap_before = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap_before.fsm_state == EdgeFSMState.DISABLED

        t.reset()
        snap_after = t.snapshot_for_key(FAM, SYM, EX, TS)
        assert snap_after.fsm_state == EdgeFSMState.ACTIVE  # no history → ACTIVE
        assert snap_after.ehs_score is None
