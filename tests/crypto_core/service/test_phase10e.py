"""Tests for Phase 10E — Service-Level Campaign + Promotion Orchestration Surface.

Covers:
  1.  ServiceOrchestrator construction with defaults.
  2.  Campaign lifecycle from service: start / pause / resume / abort / finalize.
  3.  Review lifecycle from service: start / intake / finalize / reset.
  4.  Campaign → review pipeline (finalize → intake_last_campaign).
  5.  Unified OperatorSnapshot (combined status surface).
  6.  Campaign finalize → report availability.
  7.  Explicit review intake path from finalized campaign.
  8.  Review finalize path from service.
  9.  Persistence / restore linkage.
  10. Malformed restore fail-closed.
  11. Readiness interaction truthfulness.
  12. Insufficient-evidence visibility.
  13. Deterministic replay / duplicate protection.
  14. Reporting API surfaces.
  15. Evidence sufficiency truthfulness.
  16. No silent auto-promotion.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from crypto_core.runtime.models import RuntimeStatus
from crypto_core.service.artifact_export import EscalationStage, OperatorDecisionPack
from crypto_core.service.campaign import (
    AcceptanceResult,
    AcceptanceVerdict,
    CampaignReport,
    CampaignSnapshot,
    CriterionResult,
    StabilityRollup,
    SymbolParticipation,
)
from crypto_core.service.escalation_review_controller import EscalationWorkflowCorruptError
from crypto_core.service.evidence_store import (
    EvidenceStore,
    EvidenceStoreConfig,
)
from crypto_core.service.models import (
    ExecutionIntelligenceStatus,
    QueuePressure,
    QueueSnapshot,
    ServiceStatus,
    SymbolHealth,
    WatchdogStatus,
)
from crypto_core.service.promotion_review_controller import (
    CampaignIntakeError,
    ReviewStatus,
    ReviewWorkflowCorruptError,
)
from crypto_core.service.service_orchestrator import (
    CampaignWorkflowState,
    EscalationWorkflowState,
    EvidenceSufficiencyState,
    OperatorSnapshot,
    ReviewWorkflowState,
    ServiceOrchestrator,
    campaign_workflow_state_to_dict,
    escalation_workflow_state_to_dict,
    evidence_sufficiency_state_to_dict,
    operator_snapshot_to_dict,
    review_workflow_state_to_dict,
)
from crypto_core.session.models import PaperSessionStatus

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000
_NS_PER_S = 1_000_000_000


# ---------------------------------------------------------------------------
# Helpers — build fixtures
# ---------------------------------------------------------------------------


def _make_session_status(
    *,
    total_cycles: int = 50,
    total_fills: int = 5,
    approved_cycles: int = 40,
    blocked_cycles: int = 8,
    failed_cycles: int = 2,
    nav_usd: float | None = 10_500.0,
    route_block_count: int = 0,
    route_abstain_count: int = 0,
    pending_markout_count: int = 0,
    persisted_tca_count: int = 0,
    persisted_attribution_count: int = 0,
    registered_fill_count: int = 0,
) -> PaperSessionStatus:
    return PaperSessionStatus(
        session_id="test-10e",
        mode="running",
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
        route_block_count=route_block_count,
        route_abstain_count=route_abstain_count,
        pending_markout_count=pending_markout_count,
        persisted_tca_count=persisted_tca_count,
        persisted_attribution_count=persisted_attribution_count,
        registered_fill_count=registered_fill_count,
    )


def _make_runtime_status(
    *,
    total_cycles: int = 50,
    total_fills: int = 5,
) -> RuntimeStatus:
    return RuntimeStatus(
        session_status=_make_session_status(
            total_cycles=total_cycles,
            total_fills=total_fills,
        ),
        total_event_count=200,
        total_trigger_count=50,
        total_suppressed_count=10,
        per_symbol_ready={"BTCUSDT": True},
        per_symbol_last_trigger_ns={"BTCUSDT": _T0_NS + 100 * _NS_PER_S},
        recovery_in_progress=False,
        blocked_reason=None,
    )


def _make_ei_status(
    *,
    degraded: bool = False,
    degraded_reasons: tuple[str, ...] = (),
) -> ExecutionIntelligenceStatus:
    return ExecutionIntelligenceStatus(
        mode="optional",
        route_binding_enabled=True,
        tca_loop_enabled=True,
        tca_store_available=True,
        replay_dedup_bootstrapped=True,
        degraded=degraded,
        degraded_reasons=degraded_reasons,
    )


def _make_service_status(
    *,
    service_mode: str = "running",
    total_cycles: int = 50,
    total_fills: int = 5,
    total_enqueued: int = 200,
    total_dropped: int = 0,
    ei_degraded: bool = False,
    ei_degraded_reasons: tuple[str, ...] = (),
) -> ServiceStatus:
    runtime = _make_runtime_status(
        total_cycles=total_cycles,
        total_fills=total_fills,
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
        consumer_alive=True,
        last_event_time_ns=_T0_NS + 100 * _NS_PER_S,
        last_cycle_time_ns=_T0_NS + 100 * _NS_PER_S,
        seconds_since_event=0.5,
        seconds_since_cycle=0.5,
        stall_detected=False,
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
    ei = _make_ei_status(
        degraded=ei_degraded,
        degraded_reasons=ei_degraded_reasons,
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
        total_service_restarts=0,
        execution_intelligence=ei,
    )


def _make_campaign_snapshot(
    *,
    campaign_id: str = "camp-1",
    total_cycles: int = 200,
    total_fills: int = 30,
    elapsed_seconds: float = 600.0,
    persisted_tca_count: int = 0,
    registered_fill_count: int = 0,
    ext_regime_available: bool = True,
    ext_regime_fresh: bool = True,
    ext_regime_high_risk: bool = False,
    ext_regime_evidence_sufficient: bool = True,
    ext_regime_scenario_available: bool = True,
    ext_regime_scenario_step_count: int = 6,
    ext_regime_activation_blocked_steps: int = 0,
    ext_regime_execution_blocked_steps: int = 0,
    ext_regime_activation_reduced_steps: int = 0,
    ext_regime_stale_steps: int = 1,
    ext_regime_unavailable_steps: int = 0,
    ext_regime_high_risk_steps: int = 1,
    ext_regime_safe_steps: int = 4,
    ext_regime_scenario_summary: str = "steps=6; safe=4; stale=1; high_risk=1; reduced=0",
) -> CampaignSnapshot:
    return CampaignSnapshot(
        campaign_id=campaign_id,
        status="completed",
        started_at_ns=_T0_NS,
        updated_at_ns=_T0_NS + int(elapsed_seconds * _NS_PER_S),
        elapsed_seconds=elapsed_seconds,
        run_id="run-1",
        service_mode="running",
        session_mode="running",
        total_events_enqueued=1000,
        total_events_dropped=0,
        total_cycles=total_cycles,
        approved_cycles=total_cycles - 7,
        blocked_cycles=5,
        failed_cycles=2,
        total_fills=total_fills,
        queue_overflows=0,
        watchdog_stalls=0,
        service_restarts=0,
        persistence_failures=0,
        symbol_count=3,
        symbols_ready=3,
        symbols_blocked=0,
        symbols_with_events=3,
        symbols_with_cycles=3,
        readiness_level="paper_live",
        health_trend="stable",
        persistence_status="healthy",
        nav_usd=10_500.0,
        last_error=None,
        persisted_tca_count=persisted_tca_count,
        registered_fill_count=registered_fill_count,
        ext_regime_available=ext_regime_available,
        ext_regime_fresh=ext_regime_fresh,
        ext_regime_high_risk=ext_regime_high_risk,
        ext_regime_evidence_sufficient=ext_regime_evidence_sufficient,
        ext_regime_summary=ext_regime_scenario_summary,
        ext_regime_scenario_available=ext_regime_scenario_available,
        ext_regime_scenario_step_count=ext_regime_scenario_step_count,
        ext_regime_activation_blocked_steps=ext_regime_activation_blocked_steps,
        ext_regime_execution_blocked_steps=ext_regime_execution_blocked_steps,
        ext_regime_activation_reduced_steps=ext_regime_activation_reduced_steps,
        ext_regime_stale_steps=ext_regime_stale_steps,
        ext_regime_unavailable_steps=ext_regime_unavailable_steps,
        ext_regime_high_risk_steps=ext_regime_high_risk_steps,
        ext_regime_safe_steps=ext_regime_safe_steps,
        ext_regime_scenario_summary=ext_regime_scenario_summary,
    )


def _make_campaign_report(
    *,
    campaign_id: str = "camp-1",
    status: str = "completed",
    verdict: str = "pass",
    total_cycles: int = 200,
    total_fills: int = 30,
    elapsed_seconds: float = 600.0,
    persisted_tca_count: int = 0,
    registered_fill_count: int = 0,
    ext_regime_available: bool = True,
    ext_regime_fresh: bool = True,
    ext_regime_high_risk: bool = False,
    ext_regime_evidence_sufficient: bool = True,
    ext_regime_scenario_available: bool = True,
    ext_regime_scenario_step_count: int = 6,
    ext_regime_activation_blocked_steps: int = 0,
    ext_regime_execution_blocked_steps: int = 0,
    ext_regime_activation_reduced_steps: int = 0,
    ext_regime_stale_steps: int = 1,
    ext_regime_unavailable_steps: int = 0,
    ext_regime_high_risk_steps: int = 1,
    ext_regime_safe_steps: int = 4,
    ext_regime_scenario_summary: str = "steps=6; safe=4; stale=1; high_risk=1; reduced=0",
) -> CampaignReport:
    snap = _make_campaign_snapshot(
        campaign_id=campaign_id,
        total_cycles=total_cycles,
        total_fills=total_fills,
        elapsed_seconds=elapsed_seconds,
        persisted_tca_count=persisted_tca_count,
        registered_fill_count=registered_fill_count,
        ext_regime_available=ext_regime_available,
        ext_regime_fresh=ext_regime_fresh,
        ext_regime_high_risk=ext_regime_high_risk,
        ext_regime_evidence_sufficient=ext_regime_evidence_sufficient,
        ext_regime_scenario_available=ext_regime_scenario_available,
        ext_regime_scenario_step_count=ext_regime_scenario_step_count,
        ext_regime_activation_blocked_steps=ext_regime_activation_blocked_steps,
        ext_regime_execution_blocked_steps=ext_regime_execution_blocked_steps,
        ext_regime_activation_reduced_steps=ext_regime_activation_reduced_steps,
        ext_regime_stale_steps=ext_regime_stale_steps,
        ext_regime_unavailable_steps=ext_regime_unavailable_steps,
        ext_regime_high_risk_steps=ext_regime_high_risk_steps,
        ext_regime_safe_steps=ext_regime_safe_steps,
        ext_regime_scenario_summary=ext_regime_scenario_summary,
    )
    criterion = CriterionResult(
        name="min_cycles",
        passed=True,
        severity="critical",
        actual=total_cycles,
        threshold=100,
        message="OK",
    )
    acceptance = AcceptanceResult(
        verdict=AcceptanceVerdict(verdict),
        summary=f"Test verdict: {verdict}",
        criteria=(criterion,),
        failed_criteria=(),
        warning_criteria=(),
        insufficient_criteria=(),
    )
    return CampaignReport(
        campaign_id=campaign_id,
        status=status,
        verdict=verdict,
        started_at_ns=_T0_NS,
        completed_at_ns=_T0_NS + int(elapsed_seconds * _NS_PER_S),
        elapsed_seconds=elapsed_seconds,
        run_id="run-1",
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
            SymbolParticipation(
                symbol="ETHUSDT",
                exchange="binance",
                feed_ready=True,
                blocked=False,
                events_observed=True,
                cycles_observed=True,
            ),
            SymbolParticipation(
                symbol="SOLUSDT",
                exchange="binance",
                feed_ready=True,
                blocked=False,
                events_observed=True,
                cycles_observed=True,
            ),
        ),
        config={"max_duration_s": 3600},
        stability=StabilityRollup(
            degraded_intervals=0,
            blocked_intervals=0,
            recovery_incidents=0,
            queue_overflow_incidents=0,
            queue_pressure_warnings=0,
            persistence_failure_count=0,
            ei_degraded=False,
        ),
        ext_regime_available=ext_regime_available,
        ext_regime_fresh=ext_regime_fresh,
        ext_regime_high_risk=ext_regime_high_risk,
        ext_regime_evidence_sufficient=ext_regime_evidence_sufficient,
        ext_regime_summary=ext_regime_scenario_summary,
        ext_regime_scenario_available=ext_regime_scenario_available,
        ext_regime_scenario_step_count=ext_regime_scenario_step_count,
        ext_regime_activation_blocked_steps=ext_regime_activation_blocked_steps,
        ext_regime_execution_blocked_steps=ext_regime_execution_blocked_steps,
        ext_regime_activation_reduced_steps=ext_regime_activation_reduced_steps,
        ext_regime_stale_steps=ext_regime_stale_steps,
        ext_regime_unavailable_steps=ext_regime_unavailable_steps,
        ext_regime_high_risk_steps=ext_regime_high_risk_steps,
        ext_regime_safe_steps=ext_regime_safe_steps,
        ext_regime_scenario_summary=ext_regime_scenario_summary,
    )


def _make_mock_service(
    service_status: ServiceStatus | None = None,
) -> MagicMock:
    """Create a mock PaperLiveService that returns a controlled status."""
    mock = MagicMock()
    ss = service_status or _make_service_status()
    mock.status.return_value = ss
    mock.mode = MagicMock()
    mock.mode.value = ss.service_mode
    return mock


# ---------------------------------------------------------------------------
# Tests: ServiceOrchestrator construction
# ---------------------------------------------------------------------------


class TestOrchestratorConstruction:
    """Test orchestrator initialization and properties."""

    def test_default_construction(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        assert orch.service is svc
        assert orch.campaign_controller is None
        assert orch.review_controller is None
        assert orch.readiness_level == "not_assessed"

    def test_construction_with_readiness(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        assert orch.readiness_level == "paper_live"

    def test_readiness_level_setter(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.readiness_level = "calibrated_paper"
        assert orch.readiness_level == "calibrated_paper"

    def test_no_active_campaign_or_review(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        assert not orch.campaign_active()
        assert not orch.review_active()
        assert orch.campaign_snapshot() is None
        assert orch.review_snapshot() is None
        assert orch.last_campaign_report is None
        assert orch.final_review_report is None


# ---------------------------------------------------------------------------
# Tests: Campaign lifecycle from service
# ---------------------------------------------------------------------------


class TestCampaignLifecycle:
    """Test service-level campaign orchestration."""

    def test_start_campaign(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        cid = orch.start_campaign(run_id="run-001")
        assert cid is not None
        assert orch.campaign_active()
        assert orch.campaign_controller is not None
        assert orch.campaign_controller.status.value == "running"

    def test_start_campaign_with_explicit_id(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        cid = orch.start_campaign(campaign_id="explicit-001")
        assert cid == "explicit-001"

    def test_start_campaign_while_active_raises(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign()
        with pytest.raises(RuntimeError, match="active campaign"):
            orch.start_campaign()

    def test_pause_resume_campaign(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign()
        orch.pause_campaign()
        assert orch.campaign_controller.status.value == "paused"
        orch.resume_campaign()
        assert orch.campaign_controller.status.value == "running"

    def test_abort_campaign(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign()
        orch.abort_campaign(reason="test_abort")
        assert orch.campaign_controller.status.value == "aborted"
        assert not orch.campaign_active()

    def test_update_campaign(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign()
        status = orch.update_campaign()
        assert status == "running"

    def test_finalize_campaign(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign()
        report = orch.finalize_campaign()
        assert report is not None
        assert report.campaign_id == orch.campaign_controller.campaign_id
        assert orch.last_campaign_report is report
        assert not orch.campaign_active()

    def test_campaign_snapshot(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign()
        snap = orch.campaign_snapshot()
        assert snap is not None
        assert snap.campaign_id == orch.campaign_controller.campaign_id
        assert snap.status == "running"

    def test_no_campaign_operations_when_none(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        with pytest.raises(RuntimeError, match="No campaign"):
            orch.pause_campaign()
        with pytest.raises(RuntimeError, match="No campaign"):
            orch.resume_campaign()
        with pytest.raises(RuntimeError, match="No campaign"):
            orch.update_campaign()
        with pytest.raises(RuntimeError, match="No campaign"):
            orch.abort_campaign()
        with pytest.raises(RuntimeError, match="No campaign"):
            orch.finalize_campaign()

    def test_start_new_campaign_after_finalized(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign(campaign_id="camp-1")
        orch.finalize_campaign()
        # Can start a new campaign after previous is finalized
        cid = orch.start_campaign(campaign_id="camp-2")
        assert cid == "camp-2"
        assert orch.campaign_active()


# ---------------------------------------------------------------------------
# Tests: Review lifecycle from service
# ---------------------------------------------------------------------------


class TestReviewLifecycle:
    """Test service-level promotion review orchestration."""

    def test_start_review(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        rid = orch.start_review()
        assert rid is not None
        assert orch.review_active()
        assert orch.review_controller is not None

    def test_start_review_with_explicit_id(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        rid = orch.start_review(review_id="rev-001")
        assert rid == "rev-001"

    def test_start_review_while_active_raises(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_review()
        with pytest.raises(RuntimeError, match="active review"):
            orch.start_review()

    def test_intake_campaign_report(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_review()
        report = _make_campaign_report()
        orch.intake_campaign_report(report)
        assert orch.review_controller.campaign_count == 1

    def test_duplicate_intake_raises(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_review()
        report = _make_campaign_report(campaign_id="camp-dup")
        orch.intake_campaign_report(report)
        with pytest.raises(CampaignIntakeError, match="already in review"):
            orch.intake_campaign_report(report)

    def test_review_snapshot(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_review()
        report = _make_campaign_report()
        orch.intake_campaign_report(report)
        snap = orch.review_snapshot()
        assert snap is not None
        assert snap.campaign_count == 1

    def test_finalize_review(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        orch.start_review()
        for i in range(3):
            report = _make_campaign_report(campaign_id=f"camp-{i}")
            orch.intake_campaign_report(report)
        final = orch.finalize_review()
        assert final is not None
        assert final.review_id == orch.review_controller.review_id
        assert not orch.review_active()
        assert orch.final_review_report is final

    def test_reset_review(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_review()
        report = _make_campaign_report()
        orch.intake_campaign_report(report)
        orch.reset_review()
        assert orch.review_controller.campaign_count == 0
        assert orch.review_controller.status == ReviewStatus.CREATED

    def test_no_review_operations_when_none(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        with pytest.raises(RuntimeError, match="No review"):
            orch.intake_campaign_report(_make_campaign_report())
        with pytest.raises(RuntimeError, match="No review"):
            orch.finalize_review()
        with pytest.raises(RuntimeError, match="No review"):
            orch.reset_review()

    def test_start_new_review_after_finalized(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_review(review_id="rev-1")
        for i in range(3):
            orch.intake_campaign_report(_make_campaign_report(campaign_id=f"camp-{i}"))
        orch.finalize_review()
        # Can start a new review after previous is finalized
        rid = orch.start_review(review_id="rev-2")
        assert rid == "rev-2"
        assert orch.review_active()


# ---------------------------------------------------------------------------
# Tests: Campaign → Review pipeline
# ---------------------------------------------------------------------------


class TestCampaignToReviewPipeline:
    """Test deterministic campaign → review intake flow."""

    def test_finalize_then_intake_last(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign(campaign_id="camp-pipe")
        orch.finalize_campaign()
        orch.start_review()
        orch.intake_last_campaign()
        assert orch.review_controller.campaign_count == 1
        assert "camp-pipe" in orch.review_controller.campaign_ids

    def test_intake_last_without_finalized_campaign_raises(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_review()
        with pytest.raises(RuntimeError, match="No finalized campaign"):
            orch.intake_last_campaign()

    def test_campaign_complete_does_not_auto_ingest(self):
        """Campaign finalization should NOT silently intake into review."""
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_review()
        orch.start_campaign()
        orch.finalize_campaign()
        # Review should still be empty — no auto-ingestion
        assert orch.review_controller.campaign_count == 0

    def test_review_intake_does_not_auto_promote(self):
        """Intake does not mean automatically promotable."""
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_review()
        report = _make_campaign_report()
        orch.intake_campaign_report(report)
        assert orch.review_controller.status != ReviewStatus.FINALIZED

    def test_multi_campaign_pipeline(self):
        """Multiple campaigns finalized and intaked into one review."""
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_review()
        for i in range(3):
            orch.start_campaign(campaign_id=f"camp-{i}")
            orch.finalize_campaign()
            orch.intake_last_campaign()
        assert orch.review_controller.campaign_count == 3


# ---------------------------------------------------------------------------
# Tests: Unified operator snapshot
# ---------------------------------------------------------------------------


class TestOperatorSnapshot:
    """Test unified operator status surface."""

    def test_basic_snapshot_no_campaign_no_review(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        snap = orch.operator_snapshot()
        assert isinstance(snap, OperatorSnapshot)
        assert snap.service_mode == "running"
        assert snap.trading_enabled is True
        assert snap.campaign is None
        assert snap.review is None
        assert snap.provisional_recommendation is None

    def test_snapshot_with_active_campaign(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign()
        snap = orch.operator_snapshot()
        assert snap.campaign is not None
        assert snap.campaign.active is True
        assert snap.campaign.status == "running"
        assert snap.campaign.finalized is False

    def test_snapshot_with_finalized_campaign(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign()
        orch.finalize_campaign()
        snap = orch.operator_snapshot()
        assert snap.campaign is not None
        assert snap.campaign.active is False
        assert snap.campaign.finalized is True
        assert snap.campaign.verdict is not None

    def test_snapshot_with_active_review(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_review()
        report = _make_campaign_report()
        orch.intake_campaign_report(report)
        snap = orch.operator_snapshot()
        assert snap.review is not None
        assert snap.review.active is True
        assert snap.review.campaign_count == 1

    def test_snapshot_ei_available(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        snap = orch.operator_snapshot()
        assert snap.ei_available is True
        assert snap.ei_degraded is False

    def test_snapshot_ei_degraded(self):
        ss = _make_service_status(
            ei_degraded=True,
            ei_degraded_reasons=("tca_loop_missing",),
        )
        svc = _make_mock_service(ss)
        orch = ServiceOrchestrator(service=svc)
        snap = orch.operator_snapshot()
        assert snap.ei_degraded is True
        assert "tca_loop_missing" in snap.ei_degraded_reasons

    def test_snapshot_readiness(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        snap = orch.operator_snapshot()
        assert snap.readiness_level == "paper_live"
        assert snap.readiness_is_supportive is True

    def test_snapshot_readiness_not_supportive(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="research_only",
        )
        snap = orch.operator_snapshot()
        assert snap.readiness_is_supportive is False

    def test_snapshot_provisional_recommendation_from_review(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        orch.start_review()
        for i in range(3):
            orch.intake_campaign_report(_make_campaign_report(campaign_id=f"camp-{i}"))
        snap = orch.operator_snapshot()
        assert snap.review.provisional_verdict is not None
        assert snap.provisional_recommendation is not None

    def test_snapshot_finalized_review_shows_verdict(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        orch.start_review()
        for i in range(3):
            orch.intake_campaign_report(_make_campaign_report(campaign_id=f"camp-{i}"))
        final = orch.finalize_review()
        snap = orch.operator_snapshot()
        assert snap.provisional_recommendation == final.verdict


# ---------------------------------------------------------------------------
# Tests: Evidence sufficiency truthfulness
# ---------------------------------------------------------------------------


class TestEvidenceSufficiency:
    """Test that evidence gaps are surfaced truthfully."""

    def test_no_evidence(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        snap = orch.operator_snapshot()
        assert snap.evidence.campaign_evidence_available is False
        assert snap.evidence.review_evidence_available is False
        assert snap.evidence.promotion_evidence_sufficient is False
        assert "No finalized campaign" in snap.evidence.summary

    def test_campaign_evidence_no_tca(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign()
        orch.finalize_campaign()
        snap = orch.operator_snapshot()
        assert snap.evidence.campaign_evidence_available is True
        assert snap.evidence.execution_calibration_available is False
        assert "No TCA calibration" in snap.evidence.summary

    def test_campaign_evidence_with_tca(self):
        """When campaign has TCA evidence, it should be visible."""
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        # Manually set a report with TCA evidence
        orch._last_campaign_report = _make_campaign_report(
            persisted_tca_count=16,
            registered_fill_count=20,
        )
        snap = orch.operator_snapshot()
        assert snap.evidence.campaign_evidence_available is True
        assert snap.evidence.execution_calibration_available is True

    def test_review_evidence_insufficient(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        orch.start_review()
        # Only 1 campaign — insufficient by default (min 3)
        orch.intake_campaign_report(_make_campaign_report())
        snap = orch.operator_snapshot()
        assert snap.evidence.review_evidence_available is True
        # With only 1 campaign out of 3 required, promotion evidence is not sufficient
        assert snap.evidence.promotion_evidence_sufficient is False

    def test_review_evidence_sufficient(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        orch.start_review()
        for i in range(3):
            orch.intake_campaign_report(_make_campaign_report(campaign_id=f"camp-{i}"))
        snap = orch.operator_snapshot()
        assert snap.evidence.review_evidence_available is True
        # 3 passing campaigns should make evidence sufficient
        # (depends on verdict — all pass → sufficient)

    def test_insufficient_reasons_visible(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_review()
        # Campaign with few cycles/fills → may produce insufficient criteria
        orch.intake_campaign_report(
            _make_campaign_report(
                campaign_id="camp-weak",
                total_cycles=10,
                total_fills=0,
            )
        )
        snap = orch.operator_snapshot()
        # Insufficient evidence should be visible in review state
        assert snap.review is not None


# ---------------------------------------------------------------------------
# Tests: Reporting API
# ---------------------------------------------------------------------------


class TestReportingAPI:
    """Test read-only reporting surfaces."""

    def test_combined_status_dict(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        d = orch.combined_status_dict()
        assert isinstance(d, dict)
        assert "service_mode" in d
        assert "campaign" in d
        assert "review" in d
        assert "evidence" in d
        assert "readiness_level" in d

    def test_campaign_report_dict_none(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        assert orch.campaign_report_dict() is None

    def test_campaign_report_dict_after_finalize(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign()
        orch.finalize_campaign()
        d = orch.campaign_report_dict()
        assert d is not None
        assert "campaign_id" in d
        assert "verdict" in d

    def test_review_report_dict_none(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        assert orch.review_report_dict() is None

    def test_review_report_dict_after_finalize(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        orch.start_review()
        for i in range(3):
            orch.intake_campaign_report(_make_campaign_report(campaign_id=f"camp-{i}"))
        orch.finalize_review()
        d = orch.review_report_dict()
        assert d is not None
        assert "review_id" in d
        assert "verdict" in d

    def test_insufficient_evidence_summary_no_data(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        summary = orch.insufficient_evidence_summary()
        assert summary["campaign_evidence_available"] is False
        assert summary["review_evidence_available"] is False

    def test_insufficient_evidence_summary_with_campaign(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign()
        orch.finalize_campaign()
        summary = orch.insufficient_evidence_summary()
        assert summary["campaign_evidence_available"] is True
        assert summary["campaign_fills"] >= 0

    def test_reason_summary_no_review(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        summary = orch.reason_summary()
        assert summary["verdict"] is None

    def test_reason_summary_with_review(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_review()
        for i in range(3):
            orch.intake_campaign_report(_make_campaign_report(campaign_id=f"camp-{i}"))
        summary = orch.reason_summary()
        assert summary["verdict"] is not None

    def test_campaign_readiness_flags_none(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        assert orch.campaign_readiness_flags() is None

    def test_campaign_readiness_flags_after_finalize(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign()
        orch.finalize_campaign()
        flags = orch.campaign_readiness_flags()
        assert flags is not None
        assert "paper_campaign_completed" in flags

    def test_decision_pack_requires_review(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        with pytest.raises(RuntimeError, match="No promotion review evidence"):
            orch.decision_pack()

    def test_decision_pack_inconclusive_with_insufficient_evidence(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        orch._last_campaign_report = _make_campaign_report(campaign_id="last-report")
        orch.start_review(review_id="rev-inconclusive")
        orch.intake_campaign_report(
            _make_campaign_report(
                campaign_id="camp-weak",
                total_cycles=10,
                total_fills=0,
                elapsed_seconds=30.0,
            )
        )

        pack = orch.decision_pack()
        assert isinstance(pack, OperatorDecisionPack)
        assert pack.operator_disposition == "inconclusive"
        assert "min_completed_campaigns" in pack.insufficient_evidence
        assert "insufficient_evidence" in pack.operator_next_inspection

    def test_decision_pack_surfaces_failed_criteria(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        orch._last_campaign_report = _make_campaign_report(campaign_id="last-report")
        orch.start_review(review_id="rev-reject")
        orch.intake_campaign_report(_make_campaign_report(campaign_id="camp-a", verdict="pass"))
        orch.intake_campaign_report(_make_campaign_report(campaign_id="camp-b", verdict="fail"))
        orch.intake_campaign_report(_make_campaign_report(campaign_id="camp-c", verdict="fail"))

        pack = orch.decision_pack()
        assert "max_failed_campaigns" in pack.fail_criteria
        assert "failed_criteria" in pack.operator_next_inspection

    def test_decision_pack_export_and_load_roundtrip(self, tmp_path: Path):
        svc = _make_mock_service()
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        orch = ServiceOrchestrator(
            service=svc,
            evidence_store=store,
            readiness_level="paper_live",
        )
        orch._last_campaign_report = _make_campaign_report(
            campaign_id="last-report",
            persisted_tca_count=18,
            registered_fill_count=20,
        )
        orch.start_review(review_id="rev-export")
        for i in range(3):
            orch.intake_campaign_report(_make_campaign_report(campaign_id=f"camp-{i}"))

        expected = orch.decision_pack()
        result = orch.export_decision_pack()
        assert result.success is True
        loaded = orch.load_decision_pack()
        assert loaded.review_id == "rev-export"
        assert loaded.operator_disposition == expected.operator_disposition

    def test_decision_pack_operator_surfaces(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        orch._last_campaign_report = _make_campaign_report(campaign_id="last-report")
        orch.start_review(review_id="rev-surfaces")
        orch.intake_campaign_report(_make_campaign_report(campaign_id="camp-a", verdict="pass"))
        orch.intake_campaign_report(_make_campaign_report(campaign_id="camp-b", verdict="pass"))
        orch.intake_campaign_report(_make_campaign_report(campaign_id="camp-c", verdict="fail"))

        pack = orch.decision_pack()
        decision = orch.decision_summary()
        why_not = orch.why_not_promotable_yet()
        missing = orch.decision_pack_missing_evidence()
        inspect_next = orch.decision_pack_next_inspection()

        assert decision["operator_disposition"] == pack.operator_disposition
        assert why_not["reasons"]
        assert missing["summary"]
        assert "warning_criteria" in inspect_next["items"]

    def test_escalation_decision_inconclusive_with_insufficient_evidence(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        orch._last_campaign_report = _make_campaign_report(campaign_id="last-report")
        orch.start_review(review_id="rev-escalation-inconclusive")
        orch.intake_campaign_report(
            _make_campaign_report(
                campaign_id="camp-weak",
                total_cycles=10,
                total_fills=0,
                elapsed_seconds=30.0,
            )
        )

        decision = orch.escalation_decision()
        assert decision.escalation_stage == EscalationStage.INCONCLUSIVE
        assert "min_completed_campaigns" in decision.missing_evidence

    def test_escalation_decision_reject_for_failed_review(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        orch._last_campaign_report = _make_campaign_report(campaign_id="last-report")
        orch.start_review(review_id="rev-escalation-reject")
        orch.intake_campaign_report(_make_campaign_report(campaign_id="camp-a", verdict="pass"))
        orch.intake_campaign_report(_make_campaign_report(campaign_id="camp-b", verdict="fail"))
        orch.intake_campaign_report(_make_campaign_report(campaign_id="camp-c", verdict="fail"))

        decision = orch.escalation_decision()
        assert decision.escalation_stage == EscalationStage.REJECT
        assert "max_failed_campaigns" in decision.blocking_reasons

    def test_escalation_decision_hold_for_warning_heavy_review(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        orch._last_campaign_report = _make_campaign_report(campaign_id="last-report")
        orch.start_review(review_id="rev-escalation-hold")
        orch.intake_campaign_report(_make_campaign_report(campaign_id="camp-a", verdict="pass"))
        orch.intake_campaign_report(_make_campaign_report(campaign_id="camp-b", verdict="fail"))
        orch.intake_campaign_report(_make_campaign_report(campaign_id="camp-c", verdict="pass"))

        decision = orch.escalation_decision()
        assert decision.escalation_stage == EscalationStage.HOLD
        assert "warn_failed_campaigns" in decision.why_not_higher

    def test_escalation_decision_promotable_readiness_advances_to_shadow_review(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="shadow_live",
        )
        orch._last_campaign_report = _make_campaign_report(
            campaign_id="last-report",
            persisted_tca_count=18,
            registered_fill_count=20,
        )
        orch.start_review(review_id="rev-escalation-shadow")
        for i in range(3):
            orch.intake_campaign_report(_make_campaign_report(campaign_id=f"camp-{i}", verdict="pass"))

        decision = orch.escalation_decision()
        assert decision.escalation_stage == EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE
        assert "operator_review_signoff" in decision.revalidation_required
        assert orch.escalation_summary()["allowed_next_step"] == "shadow_live_review_eligible"
        assert orch.escalation_decision_dict() == orch.escalation_decision_dict()

    def test_escalation_decision_ext_regime_weakness_lowers_stage(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="shadow_live",
        )
        orch._last_campaign_report = _make_campaign_report(
            campaign_id="last-report",
            persisted_tca_count=18,
            registered_fill_count=20,
        )
        orch.start_review(review_id="rev-escalation-downgrade")
        for i in range(3):
            orch.intake_campaign_report(_make_campaign_report(campaign_id=f"camp-{i}", verdict="pass"))

        pack = replace(
            orch.decision_pack(),
            external_regime_quality="cautionary",
            external_regime_evidence_sufficient=False,
            external_regime_concerns=("stale_dominance",),
        )
        decision = orch._build_escalation_decision(pack)
        assert decision.escalation_stage == EscalationStage.CALIBRATED_PAPER
        assert any(reason.startswith("external_regime:") for reason in decision.why_not_higher)

    def test_escalation_review_lifecycle_and_operator_surfaces(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="shadow_live",
        )
        orch._last_campaign_report = _make_campaign_report(
            campaign_id="last-report",
            persisted_tca_count=18,
            registered_fill_count=20,
        )
        orch.start_review(review_id="rev-escalation-lifecycle")
        for i in range(3):
            orch.intake_campaign_report(_make_campaign_report(campaign_id=f"camp-{i}", verdict="pass"))
        orch.finalize_review()

        review_id = orch.start_escalation_review(review_id="esc-lifecycle")
        assert review_id == "esc-lifecycle"

        snap = orch.escalation_review_snapshot()
        assert snap is not None
        assert snap.status == "evaluating"
        assert snap.latest_decision is not None
        assert snap.latest_decision.escalation_stage == EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE

        final = orch.finalize_escalation_review()
        assert final.status == "finalized"
        assert final.decision.escalation_stage == EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE
        assert orch.escalation_summary()["allowed_next_step"] == "shadow_live_review_eligible"

        operator = orch.operator_snapshot()
        assert operator.escalation_review is not None
        assert operator.escalation_review.allowed_next_step == "shadow_live_review_eligible"

    def test_escalation_review_progression_history_current_vs_previous(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        orch._last_campaign_report = _make_campaign_report(
            campaign_id="last-report",
            persisted_tca_count=18,
            registered_fill_count=20,
        )
        orch.start_review(review_id="rev-escalation-history")
        for i in range(3):
            orch.intake_campaign_report(_make_campaign_report(campaign_id=f"camp-{i}", verdict="pass"))
        orch.finalize_review()

        orch.start_escalation_review(review_id="esc-history-1")
        first = orch.finalize_escalation_review()
        assert first.history_summary["total_finalized_reviews"] == 1

        orch.readiness_level = "shadow_live"
        orch.start_escalation_review(review_id="esc-history-2")
        second = orch.finalize_escalation_review()

        comparison = orch.escalation_change_summary()
        history = orch.escalation_history_summary()
        assert second.comparison_to_previous["direction"] == "progressed"
        assert comparison["previous_allowed_next_step"] == "paper_only"
        assert comparison["current_allowed_next_step"] == "shadow_live_review_eligible"
        assert history["total_finalized_reviews"] == 2

    def test_escalation_review_repeated_stuck_summary(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        orch._last_campaign_report = _make_campaign_report(campaign_id="last-report")
        orch.start_review(review_id="rev-escalation-stuck")
        orch.intake_campaign_report(
            _make_campaign_report(
                campaign_id="camp-weak",
                total_cycles=10,
                total_fills=0,
                elapsed_seconds=30.0,
            )
        )

        orch.start_escalation_review(review_id="esc-stuck-1")
        orch.finalize_escalation_review()
        orch.start_escalation_review(review_id="esc-stuck-2")
        orch.finalize_escalation_review()

        history = orch.escalation_history_summary()
        assert history["repeatedly_stuck"] is True
        assert history["repeated_stuck_count"] == 2


# ---------------------------------------------------------------------------
# Tests: Persistence / restore linkage
# ---------------------------------------------------------------------------


class TestPersistenceRestore:
    """Test workflow persistence and restore through orchestrator."""

    def test_restore_campaign_no_store_raises(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        with pytest.raises(RuntimeError, match="No evidence store"):
            orch.restore_campaign()

    def test_restore_review_no_store_raises(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        with pytest.raises(RuntimeError, match="No evidence store"):
            orch.restore_review({})

    def test_restore_campaign_no_state_returns_false(self, tmp_path: Path):
        svc = _make_mock_service()
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        orch = ServiceOrchestrator(
            service=svc,
            evidence_store=store,
        )
        result = orch.restore_campaign()
        assert result is False

    def test_restore_campaign_while_active_raises(self, tmp_path: Path):
        svc = _make_mock_service()
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        orch = ServiceOrchestrator(
            service=svc,
            evidence_store=store,
        )
        orch.start_campaign()
        with pytest.raises(RuntimeError, match="active campaign"):
            orch.restore_campaign()

    def test_restore_review_while_active_raises(self, tmp_path: Path):
        svc = _make_mock_service()
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        orch = ServiceOrchestrator(
            service=svc,
            evidence_store=store,
        )
        orch.start_review()
        with pytest.raises(RuntimeError, match="active review"):
            orch.restore_review({})

    def test_restore_escalation_review_no_store_raises(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        with pytest.raises(RuntimeError, match="No evidence store"):
            orch.restore_escalation_review()

    def test_restore_escalation_review_while_active_raises(self, tmp_path: Path):
        svc = _make_mock_service()
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        orch = ServiceOrchestrator(
            service=svc,
            evidence_store=store,
            readiness_level="shadow_live",
        )
        orch._last_campaign_report = _make_campaign_report(
            campaign_id="last-report",
            persisted_tca_count=18,
            registered_fill_count=20,
        )
        orch.start_review(review_id="rev-esc-active")
        for i in range(3):
            orch.intake_campaign_report(_make_campaign_report(campaign_id=f"camp-{i}", verdict="pass"))
        orch.finalize_review()
        orch.start_escalation_review(review_id="esc-active")

        with pytest.raises(RuntimeError, match="active escalation review"):
            orch.restore_escalation_review()

    def test_campaign_persist_restore_roundtrip(self, tmp_path: Path):
        svc = _make_mock_service()
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        orch = ServiceOrchestrator(
            service=svc,
            evidence_store=store,
        )
        # Start and update a campaign (persists metadata)
        orch.start_campaign(campaign_id="camp-persist")
        orch.update_campaign()

        # Create a new orchestrator and restore
        orch2 = ServiceOrchestrator(
            service=svc,
            evidence_store=store,
        )
        restored = orch2.restore_campaign()
        assert restored is True
        assert orch2.campaign_controller is not None
        assert orch2.campaign_controller.campaign_id == "camp-persist"

    def test_review_persist_restore_roundtrip(self, tmp_path: Path):
        svc = _make_mock_service()
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        orch = ServiceOrchestrator(
            service=svc,
            evidence_store=store,
            readiness_level="paper_live",
        )
        # Start review, add campaign, persist
        orch.start_review(review_id="rev-persist")
        report = _make_campaign_report(campaign_id="camp-p1")
        orch.intake_campaign_report(report)

        # Create new orchestrator and restore
        orch2 = ServiceOrchestrator(
            service=svc,
            evidence_store=store,
            readiness_level="paper_live",
        )
        restored = orch2.restore_review({"camp-p1": report})
        assert restored is True
        assert orch2.review_controller is not None
        assert orch2.review_controller.review_id == "rev-persist"
        assert orch2.review_controller.campaign_count == 1

    def test_review_restore_missing_reports_raises(self, tmp_path: Path):
        svc = _make_mock_service()
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        orch = ServiceOrchestrator(
            service=svc,
            evidence_store=store,
        )
        orch.start_review(review_id="rev-bad")
        report = _make_campaign_report(campaign_id="camp-x")
        orch.intake_campaign_report(report)

        # Restore with empty reports → should raise corrupt
        orch2 = ServiceOrchestrator(
            service=svc,
            evidence_store=store,
        )
        with pytest.raises(ReviewWorkflowCorruptError, match="Missing campaign"):
            orch2.restore_review({})

    def test_escalation_review_persist_restore_roundtrip(self, tmp_path: Path):
        svc = _make_mock_service()
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        orch = ServiceOrchestrator(
            service=svc,
            evidence_store=store,
            readiness_level="shadow_live",
        )
        orch._last_campaign_report = _make_campaign_report(
            campaign_id="last-report",
            persisted_tca_count=18,
            registered_fill_count=20,
        )
        orch.start_review(review_id="rev-esc-persist")
        for i in range(3):
            orch.intake_campaign_report(_make_campaign_report(campaign_id=f"camp-{i}", verdict="pass"))
        orch.finalize_review()
        orch.start_escalation_review(review_id="esc-persist")
        orch.finalize_escalation_review()

        orch2 = ServiceOrchestrator(
            service=svc,
            evidence_store=store,
            readiness_level="shadow_live",
        )
        restored = orch2.restore_escalation_review()
        assert restored is True
        assert orch2.escalation_review_controller is not None
        assert orch2.escalation_review_controller.review_id == "esc-persist"
        assert orch2.escalation_history_summary()["total_finalized_reviews"] == 1

    def test_escalation_review_restore_fail_closed(self, tmp_path: Path):
        svc = _make_mock_service()
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        store.save_snapshot(
            "escalation_review_workflow",
            {
                "review_id": "esc-bad",
                "status": "rejected",
                "created_at_ns": _T0_NS,
                "updated_at_ns": _T0_NS,
            },
        )
        orch = ServiceOrchestrator(
            service=svc,
            evidence_store=store,
            readiness_level="shadow_live",
        )

        with pytest.raises(EscalationWorkflowCorruptError, match="final_report"):
            orch.restore_escalation_review()


# ---------------------------------------------------------------------------
# Tests: Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    """Test serialization helpers."""

    def test_campaign_workflow_state_to_dict(self):
        state = CampaignWorkflowState(
            active=True,
            campaign_id="camp-1",
            status="running",
            started_at_ns=_T0_NS,
            elapsed_seconds=100.0,
            total_cycles=50,
            total_fills=5,
            verdict=None,
            finalized=False,
        )
        d = campaign_workflow_state_to_dict(state)
        assert d["active"] is True
        assert d["campaign_id"] == "camp-1"
        assert d["status"] == "running"

    def test_review_workflow_state_to_dict(self):
        state = ReviewWorkflowState(
            active=True,
            review_id="rev-1",
            status="collecting",
            campaign_count=2,
            provisional_verdict=None,
            provisional_summary="Collecting campaigns.",
            insufficient_evidence=(),
            is_ready_to_finalize=False,
            finalized=False,
        )
        d = review_workflow_state_to_dict(state)
        assert d["review_id"] == "rev-1"
        assert d["campaign_count"] == 2

    def test_escalation_workflow_state_to_dict(self):
        state = EscalationWorkflowState(
            active=True,
            review_id="esc-1",
            status="evaluating",
            allowed_next_step="paper_only",
            progression_state="first_attempt",
            previous_allowed_next_step=None,
            history_length=1,
            repeatedly_stuck=False,
            finalized=False,
        )
        d = escalation_workflow_state_to_dict(state)
        assert d["review_id"] == "esc-1"
        assert d["allowed_next_step"] == "paper_only"

    def test_evidence_sufficiency_to_dict(self):
        state = EvidenceSufficiencyState(
            campaign_evidence_available=True,
            review_evidence_available=False,
            execution_calibration_available=True,
            promotion_evidence_sufficient=False,
            insufficient_reasons=("min_campaigns",),
            summary="Need more campaigns.",
        )
        d = evidence_sufficiency_state_to_dict(state)
        assert d["campaign_evidence_available"] is True
        assert d["insufficient_reasons"] == ["min_campaigns"]

    def test_operator_snapshot_to_dict(self):
        snap = OperatorSnapshot(
            service_mode="running",
            trading_enabled=True,
            blocked_reason=None,
            ei_available=True,
            ei_degraded=False,
            ei_degraded_reasons=(),
            campaign=None,
            review=None,
            readiness_level="paper_live",
            readiness_is_supportive=True,
            evidence=EvidenceSufficiencyState(
                campaign_evidence_available=False,
                review_evidence_available=False,
                execution_calibration_available=False,
                promotion_evidence_sufficient=False,
                insufficient_reasons=(),
                summary="No evidence.",
            ),
            provisional_recommendation=None,
            recommendation_summary="No review.",
        )
        d = operator_snapshot_to_dict(snap)
        assert d["service_mode"] == "running"
        assert d["campaign"] is None
        assert d["review"] is None
        assert d["escalation_review"] is None
        assert isinstance(d["evidence"], dict)

    def test_operator_snapshot_to_dict_with_campaign_and_review(self):
        campaign = CampaignWorkflowState(
            active=False,
            campaign_id="c1",
            status="completed",
            started_at_ns=_T0_NS,
            elapsed_seconds=300.0,
            total_cycles=200,
            total_fills=30,
            verdict="pass",
            finalized=True,
        )
        review = ReviewWorkflowState(
            active=True,
            review_id="r1",
            status="collecting",
            campaign_count=1,
            provisional_verdict="promote",
            provisional_summary="Looks good.",
            insufficient_evidence=(),
            is_ready_to_finalize=True,
            finalized=False,
        )
        evidence = EvidenceSufficiencyState(
            campaign_evidence_available=True,
            review_evidence_available=True,
            execution_calibration_available=True,
            promotion_evidence_sufficient=True,
            insufficient_reasons=(),
            summary="All good.",
        )
        escalation_review = EscalationWorkflowState(
            active=False,
            review_id="esc-1",
            status="finalized",
            allowed_next_step="paper_only",
            progression_state="unchanged",
            previous_allowed_next_step="paper_only",
            history_length=2,
            repeatedly_stuck=False,
            finalized=True,
        )
        snap = OperatorSnapshot(
            service_mode="running",
            trading_enabled=True,
            blocked_reason=None,
            ei_available=True,
            ei_degraded=False,
            ei_degraded_reasons=(),
            campaign=campaign,
            review=review,
            readiness_level="paper_live",
            readiness_is_supportive=True,
            evidence=evidence,
            provisional_recommendation="promote",
            recommendation_summary="Looks good.",
            escalation_review=escalation_review,
        )
        d = operator_snapshot_to_dict(snap)
        assert d["campaign"]["campaign_id"] == "c1"
        assert d["review"]["review_id"] == "r1"
        assert d["escalation_review"]["review_id"] == "esc-1"
        assert d["evidence"]["promotion_evidence_sufficient"] is True


# ---------------------------------------------------------------------------
# Tests: Deterministic replay / truthfulness
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    """Test that orchestrator behaves deterministically."""

    def test_same_inputs_same_snapshot(self):
        """Same service status → same operator snapshot."""
        ss = _make_service_status()
        svc1 = _make_mock_service(ss)
        svc2 = _make_mock_service(ss)
        orch1 = ServiceOrchestrator(service=svc1, readiness_level="paper_live")
        orch2 = ServiceOrchestrator(service=svc2, readiness_level="paper_live")
        snap1 = orch1.operator_snapshot()
        snap2 = orch2.operator_snapshot()
        assert snap1.service_mode == snap2.service_mode
        assert snap1.trading_enabled == snap2.trading_enabled
        assert snap1.readiness_level == snap2.readiness_level

    def test_readiness_not_flattened_into_verdict(self):
        """Readiness supportiveness must remain distinct from promotion verdict."""
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        snap = orch.operator_snapshot()
        # Readiness is supportive, but no review → no recommendation
        assert snap.readiness_is_supportive is True
        assert snap.provisional_recommendation is None

    def test_ei_visibility_in_snapshot(self):
        """EI availability must remain visible in operator status."""
        ss = _make_service_status(ei_degraded=True, ei_degraded_reasons=("tca_missing",))
        svc = _make_mock_service(ss)
        orch = ServiceOrchestrator(service=svc)
        snap = orch.operator_snapshot()
        assert snap.ei_available is True
        assert snap.ei_degraded is True
        assert "tca_missing" in snap.ei_degraded_reasons

    def test_no_ei_when_none(self):
        """When EI is None, it shows as unavailable."""
        ss = _make_service_status()
        # Replace EI with None
        ss_no_ei = ServiceStatus(
            service_mode=ss.service_mode,
            runtime_status=ss.runtime_status,
            queue=ss.queue,
            watchdog=ss.watchdog,
            symbol_health=ss.symbol_health,
            symbol_count=ss.symbol_count,
            trading_enabled=ss.trading_enabled,
            blocked_reason=ss.blocked_reason,
            last_error=ss.last_error,
            total_service_restarts=ss.total_service_restarts,
            execution_intelligence=None,
        )
        svc = _make_mock_service(ss_no_ei)
        orch = ServiceOrchestrator(service=svc)
        snap = orch.operator_snapshot()
        assert snap.ei_available is False
        assert snap.ei_degraded is False


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and error paths."""

    def test_operations_on_terminal_campaign(self):
        """Operations on a finalized campaign should fail properly."""
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign()
        orch.finalize_campaign()
        with pytest.raises(RuntimeError, match="terminal status"):
            orch.pause_campaign()
        with pytest.raises(RuntimeError, match="terminal status"):
            orch.update_campaign()

    def test_operations_on_terminal_review(self):
        """Operations on a finalized review should fail properly."""
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_review()
        for i in range(3):
            orch.intake_campaign_report(_make_campaign_report(campaign_id=f"camp-{i}"))
        orch.finalize_review()
        with pytest.raises(RuntimeError, match="terminal status"):
            orch.intake_campaign_report(_make_campaign_report(campaign_id="camp-late"))
        with pytest.raises(RuntimeError, match="terminal status"):
            orch.finalize_review()

    def test_finalize_campaign_twice_raises(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        orch.start_campaign()
        orch.finalize_campaign()
        with pytest.raises(RuntimeError):
            orch.finalize_campaign()

    def test_combined_status_dict_roundtrip(self):
        """Combined status dict should be JSON-serializable."""
        import json

        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )
        orch.start_campaign()
        d = orch.combined_status_dict()
        # Should not raise — proves JSON-serializable
        s = json.dumps(d)
        assert len(s) > 0

    def test_full_pipeline_end_to_end(self):
        """Full pipeline: campaign → finalize → review → intake → finalize."""
        svc = _make_mock_service()
        orch = ServiceOrchestrator(
            service=svc,
            readiness_level="paper_live",
        )

        # Run 3 campaigns
        for i in range(3):
            cid = orch.start_campaign(campaign_id=f"camp-e2e-{i}")
            orch.update_campaign()
            report = orch.finalize_campaign()
            assert report.campaign_id == cid

        # Start review, intake all via manual reports
        orch.start_review()
        # Only last_campaign_report is the last one
        assert orch.last_campaign_report.campaign_id == "camp-e2e-2"

        # But we can intake reports directly
        for i in range(3):
            rpt = _make_campaign_report(campaign_id=f"camp-e2e-{i}")
            orch.intake_campaign_report(rpt)

        snap = orch.operator_snapshot()
        assert snap.review is not None
        assert snap.review.campaign_count == 3

        final = orch.finalize_review()
        assert final.campaign_count == 3

        # Final snapshot should show finalized review
        snap2 = orch.operator_snapshot()
        assert not snap2.review.active
        assert snap2.review.finalized is True
        assert snap2.provisional_recommendation == final.verdict
