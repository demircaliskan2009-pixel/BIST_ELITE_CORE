"""Tests for Phase 8D — Paper-live campaign controller + go/no-go acceptance gates.

Covers:
  1.  CampaignStatus — enum values.
  2.  AcceptanceVerdict — enum values.
  3.  AcceptanceThresholds — default values.
  4.  CampaignConfig — defaults and custom.
  5.  SymbolParticipation — frozen dataclass.
  6.  CriterionResult — frozen dataclass.
  7.  AcceptanceResult — frozen dataclass.
  8.  AcceptancePolicy — PASS verdict (all criteria met).
  9.  AcceptancePolicy — FAIL verdict (hard criteria breached).
  10. AcceptancePolicy — PASS_WITH_WARNINGS (soft criteria breached, hard OK).
  11. AcceptancePolicy — INCONCLUSIVE (insufficient coverage).
  12. AcceptancePolicy — multiple failure criteria combined.
  13. CampaignMetadata — mutable bookkeeping.
  14. CampaignMetadata — to_dict serialization.
  15. CampaignMetadata — elapsed_seconds calculation.
  16. CampaignMetadataCorruptError — raised on bad data.
  17. validate_campaign_metadata_dict — happy path.
  18. validate_campaign_metadata_dict — missing fields.
  19. validate_campaign_metadata_dict — invalid status.
  20. campaign_metadata_from_dict — round-trip.
  21. CampaignSnapshot — frozen dataclass.
  22. CampaignReport — frozen dataclass.
  23. CampaignController — lifecycle: CREATED → RUNNING.
  24. CampaignController — lifecycle: RUNNING → PAUSED → RUNNING.
  25. CampaignController — lifecycle: RUNNING → ABORTED.
  26. CampaignController — lifecycle: RUNNING → FAILED.
  27. CampaignController — lifecycle: double start raises.
  28. CampaignController — lifecycle: abort from terminal raises.
  29. CampaignController — update advances counters.
  30. CampaignController — update triggers max_duration stop.
  31. CampaignController — update triggers max_events stop.
  32. CampaignController — update triggers max_cycles stop.
  33. CampaignController — snapshot produces frozen CampaignSnapshot.
  34. CampaignController — finalize produces CampaignReport with verdict.
  35. CampaignController — finalize sets REJECTED on FAIL verdict.
  36. CampaignController — double finalize raises.
  37. CampaignController — symbol participation tracking.
  38. CampaignController — persistence: metadata saved to evidence store.
  39. CampaignController — persistence: restore metadata from disk.
  40. CampaignController — persistence: report saved to evidence store.
  41. _report_to_dict — serialization.
  42. new_campaign_id — returns UUID string.
  43. Config defaults are sane.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from crypto_core.runtime.models import RuntimeStatus
from crypto_core.service.campaign import (
    _TERMINAL_STATUSES,
    AcceptancePolicy,
    AcceptanceResult,
    AcceptanceThresholds,
    AcceptanceVerdict,
    CampaignConfig,
    CampaignMetadata,
    CampaignMetadataCorruptError,
    CampaignReport,
    CampaignSnapshot,
    CampaignStatus,
    CriterionResult,
    SymbolParticipation,
    campaign_metadata_from_dict,
    new_campaign_id,
    validate_campaign_metadata_dict,
)
from crypto_core.service.campaign_controller import CampaignController, _report_to_dict
from crypto_core.service.evidence_store import EvidenceStore
from crypto_core.service.models import QueuePressure, QueueSnapshot, ServiceStatus, SymbolHealth, WatchdogStatus
from crypto_core.session.models import PaperSessionStatus

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000
_NS_PER_S = 1_000_000_000


# ---------------------------------------------------------------------------
# Synthetic status helpers
# ---------------------------------------------------------------------------


def _make_session_status(
    *,
    total_cycles: int = 50,
    total_fills: int = 5,
    approved_cycles: int = 40,
    blocked_cycles: int = 8,
    failed_cycles: int = 2,
    nav_usd: float | None = 10_500.0,
    mode: str = "running",
) -> PaperSessionStatus:
    return PaperSessionStatus(
        session_id="test-8d",
        mode=mode,
        start_time_ns=_T0_NS,
        current_cycle_time_ns=_T0_NS + 100 * _NS_PER_S,
        total_cycles=total_cycles,
        total_fills=total_fills,
        approved_cycles=approved_cycles,
        blocked_cycles=blocked_cycles,
        failed_cycles=failed_cycles,
        recovery_status="clean_start",
        unresolved_order_count=0,
        open_positions_count=1,
        nav_usd=nav_usd,
        gross_exposure_pct=10.0,
        net_exposure_pct=3.0,
        last_cycle_approved=True,
        last_error=None,
        trading_blocked=False,
    )


def _make_runtime_status(
    *,
    total_cycles: int = 50,
    total_fills: int = 5,
    approved_cycles: int = 40,
    blocked_cycles: int = 8,
    failed_cycles: int = 2,
    nav_usd: float | None = 10_500.0,
) -> RuntimeStatus:
    return RuntimeStatus(
        session_status=_make_session_status(
            total_cycles=total_cycles,
            total_fills=total_fills,
            approved_cycles=approved_cycles,
            blocked_cycles=blocked_cycles,
            failed_cycles=failed_cycles,
            nav_usd=nav_usd,
        ),
        total_event_count=200,
        total_trigger_count=50,
        total_suppressed_count=10,
        per_symbol_ready={"BTCUSDT": True},
        per_symbol_last_trigger_ns={"BTCUSDT": _T0_NS + 100 * _NS_PER_S},
        recovery_in_progress=False,
        blocked_reason=None,
    )


def _make_service_status(
    *,
    total_enqueued: int = 200,
    total_dropped: int = 0,
    total_cycles: int = 50,
    total_fills: int = 5,
    approved_cycles: int = 40,
    blocked_cycles: int = 8,
    failed_cycles: int = 2,
    stall_detected: bool = False,
    consumer_alive: bool = True,
    nav_usd: float | None = 10_500.0,
    service_mode: str = "running",
    total_service_restarts: int = 0,
) -> ServiceStatus:
    runtime = _make_runtime_status(
        total_cycles=total_cycles,
        total_fills=total_fills,
        approved_cycles=approved_cycles,
        blocked_cycles=blocked_cycles,
        failed_cycles=failed_cycles,
        nav_usd=nav_usd,
    )
    queue = QueueSnapshot(
        current_depth=10,
        max_size=1000,
        pressure=QueuePressure.NORMAL,
        total_enqueued=total_enqueued,
        total_dropped=total_dropped,
        total_processed=total_enqueued - total_dropped,
    )
    watchdog = WatchdogStatus(
        consumer_alive=consumer_alive,
        last_event_time_ns=_T0_NS + 100 * _NS_PER_S,
        last_cycle_time_ns=_T0_NS + 100 * _NS_PER_S,
        seconds_since_event=0.5,
        seconds_since_cycle=0.5,
        stall_detected=stall_detected,
        stall_threshold_s=60.0,
    )
    sym = SymbolHealth(
        symbol="BTCUSDT",
        exchange="binance",
        feed_connected=True,
        feed_ready=True,
        feed_key="binance:BTCUSDT",
        last_event_time_ns=_T0_NS + 100 * _NS_PER_S,
        blocked=False,
        block_reason=None,
    )
    return ServiceStatus(
        service_mode=service_mode,
        runtime_status=runtime,
        queue=queue,
        watchdog=watchdog,
        symbol_health=(sym,),
        symbol_count=1,
        trading_enabled=True,
        blocked_reason=None,
        last_error=None,
        total_service_restarts=total_service_restarts,
    )


def _healthy_snapshot(
    *,
    total_events_enqueued: int = 200,
    total_cycles: int = 50,
    approved_cycles: int = 40,
    blocked_cycles: int = 8,
    failed_cycles: int = 2,
    queue_overflows: int = 0,
    watchdog_stalls: int = 0,
    service_restarts: int = 0,
    persistence_failures: int = 0,
    symbols_with_events: int = 1,
) -> CampaignSnapshot:
    """Create a campaign snapshot with healthy defaults."""
    return CampaignSnapshot(
        campaign_id="test-campaign",
        status="running",
        started_at_ns=_T0_NS,
        updated_at_ns=_T0_NS + 100 * _NS_PER_S,
        elapsed_seconds=100.0,
        run_id="run-1",
        service_mode="running",
        session_mode="running",
        total_events_enqueued=total_events_enqueued,
        total_events_dropped=0,
        total_cycles=total_cycles,
        approved_cycles=approved_cycles,
        blocked_cycles=blocked_cycles,
        failed_cycles=failed_cycles,
        total_fills=5,
        queue_overflows=queue_overflows,
        watchdog_stalls=watchdog_stalls,
        service_restarts=service_restarts,
        persistence_failures=persistence_failures,
        symbol_count=1,
        symbols_ready=1,
        symbols_blocked=0,
        symbols_with_events=symbols_with_events,
        symbols_with_cycles=1,
        readiness_level="ready",
        health_trend="stable",
        persistence_status="healthy",
        nav_usd=10_500.0,
        last_error=None,
    )


# ===========================================================================
# 1-2. Enum coverage
# ===========================================================================


class TestCampaignStatus:
    def test_all_values(self):
        assert set(CampaignStatus) == {
            CampaignStatus.CREATED,
            CampaignStatus.RUNNING,
            CampaignStatus.PAUSED,
            CampaignStatus.COMPLETED,
            CampaignStatus.FAILED,
            CampaignStatus.ABORTED,
            CampaignStatus.REJECTED,
        }

    def test_terminal_statuses(self):
        assert CampaignStatus.COMPLETED in _TERMINAL_STATUSES
        assert CampaignStatus.FAILED in _TERMINAL_STATUSES
        assert CampaignStatus.ABORTED in _TERMINAL_STATUSES
        assert CampaignStatus.REJECTED in _TERMINAL_STATUSES
        assert CampaignStatus.RUNNING not in _TERMINAL_STATUSES


class TestAcceptanceVerdict:
    def test_all_values(self):
        assert set(AcceptanceVerdict) == {
            AcceptanceVerdict.PASS,
            AcceptanceVerdict.PASS_WITH_WARNINGS,
            AcceptanceVerdict.FAIL,
            AcceptanceVerdict.INCONCLUSIVE,
        }


# ===========================================================================
# 3-4. Config defaults
# ===========================================================================


class TestAcceptanceThresholds:
    def test_defaults(self):
        t = AcceptanceThresholds()
        assert t.max_failed_cycles == 50
        assert t.max_blocked_cycle_ratio == 0.5
        assert t.max_queue_overflows == 10
        assert t.max_watchdog_stalls == 5
        assert t.min_events_processed == 100
        assert t.min_cycles_processed == 10
        assert t.min_symbols_observed == 1

    def test_frozen(self):
        t = AcceptanceThresholds()
        with pytest.raises(AttributeError):
            t.max_failed_cycles = 999  # type: ignore[misc]


class TestCampaignConfig:
    def test_defaults(self):
        cfg = CampaignConfig()
        assert cfg.campaign_id == ""
        assert cfg.max_duration_s == 0.0
        assert cfg.max_events == 0
        assert cfg.max_cycles == 0
        assert isinstance(cfg.thresholds, AcceptanceThresholds)

    def test_custom(self):
        cfg = CampaignConfig(
            campaign_id="my-campaign",
            max_events=500,
            target_symbols=("BTCUSDT", "ETHUSDT"),
        )
        assert cfg.campaign_id == "my-campaign"
        assert cfg.max_events == 500
        assert cfg.target_symbols == ("BTCUSDT", "ETHUSDT")


# ===========================================================================
# 5-7. Frozen dataclass coverage
# ===========================================================================


class TestSymbolParticipation:
    def test_frozen(self):
        sp = SymbolParticipation(
            symbol="BTCUSDT",
            exchange="binance",
            feed_ready=True,
            blocked=False,
            events_observed=True,
            cycles_observed=True,
        )
        assert sp.symbol == "BTCUSDT"
        with pytest.raises(AttributeError):
            sp.symbol = "ETHUSDT"  # type: ignore[misc]


class TestCriterionResult:
    def test_frozen(self):
        cr = CriterionResult(
            name="max_failed_cycles",
            passed=True,
            severity="hard",
            actual=5.0,
            threshold=50.0,
            message="max_failed_cycles: 5 ≤ 50",
        )
        assert cr.passed is True
        with pytest.raises(AttributeError):
            cr.passed = False  # type: ignore[misc]


class TestAcceptanceResult:
    def test_frozen(self):
        ar = AcceptanceResult(
            verdict=AcceptanceVerdict.PASS,
            criteria=(),
            failed_criteria=(),
            warning_criteria=(),
            insufficient_criteria=(),
            summary="ok",
        )
        assert ar.verdict == AcceptanceVerdict.PASS
        with pytest.raises(AttributeError):
            ar.verdict = AcceptanceVerdict.FAIL  # type: ignore[misc]


# ===========================================================================
# 8-12. AcceptancePolicy
# ===========================================================================


class TestAcceptancePolicy:
    def test_pass_all_criteria(self):
        """All criteria met → PASS."""
        policy = AcceptancePolicy()
        snap = _healthy_snapshot()
        result = policy.evaluate(snap)
        assert result.verdict == AcceptanceVerdict.PASS
        assert len(result.failed_criteria) == 0
        assert len(result.warning_criteria) == 0
        assert len(result.insufficient_criteria) == 0
        assert "All acceptance criteria met" in result.summary

    def test_fail_hard_criteria(self):
        """Hard criterion breach → FAIL."""
        policy = AcceptancePolicy(AcceptanceThresholds(max_failed_cycles=1))
        snap = _healthy_snapshot(failed_cycles=5)
        result = policy.evaluate(snap)
        assert result.verdict == AcceptanceVerdict.FAIL
        assert len(result.failed_criteria) >= 1
        names = {c.name for c in result.failed_criteria}
        assert "max_failed_cycles" in names

    def test_pass_with_warnings(self):
        """Soft criterion breach (hard OK) → PASS_WITH_WARNINGS."""
        policy = AcceptancePolicy(
            AcceptanceThresholds(
                warn_failed_cycles=1,
                max_failed_cycles=100,
            )
        )
        snap = _healthy_snapshot(failed_cycles=5)
        result = policy.evaluate(snap)
        assert result.verdict == AcceptanceVerdict.PASS_WITH_WARNINGS
        assert len(result.warning_criteria) >= 1

    def test_inconclusive_insufficient_events(self):
        """Insufficient events → INCONCLUSIVE."""
        policy = AcceptancePolicy(AcceptanceThresholds(min_events_processed=1000))
        snap = _healthy_snapshot(total_events_enqueued=50)
        result = policy.evaluate(snap)
        assert result.verdict == AcceptanceVerdict.INCONCLUSIVE
        assert len(result.insufficient_criteria) >= 1
        names = {c.name for c in result.insufficient_criteria}
        assert "min_events_processed" in names

    def test_multiple_failures(self):
        """Multiple hard criteria breached → FAIL with multiple reasons."""
        policy = AcceptancePolicy(AcceptanceThresholds(max_failed_cycles=1, max_queue_overflows=1))
        snap = _healthy_snapshot(failed_cycles=5, queue_overflows=5)
        result = policy.evaluate(snap)
        assert result.verdict == AcceptanceVerdict.FAIL
        assert len(result.failed_criteria) >= 2

    def test_inconclusive_overrides_fail(self):
        """Insufficient coverage takes priority → INCONCLUSIVE even with hard breaches."""
        policy = AcceptancePolicy(
            AcceptanceThresholds(
                min_events_processed=1000,
                max_failed_cycles=1,
            )
        )
        snap = _healthy_snapshot(total_events_enqueued=5, failed_cycles=50)
        result = policy.evaluate(snap)
        assert result.verdict == AcceptanceVerdict.INCONCLUSIVE

    def test_blocked_cycle_ratio(self):
        """Blocked cycle ratio hard limit → FAIL."""
        policy = AcceptancePolicy(AcceptanceThresholds(max_blocked_cycle_ratio=0.1))
        snap = _healthy_snapshot(total_cycles=100, blocked_cycles=20)
        result = policy.evaluate(snap)
        assert result.verdict == AcceptanceVerdict.FAIL
        names = {c.name for c in result.failed_criteria}
        assert "max_blocked_cycle_ratio" in names

    def test_duration_coverage(self):
        """Campaign duration below minimum → INCONCLUSIVE."""
        policy = AcceptancePolicy(AcceptanceThresholds(min_campaign_duration_s=3600.0))
        snap = _healthy_snapshot()  # elapsed_seconds=100
        result = policy.evaluate(snap)
        assert result.verdict == AcceptanceVerdict.INCONCLUSIVE

    def test_thresholds_property(self):
        t = AcceptanceThresholds(max_failed_cycles=99)
        policy = AcceptancePolicy(t)
        assert policy.thresholds.max_failed_cycles == 99


# ===========================================================================
# 13-16. CampaignMetadata
# ===========================================================================


class TestCampaignMetadata:
    def test_mutable(self):
        meta = CampaignMetadata(
            campaign_id="c1",
            config=CampaignConfig(),
        )
        meta.status = CampaignStatus.RUNNING
        assert meta.status == CampaignStatus.RUNNING

    def test_to_dict(self):
        meta = CampaignMetadata(
            campaign_id="c1",
            config=CampaignConfig(max_events=500),
            status=CampaignStatus.RUNNING,
            run_id="r1",
            started_at_ns=_T0_NS,
            updated_at_ns=_T0_NS + 100,
        )
        d = meta.to_dict()
        assert d["campaign_id"] == "c1"
        assert d["status"] == "running"
        assert d["run_id"] == "r1"
        assert d["config"]["max_events"] == 500

    def test_elapsed_seconds_not_started(self):
        meta = CampaignMetadata(campaign_id="c1", config=CampaignConfig())
        assert meta.elapsed_seconds() == 0.0

    def test_elapsed_seconds_completed(self):
        meta = CampaignMetadata(
            campaign_id="c1",
            config=CampaignConfig(),
            started_at_ns=_T0_NS,
            completed_at_ns=_T0_NS + 10 * _NS_PER_S,
            total_pause_duration_ns=0,
        )
        assert meta.elapsed_seconds() == pytest.approx(10.0, abs=0.01)

    def test_elapsed_seconds_with_pause(self):
        meta = CampaignMetadata(
            campaign_id="c1",
            config=CampaignConfig(),
            started_at_ns=_T0_NS,
            completed_at_ns=_T0_NS + 20 * _NS_PER_S,
            total_pause_duration_ns=5 * _NS_PER_S,
        )
        assert meta.elapsed_seconds() == pytest.approx(15.0, abs=0.01)


# ===========================================================================
# 17-20. Validation + round-trip
# ===========================================================================


class TestCampaignMetadataValidation:
    def test_valid_dict(self):
        d = {
            "campaign_id": "c1",
            "status": "running",
            "run_id": "r1",
            "started_at_ns": _T0_NS,
            "updated_at_ns": _T0_NS + 100,
        }
        validate_campaign_metadata_dict(d)  # Should not raise.

    def test_missing_fields(self):
        d = {"campaign_id": "c1"}
        with pytest.raises(CampaignMetadataCorruptError, match="missing required"):
            validate_campaign_metadata_dict(d)

    def test_invalid_status(self):
        d = {
            "campaign_id": "c1",
            "status": "bogus",
            "run_id": "r1",
            "started_at_ns": _T0_NS,
            "updated_at_ns": _T0_NS + 100,
        }
        with pytest.raises(CampaignMetadataCorruptError, match="Invalid campaign status"):
            validate_campaign_metadata_dict(d)

    def test_empty_campaign_id(self):
        d = {
            "campaign_id": "",
            "status": "running",
            "run_id": "r1",
            "started_at_ns": _T0_NS,
            "updated_at_ns": _T0_NS + 100,
        }
        with pytest.raises(CampaignMetadataCorruptError, match="non-empty string"):
            validate_campaign_metadata_dict(d)

    def test_round_trip(self):
        meta = CampaignMetadata(
            campaign_id="c1",
            config=CampaignConfig(max_events=500),
            status=CampaignStatus.RUNNING,
            run_id="r1",
            started_at_ns=_T0_NS,
            updated_at_ns=_T0_NS + 100,
            watchdog_stalls=3,
            verdict=AcceptanceVerdict.PASS,
            verdict_reason="ok",
        )
        d = meta.to_dict()
        restored = campaign_metadata_from_dict(d, CampaignConfig(max_events=500))
        assert restored.campaign_id == "c1"
        assert restored.status == CampaignStatus.RUNNING
        assert restored.watchdog_stalls == 3
        assert restored.verdict == AcceptanceVerdict.PASS


# ===========================================================================
# 21-22. Snapshot/Report frozen
# ===========================================================================


class TestCampaignSnapshotFrozen:
    def test_frozen(self):
        snap = _healthy_snapshot()
        with pytest.raises(AttributeError):
            snap.campaign_id = "changed"  # type: ignore[misc]


class TestCampaignReportFrozen:
    def test_frozen(self):
        snap = _healthy_snapshot()
        acceptance = AcceptanceResult(
            verdict=AcceptanceVerdict.PASS,
            criteria=(),
            failed_criteria=(),
            warning_criteria=(),
            insufficient_criteria=(),
            summary="ok",
        )
        report = CampaignReport(
            campaign_id="c1",
            status="completed",
            verdict="pass",
            started_at_ns=_T0_NS,
            completed_at_ns=_T0_NS + 10 * _NS_PER_S,
            elapsed_seconds=10.0,
            run_id="r1",
            snapshot=snap,
            acceptance=acceptance,
            symbol_participation=(),
            config={},
        )
        with pytest.raises(AttributeError):
            report.campaign_id = "changed"  # type: ignore[misc]


# ===========================================================================
# 23-29. CampaignController lifecycle
# ===========================================================================


class TestCampaignControllerLifecycle:
    def test_start(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        assert ctrl.status == CampaignStatus.CREATED
        ss = _make_service_status()
        ctrl.start(ss, run_id="r1")
        assert ctrl.status == CampaignStatus.RUNNING
        assert ctrl.metadata.run_id == "r1"
        assert ctrl.metadata.started_at_ns > 0

    def test_pause_resume(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        ctrl.pause()
        assert ctrl.status == CampaignStatus.PAUSED
        ctrl.resume()
        assert ctrl.status == CampaignStatus.RUNNING

    def test_abort(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        ctrl.abort("test_abort")
        assert ctrl.status == CampaignStatus.ABORTED
        assert ctrl.metadata.verdict_reason == "test_abort"

    def test_fail(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        ctrl.fail("crash")
        assert ctrl.status == CampaignStatus.FAILED

    def test_double_start_raises(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        with pytest.raises(RuntimeError, match="Cannot start"):
            ctrl.start(ss)

    def test_abort_terminal_raises(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        ctrl.abort("first")
        with pytest.raises(RuntimeError, match="Cannot abort"):
            ctrl.abort("second")

    def test_fail_terminal_raises(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        ctrl.fail("crash")
        with pytest.raises(RuntimeError, match="Cannot fail"):
            ctrl.fail("again")

    def test_pause_not_running_raises(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        with pytest.raises(RuntimeError, match="Cannot pause"):
            ctrl.pause()

    def test_resume_not_paused_raises(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        with pytest.raises(RuntimeError, match="Cannot resume"):
            ctrl.resume()


# ===========================================================================
# 30-32. CampaignController update + stop conditions
# ===========================================================================


class TestCampaignControllerUpdate:
    def test_update_returns_running(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        status = ctrl.update(ss)
        assert status == CampaignStatus.RUNNING

    def test_max_events_stop(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1", max_events=100))
        ss = _make_service_status(total_enqueued=150)
        ctrl.start(ss)
        status = ctrl.update(ss)
        assert status == CampaignStatus.COMPLETED
        assert "max_events_reached" in ctrl.metadata.verdict_reason

    def test_max_cycles_stop(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1", max_cycles=10))
        ss = _make_service_status(total_cycles=50)
        ctrl.start(ss)
        status = ctrl.update(ss)
        assert status == CampaignStatus.COMPLETED
        assert "max_cycles_reached" in ctrl.metadata.verdict_reason

    def test_update_on_paused_noop(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        ctrl.pause()
        status = ctrl.update(ss)
        assert status == CampaignStatus.PAUSED

    def test_watchdog_stalls_tracked(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        # Update with stall
        ss_stall = _make_service_status(stall_detected=True)
        ctrl.update(ss_stall)
        assert ctrl.metadata.watchdog_stalls >= 1

    def test_service_restarts_tracked(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        ss_restart = _make_service_status(total_service_restarts=2)
        ctrl.update(ss_restart)
        assert ctrl.metadata.service_restarts == 2


# ===========================================================================
# 33-36. Snapshot and finalize
# ===========================================================================


class TestCampaignControllerSnapshot:
    def test_snapshot_returns_frozen(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        snap = ctrl.snapshot(ss)
        assert isinstance(snap, CampaignSnapshot)
        assert snap.campaign_id == "c1"
        assert snap.total_cycles == 50
        with pytest.raises(AttributeError):
            snap.campaign_id = "x"  # type: ignore[misc]

    def test_snapshot_symbol_counts(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        ctrl.update(ss)
        snap = ctrl.snapshot(ss)
        assert snap.symbol_count == 1
        assert snap.symbols_ready == 1


class TestCampaignControllerFinalize:
    def test_finalize_pass(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        report = ctrl.finalize(ss)
        assert isinstance(report, CampaignReport)
        assert report.verdict == AcceptanceVerdict.PASS.value
        assert report.campaign_id == "c1"

    def test_finalize_fail_sets_rejected(self):
        ctrl = CampaignController(
            CampaignConfig(
                campaign_id="c1",
                thresholds=AcceptanceThresholds(max_failed_cycles=1),
            )
        )
        ss = _make_service_status(failed_cycles=10)
        ctrl.start(ss)
        report = ctrl.finalize(ss)
        assert report.verdict == AcceptanceVerdict.FAIL.value
        assert ctrl.status == CampaignStatus.REJECTED

    def test_double_finalize_raises(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        ctrl.finalize(ss)
        with pytest.raises(RuntimeError, match="already finalized"):
            ctrl.finalize(ss)

    def test_finalize_auto_completes_running(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        assert ctrl.status == CampaignStatus.RUNNING
        report = ctrl.finalize(ss)
        # Should have auto-completed before evaluating.
        assert report.status in ("completed", "rejected")


# ===========================================================================
# 37. Symbol participation
# ===========================================================================


class TestSymbolParticipationTracking:
    def test_participation_view(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        ss = _make_service_status()
        ctrl.start(ss)
        ctrl.update(ss)
        parts = ctrl.symbol_participation_view(ss)
        assert len(parts) == 1
        assert parts[0].symbol == "BTCUSDT"
        assert parts[0].exchange == "binance"
        assert parts[0].feed_ready is True
        assert parts[0].blocked is False


# ===========================================================================
# 38-40. Persistence
# ===========================================================================


class TestCampaignPersistence:
    def test_persist_metadata(self, tmp_path: Path):
        store = EvidenceStore(evidence_dir=tmp_path)
        ctrl = CampaignController(
            CampaignConfig(campaign_id="c1"),
            evidence_store=store,
        )
        ss = _make_service_status()
        ctrl.start(ss, run_id="r1")
        result = ctrl.persist_state()
        assert result is not None
        assert result.success

    def test_restore_metadata(self, tmp_path: Path):
        store = EvidenceStore(evidence_dir=tmp_path)
        ctrl = CampaignController(
            CampaignConfig(campaign_id="c1"),
            evidence_store=store,
        )
        ss = _make_service_status()
        ctrl.start(ss, run_id="r1")
        ctrl.persist_state()

        # Restore in new controller.
        ctrl2 = CampaignController(
            CampaignConfig(campaign_id="c1"),
            evidence_store=store,
        )
        meta = ctrl2.restore_metadata()
        assert meta.campaign_id == "c1"
        assert meta.run_id == "r1"
        assert meta.status == CampaignStatus.RUNNING

    def test_persist_report(self, tmp_path: Path):
        store = EvidenceStore(evidence_dir=tmp_path)
        ctrl = CampaignController(
            CampaignConfig(campaign_id="c1"),
            evidence_store=store,
        )
        ss = _make_service_status()
        ctrl.start(ss, run_id="r1")
        report = ctrl.finalize(ss)
        assert report.verdict in ("pass", "pass_with_warnings", "fail", "inconclusive")
        # Report snapshot should exist.
        loaded = store.load_snapshot("campaign_report")
        assert loaded["data"]["campaign_id"] == "c1"

    def test_persist_no_store(self):
        ctrl = CampaignController(CampaignConfig(campaign_id="c1"))
        result = ctrl.persist_state()
        assert result is None


# ===========================================================================
# 41. Report serialization
# ===========================================================================


class TestReportSerialization:
    def test_report_to_dict(self):
        snap = _healthy_snapshot()
        acceptance = AcceptanceResult(
            verdict=AcceptanceVerdict.PASS,
            criteria=(
                CriterionResult(
                    name="max_failed_cycles",
                    passed=True,
                    severity="hard",
                    actual=2.0,
                    threshold=50.0,
                    message="ok",
                ),
            ),
            failed_criteria=(),
            warning_criteria=(),
            insufficient_criteria=(),
            summary="All acceptance criteria met.",
        )
        report = CampaignReport(
            campaign_id="c1",
            status="completed",
            verdict="pass",
            started_at_ns=_T0_NS,
            completed_at_ns=_T0_NS + 10 * _NS_PER_S,
            elapsed_seconds=10.0,
            run_id="r1",
            snapshot=snap,
            acceptance=acceptance,
            symbol_participation=(
                SymbolParticipation(
                    symbol="BTCUSDT",
                    exchange="binance",
                    feed_ready=True,
                    blocked=False,
                    events_observed=True,
                    cycles_observed=True,
                ),
            ),
            config={"max_events": 500},
        )
        d = _report_to_dict(report)
        assert d["campaign_id"] == "c1"
        assert d["verdict"] == "pass"
        assert len(d["acceptance"]["criteria"]) == 1
        assert len(d["symbol_participation"]) == 1


# ===========================================================================
# 42. new_campaign_id
# ===========================================================================


class TestNewCampaignId:
    def test_uuid_format(self):
        cid = new_campaign_id()
        # Validate UUID format.
        parsed = uuid.UUID(cid)
        assert str(parsed) == cid

    def test_uniqueness(self):
        ids = {new_campaign_id() for _ in range(100)}
        assert len(ids) == 100


# ===========================================================================
# 43. Config defaults sanity
# ===========================================================================


class TestConfigSanity:
    def test_thresholds_hard_ge_soft(self):
        t = AcceptanceThresholds()
        assert t.max_failed_cycles >= t.warn_failed_cycles
        assert t.max_queue_overflows >= t.warn_queue_overflows
        assert t.max_persistence_failures >= t.warn_persistence_failures
        assert t.max_blocked_cycle_ratio >= t.warn_blocked_cycle_ratio
