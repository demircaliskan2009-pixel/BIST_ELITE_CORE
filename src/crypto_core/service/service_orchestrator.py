"""Service-level campaign + promotion orchestration surface — Phase 10E.

Unified top-level operator control surface composing:
  - PaperLiveService (runtime lifecycle, event queue, EI)
  - CampaignController (campaign lifecycle, verdict, persistence)
  - PromotionReviewController (review lifecycle, promotion verdict, persistence)

Provides:
  1. Service-level campaign lifecycle methods (start/pause/resume/abort/finalize).
  2. Service-level promotion review lifecycle methods (start/intake/finalize/reset).
  3. Campaign → review deterministic pipeline (explicit operator-controlled intake).
  4. Unified OperatorSnapshot combining all workflow states.
  5. Read-only reporting API (combined, campaign, review, evidence, reasons).
  6. Persistence/restore linkage for workflow continuity.
  7. Truthful evidence surfacing — no hidden weak calibration or missing evidence.

Design rules:
  - Orchestration only — all logic delegated to existing controllers.
  - No silent auto-promotion: campaign complete ≠ reviewed, reviewed ≠ promotable.
  - Fail-closed: malformed state → raise, never silently degrade.
  - Deterministic: same inputs → same outputs.
  - PAPER-ONLY.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from crypto_core.service.campaign import (
    CampaignConfig,
    CampaignReport,
    CampaignSnapshot,
)
from crypto_core.service.campaign_controller import (
    CampaignController,
    campaign_readiness_flags,
)
from crypto_core.service.evidence_store import EvidenceStore
from crypto_core.service.external_regime import (
    ExternalRegimeDataPlane,
    ExternalRegimeSnapshot,
)
from crypto_core.service.models import ServiceStatus
from crypto_core.service.paper_live_service import PaperLiveService
from crypto_core.service.promotion_review import PromotionThresholds
from crypto_core.service.promotion_review_controller import (
    CurrentReviewSnapshot,
    FinalReviewReport,
    PromotionReviewController,
    ReviewStatus,
    ReviewWorkflowCorruptError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Operator snapshot models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CampaignWorkflowState:
    """Campaign workflow state summary for the operator surface.

    Deterministic, serialization-friendly.
    """

    active: bool
    campaign_id: str | None
    status: str  # CampaignStatus.value
    started_at_ns: int
    elapsed_seconds: float
    total_cycles: int
    total_fills: int
    verdict: str | None  # AcceptanceVerdict.value if finalized
    finalized: bool


@dataclass(frozen=True)
class ReviewWorkflowState:
    """Review workflow state summary for the operator surface.

    Deterministic, serialization-friendly.
    """

    active: bool
    review_id: str | None
    status: str  # ReviewStatus.value
    campaign_count: int
    provisional_verdict: str | None  # PromotionVerdict.value or None
    provisional_summary: str
    insufficient_evidence: tuple[str, ...]
    is_ready_to_finalize: bool
    finalized: bool


@dataclass(frozen=True)
class EvidenceSufficiencyState:
    """Evidence sufficiency summary for operator truthfulness.

    Exposes whether promotion evidence is currently sufficient, and what
    specific evidence gaps exist.  This prevents the unified status from
    hiding weak execution calibration behind a healthy-looking surface.
    """

    campaign_evidence_available: bool
    review_evidence_available: bool
    execution_calibration_available: bool
    promotion_evidence_sufficient: bool
    insufficient_reasons: tuple[str, ...]
    summary: str

    # External regime evidence (Phase 11A)
    external_regime_available: bool = False
    external_regime_fresh: bool = False
    external_regime_has_high_risk: bool = False


@dataclass(frozen=True)
class OperatorSnapshot:
    """Unified top-level operator status combining all workflow states.

    Single read-only snapshot answering: "What is the system doing right now,
    where is the campaign, where is the review, and what is the current
    recommendation state?"

    Deterministic: same system state → same snapshot.
    Truthful: no healthy-looking status hiding weak evidence.
    """

    # Service runtime
    service_mode: str
    trading_enabled: bool
    blocked_reason: str | None

    # Execution intelligence
    ei_available: bool
    ei_degraded: bool
    ei_degraded_reasons: tuple[str, ...]

    # Campaign workflow
    campaign: CampaignWorkflowState | None

    # Review workflow
    review: ReviewWorkflowState | None

    # Readiness
    readiness_level: str
    readiness_is_supportive: bool

    # Evidence sufficiency (truthfulness surface)
    evidence: EvidenceSufficiencyState

    # Provisional recommendation
    provisional_recommendation: str | None  # PromotionVerdict.value
    recommendation_summary: str

    # External regime (Phase 11A)
    external_regime: ExternalRegimeSnapshot | None = None


# ---------------------------------------------------------------------------
# Service orchestrator
# ---------------------------------------------------------------------------


class ServiceOrchestrator:
    """Unified top-level control surface for paper-live operations.

    Composes PaperLiveService, CampaignController, and PromotionReviewController
    into a single coherent workflow.  All logic is delegated to the existing
    controllers — this class provides orchestration and operator surfacing only.

    Usage::

        orchestrator = ServiceOrchestrator(
            service=paper_live_service,
            evidence_store=evidence_store,
            readiness_level="paper_live",
        )
        # Campaign lifecycle
        orchestrator.start_campaign(run_id="run-001")
        orchestrator.update_campaign()
        report = orchestrator.finalize_campaign()

        # Review lifecycle
        orchestrator.start_review()
        orchestrator.intake_last_campaign()
        snapshot = orchestrator.operator_snapshot()
        final = orchestrator.finalize_review()

    Thread safety: NOT thread-safe — call from the operator thread only.
    """

    def __init__(
        self,
        *,
        service: PaperLiveService,
        campaign_config: CampaignConfig | None = None,
        evidence_store: EvidenceStore | None = None,
        readiness_level: str = "not_assessed",
        promotion_thresholds: PromotionThresholds | None = None,
        external_regime_plane: ExternalRegimeDataPlane | None = None,
    ) -> None:
        self._service = service
        self._evidence_store = evidence_store
        self._readiness_level = readiness_level
        self._promotion_thresholds = promotion_thresholds
        self._campaign_config = campaign_config
        self._external_regime_plane = external_regime_plane

        self._campaign: CampaignController | None = None
        self._last_campaign_report: CampaignReport | None = None

        self._review: PromotionReviewController | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def service(self) -> PaperLiveService:
        """Underlying PaperLiveService."""
        return self._service

    @property
    def campaign_controller(self) -> CampaignController | None:
        """Active CampaignController, or None."""
        return self._campaign

    @property
    def review_controller(self) -> PromotionReviewController | None:
        """Active PromotionReviewController, or None."""
        return self._review

    @property
    def external_regime_plane(self) -> ExternalRegimeDataPlane | None:
        """Active ExternalRegimeDataPlane, or None."""
        return self._external_regime_plane

    @property
    def readiness_level(self) -> str:
        """Current readiness level."""
        return self._readiness_level

    @readiness_level.setter
    def readiness_level(self, value: str) -> None:
        self._readiness_level = value

    # ------------------------------------------------------------------
    # Campaign lifecycle
    # ------------------------------------------------------------------

    def campaign_active(self) -> bool:
        """Whether a campaign is currently active (non-terminal)."""
        if self._campaign is None:
            return False
        return self._campaign.status.value not in (
            "completed",
            "rejected",
            "aborted",
            "failed",
        )

    def start_campaign(
        self,
        *,
        campaign_id: str | None = None,
        run_id: str = "",
        config: CampaignConfig | None = None,
    ) -> str:
        """Start a new campaign from the service level.

        Creates a CampaignController and starts it with the current
        service status.  Previous campaign must be finalized or absent.

        Args:
            campaign_id: optional explicit campaign ID.
            run_id: optional run linkage.
            config: optional campaign config override.

        Returns:
            The campaign ID.

        Raises:
            RuntimeError: if a campaign is already active.
        """
        if self.campaign_active():
            raise RuntimeError(
                f"Cannot start a new campaign: active campaign "
                f"{self._campaign.campaign_id!r} in status "
                f"{self._campaign.status.value!r}"
            )

        cfg = config or self._campaign_config or CampaignConfig()
        if campaign_id is not None:
            cfg = CampaignConfig(
                campaign_id=campaign_id,
                max_duration_s=cfg.max_duration_s,
                max_events=cfg.max_events,
                max_cycles=cfg.max_cycles,
                thresholds=cfg.thresholds,
            )

        self._campaign = CampaignController(
            config=cfg,
            evidence_store=self._evidence_store,
        )

        ss = self._service.status()
        self._campaign.start(ss, run_id=run_id)
        logger.info(
            "Campaign %s started via orchestrator",
            self._campaign.campaign_id,
        )
        return self._campaign.campaign_id

    def pause_campaign(self) -> None:
        """Pause the active campaign.

        Raises:
            RuntimeError: if no active campaign.
        """
        self._require_campaign("pause")
        self._campaign.pause()

    def resume_campaign(self) -> None:
        """Resume a paused campaign.

        Raises:
            RuntimeError: if no active campaign.
        """
        self._require_campaign("resume")
        self._campaign.resume()

    def abort_campaign(self, reason: str = "operator_abort") -> None:
        """Abort the active campaign.

        Raises:
            RuntimeError: if no campaign.
        """
        if self._campaign is None:
            raise RuntimeError("No campaign to abort")
        self._campaign.abort(reason)

    def update_campaign(self) -> str:
        """Update campaign counters from current service status.

        Returns:
            Current campaign status value.

        Raises:
            RuntimeError: if no active campaign.
        """
        self._require_campaign("update")
        ss = self._service.status()
        status = self._campaign.update(ss)
        return status.value

    def finalize_campaign(self) -> CampaignReport:
        """Finalize the active campaign and produce the verdict report.

        The finalized report is stored for subsequent review intake.

        Returns:
            CampaignReport.

        Raises:
            RuntimeError: if no campaign.
        """
        if self._campaign is None:
            raise RuntimeError("No campaign to finalize")
        ss = self._service.status()

        # Phase 11B: thread external regime evidence into campaign finalization.
        ext_regime = None
        if self._external_regime_plane is not None:
            last_ns = ss.watchdog.last_event_time_ns if ss.watchdog else 0
            ext_regime = self._external_regime_plane.snapshot(last_ns)

        report = self._campaign.finalize(ss, ext_regime=ext_regime)
        self._last_campaign_report = report
        logger.info(
            "Campaign %s finalized via orchestrator (verdict=%s)",
            report.campaign_id,
            report.verdict,
        )
        return report

    def campaign_snapshot(self) -> CampaignSnapshot | None:
        """Current campaign snapshot, or None if no campaign."""
        if self._campaign is None:
            return None
        ss = self._service.status()
        # Phase 11B: thread external regime evidence into campaign snapshot.
        ext_regime = None
        if self._external_regime_plane is not None:
            last_ns = ss.watchdog.last_event_time_ns if ss.watchdog else 0
            ext_regime = self._external_regime_plane.snapshot(last_ns)
        return self._campaign.snapshot(ss, ext_regime=ext_regime)

    @property
    def last_campaign_report(self) -> CampaignReport | None:
        """The most recently finalized campaign report."""
        return self._last_campaign_report

    # ------------------------------------------------------------------
    # Review lifecycle
    # ------------------------------------------------------------------

    def review_active(self) -> bool:
        """Whether a promotion review is currently active (non-terminal)."""
        if self._review is None:
            return False
        return self._review.status not in (
            ReviewStatus.FINALIZED,
            ReviewStatus.FAILED,
            ReviewStatus.REJECTED,
        )

    def start_review(self, *, review_id: str | None = None) -> str:
        """Start a new promotion review workflow.

        Creates a PromotionReviewController.  Previous review must be
        finalized/absent.

        Args:
            review_id: optional explicit review ID.

        Returns:
            The review ID.

        Raises:
            RuntimeError: if a review is already active.
        """
        if self.review_active():
            raise RuntimeError(
                f"Cannot start a new review: active review "
                f"{self._review.review_id!r} in status "
                f"{self._review.status.value!r}"
            )

        self._review = PromotionReviewController(
            review_id=review_id,
            readiness_level=self._readiness_level,
            thresholds=self._promotion_thresholds,
            evidence_store=self._evidence_store,
        )
        logger.info("Review %s started via orchestrator", self._review.review_id)
        return self._review.review_id

    def intake_campaign_report(self, report: CampaignReport) -> None:
        """Intake a campaign report into the active review.

        Explicit operator-controlled intake — no silent auto-ingestion.

        Args:
            report: finalized CampaignReport.

        Raises:
            RuntimeError: if no active review.
            CampaignIntakeError: if report fails validation.
        """
        self._require_review("intake campaign report")
        self._review.add_campaign_report(report)
        logger.info(
            "Campaign %s ingested into review %s via orchestrator",
            report.campaign_id,
            self._review.review_id,
        )

    def intake_last_campaign(self) -> None:
        """Intake the most recently finalized campaign into the active review.

        Convenience method for the common campaign → review pipeline.

        Raises:
            RuntimeError: if no last campaign report or no active review.
            CampaignIntakeError: if report fails validation.
        """
        if self._last_campaign_report is None:
            raise RuntimeError("No finalized campaign report available for intake")
        self.intake_campaign_report(self._last_campaign_report)

    def review_snapshot(self) -> CurrentReviewSnapshot | None:
        """Current review snapshot, or None if no review."""
        if self._review is None:
            return None
        return self._review.current_snapshot()

    def finalize_review(self) -> FinalReviewReport:
        """Finalize the active review and produce the final report.

        Returns:
            FinalReviewReport.

        Raises:
            RuntimeError: if no active review or review has no campaigns.
        """
        self._require_review("finalize review")
        report = self._review.finalize_review()
        logger.info(
            "Review %s finalized via orchestrator (verdict=%s)",
            report.review_id,
            report.verdict,
        )
        return report

    def reset_review(self) -> None:
        """Reset the active review to CREATED state.

        Raises:
            RuntimeError: if no review or review is FAILED.
        """
        if self._review is None:
            raise RuntimeError("No review to reset")
        self._review.reset()

    @property
    def final_review_report(self) -> FinalReviewReport | None:
        """The final review report if review was finalized."""
        if self._review is None:
            return None
        return self._review.final_report

    # ------------------------------------------------------------------
    # Unified operator status surface
    # ------------------------------------------------------------------

    def operator_snapshot(self) -> OperatorSnapshot:
        """Produce a unified operator snapshot.

        Single read-only call answering: "What is the system doing right now,
        where is the campaign, where is the review, and what is the current
        recommendation state?"

        Truthful: does not hide weak execution calibration, missing evidence,
        or insufficient review behind a healthy-looking status.

        Returns:
            Frozen OperatorSnapshot.
        """
        ss = self._service.status()

        # Execution intelligence
        ei = ss.execution_intelligence
        ei_available = ei is not None
        ei_degraded = ei.degraded if ei is not None else False
        ei_degraded_reasons = ei.degraded_reasons if ei is not None else ()

        # Campaign workflow state
        campaign_state = self._build_campaign_workflow_state(ss)

        # Review workflow state
        review_state = self._build_review_workflow_state()

        # External regime snapshot
        ext_regime: ExternalRegimeSnapshot | None = None
        if self._external_regime_plane is not None:
            ext_regime = self._external_regime_plane.snapshot(ss.watchdog.last_event_time_ns)

        # Evidence sufficiency
        evidence = self._build_evidence_sufficiency(campaign_state, review_state, ext_regime)

        # Readiness
        readiness_is_supportive = self._readiness_level in (
            "paper_live",
            "calibrated_paper",
            "shadow_live",
            "tiny_cap_live",
        )

        # Provisional recommendation
        prov_verdict: str | None = None
        prov_summary = "No promotion review active."
        if review_state is not None and review_state.provisional_verdict is not None:
            prov_verdict = review_state.provisional_verdict
            prov_summary = review_state.provisional_summary
        elif review_state is not None and not review_state.active:
            # Finalized review — show the final verdict
            if self._review is not None and self._review.final_report is not None:
                prov_verdict = self._review.final_report.verdict
                prov_summary = self._review.final_report.summary

        return OperatorSnapshot(
            service_mode=ss.service_mode,
            trading_enabled=ss.trading_enabled,
            blocked_reason=ss.blocked_reason,
            ei_available=ei_available,
            ei_degraded=ei_degraded,
            ei_degraded_reasons=ei_degraded_reasons,
            campaign=campaign_state,
            review=review_state,
            readiness_level=self._readiness_level,
            readiness_is_supportive=readiness_is_supportive,
            evidence=evidence,
            provisional_recommendation=prov_verdict,
            recommendation_summary=prov_summary,
            external_regime=ext_regime,
        )

    # ------------------------------------------------------------------
    # Reporting API (read-only, deterministic)
    # ------------------------------------------------------------------

    def combined_status_dict(self) -> dict:
        """Serialize the full operator snapshot to a plain dict.

        Suitable for JSON export or API response.
        """
        snap = self.operator_snapshot()
        return operator_snapshot_to_dict(snap)

    def campaign_report_dict(self) -> dict | None:
        """Serialize the last finalized campaign report to a dict.

        Returns None if no campaign has been finalized.
        """
        if self._last_campaign_report is None:
            return None
        from crypto_core.service.campaign_controller import _report_to_dict

        return _report_to_dict(self._last_campaign_report)

    def review_report_dict(self) -> dict | None:
        """Serialize the final review report to a dict.

        Returns None if no review has been finalized.
        """
        if self._review is None or self._review.final_report is None:
            return None
        from crypto_core.service.promotion_review_controller import (
            final_review_report_to_dict,
        )

        return final_review_report_to_dict(self._review.final_report)

    def insufficient_evidence_summary(self) -> dict:
        """Top-level insufficient evidence summary.

        Shows what evidence is missing across campaign + review.
        """
        result: dict = {
            "campaign_evidence_available": False,
            "review_evidence_available": False,
            "campaign_fills": 0,
            "campaign_tca_records": 0,
            "review_campaign_count": 0,
            "review_insufficient_criteria": [],
            "summary": "No campaign or review evidence available.",
        }

        if self._last_campaign_report is not None:
            snap = self._last_campaign_report.snapshot
            result["campaign_evidence_available"] = True
            result["campaign_fills"] = snap.total_fills
            result["campaign_tca_records"] = getattr(snap, "persisted_tca_count", 0)

        if self._review is not None and self._review.campaign_count > 0:
            result["review_evidence_available"] = True
            result["review_campaign_count"] = self._review.campaign_count
            missing = self._review.get_missing_evidence()
            result["review_insufficient_criteria"] = missing.get("insufficient_criteria", [])
            result["summary"] = missing.get("message", "")
        elif self._last_campaign_report is not None:
            result["summary"] = "Campaign evidence available but no review initiated."

        return result

    def reason_summary(self) -> dict:
        """Top-level promotion reason summary from the review."""
        if self._review is None:
            return {
                "verdict": None,
                "summary": "No promotion review active.",
            }
        return self._review.get_promotion_reason_summary()

    def campaign_readiness_flags(self) -> dict[str, bool] | None:
        """Derive readiness flags from the last finalized campaign.

        Returns None if no campaign has been finalized.
        """
        if self._last_campaign_report is None:
            return None
        return campaign_readiness_flags(self._last_campaign_report)

    def external_regime_snapshot(self) -> ExternalRegimeSnapshot | None:
        """Current external regime snapshot, or None if no data plane configured.

        Uses the last event timestamp from the service watchdog as ``now_ns``.
        """
        if self._external_regime_plane is None:
            return None
        ss = self._service.status()
        return self._external_regime_plane.snapshot(ss.watchdog.last_event_time_ns)

    def external_regime_dict(self) -> dict | None:
        """Serialize the external regime snapshot to a dict.

        Returns None if no data plane configured.
        """
        snap = self.external_regime_snapshot()
        if snap is None:
            return None
        from crypto_core.service.external_regime import (
            external_regime_snapshot_to_dict,
        )

        return external_regime_snapshot_to_dict(snap)

    # ------------------------------------------------------------------
    # Persistence / restore linkage
    # ------------------------------------------------------------------

    def restore_campaign(self) -> bool:
        """Attempt to restore campaign state from evidence store.

        Returns True if campaign was restored, False if no state exists.

        Raises:
            CampaignMetadataCorruptError: if persisted state is malformed.
            RuntimeError: if no evidence store configured.
        """
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for restore")

        if self._campaign is not None and self.campaign_active():
            raise RuntimeError("Cannot restore: active campaign in progress")

        controller = CampaignController(
            config=self._campaign_config or CampaignConfig(),
            evidence_store=self._evidence_store,
        )
        try:
            controller.restore_metadata()
        except Exception:
            return False

        self._campaign = controller
        logger.info(
            "Campaign %s restored via orchestrator (status=%s)",
            controller.campaign_id,
            controller.status.value,
        )
        return True

    def restore_review(
        self,
        reports_by_id: dict[str, CampaignReport],
    ) -> bool:
        """Attempt to restore review workflow from evidence store.

        Args:
            reports_by_id: campaign reports keyed by campaign_id for
                re-linking into the restored review set.

        Returns True if review was restored, False if no state exists.

        Raises:
            ReviewWorkflowCorruptError: if persisted state is malformed.
            RuntimeError: if no evidence store configured.
        """
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for restore")

        if self._review is not None and self.review_active():
            raise RuntimeError("Cannot restore: active review in progress")

        try:
            controller = PromotionReviewController.restore(
                self._evidence_store,
                reports_by_id,
                thresholds=self._promotion_thresholds,
            )
        except (ReviewWorkflowCorruptError, RuntimeError):
            raise
        except Exception:
            return False

        self._review = controller
        logger.info(
            "Review %s restored via orchestrator (status=%s, campaigns=%d)",
            controller.review_id,
            controller.status.value,
            controller.campaign_count,
        )
        return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_campaign(self, operation: str) -> None:
        """Validate that an active campaign exists."""
        if self._campaign is None:
            raise RuntimeError(f"No campaign to {operation}")
        if not self.campaign_active():
            raise RuntimeError(
                f"Cannot {operation}: campaign {self._campaign.campaign_id!r} "
                f"in terminal status {self._campaign.status.value!r}"
            )

    def _require_review(self, operation: str) -> None:
        """Validate that an active review exists."""
        if self._review is None:
            raise RuntimeError(f"No review to {operation}")
        if not self.review_active():
            raise RuntimeError(
                f"Cannot {operation}: review {self._review.review_id!r} "
                f"in terminal status {self._review.status.value!r}"
            )

    def _build_campaign_workflow_state(
        self,
        ss: ServiceStatus,
    ) -> CampaignWorkflowState | None:
        """Build campaign workflow state summary."""
        if self._campaign is None:
            return None

        snap = self._campaign.snapshot(ss)
        finalized = self._campaign.verdict is not None

        return CampaignWorkflowState(
            active=self.campaign_active(),
            campaign_id=self._campaign.campaign_id,
            status=self._campaign.status.value,
            started_at_ns=snap.started_at_ns,
            elapsed_seconds=snap.elapsed_seconds,
            total_cycles=snap.total_cycles,
            total_fills=snap.total_fills,
            verdict=self._campaign.verdict.value if self._campaign.verdict else None,
            finalized=finalized,
        )

    def _build_review_workflow_state(self) -> ReviewWorkflowState | None:
        """Build review workflow state summary."""
        if self._review is None:
            return None

        snap = self._review.current_snapshot()
        return ReviewWorkflowState(
            active=self.review_active(),
            review_id=self._review.review_id,
            status=self._review.status.value,
            campaign_count=self._review.campaign_count,
            provisional_verdict=snap.provisional_verdict,
            provisional_summary=snap.provisional_summary,
            insufficient_evidence=snap.insufficient_evidence,
            is_ready_to_finalize=snap.is_ready_to_finalize,
            finalized=self._review.is_finalized,
        )

    def _build_evidence_sufficiency(
        self,
        campaign_state: CampaignWorkflowState | None,
        review_state: ReviewWorkflowState | None,
        ext_regime: ExternalRegimeSnapshot | None = None,
    ) -> EvidenceSufficiencyState:
        """Build evidence sufficiency summary.

        Truthful: exposes exactly what evidence is available and what is missing.
        """
        campaign_available = self._last_campaign_report is not None
        review_available = self._review is not None and self._review.campaign_count > 0

        # Execution calibration: check if last campaign had TCA evidence
        ei_available = False
        if campaign_available:
            snap = self._last_campaign_report.snapshot
            ei_available = getattr(snap, "persisted_tca_count", 0) > 0

        # Promotion evidence sufficient: review must have campaigns AND
        # no insufficient criteria in provisional evaluation
        insufficient_reasons: tuple[str, ...] = ()
        promotion_sufficient = False

        if review_available:
            snap_rev = self._review.current_snapshot()
            insufficient_reasons = snap_rev.insufficient_evidence
            promotion_sufficient = (
                len(insufficient_reasons) == 0
                and snap_rev.provisional_verdict is not None
                and snap_rev.provisional_verdict != "reject"
            )

        # External regime evidence (Phase 11A)
        ext_available = ext_regime is not None and len(ext_regime.available_dimensions) > 0
        ext_fresh = ext_regime is not None and ext_regime.evidence_sufficient
        ext_high_risk = ext_regime is not None and ext_regime.high_risk_regime_present

        # Build summary
        parts: list[str] = []
        if not campaign_available:
            parts.append("No finalized campaign evidence.")
        if not review_available:
            parts.append("No review evidence.")
        if campaign_available and not ei_available:
            parts.append("No TCA calibration evidence in campaign.")
        if insufficient_reasons:
            parts.append(f"Insufficient review criteria: {', '.join(insufficient_reasons)}.")
        if not ext_available:
            parts.append("No external regime evidence available.")
        elif not ext_fresh:
            parts.append("External regime evidence stale or insufficient.")
        if ext_high_risk:
            parts.append("High-risk external regime conditions present.")
        if not parts:
            parts.append("Evidence appears sufficient for promotion consideration.")

        return EvidenceSufficiencyState(
            campaign_evidence_available=campaign_available,
            review_evidence_available=review_available,
            execution_calibration_available=ei_available,
            promotion_evidence_sufficient=promotion_sufficient,
            insufficient_reasons=insufficient_reasons,
            summary=" ".join(parts),
            external_regime_available=ext_available,
            external_regime_fresh=ext_fresh,
            external_regime_has_high_risk=ext_high_risk,
        )


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def campaign_workflow_state_to_dict(state: CampaignWorkflowState) -> dict:
    """Serialize CampaignWorkflowState to a plain dict."""
    return {
        "active": state.active,
        "campaign_id": state.campaign_id,
        "status": state.status,
        "started_at_ns": state.started_at_ns,
        "elapsed_seconds": state.elapsed_seconds,
        "total_cycles": state.total_cycles,
        "total_fills": state.total_fills,
        "verdict": state.verdict,
        "finalized": state.finalized,
    }


def review_workflow_state_to_dict(state: ReviewWorkflowState) -> dict:
    """Serialize ReviewWorkflowState to a plain dict."""
    return {
        "active": state.active,
        "review_id": state.review_id,
        "status": state.status,
        "campaign_count": state.campaign_count,
        "provisional_verdict": state.provisional_verdict,
        "provisional_summary": state.provisional_summary,
        "insufficient_evidence": list(state.insufficient_evidence),
        "is_ready_to_finalize": state.is_ready_to_finalize,
        "finalized": state.finalized,
    }


def evidence_sufficiency_state_to_dict(state: EvidenceSufficiencyState) -> dict:
    """Serialize EvidenceSufficiencyState to a plain dict."""
    return {
        "campaign_evidence_available": state.campaign_evidence_available,
        "review_evidence_available": state.review_evidence_available,
        "execution_calibration_available": state.execution_calibration_available,
        "promotion_evidence_sufficient": state.promotion_evidence_sufficient,
        "insufficient_reasons": list(state.insufficient_reasons),
        "summary": state.summary,
        "external_regime_available": state.external_regime_available,
        "external_regime_fresh": state.external_regime_fresh,
        "external_regime_has_high_risk": state.external_regime_has_high_risk,
    }


def operator_snapshot_to_dict(snap: OperatorSnapshot) -> dict:
    """Serialize OperatorSnapshot to a plain dict."""
    return {
        "service_mode": snap.service_mode,
        "trading_enabled": snap.trading_enabled,
        "blocked_reason": snap.blocked_reason,
        "ei_available": snap.ei_available,
        "ei_degraded": snap.ei_degraded,
        "ei_degraded_reasons": list(snap.ei_degraded_reasons),
        "campaign": (campaign_workflow_state_to_dict(snap.campaign) if snap.campaign is not None else None),
        "review": (review_workflow_state_to_dict(snap.review) if snap.review is not None else None),
        "readiness_level": snap.readiness_level,
        "readiness_is_supportive": snap.readiness_is_supportive,
        "evidence": evidence_sufficiency_state_to_dict(snap.evidence),
        "provisional_recommendation": snap.provisional_recommendation,
        "recommendation_summary": snap.recommendation_summary,
        "external_regime": (
            _external_regime_snap_to_dict(snap.external_regime) if snap.external_regime is not None else None
        ),
    }


def _external_regime_snap_to_dict(snap: ExternalRegimeSnapshot) -> dict:
    """Serialize ExternalRegimeSnapshot via the external_regime module."""
    from crypto_core.service.external_regime import external_regime_snapshot_to_dict

    return external_regime_snapshot_to_dict(snap)
