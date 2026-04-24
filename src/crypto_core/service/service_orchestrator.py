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
from collections.abc import Callable
from dataclasses import dataclass

from crypto_core.service.artifact_export import (
    EscalationDecision,
    EscalationStage,
    OperatorDecisionPack,
    decision_pack_decision_summary,
    decision_pack_missing_evidence,
    decision_pack_next_inspection,
    decision_pack_to_dict,
    decision_pack_why_not_promotable,
    escalation_decision_blockers,
    escalation_decision_missing_evidence,
    escalation_decision_revalidation,
    escalation_decision_summary,
    escalation_decision_to_dict,
    escalation_decision_why_not_higher,
    export_escalation_decision,
    export_operator_decision_pack,
    export_sleeve_portfolio_snapshot,
    load_escalation_decision,
    load_operator_decision_pack,
    load_sleeve_portfolio_snapshot,
    operator_disposition_from_verdict,
)
from crypto_core.service.artifact_export import (
    export_sleeve_admission_release_pack as export_admission_release_pack,
)
from crypto_core.service.artifact_export import (
    load_sleeve_admission_release_pack as load_admission_release_pack,
)
from crypto_core.service.campaign import (
    CampaignConfig,
    CampaignReport,
    CampaignSleeveLinkSummary,
    CampaignSnapshot,
)
from crypto_core.service.campaign_controller import (
    CampaignController,
    campaign_readiness_flags,
)
from crypto_core.service.escalation_review_controller import (
    CurrentEscalationReviewSnapshot,
    EscalationAttemptSummary,
    EscalationReviewController,
    EscalationReviewStatus,
    EscalationWorkflowCorruptError,
    FinalEscalationReviewReport,
)
from crypto_core.service.evidence_store import EvidenceStore
from crypto_core.service.external_regime import (
    ExternalRegimeBundleApplyMode,
    ExternalRegimeBundleIngestionRecord,
    ExternalRegimeBundleReplayArtifact,
    ExternalRegimeDataPlane,
    ExternalRegimeManager,
    ExternalRegimePayloadIngestionRecord,
    ExternalRegimeSafetyPolicy,
    ExternalRegimeScenario,
    ExternalRegimeScenarioResult,
    ExternalRegimeSnapshot,
    ExternalRegimeUpdateRecord,
    evaluate_external_regime_activation_safety,
    evaluate_external_regime_execution_safety,
    external_regime_scenario_result_to_dict,
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
from crypto_core.service.readiness import ReadinessEvaluator, readiness_to_dict
from crypto_core.service.sleeve_admission_controller import (
    SleeveAdmissionController,
    SleeveAdmissionReleasePack,
    SleeveAdmissionSnapshot,
    sleeve_admission_portfolio_summary_to_dict,
    sleeve_admission_release_pack_to_dict,
    sleeve_admission_snapshot_to_dict,
)
from crypto_core.service.sleeve_admission_controller import (
    build_sleeve_admission_release_pack as build_admission_release_pack,
)
from crypto_core.service.sleeve_candidate_workflow import (
    SleeveCandidateWorkflowController,
    SleeveCandidateWorkflowCorruptError,
    SleeveCandidateWorkflowSnapshot,
    SleeveCandidateWorkflowStatus,
    sleeve_candidate_workflow_snapshot_to_dict,
)
from crypto_core.service.sleeve_portfolio import (
    CryptoSleeveState,
    SleeveAllocationPolicy,
    SleevePortfolioSnapshot,
    build_sleeve_portfolio_snapshot,
    sleeve_allocation_policy_to_dict,
    sleeve_campaign_evidence_result_to_dict,
    sleeve_decision_pack_result_to_dict,
    sleeve_effective_allocation_summary_to_dict,
    sleeve_portfolio_decision_pack_summary_to_dict,
    sleeve_portfolio_decision_summary_to_dict,
    sleeve_portfolio_evidence_summary_to_dict,
    sleeve_portfolio_snapshot_to_dict,
    sleeve_promotion_candidate_result_to_dict,
    sleeve_promotion_support_result_to_dict,
    sleeve_qualification_result_to_dict,
    sleeve_qualification_summary_to_dict,
    sleeve_recommendation_result_to_dict,
)
from crypto_core.service.sleeve_portfolio_controller import (
    SleeveOperatorOverride,
    SleevePortfolioController,
)
from crypto_core.service.sleeve_promotion_review_controller import (
    SleevePromotionReviewController,
    SleevePromotionReviewPortfolioSummary,
    SleevePromotionReviewSnapshot,
    sleeve_promotion_review_snapshot_to_dict,
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
class EscalationWorkflowState:
    """Escalation review workflow state summary for operator surfaces."""

    active: bool
    review_id: str | None
    status: str
    allowed_next_step: str | None
    progression_state: str
    previous_allowed_next_step: str | None
    history_length: int
    repeatedly_stuck: bool
    finalized: bool


@dataclass(frozen=True)
class SleeveCandidateWorkflowState:
    """Sleeve candidate workflow state summary for operator surfaces."""

    active: bool
    workflow_id: str | None
    status: str
    candidate_sleeves: int
    supported_candidate_sleeves: int
    weak_candidate_sleeves: int
    blocked_candidate_sleeves: int
    inconclusive_candidate_sleeves: int
    progression_state: str
    previous_as_of_ns: int | None
    history_length: int
    repeatedly_weak: bool
    repeatedly_blocked: bool
    repeatedly_inconclusive: bool
    finalized: bool


@dataclass(frozen=True)
class SleeveAdmissionReleaseState:
    """Compact sleeve admission release-pack status for operator snapshots."""

    available: bool
    pack_id: str | None
    as_of_ns: int | None
    overall_release_status: str
    admitted_sleeves: int
    admitted_active_sleeves: int
    admitted_unallocated_sleeves: int
    review_supported_not_admitted_sleeves: int
    blocked_sleeves: int
    inconclusive_sleeves: int
    insufficient_evidence_sleeves: int
    disabled_operator_off_sleeves: int
    evidence_blockers: tuple[str, ...]
    governance_blockers: tuple[str, ...]


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
    external_regime_scenario_available: bool = False
    external_regime_execution_blocked_steps: int = 0
    external_regime_activation_blocked_steps: int = 0
    external_regime_activation_reduced_steps: int = 0
    external_regime_scenario_summary: str = ""


@dataclass(frozen=True)
class ExternalRegimeSafetyState:
    """Current external regime safety posture for activation and execution."""

    activation_blocked: bool
    activation_reason: str | None
    activation_allocation_scale: float
    execution_blocked: bool
    execution_reason: str | None
    evidence: dict[str, object]


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
    external_regime_safety: ExternalRegimeSafetyState | None = None
    external_regime_scenario: ExternalRegimeScenarioResult | None = None
    sleeve_portfolio: SleevePortfolioSnapshot | None = None
    sleeve_candidate_workflow: SleeveCandidateWorkflowState | None = None

    # Phase 15E: Sleeve promotion review
    sleeve_promotion_review: SleevePromotionReviewSnapshot | None = None

    # Phase 15F: Sleeve admission gate
    sleeve_admission: SleeveAdmissionSnapshot | None = None

    # Phase 15I: Sleeve admission release-pack compact status
    sleeve_admission_release: SleeveAdmissionReleaseState | None = None

    # Escalation review workflow (Phase 13B)
    escalation_review: EscalationWorkflowState | None = None


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
        external_regime_manager: ExternalRegimeManager | None = None,
        external_regime_policy: ExternalRegimeSafetyPolicy | None = None,
        sleeves: tuple[CryptoSleeveState, ...] = (),
        sleeve_allocation_policy: SleeveAllocationPolicy | None = None,
        sleeve_workflow_clock_ns: Callable[[], int] | None = None,
    ) -> None:
        self._service = service
        self._evidence_store = evidence_store
        self._readiness_level = readiness_level
        self._promotion_thresholds = promotion_thresholds
        self._campaign_config = campaign_config
        self._external_regime_policy = external_regime_policy or ExternalRegimeSafetyPolicy()
        self._sleeve_workflow_clock_ns = sleeve_workflow_clock_ns

        if external_regime_manager is not None and external_regime_plane is not None:
            if external_regime_manager.plane is not external_regime_plane:
                raise ValueError(
                    "external_regime_manager.plane must match external_regime_plane when both are provided"
                )

        if external_regime_manager is not None:
            self._external_regime_manager = external_regime_manager
            self._external_regime_plane = external_regime_manager.plane
        elif external_regime_plane is not None:
            self._external_regime_manager = ExternalRegimeManager(
                plane=external_regime_plane,
                evidence_store=evidence_store,
            )
            self._external_regime_plane = external_regime_plane
        else:
            self._external_regime_manager = None
            self._external_regime_plane = None

        self._campaign: CampaignController | None = None
        self._review: PromotionReviewController | None = None
        self._last_campaign_report: CampaignReport | None = None
        self._sleeve_portfolio_controller: SleevePortfolioController | None = None
        self._sleeve_candidate_workflow_controller: SleeveCandidateWorkflowController | None = None
        self._sleeve_promotion_review_controller: SleevePromotionReviewController | None = None
        self._sleeve_admission_controller: SleeveAdmissionController | None = None
        self._configured_sleeves = tuple(sleeves)
        self._escalation_review: EscalationReviewController | None = None
        self._sleeve_allocation_policy = (
            SleeveAllocationPolicy() if sleeve_allocation_policy is None else sleeve_allocation_policy
        )

    def build_sleeve_admission_controller(
        self,
        *,
        portfolio_snapshot: SleevePortfolioSnapshot | None = None,
        review_portfolio_summary: SleevePromotionReviewPortfolioSummary | None = None,
        history_limit: int = 5,
    ) -> SleeveAdmissionController:
        """Build or refresh the sleeve admission controller from current review and portfolio truth."""
        if review_portfolio_summary is None:
            review_snapshot = self.sleeve_promotion_review_snapshot()
            review_portfolio_summary = None if review_snapshot is None else review_snapshot.portfolio_summary
        portfolio = self.sleeve_portfolio_snapshot() if portfolio_snapshot is None else portfolio_snapshot
        if self._sleeve_admission_controller is None:
            self._sleeve_admission_controller = SleeveAdmissionController(
                review_portfolio_summary,
                portfolio_snapshot=portfolio,
                history_limit=history_limit,
            )
        else:
            self._sleeve_admission_controller.configure(
                review_portfolio_summary,
                portfolio_snapshot=portfolio,
            )
        return self._sleeve_admission_controller

    def get_sleeve_admission_snapshot(
        self,
        *,
        portfolio_snapshot: SleevePortfolioSnapshot | None = None,
    ) -> SleeveAdmissionSnapshot:
        controller = self.build_sleeve_admission_controller(portfolio_snapshot=portfolio_snapshot)
        return controller.snapshot()

    def get_sleeve_admission_portfolio_summary(
        self,
        *,
        portfolio_snapshot: SleevePortfolioSnapshot | None = None,
    ):
        controller = self.build_sleeve_admission_controller(portfolio_snapshot=portfolio_snapshot)
        return controller.build_portfolio_summary()

    def finalize_sleeve_admission(
        self,
        *,
        portfolio_snapshot: SleevePortfolioSnapshot | None = None,
    ) -> SleeveAdmissionSnapshot:
        controller = self.build_sleeve_admission_controller(portfolio_snapshot=portfolio_snapshot)
        return controller.finalize()

    def reset_sleeve_admission(self) -> None:
        if self._sleeve_admission_controller is not None:
            self._sleeve_admission_controller.reset()

    # ------------------------------------------------------------------
    # Sleeve promotion review surface (Phase 15E)
    # ------------------------------------------------------------------

    def start_sleeve_promotion_review(
        self, *, workflow_snapshot: SleeveCandidateWorkflowSnapshot, history_limit: int = 5
    ) -> None:
        from crypto_core.service.sleeve_promotion_review_controller import SleevePromotionReviewController

        self._sleeve_promotion_review_controller = SleevePromotionReviewController(
            workflow_snapshot,
            history_limit=history_limit,
            clock_ns=self._sleeve_workflow_clock_ns,
        )

    def inspect_sleeve_promotion_review(self) -> SleevePromotionReviewSnapshot | None:
        if self._sleeve_promotion_review_controller is None:
            return None
        return self._sleeve_promotion_review_controller.snapshot()

    def finalize_sleeve_promotion_review(self) -> SleevePromotionReviewSnapshot | None:
        if self._sleeve_promotion_review_controller is None:
            return None
        return self._sleeve_promotion_review_controller.finalize()

    def reset_sleeve_promotion_review(self) -> None:
        if self._sleeve_promotion_review_controller is not None:
            self._sleeve_promotion_review_controller.reset()

    def sleeve_promotion_review_snapshot(self) -> SleevePromotionReviewSnapshot | None:
        if self._sleeve_promotion_review_controller is None:
            return None
        return self._sleeve_promotion_review_controller.snapshot()

    def sleeve_promotion_review_dict(self) -> dict | None:
        snap = self.sleeve_promotion_review_snapshot()
        if snap is None:
            return None
        return sleeve_promotion_review_snapshot_to_dict(snap)

    def sleeve_admission_snapshot(self) -> SleeveAdmissionSnapshot:
        """Return the current sleeve admission gate snapshot."""
        return self.get_sleeve_admission_snapshot()

    def sleeve_admission_dict(self) -> dict:
        """Serialize the current sleeve admission gate snapshot."""
        return sleeve_admission_snapshot_to_dict(self.sleeve_admission_snapshot())

    def sleeve_admission_summary_dict(self) -> dict:
        """Serialize the portfolio-level sleeve admission summary."""
        return sleeve_admission_portfolio_summary_to_dict(self.get_sleeve_admission_portfolio_summary())

    def sleeve_admission_release_pack(
        self,
        *,
        portfolio_snapshot: SleevePortfolioSnapshot | None = None,
        admission_snapshot: SleeveAdmissionSnapshot | None = None,
        promotion_review_snapshot: SleevePromotionReviewSnapshot | None = None,
        candidate_workflow_snapshot: SleeveCandidateWorkflowSnapshot | None = None,
    ) -> SleeveAdmissionReleasePack:
        """Build the deterministic operator-facing sleeve admission release pack."""
        portfolio = self.sleeve_portfolio_snapshot() if portfolio_snapshot is None else portfolio_snapshot
        promotion_review = promotion_review_snapshot
        if promotion_review is None and self._sleeve_promotion_review_controller is not None:
            promotion_review = self._sleeve_promotion_review_controller.snapshot()
        review_portfolio_summary = None if promotion_review is None else promotion_review.portfolio_summary
        admission = admission_snapshot
        if admission is None:
            admission = self.build_sleeve_admission_controller(
                portfolio_snapshot=portfolio,
                review_portfolio_summary=review_portfolio_summary,
            ).snapshot()
        candidate_workflow = (
            self.sleeve_candidate_workflow_snapshot()
            if candidate_workflow_snapshot is None
            else candidate_workflow_snapshot
        )
        return build_admission_release_pack(
            admission,
            promotion_review_snapshot=promotion_review,
            candidate_workflow_snapshot=candidate_workflow,
            portfolio_snapshot=portfolio,
        )

    def sleeve_admission_release_pack_dict(self) -> dict:
        """Serialize the current sleeve admission release pack to a plain dict."""
        return sleeve_admission_release_pack_to_dict(self.sleeve_admission_release_pack())

    def export_sleeve_admission_release_pack(self):
        """Persist the current sleeve admission release pack via EvidenceStore."""
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for sleeve admission release pack export")
        return export_admission_release_pack(
            pack=self.sleeve_admission_release_pack(),
            evidence_store=self._evidence_store,
        )

    def load_sleeve_admission_release_pack(self) -> SleeveAdmissionReleasePack:
        """Load the latest persisted sleeve admission release pack."""
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for sleeve admission release pack load")
        return load_admission_release_pack(evidence_store=self._evidence_store)

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
    def escalation_review_controller(self) -> EscalationReviewController | None:
        """Active EscalationReviewController, or None."""
        return self._escalation_review

    @property
    def sleeve_candidate_workflow_controller(self) -> SleeveCandidateWorkflowController | None:
        """Active sleeve candidate workflow controller, or None."""
        return self._sleeve_candidate_workflow_controller

    @property
    def external_regime_plane(self) -> ExternalRegimeDataPlane | None:
        """Active ExternalRegimeDataPlane, or None."""
        return self._external_regime_plane

    @property
    def external_regime_manager(self) -> ExternalRegimeManager | None:
        """Managed external regime lifecycle surface, or None."""
        return self._external_regime_manager

    @property
    def readiness_level(self) -> str:
        """Current readiness level."""
        return self._readiness_level

    @readiness_level.setter
    def readiness_level(self, value: str) -> None:
        self._readiness_level = value

    # ------------------------------------------------------------------
    # Sleeve portfolio surface
    # ------------------------------------------------------------------

    def set_sleeve_portfolio(
        self,
        sleeves: tuple[CryptoSleeveState, ...],
    ) -> SleevePortfolioSnapshot:
        """Replace the configured crypto sleeve portfolio surface."""
        self._configured_sleeves = tuple(sleeves)
        if self._sleeve_portfolio_controller is not None:
            self._sleeve_portfolio_controller.configure_sleeves(self._configured_sleeves)
        return self.sleeve_portfolio_snapshot()

    def set_sleeve_allocation_policy(self, policy: SleeveAllocationPolicy) -> SleevePortfolioSnapshot:
        """Replace the explicit sleeve effective-allocation recompute policy."""
        self._sleeve_allocation_policy = policy
        if self._sleeve_portfolio_controller is not None:
            self._sleeve_portfolio_controller.configure_allocation_policy(policy)
        return self.sleeve_portfolio_snapshot()

    def enable_sleeve(self, sleeve_id: str) -> SleeveOperatorOverride:
        """Explicitly enable or unblock a sleeve at the operator layer."""
        return self._ensure_sleeve_portfolio_controller().enable_sleeve(sleeve_id)

    def disable_sleeve(
        self,
        sleeve_id: str,
        *,
        reason_summary: str = "Explicitly disabled by operator.",
        required_change: str = "Use enable_sleeve after operator review.",
    ) -> SleeveOperatorOverride:
        """Explicitly disable a sleeve at the operator layer."""
        return self._ensure_sleeve_portfolio_controller().disable_sleeve(
            sleeve_id,
            reason_summary=reason_summary,
            required_change=required_change,
        )

    def block_sleeve(
        self,
        sleeve_id: str,
        *,
        reason_summary: str,
        required_change: str = "Clear the operator block before enabling.",
    ) -> SleeveOperatorOverride:
        """Explicitly block a sleeve at the operator layer."""
        return self._ensure_sleeve_portfolio_controller().block_sleeve(
            sleeve_id,
            reason_summary=reason_summary,
            required_change=required_change,
        )

    def unblock_sleeve(self, sleeve_id: str) -> SleeveOperatorOverride:
        """Explicitly remove operator/configuration block pressure for a sleeve."""
        return self._ensure_sleeve_portfolio_controller().unblock_sleeve(sleeve_id)

    def sleeve_portfolio_snapshot(self) -> SleevePortfolioSnapshot:
        """Build the current crypto sleeve portfolio snapshot."""
        service_status = self._service.status()
        ext_regime = self._external_regime_snapshot_from_status(service_status)
        ext_regime_safety = self._build_external_regime_safety_state(ext_regime)
        return self._build_sleeve_portfolio_snapshot(service_status, ext_regime_safety)

    def sleeve_portfolio_dict(self) -> dict:
        """Serialize the current crypto sleeve portfolio snapshot to a dict."""
        return sleeve_portfolio_snapshot_to_dict(self.sleeve_portfolio_snapshot())

    def sleeve_allocation_policy_dict(self) -> dict:
        """Serialize the current sleeve allocation policy to a plain dict."""
        return sleeve_allocation_policy_to_dict(self.sleeve_portfolio_snapshot().allocation_policy)

    def sleeve_allocation_result_dict(self) -> dict:
        """Serialize the current effective sleeve allocation result to a plain dict."""
        return sleeve_effective_allocation_summary_to_dict(self.sleeve_portfolio_snapshot().effective_allocation)

    def sleeve_qualification_summary_dict(self) -> dict:
        """Serialize the current sleeve qualification summary to a plain dict."""
        return sleeve_qualification_summary_to_dict(self.sleeve_portfolio_snapshot().qualification)

    def sleeve_qualification_result_dict(self) -> dict:
        """Serialize per-sleeve qualification results keyed by sleeve id."""
        snapshot = self.sleeve_portfolio_snapshot()
        return {
            sleeve.sleeve_id: sleeve_qualification_result_to_dict(sleeve.qualification) for sleeve in snapshot.sleeves
        }

    def sleeve_portfolio_decision_dict(self) -> dict:
        """Serialize the current sleeve portfolio decision summary to a plain dict."""
        return sleeve_portfolio_decision_summary_to_dict(self.sleeve_portfolio_snapshot().decision)

    def sleeve_recommendation_result_dict(self) -> dict:
        """Serialize per-sleeve recommendation results keyed by sleeve id."""
        snapshot = self.sleeve_portfolio_snapshot()
        return {
            sleeve.sleeve_id: sleeve_recommendation_result_to_dict(sleeve.recommendation) for sleeve in snapshot.sleeves
        }

    def sleeve_campaign_evidence_result_dict(self) -> dict:
        """Serialize per-sleeve campaign evidence results keyed by sleeve id."""
        snapshot = self.sleeve_portfolio_snapshot()
        return {
            sleeve.sleeve_id: sleeve_campaign_evidence_result_to_dict(sleeve.campaign_evidence)
            for sleeve in snapshot.sleeves
        }

    def sleeve_promotion_support_result_dict(self) -> dict:
        """Serialize per-sleeve promotion-support results keyed by sleeve id."""
        snapshot = self.sleeve_portfolio_snapshot()
        return {
            sleeve.sleeve_id: sleeve_promotion_support_result_to_dict(sleeve.promotion_support)
            for sleeve in snapshot.sleeves
        }

    def sleeve_portfolio_evidence_dict(self) -> dict:
        """Serialize the portfolio-wide sleeve evidence summary to a plain dict."""
        return sleeve_portfolio_evidence_summary_to_dict(self.sleeve_portfolio_snapshot().evidence)

    def sleeve_decision_pack_result_dict(self) -> dict:
        """Serialize per-sleeve decision-pack results keyed by sleeve id."""
        snapshot = self.sleeve_portfolio_snapshot()
        return {
            sleeve.sleeve_id: sleeve_decision_pack_result_to_dict(sleeve.decision_pack) for sleeve in snapshot.sleeves
        }

    def sleeve_promotion_candidate_result_dict(self) -> dict:
        """Serialize per-sleeve promotion-candidate results keyed by sleeve id."""
        snapshot = self.sleeve_portfolio_snapshot()
        return {
            sleeve.sleeve_id: sleeve_promotion_candidate_result_to_dict(sleeve.promotion_candidate)
            for sleeve in snapshot.sleeves
        }

    def sleeve_portfolio_decision_pack_dict(self) -> dict:
        """Serialize the portfolio-wide sleeve decision pack to a plain dict."""
        return sleeve_portfolio_decision_pack_summary_to_dict(self.sleeve_portfolio_snapshot().decision_pack)

    def export_sleeve_portfolio(self):
        """Persist the current crypto sleeve portfolio snapshot via EvidenceStore."""
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for sleeve portfolio export")
        return export_sleeve_portfolio_snapshot(
            snapshot=self.sleeve_portfolio_snapshot(),
            evidence_store=self._evidence_store,
        )

    def load_sleeve_portfolio(self) -> SleevePortfolioSnapshot:
        """Load and activate the latest persisted crypto sleeve portfolio snapshot."""
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for sleeve portfolio load")
        snapshot = load_sleeve_portfolio_snapshot(evidence_store=self._evidence_store)
        self._configured_sleeves = snapshot.sleeves
        self._sleeve_allocation_policy = snapshot.allocation_policy
        if self._sleeve_portfolio_controller is not None:
            self._sleeve_portfolio_controller.configure_sleeves(snapshot.sleeves)
            self._sleeve_portfolio_controller.configure_allocation_policy(snapshot.allocation_policy)
        return snapshot

    def restore_sleeve_portfolio_workflow(self) -> SleevePortfolioSnapshot:
        """Restore the managed sleeve workflow state if a persisted controller snapshot exists."""
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for sleeve portfolio workflow restore")
        controller = SleevePortfolioController.restore(
            self._evidence_store,
            clock_ns=self._sleeve_workflow_clock_ns,
        )
        self._sleeve_portfolio_controller = controller
        self._configured_sleeves = controller.defined_sleeves
        self._sleeve_allocation_policy = controller.allocation_policy
        return self.sleeve_portfolio_snapshot()

    def start_sleeve_candidate_workflow(self, *, workflow_id: str | None = None) -> str:
        """Start an explicit sleeve candidate workflow inspection cycle."""
        return self._ensure_sleeve_candidate_workflow_controller().start(workflow_id=workflow_id)

    def inspect_sleeve_candidate_workflow(self) -> SleeveCandidateWorkflowSnapshot:
        """Inspect the current sleeve candidate truth without finalizing history."""
        snapshot = self.sleeve_portfolio_snapshot()
        return self._ensure_sleeve_candidate_workflow_controller().inspect(snapshot)

    def finalize_sleeve_candidate_workflow(self) -> SleeveCandidateWorkflowSnapshot:
        """Finalize the current sleeve candidate workflow inspection."""
        snapshot = self.sleeve_portfolio_snapshot()
        return self._ensure_sleeve_candidate_workflow_controller().finalize(snapshot)

    def reset_sleeve_candidate_workflow(self) -> None:
        """Reset the active sleeve candidate workflow while preserving history."""
        if self._sleeve_candidate_workflow_controller is None:
            raise RuntimeError("No sleeve candidate workflow to reset")
        self._sleeve_candidate_workflow_controller.reset()

    def sleeve_candidate_workflow_snapshot(self) -> SleeveCandidateWorkflowSnapshot | None:
        """Return the latest inspected sleeve candidate workflow snapshot, if present."""
        if self._sleeve_candidate_workflow_controller is None:
            return None
        return self._sleeve_candidate_workflow_controller.current_snapshot

    def sleeve_candidate_workflow_dict(self) -> dict | None:
        """Serialize the latest inspected sleeve candidate workflow snapshot to a dict."""
        snapshot = self.sleeve_candidate_workflow_snapshot()
        if snapshot is None:
            return None
        return sleeve_candidate_workflow_snapshot_to_dict(snapshot)

    def sleeve_candidate_change_summary(self) -> dict:
        """Current-vs-previous sleeve candidate comparison summary."""
        snapshot = self.sleeve_candidate_workflow_snapshot()
        if snapshot is None:
            return {
                "available": False,
                "changed": False,
                "progression_state": "not_assessed",
                "previous_as_of_ns": None,
                "current_as_of_ns": None,
                "changed_sleeves": [],
            }
        return dict(snapshot.comparison_to_previous)

    def sleeve_candidate_history_summary(self) -> dict:
        """Bounded sleeve candidate workflow history summary."""
        if self._sleeve_candidate_workflow_controller is None:
            return {
                "total_finalized_workflows": 0,
                "latest_finalized_as_of_ns": None,
                "latest_summary": None,
                "repeated_weak_sleeve_ids": [],
                "repeated_blocked_sleeve_ids": [],
                "repeated_inconclusive_sleeve_ids": [],
            }
        snapshot = self._sleeve_candidate_workflow_controller.current_snapshot
        return self._sleeve_candidate_workflow_controller.history_summary(snapshot)

    def restore_sleeve_candidate_workflow(self) -> bool:
        """Attempt to restore sleeve candidate workflow state from evidence store."""
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for restore")

        if (
            self._sleeve_candidate_workflow_controller is not None
            and self._sleeve_candidate_workflow_controller.status == SleeveCandidateWorkflowStatus.ACTIVE
        ):
            raise RuntimeError("Cannot restore: active sleeve candidate workflow in progress")

        try:
            controller = SleeveCandidateWorkflowController.restore(
                self._evidence_store,
                clock_ns=self._sleeve_workflow_clock_ns,
            )
        except (SleeveCandidateWorkflowCorruptError, RuntimeError):
            raise
        except Exception:
            return False

        self._sleeve_candidate_workflow_controller = controller
        logger.info(
            "Sleeve candidate workflow %s restored via orchestrator (status=%s, history=%d)",
            controller.workflow_id,
            controller.status.value,
            len(controller.history),
        )
        return True

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
        ext_regime = self._external_regime_snapshot_from_status(ss)
        ext_regime_safety = self._build_external_regime_safety_state(ext_regime)
        sleeve_snapshot = self._build_sleeve_portfolio_snapshot(ss, ext_regime_safety)

        report = self._campaign.finalize(
            ss,
            ext_regime=ext_regime,
            ext_regime_scenario=(
                None if self._external_regime_manager is None else self._external_regime_manager.latest_scenario_result
            ),
            sleeve_link=self._campaign_sleeve_link_summary(sleeve_snapshot),
        )
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
        ext_regime = self._external_regime_snapshot_from_status(ss)
        ext_regime_safety = self._build_external_regime_safety_state(ext_regime)
        sleeve_snapshot = self._build_sleeve_portfolio_snapshot(ss, ext_regime_safety)
        return self._campaign.snapshot(
            ss,
            ext_regime=ext_regime,
            ext_regime_scenario=(
                None if self._external_regime_manager is None else self._external_regime_manager.latest_scenario_result
            ),
            sleeve_link=self._campaign_sleeve_link_summary(sleeve_snapshot),
        )

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

    def escalation_review_active(self) -> bool:
        """Whether an escalation review is currently active (non-terminal)."""
        if self._escalation_review is None:
            return False
        return self._escalation_review.status not in (
            EscalationReviewStatus.FINALIZED,
            EscalationReviewStatus.FAILED,
            EscalationReviewStatus.REJECTED,
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

    def start_escalation_review(self, *, review_id: str | None = None) -> str:
        """Start a new escalation review workflow and evaluate current state."""
        if self.escalation_review_active():
            raise RuntimeError(
                f"Cannot start a new escalation review: active review "
                f"{self._escalation_review.review_id!r} in status "
                f"{self._escalation_review.status.value!r}"
            )

        history = () if self._escalation_review is None else self._escalation_review.history

        controller = EscalationReviewController(
            review_id=review_id,
            decision_builder=lambda: self._build_escalation_decision(self.decision_pack()),
            evidence_store=self._evidence_store,
            history=history,
        )
        controller.evaluate_current()
        self._escalation_review = controller
        logger.info("Escalation review %s started via orchestrator", self._escalation_review.review_id)
        return self._escalation_review.review_id

    def escalation_review_snapshot(self) -> CurrentEscalationReviewSnapshot | None:
        """Current escalation review snapshot, or None if no workflow exists."""
        if self._escalation_review is None:
            return None
        return self._escalation_review.current_snapshot()

    def finalize_escalation_review(self) -> FinalEscalationReviewReport:
        """Finalize the active escalation review and append bounded history."""
        self._require_escalation_review("finalize escalation review")
        report = self._escalation_review.finalize_review()
        logger.info(
            "Escalation review %s finalized via orchestrator (allowed_next_step=%s)",
            report.review_id,
            report.decision.escalation_stage.value,
        )
        return report

    def reset_escalation_review(self) -> None:
        """Reset the active escalation review while preserving finalized history."""
        if self._escalation_review is None:
            raise RuntimeError("No escalation review to reset")
        self._escalation_review.reset()

    def escalation_history(self) -> tuple[EscalationAttemptSummary, ...]:
        """Bounded finalized escalation review history."""
        if self._escalation_review is None:
            return ()
        return self._escalation_review.history

    def escalation_history_summary(self) -> dict:
        """Compact bounded escalation history summary."""
        if self._escalation_review is None:
            return {
                "total_finalized_reviews": 0,
                "latest_review_id": None,
                "latest_allowed_next_step": None,
                "current_allowed_next_step": None,
                "repeated_stuck_count": 0,
                "repeatedly_stuck": False,
            }
        return self._escalation_review.history_summary(self._current_escalation_decision_surface())

    def escalation_change_summary(self) -> dict:
        """Current-vs-previous escalation comparison summary."""
        if self._escalation_review is None:
            return {
                "available": False,
                "direction": "not_assessed",
                "changed": False,
                "previous_review_id": None,
                "previous_allowed_next_step": None,
                "current_allowed_next_step": None,
            }
        return self._escalation_review.compare_to_previous(self._current_escalation_decision_surface())

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

        # Escalation review workflow state
        escalation_review_state = self._build_escalation_workflow_state()

        # External regime snapshot
        ext_regime = self._external_regime_snapshot_from_status(ss)
        ext_regime_safety = self._build_external_regime_safety_state(ext_regime)
        ext_regime_scenario = self.external_regime_latest_scenario_result()
        sleeve_portfolio = self._build_sleeve_portfolio_snapshot(ss, ext_regime_safety)
        sleeve_candidate_workflow = self._build_sleeve_candidate_workflow_state()

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

        # Phase 15E: Add sleeve promotion review snapshot to operator surface
        sleeve_promotion_review = None
        if self._sleeve_promotion_review_controller is not None:
            sleeve_promotion_review = self._sleeve_promotion_review_controller.snapshot()

        review_portfolio_summary = (
            None if sleeve_promotion_review is None else sleeve_promotion_review.portfolio_summary
        )
        sleeve_admission = self.build_sleeve_admission_controller(
            portfolio_snapshot=sleeve_portfolio,
            review_portfolio_summary=review_portfolio_summary,
        ).snapshot()
        sleeve_admission_release = sleeve_admission_release_state_from_pack(
            build_admission_release_pack(
                sleeve_admission,
                promotion_review_snapshot=sleeve_promotion_review,
                candidate_workflow_snapshot=self.sleeve_candidate_workflow_snapshot(),
                portfolio_snapshot=sleeve_portfolio,
            )
        )
        return OperatorSnapshot(
            service_mode=ss.service_mode,
            trading_enabled=ss.trading_enabled,
            blocked_reason=ss.blocked_reason,
            ei_available=ei_available,
            ei_degraded=ei_degraded,
            ei_degraded_reasons=ei_degraded_reasons,
            campaign=campaign_state,
            review=review_state,
            escalation_review=escalation_review_state,
            sleeve_portfolio=sleeve_portfolio,
            sleeve_candidate_workflow=sleeve_candidate_workflow,
            sleeve_promotion_review=sleeve_promotion_review,
            sleeve_admission=sleeve_admission,
            sleeve_admission_release=sleeve_admission_release,
            readiness_level=self._readiness_level,
            readiness_is_supportive=readiness_is_supportive,
            evidence=evidence,
            provisional_recommendation=prov_verdict,
            recommendation_summary=prov_summary,
            external_regime=ext_regime,
            external_regime_safety=ext_regime_safety,
            external_regime_scenario=ext_regime_scenario,
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

    def decision_pack(self) -> OperatorDecisionPack:
        """Build a compact operator decision artifact from current review state."""
        if self._review is None or self._review.campaign_count == 0:
            raise RuntimeError("No promotion review evidence available for decision pack")

        operator_snapshot = self.operator_snapshot()
        review_snapshot = self._review.current_snapshot()
        final_report = self._review.final_report
        reason_codes = (
            final_report.reason_codes if final_report is not None else self._review.get_promotion_reason_summary()
        )
        missing_evidence = self._review.get_missing_evidence()

        review_timestamp_ns = (
            final_report.finalized_at_ns if final_report is not None else review_snapshot.updated_at_ns
        )
        promotion_verdict = final_report.verdict if final_report is not None else review_snapshot.provisional_verdict
        if promotion_verdict is None:
            raise RuntimeError("Promotion verdict unavailable for decision pack")

        readiness_status = self._decision_pack_readiness_status(review_timestamp_ns)
        readiness_dict = readiness_to_dict(readiness_status) if readiness_status is not None else None
        pass_criteria = tuple(reason_codes.get("pass_reasons", ()))
        warning_criteria = tuple(reason_codes.get("warning_reasons", ()))
        fail_criteria = tuple(reason_codes.get("fail_reasons", ()))
        insufficient_evidence = tuple(reason_codes.get("insufficient_reasons", ()))

        ext_regime_quality = (
            final_report.ext_regime_quality if final_report is not None else review_snapshot.ext_regime_quality
        )
        ext_regime_governance = (
            final_report.ext_regime_governance if final_report is not None else review_snapshot.ext_regime_governance
        ) or {}
        ext_regime_evidence_available = bool(
            ext_regime_governance.get("campaigns_with_ext_regime", 0) > 0
            or operator_snapshot.evidence.external_regime_available
        )
        ext_regime_evidence_sufficient = ext_regime_quality in {"supportive", "sufficient"}
        ext_regime_concerns = self._decision_pack_ext_regime_concerns(
            ext_regime_quality,
            ext_regime_governance,
            operator_snapshot,
        )
        disposition = operator_disposition_from_verdict(promotion_verdict)

        return OperatorDecisionPack(
            artifact_time_ns=review_timestamp_ns,
            review_id=self._review.review_id,
            review_timestamp_ns=review_timestamp_ns,
            review_status=self._review.status.value,
            promotion_verdict=promotion_verdict,
            operator_disposition=disposition,
            decision_summary=(
                final_report.summary if final_report is not None else review_snapshot.provisional_summary
            ),
            readiness_level=operator_snapshot.readiness_level,
            readiness_is_supportive=operator_snapshot.readiness_is_supportive,
            criteria_summary=self._decision_pack_criteria_summary(reason_codes, readiness_dict),
            pass_criteria=pass_criteria,
            warning_criteria=warning_criteria,
            fail_criteria=fail_criteria,
            insufficient_evidence=insufficient_evidence,
            insufficient_evidence_summary=self._decision_pack_missing_evidence_summary(
                operator_snapshot,
                missing_evidence,
                readiness_dict,
            ),
            readiness_criteria=(tuple(readiness_dict.get("criteria", ())) if readiness_dict is not None else ()),
            readiness_blockers=(tuple(readiness_dict.get("blockers", ())) if readiness_dict is not None else ()),
            external_regime_quality=ext_regime_quality,
            external_regime_evidence_available=ext_regime_evidence_available,
            external_regime_evidence_sufficient=ext_regime_evidence_sufficient,
            external_regime_concerns=ext_regime_concerns,
            external_regime_governance=ext_regime_governance,
            external_regime_summary=self._decision_pack_ext_regime_summary(
                ext_regime_quality,
                ext_regime_governance,
                ext_regime_concerns,
            ),
            campaign_coverage=self._decision_pack_campaign_coverage(review_snapshot, final_report),
            reason_codes=reason_codes,
            why_not_promotable=self._decision_pack_why_not_promotable(
                disposition,
                fail_criteria,
                warning_criteria,
                insufficient_evidence,
                tuple(readiness_dict.get("blockers", ())) if readiness_dict is not None else (),
                ext_regime_concerns,
            ),
            operator_next_inspection=self._decision_pack_operator_next_inspection(
                fail_criteria,
                warning_criteria,
                insufficient_evidence,
                tuple(readiness_dict.get("blockers", ())) if readiness_dict is not None else (),
                ext_regime_concerns,
                operator_snapshot,
                promotion_verdict,
            ),
            campaign_ids=(final_report.campaign_ids if final_report is not None else review_snapshot.campaign_ids),
        )

    def decision_pack_dict(self) -> dict:
        """Serialize the current operator decision pack to a plain dict."""
        return decision_pack_to_dict(self.decision_pack())

    def export_decision_pack(self):
        """Persist the current operator decision pack via EvidenceStore."""
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for decision pack export")
        return export_operator_decision_pack(
            pack=self.decision_pack(),
            evidence_store=self._evidence_store,
        )

    def load_decision_pack(self) -> OperatorDecisionPack:
        """Load the latest persisted operator decision pack."""
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for decision pack load")
        return load_operator_decision_pack(evidence_store=self._evidence_store)

    def escalation_decision(self) -> EscalationDecision:
        """Build a deterministic crypto paper-live escalation decision."""
        pack = self.decision_pack()
        return self._build_escalation_decision(pack)

    def escalation_decision_dict(self) -> dict:
        """Serialize the current escalation decision to a plain dict."""
        return escalation_decision_to_dict(self.escalation_decision())

    def export_escalation_decision(self):
        """Persist the current escalation decision via EvidenceStore."""
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for escalation decision export")
        return export_escalation_decision(
            decision=self.escalation_decision(),
            evidence_store=self._evidence_store,
        )

    def load_escalation_decision(self) -> EscalationDecision:
        """Load the latest persisted escalation decision."""
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for escalation decision load")
        return load_escalation_decision(evidence_store=self._evidence_store)

    def escalation_summary(self) -> dict:
        """Operator-facing escalation go/no-go summary."""
        return escalation_decision_summary(self._current_escalation_decision_surface())

    def escalation_blockers(self) -> dict:
        """Operator-facing blockers for escalation beyond the current gate."""
        return escalation_decision_blockers(self._current_escalation_decision_surface())

    def escalation_missing_evidence(self) -> dict:
        """Operator-facing escalation missing-evidence summary."""
        return escalation_decision_missing_evidence(self._current_escalation_decision_surface())

    def escalation_why_not_higher(self) -> dict:
        """Operator-facing explanation for why a higher gate is not allowed."""
        return escalation_decision_why_not_higher(self._current_escalation_decision_surface())

    def escalation_revalidation_required(self) -> dict:
        """Operator-facing checklist of what must be revalidated next."""
        return escalation_decision_revalidation(self._current_escalation_decision_surface())

    def decision_summary(self) -> dict:
        """Operator-facing summary of the current decision surface."""
        return decision_pack_decision_summary(self.decision_pack())

    def why_not_promotable_yet(self) -> dict:
        """Operator-facing explanation of what still blocks clean promotion."""
        return decision_pack_why_not_promotable(self.decision_pack())

    def decision_pack_missing_evidence(self) -> dict:
        """Operator-facing summary of evidence gaps in the current decision pack."""
        return decision_pack_missing_evidence(self.decision_pack())

    def decision_pack_next_inspection(self) -> dict:
        """Operator-facing ordered checklist of what to inspect next."""
        return decision_pack_next_inspection(self.decision_pack())

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
        if self._external_regime_manager is None:
            return None
        ss = self._service.status()
        return self._external_regime_manager.snapshot(self._external_regime_now_ns(ss))

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

    def update_options_regime(
        self,
        state,
        *,
        received_at_ns: int | None = None,
    ) -> ExternalRegimeUpdateRecord:
        """Apply one options-regime update via the managed service seam."""
        manager = self._require_external_regime_manager("update options regime")
        return manager.update_options(
            state,
            received_at_ns=self._resolved_external_regime_time(received_at_ns),
        )

    def update_event_regime(
        self,
        state,
        *,
        received_at_ns: int | None = None,
    ) -> ExternalRegimeUpdateRecord:
        """Apply one event-regime update via the managed service seam."""
        manager = self._require_external_regime_manager("update event regime")
        return manager.update_event(
            state,
            received_at_ns=self._resolved_external_regime_time(received_at_ns),
        )

    def update_on_chain_regime(
        self,
        state,
        *,
        received_at_ns: int | None = None,
    ) -> ExternalRegimeUpdateRecord:
        """Apply one on-chain-regime update via the managed service seam."""
        manager = self._require_external_regime_manager("update on-chain regime")
        return manager.update_on_chain(
            state,
            received_at_ns=self._resolved_external_regime_time(received_at_ns),
        )

    def update_external_regime(
        self,
        *,
        options=None,
        event=None,
        on_chain=None,
        received_at_ns: int | None = None,
    ) -> tuple[ExternalRegimeUpdateRecord, ...]:
        """Apply a deterministic multi-dimension regime update batch."""
        manager = self._require_external_regime_manager("update external regime")
        return manager.update_composite(
            options=options,
            event=event,
            on_chain=on_chain,
            received_at_ns=self._resolved_external_regime_time(received_at_ns),
        )

    def ingest_options_regime_payload(
        self,
        payload: object,
        *,
        provider: str,
        input_format: str = "dict",
        received_at_ns: int | None = None,
    ) -> ExternalRegimePayloadIngestionRecord:
        """Validate and ingest one raw options-regime payload."""
        manager = self._require_external_regime_manager("ingest options regime payload")
        return manager.ingest_options_payload(
            payload,
            provider=provider,
            input_format=input_format,
            received_at_ns=self._resolved_external_regime_time(received_at_ns),
        )

    def ingest_event_regime_payload(
        self,
        payload: object,
        *,
        provider: str,
        input_format: str = "dict",
        received_at_ns: int | None = None,
    ) -> ExternalRegimePayloadIngestionRecord:
        """Validate and ingest one raw event-regime payload."""
        manager = self._require_external_regime_manager("ingest event regime payload")
        return manager.ingest_event_payload(
            payload,
            provider=provider,
            input_format=input_format,
            received_at_ns=self._resolved_external_regime_time(received_at_ns),
        )

    def ingest_on_chain_regime_payload(
        self,
        payload: object,
        *,
        provider: str,
        input_format: str = "dict",
        received_at_ns: int | None = None,
    ) -> ExternalRegimePayloadIngestionRecord:
        """Validate and ingest one raw on-chain-regime payload."""
        manager = self._require_external_regime_manager("ingest on-chain regime payload")
        return manager.ingest_on_chain_payload(
            payload,
            provider=provider,
            input_format=input_format,
            received_at_ns=self._resolved_external_regime_time(received_at_ns),
        )

    def ingest_external_regime_payload(
        self,
        *,
        dimension: str,
        payload: object,
        provider: str,
        input_format: str = "dict",
        received_at_ns: int | None = None,
    ) -> ExternalRegimePayloadIngestionRecord:
        """Validate and ingest one raw external-regime payload by dimension."""
        manager = self._require_external_regime_manager("ingest external regime payload")
        return manager.ingest_payload(
            dimension=dimension,
            payload=payload,
            provider=provider,
            input_format=input_format,
            received_at_ns=self._resolved_external_regime_time(received_at_ns),
        )

    def ingest_external_regime_bundle(
        self,
        payload: object,
        *,
        provider: str,
        input_format: str = "dict",
        apply_mode: ExternalRegimeBundleApplyMode | str = ExternalRegimeBundleApplyMode.ATOMIC,
        received_at_ns: int | None = None,
    ) -> ExternalRegimeBundleIngestionRecord:
        """Validate and ingest one multi-dimension external-regime bundle."""
        manager = self._require_external_regime_manager("ingest external regime bundle")
        return manager.ingest_bundle_payload(
            payload,
            provider=provider,
            input_format=input_format,
            apply_mode=apply_mode,
            received_at_ns=self._resolved_external_regime_time(received_at_ns),
        )

    def ingest_external_regime_bundle_json(
        self,
        payload: str,
        *,
        provider: str,
        apply_mode: ExternalRegimeBundleApplyMode | str = ExternalRegimeBundleApplyMode.ATOMIC,
        received_at_ns: int | None = None,
    ) -> ExternalRegimeBundleIngestionRecord:
        """Validate and ingest one JSON external-regime bundle."""
        return self.ingest_external_regime_bundle(
            payload,
            provider=provider,
            input_format="json",
            apply_mode=apply_mode,
            received_at_ns=received_at_ns,
        )

    def ingest_external_regime_bundle_json_file(
        self,
        payload: object,
        *,
        provider: str,
        apply_mode: ExternalRegimeBundleApplyMode | str = ExternalRegimeBundleApplyMode.ATOMIC,
        received_at_ns: int | None = None,
    ) -> ExternalRegimeBundleIngestionRecord:
        """Validate and ingest one JSON-file external-regime bundle."""
        return self.ingest_external_regime_bundle(
            payload,
            provider=provider,
            input_format="json_file",
            apply_mode=apply_mode,
            received_at_ns=received_at_ns,
        )

    def external_regime_latest_update(self) -> ExternalRegimeUpdateRecord | None:
        """Most recent external regime update attempt."""
        if self._external_regime_manager is None:
            return None
        return self._external_regime_manager.latest_update

    def external_regime_update_history(self) -> tuple[ExternalRegimeUpdateRecord, ...]:
        """Bounded external regime update history, or empty tuple."""
        if self._external_regime_manager is None:
            return ()
        return self._external_regime_manager.recent_update_history()

    def external_regime_latest_bundle_result(self) -> ExternalRegimeBundleIngestionRecord | None:
        """Most recent external-regime bundle ingestion result."""
        if self._external_regime_manager is None:
            return None
        return self._external_regime_manager.latest_bundle_result

    def external_regime_latest_bundle_replay_artifact(self) -> ExternalRegimeBundleReplayArtifact | None:
        """Most recent replayable external-regime bundle artifact."""
        if self._external_regime_manager is None:
            return None
        return self._external_regime_manager.latest_bundle_replay_artifact

    def external_regime_latest_scenario_result(self) -> ExternalRegimeScenarioResult | None:
        """Most recent completed external-regime scenario result."""
        if self._external_regime_manager is None:
            return None
        return self._external_regime_manager.latest_scenario_result

    def external_regime_lifecycle_dict(self) -> dict | None:
        """Full external regime lifecycle view for operators/reporting."""
        if self._external_regime_manager is None:
            return None
        ss = self._service.status()
        return self._external_regime_manager.status_dict(self._external_regime_now_ns(ss))

    def restore_external_regime(self) -> bool:
        """Restore external regime state from persistence, if present."""
        manager = self._require_external_regime_manager("restore external regime")
        return manager.restore_state()

    def replay_external_regime_bundle_artifact(
        self,
        artifact: ExternalRegimeBundleReplayArtifact,
    ) -> ExternalRegimeBundleIngestionRecord:
        """Replay a previously captured external-regime bundle artifact."""
        manager = self._require_external_regime_manager("replay external regime bundle artifact")
        return manager.replay_bundle_artifact(artifact)

    def run_external_regime_scenario(
        self,
        scenario: ExternalRegimeScenario,
    ) -> ExternalRegimeScenarioResult:
        """Replay a deterministic external-regime scenario through the service seam."""
        manager = self._require_external_regime_manager("run external regime scenario")
        return manager.run_scenario(scenario, policy=self._external_regime_policy)

    def reset_external_regime(
        self,
        *,
        reason: str = "operator_reset",
        source_label: str = "operator_reset",
        received_at_ns: int | None = None,
    ) -> ExternalRegimeUpdateRecord:
        """Explicitly clear all external regime state."""
        manager = self._require_external_regime_manager("reset external regime")
        return manager.reset(
            received_at_ns=self._resolved_external_regime_time(received_at_ns),
            reason=reason,
            source_label=source_label,
        )

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

    def restore_escalation_review(self) -> bool:
        """Attempt to restore escalation workflow from evidence store."""
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for restore")

        if self._escalation_review is not None and self.escalation_review_active():
            raise RuntimeError("Cannot restore: active escalation review in progress")

        try:
            controller = EscalationReviewController.restore(
                self._evidence_store,
                decision_builder=lambda: self._build_escalation_decision(self.decision_pack()),
            )
        except (EscalationWorkflowCorruptError, RuntimeError):
            raise
        except Exception:
            return False

        self._escalation_review = controller
        logger.info(
            "Escalation review %s restored via orchestrator (status=%s, history=%d)",
            controller.review_id,
            controller.status.value,
            len(controller.history),
        )
        return True

    def _external_regime_snapshot_from_status(
        self,
        ss: ServiceStatus,
    ) -> ExternalRegimeSnapshot | None:
        if self._external_regime_manager is None:
            return None
        return self._external_regime_manager.snapshot(self._external_regime_now_ns(ss))

    @staticmethod
    def _external_regime_now_ns(ss: ServiceStatus) -> int:
        if ss.watchdog is None:
            return 0
        return ss.watchdog.last_event_time_ns

    def _resolved_external_regime_time(self, received_at_ns: int | None) -> int:
        if received_at_ns is not None:
            return received_at_ns
        ss = self._service.status()
        return self._external_regime_now_ns(ss)

    def _require_external_regime_manager(self, action: str) -> ExternalRegimeManager:
        if self._external_regime_manager is None:
            raise RuntimeError(f"No external regime manager configured to {action}")
        return self._external_regime_manager

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

    def _require_escalation_review(self, operation: str) -> None:
        """Validate that an active escalation review exists."""
        if self._escalation_review is None:
            raise RuntimeError(f"No escalation review to {operation}")
        if not self.escalation_review_active():
            raise RuntimeError(
                f"Cannot {operation}: escalation review {self._escalation_review.review_id!r} "
                f"in terminal status {self._escalation_review.status.value!r}"
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

    def _build_escalation_workflow_state(self) -> EscalationWorkflowState | None:
        """Build escalation review workflow state summary."""
        if self._escalation_review is None:
            return None

        snap = self._escalation_review.current_snapshot()
        comparison = snap.comparison_to_previous or {}
        allowed_next_step = None
        if snap.latest_decision is not None:
            allowed_next_step = snap.latest_decision.escalation_stage.value
        return EscalationWorkflowState(
            active=self.escalation_review_active(),
            review_id=self._escalation_review.review_id,
            status=self._escalation_review.status.value,
            allowed_next_step=allowed_next_step,
            progression_state=snap.progression_state,
            previous_allowed_next_step=comparison.get("previous_allowed_next_step"),
            history_length=len(self._escalation_review.history),
            repeatedly_stuck=bool(snap.history_summary.get("repeatedly_stuck", False)),
            finalized=self._escalation_review.is_finalized,
        )

    def _build_sleeve_candidate_workflow_state(self) -> SleeveCandidateWorkflowState | None:
        """Build sleeve candidate workflow state summary."""
        controller = self._sleeve_candidate_workflow_controller
        if controller is None:
            return None

        snapshot = controller.current_snapshot
        comparison = {} if snapshot is None else snapshot.comparison_to_previous
        history_summary = controller.history_summary(snapshot)
        return SleeveCandidateWorkflowState(
            active=controller.status == SleeveCandidateWorkflowStatus.ACTIVE,
            workflow_id=controller.workflow_id,
            status=controller.status.value,
            candidate_sleeves=0 if snapshot is None else len(snapshot.candidate_sleeve_ids),
            supported_candidate_sleeves=0 if snapshot is None else len(snapshot.supported_candidate_sleeve_ids),
            weak_candidate_sleeves=0 if snapshot is None else len(snapshot.weak_candidate_sleeve_ids),
            blocked_candidate_sleeves=0 if snapshot is None else len(snapshot.blocked_candidate_sleeve_ids),
            inconclusive_candidate_sleeves=0 if snapshot is None else len(snapshot.inconclusive_candidate_sleeve_ids),
            progression_state=comparison.get("progression_state", "not_assessed"),
            previous_as_of_ns=comparison.get("previous_as_of_ns"),
            history_length=len(controller.history),
            repeatedly_weak=bool(history_summary.get("repeated_weak_sleeve_ids")),
            repeatedly_blocked=bool(history_summary.get("repeated_blocked_sleeve_ids")),
            repeatedly_inconclusive=bool(history_summary.get("repeated_inconclusive_sleeve_ids")),
            finalized=controller.status == SleeveCandidateWorkflowStatus.FINALIZED,
        )

    def _build_sleeve_portfolio_snapshot(
        self,
        ss: ServiceStatus,
        ext_regime_safety: ExternalRegimeSafetyState | None,
    ) -> SleevePortfolioSnapshot:
        """Build the additive crypto sleeve portfolio surface."""

        def _safe_int(value: object) -> int:
            return value if isinstance(value, int) and value >= 0 else 0

        runtime_status = ss.runtime_status
        session_status = getattr(runtime_status, "session_status", None)
        if session_status is None:
            session_status = getattr(runtime_status, "session", None)

        current_cycle_time_ns = _safe_int(getattr(session_status, "current_cycle_time_ns", 0)) if session_status else 0
        start_time_ns = _safe_int(getattr(session_status, "start_time_ns", 0)) if session_status else 0
        if start_time_ns == 0 and session_status is not None:
            start_time_ns = _safe_int(getattr(session_status, "started_at_ns", 0))

        as_of_ns = current_cycle_time_ns or start_time_ns or 0
        readiness_is_supportive = self._readiness_level in (
            "paper_live",
            "calibrated_paper",
            "shadow_live",
            "tiny_cap_live",
        )
        if self._sleeve_portfolio_controller is not None:
            return self._sleeve_portfolio_controller.current_snapshot(
                as_of_ns=as_of_ns,
                campaign_report=self._last_campaign_report,
                readiness_level=self._readiness_level,
                readiness_is_supportive=readiness_is_supportive,
                escalation_allowed_next_step=self._current_escalation_allowed_next_step(),
                external_regime_execution_blocked=(
                    None if ext_regime_safety is None else ext_regime_safety.execution_blocked
                ),
            )
        return build_sleeve_portfolio_snapshot(
            sleeves=self._configured_sleeves,
            as_of_ns=as_of_ns,
            campaign_report=self._last_campaign_report,
            readiness_level=self._readiness_level,
            readiness_is_supportive=readiness_is_supportive,
            escalation_allowed_next_step=self._current_escalation_allowed_next_step(),
            external_regime_execution_blocked=(
                None if ext_regime_safety is None else ext_regime_safety.execution_blocked
            ),
            allocation_policy=self._sleeve_allocation_policy,
        )

    @staticmethod
    def _campaign_sleeve_link_summary(snapshot: SleevePortfolioSnapshot) -> CampaignSleeveLinkSummary:
        configured_ids = tuple(sleeve.sleeve_id for sleeve in snapshot.sleeves)
        qualified_ids = snapshot.qualification.qualified_sleeve_ids
        recommended_ids = snapshot.decision.recommended_sleeve_ids
        blocked_ids = snapshot.blocked_sleeve_ids
        return CampaignSleeveLinkSummary(
            linkage_available=bool(snapshot.sleeves),
            configured_sleeve_ids=configured_ids,
            qualified_sleeve_ids=qualified_ids,
            recommended_sleeve_ids=recommended_ids,
            blocked_sleeve_ids=blocked_ids,
            summary=snapshot.summary,
        )

    def _ensure_sleeve_portfolio_controller(self) -> SleevePortfolioController:
        if self._sleeve_portfolio_controller is None:
            self._sleeve_portfolio_controller = SleevePortfolioController(
                defined_sleeves=self._configured_sleeves,
                allocation_policy=self._sleeve_allocation_policy,
                evidence_store=self._evidence_store,
                clock_ns=self._sleeve_workflow_clock_ns,
            )
        return self._sleeve_portfolio_controller

    def _ensure_sleeve_candidate_workflow_controller(self) -> SleeveCandidateWorkflowController:
        if self._sleeve_candidate_workflow_controller is None:
            self._sleeve_candidate_workflow_controller = SleeveCandidateWorkflowController(
                evidence_store=self._evidence_store,
                clock_ns=self._sleeve_workflow_clock_ns,
            )
        return self._sleeve_candidate_workflow_controller

    def _current_escalation_allowed_next_step(self) -> str | None:
        """Best current escalation hook for sleeve governance surfaces."""
        if self._escalation_review is not None:
            latest = self._escalation_review.latest_decision()
            if latest is not None:
                return latest.escalation_stage.value
        if self._review is None or self._review.campaign_count == 0:
            return None
        try:
            return self._build_escalation_decision(self.decision_pack()).escalation_stage.value
        except RuntimeError:
            return None

    def _current_escalation_decision_surface(self) -> EscalationDecision:
        """Current escalation decision surface, favoring workflow state when present."""
        if self._escalation_review is not None:
            latest = self._escalation_review.latest_decision()
            if latest is not None:
                return latest
        return self._build_escalation_decision(self.decision_pack())

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
        latest_scenario = self.external_regime_latest_scenario_result()

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
        if latest_scenario is not None:
            if latest_scenario.execution_blocked_steps or latest_scenario.activation_blocked_steps:
                parts.append(
                    "External regime scenario gating observed: "
                    f"execution_blocked={latest_scenario.execution_blocked_steps}, "
                    f"activation_blocked={latest_scenario.activation_blocked_steps}."
                )
            if latest_scenario.activation_reduced_steps:
                parts.append(
                    f"External regime scenario reduced activation on {latest_scenario.activation_reduced_steps} step(s)."
                )
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
            external_regime_scenario_available=latest_scenario is not None,
            external_regime_execution_blocked_steps=(
                0 if latest_scenario is None else latest_scenario.execution_blocked_steps
            ),
            external_regime_activation_blocked_steps=(
                0 if latest_scenario is None else latest_scenario.activation_blocked_steps
            ),
            external_regime_activation_reduced_steps=(
                0 if latest_scenario is None else latest_scenario.activation_reduced_steps
            ),
            external_regime_scenario_summary=("" if latest_scenario is None else latest_scenario.summary),
        )

    def _build_external_regime_safety_state(
        self,
        ext_regime: ExternalRegimeSnapshot | None,
    ) -> ExternalRegimeSafetyState | None:
        """Build current external regime safety posture for operator surfacing."""
        if ext_regime is None:
            return None

        activation = evaluate_external_regime_activation_safety(
            ext_regime,
            self._external_regime_policy,
        )
        execution = evaluate_external_regime_execution_safety(
            ext_regime,
            self._external_regime_policy,
        )
        return ExternalRegimeSafetyState(
            activation_blocked=activation.blocked,
            activation_reason=activation.reason,
            activation_allocation_scale=activation.allocation_scale,
            execution_blocked=execution.blocked,
            execution_reason=execution.reason,
            evidence={
                "activation": activation.evidence,
                "execution": execution.evidence,
            },
        )

    def _decision_pack_readiness_status(self, assessed_at_ns: int):
        source_report = self._last_campaign_report
        if source_report is None:
            return None
        evaluator = ReadinessEvaluator()
        return evaluator.evaluate(
            campaign_readiness_flags(source_report),
            assessed_at_ns=assessed_at_ns,
        )

    @staticmethod
    def _decision_pack_criteria_summary(reason_codes: dict, readiness_dict: dict | None) -> dict:
        promotion_summary = {
            "pass_count": int(reason_codes.get("pass_count", 0)),
            "warning_count": int(reason_codes.get("warning_count", 0)),
            "fail_count": int(reason_codes.get("fail_count", 0)),
            "insufficient_count": int(reason_codes.get("insufficient_count", 0)),
        }
        if readiness_dict is None:
            readiness_summary = {
                "available": False,
                "level": "not_assessed",
                "met": 0,
                "not_met": 0,
                "unknown": 0,
                "total": 0,
                "blocker_count": 0,
            }
        else:
            readiness_summary = {
                "available": True,
                "level": readiness_dict.get("level", "not_assessed"),
                **readiness_dict.get("summary", {}),
                "blocker_count": len(readiness_dict.get("blockers", ())),
            }
        return {
            "promotion": promotion_summary,
            "readiness": readiness_summary,
        }

    @staticmethod
    def _decision_pack_missing_evidence_summary(
        operator_snapshot: OperatorSnapshot,
        missing_evidence: dict,
        readiness_dict: dict | None,
    ) -> dict:
        return {
            "campaign_evidence_available": operator_snapshot.evidence.campaign_evidence_available,
            "review_evidence_available": operator_snapshot.evidence.review_evidence_available,
            "execution_calibration_available": operator_snapshot.evidence.execution_calibration_available,
            "promotion_evidence_sufficient": operator_snapshot.evidence.promotion_evidence_sufficient,
            "review_insufficient_criteria": list(missing_evidence.get("insufficient_criteria", ())),
            "review_warning_criteria": list(missing_evidence.get("warning_criteria", ())),
            "review_fail_criteria": list(missing_evidence.get("fail_criteria", ())),
            "readiness_blockers": ([] if readiness_dict is None else list(readiness_dict.get("blockers", ()))),
            "summary": operator_snapshot.evidence.summary or missing_evidence.get("message", ""),
        }

    @staticmethod
    def _decision_pack_campaign_coverage(
        review_snapshot: CurrentReviewSnapshot,
        final_report: FinalReviewReport | None,
    ) -> dict:
        if final_report is not None:
            return {
                "campaign_count": final_report.campaign_count,
                "campaign_ids": list(final_report.campaign_ids),
                "execution_calibration_quality": final_report.execution_calibration_quality,
                **final_report.coverage_stability_breadth,
            }
        return {
            "campaign_count": review_snapshot.campaign_count,
            "campaign_ids": list(review_snapshot.campaign_ids),
            "verdict_distribution": review_snapshot.verdict_distribution,
            "execution_sufficiency": review_snapshot.execution_sufficiency,
            "symbol_breadth": review_snapshot.symbol_breadth,
        }

    @staticmethod
    def _decision_pack_ext_regime_concerns(
        ext_regime_quality: str,
        ext_regime_governance: dict,
        operator_snapshot: OperatorSnapshot,
    ) -> tuple[str, ...]:
        concerns: list[str] = []
        if not operator_snapshot.evidence.external_regime_available:
            concerns.append("evidence_unavailable")
        elif not operator_snapshot.evidence.external_regime_fresh:
            concerns.append("evidence_insufficient")
        if ext_regime_governance.get("campaigns_ext_regime_stale_dominated", 0) > 0:
            concerns.append("stale_dominance")
        if ext_regime_governance.get("campaigns_ext_regime_unavailable_dominated", 0) > 0:
            concerns.append("unavailable_dominance")
        if ext_regime_governance.get("campaigns_ext_regime_high_risk_dominated", 0) > 0:
            concerns.append("high_risk_dominance")
        if ext_regime_governance.get("campaigns_ext_regime_gating_impacted", 0) > 0:
            concerns.append("gating_impact")
        if ext_regime_quality in {"blocking", "insufficient", "unavailable", "marginal", "cautionary"}:
            concerns.append(f"quality:{ext_regime_quality}")

        ordered: list[str] = []
        for concern in concerns:
            if concern not in ordered:
                ordered.append(concern)
        return tuple(ordered)

    @staticmethod
    def _decision_pack_ext_regime_summary(
        ext_regime_quality: str,
        ext_regime_governance: dict,
        concerns: tuple[str, ...],
    ) -> str:
        if not ext_regime_governance:
            return "No external regime governance evidence available."

        parts = [f"quality={ext_regime_quality}"]
        meaningful = ext_regime_governance.get("campaigns_with_meaningful_ext_regime_scenario", 0)
        campaigns = ext_regime_governance.get("campaigns_with_ext_regime_scenario", 0)
        parts.append(f"meaningful_scenarios={meaningful}/{campaigns}")
        if ext_regime_governance.get("campaigns_ext_regime_stale_dominated", 0) > 0:
            parts.append(f"stale_dominated={ext_regime_governance['campaigns_ext_regime_stale_dominated']}")
        if ext_regime_governance.get("campaigns_ext_regime_unavailable_dominated", 0) > 0:
            parts.append(f"unavailable_dominated={ext_regime_governance['campaigns_ext_regime_unavailable_dominated']}")
        if ext_regime_governance.get("campaigns_ext_regime_high_risk_dominated", 0) > 0:
            parts.append(f"high_risk_dominated={ext_regime_governance['campaigns_ext_regime_high_risk_dominated']}")
        if ext_regime_governance.get("campaigns_ext_regime_gating_impacted", 0) > 0:
            parts.append(f"gating_impacted={ext_regime_governance['campaigns_ext_regime_gating_impacted']}")
        if concerns:
            parts.append(f"concerns={','.join(concerns)}")
        return "; ".join(parts)

    @staticmethod
    def _decision_pack_why_not_promotable(
        disposition: str,
        fail_criteria: tuple[str, ...],
        warning_criteria: tuple[str, ...],
        insufficient_evidence: tuple[str, ...],
        readiness_blockers: tuple[str, ...],
        ext_regime_concerns: tuple[str, ...],
    ) -> tuple[str, ...]:
        if disposition == "promotable":
            return ()
        reasons: list[str] = []
        reasons.extend(fail_criteria)
        reasons.extend(insufficient_evidence)
        reasons.extend(warning_criteria)
        reasons.extend(f"readiness:{name}" for name in readiness_blockers)
        reasons.extend(f"external_regime:{name}" for name in ext_regime_concerns)

        ordered: list[str] = []
        for reason in reasons:
            if reason not in ordered:
                ordered.append(reason)
        return tuple(ordered)

    @staticmethod
    def _decision_pack_operator_next_inspection(
        fail_criteria: tuple[str, ...],
        warning_criteria: tuple[str, ...],
        insufficient_evidence: tuple[str, ...],
        readiness_blockers: tuple[str, ...],
        ext_regime_concerns: tuple[str, ...],
        operator_snapshot: OperatorSnapshot,
        promotion_verdict: str,
    ) -> tuple[str, ...]:
        items: list[str] = []
        if fail_criteria:
            items.append("failed_criteria")
        if insufficient_evidence:
            items.append("insufficient_evidence")
        if warning_criteria:
            items.append("warning_criteria")
        if readiness_blockers:
            items.append("readiness_blockers")
        if ext_regime_concerns:
            items.append("external_regime_governance")
        if not operator_snapshot.evidence.execution_calibration_available:
            items.append("execution_calibration")
        if promotion_verdict == "promote" and not items:
            items.append("promotion_ready_review")
        return tuple(items)

    def _build_escalation_decision(self, pack: OperatorDecisionPack) -> EscalationDecision:
        stage = self._escalation_stage_for_pack(pack)
        blocking_reasons = self._escalation_blocking_reasons(pack, stage)
        why_not_higher = self._escalation_why_not_higher(pack, stage)
        revalidation_required = self._escalation_revalidation_required(pack, stage)
        return EscalationDecision(
            artifact_time_ns=pack.artifact_time_ns,
            review_id=pack.review_id,
            review_timestamp_ns=pack.review_timestamp_ns,
            review_status=pack.review_status,
            promotion_verdict=pack.promotion_verdict,
            operator_disposition=pack.operator_disposition,
            escalation_stage=stage,
            decision_summary=self._escalation_summary_text(pack, stage),
            readiness_level=pack.readiness_level,
            readiness_is_supportive=pack.readiness_is_supportive,
            external_regime_quality=pack.external_regime_quality,
            blocking_reasons=blocking_reasons,
            missing_evidence=pack.insufficient_evidence,
            why_not_higher=why_not_higher,
            revalidation_required=revalidation_required,
            campaign_ids=pack.campaign_ids,
            reason_codes=pack.reason_codes,
        )

    def _escalation_stage_for_pack(self, pack: OperatorDecisionPack) -> EscalationStage:
        if pack.promotion_verdict == "reject" or (pack.fail_criteria and not pack.insufficient_evidence):
            return EscalationStage.REJECT
        if pack.promotion_verdict == "inconclusive" or pack.insufficient_evidence:
            return EscalationStage.INCONCLUSIVE
        if pack.promotion_verdict == "hold" or pack.warning_criteria:
            return EscalationStage.HOLD
        if pack.promotion_verdict != "promote":
            return EscalationStage.INCONCLUSIVE

        stage = self._target_escalation_stage(pack.readiness_level, pack.readiness_is_supportive)
        if pack.external_regime_quality in {"blocking", "insufficient", "unavailable", "marginal", "cautionary"}:
            stage = self._downgrade_escalation_stage(stage)
        return stage

    @staticmethod
    def _target_escalation_stage(readiness_level: str, readiness_is_supportive: bool) -> EscalationStage:
        if not readiness_is_supportive:
            return EscalationStage.PAPER_ONLY
        if readiness_level == "tiny_cap_live":
            return EscalationStage.TINY_CAP_LIVE_REVIEW_ELIGIBLE
        if readiness_level == "shadow_live":
            return EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE
        if readiness_level == "calibrated_paper":
            return EscalationStage.CALIBRATED_PAPER
        return EscalationStage.PAPER_ONLY

    @staticmethod
    def _downgrade_escalation_stage(stage: EscalationStage) -> EscalationStage:
        return {
            EscalationStage.TINY_CAP_LIVE_REVIEW_ELIGIBLE: EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE,
            EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE: EscalationStage.CALIBRATED_PAPER,
            EscalationStage.CALIBRATED_PAPER: EscalationStage.PAPER_ONLY,
            EscalationStage.PAPER_ONLY: EscalationStage.PAPER_ONLY,
            EscalationStage.HOLD: EscalationStage.HOLD,
            EscalationStage.REJECT: EscalationStage.REJECT,
            EscalationStage.INCONCLUSIVE: EscalationStage.INCONCLUSIVE,
        }[stage]

    @staticmethod
    def _escalation_summary_text(pack: OperatorDecisionPack, stage: EscalationStage) -> str:
        return f"allowed_next_step={stage.value}; promotion_verdict={pack.promotion_verdict}; summary={pack.decision_summary}"

    @staticmethod
    def _escalation_blocking_reasons(
        pack: OperatorDecisionPack,
        stage: EscalationStage,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if stage in {EscalationStage.REJECT, EscalationStage.HOLD, EscalationStage.INCONCLUSIVE}:
            reasons.extend(pack.why_not_promotable)
        if stage in {EscalationStage.PAPER_ONLY, EscalationStage.CALIBRATED_PAPER}:
            reasons.extend(pack.readiness_blockers)
            reasons.extend(pack.external_regime_concerns)
        return ServiceOrchestrator._ordered_unique(reasons)

    def _escalation_why_not_higher(
        self,
        pack: OperatorDecisionPack,
        stage: EscalationStage,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if stage == EscalationStage.REJECT:
            reasons.extend(pack.fail_criteria)
        elif stage == EscalationStage.INCONCLUSIVE:
            reasons.extend(pack.insufficient_evidence)
        elif stage == EscalationStage.HOLD:
            reasons.extend(pack.warning_criteria)
        elif stage == EscalationStage.PAPER_ONLY:
            if pack.readiness_level != "calibrated_paper":
                reasons.append(f"readiness_level:{pack.readiness_level}")
            reasons.extend(pack.readiness_blockers)
            reasons.extend(f"external_regime:{item}" for item in pack.external_regime_concerns)
        elif stage == EscalationStage.CALIBRATED_PAPER:
            if pack.readiness_level != "shadow_live":
                reasons.append(f"readiness_level:{pack.readiness_level}")
            reasons.extend(f"external_regime:{item}" for item in pack.external_regime_concerns)
        elif stage == EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE:
            if pack.readiness_level != "tiny_cap_live":
                reasons.append(f"readiness_level:{pack.readiness_level}")
            reasons.extend(f"external_regime:{item}" for item in pack.external_regime_concerns)
        return self._ordered_unique(reasons)

    @staticmethod
    def _escalation_revalidation_required(
        pack: OperatorDecisionPack,
        stage: EscalationStage,
    ) -> tuple[str, ...]:
        items: list[str] = []
        if stage == EscalationStage.INCONCLUSIVE:
            items.append("insufficient_evidence")
        if stage == EscalationStage.HOLD:
            items.append("warning_criteria")
        if pack.readiness_blockers:
            items.append("readiness_blockers")
        if pack.external_regime_concerns:
            items.append("external_regime_governance")
        if not pack.external_regime_evidence_sufficient:
            items.append("external_regime_evidence")
        if not pack.criteria_summary.get("readiness", {}).get("available", False):
            items.append("readiness_assessment")
        if pack.reason_codes.get("fail_count", 0) > 0:
            items.append("failed_criteria")
        if stage in {
            EscalationStage.CALIBRATED_PAPER,
            EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE,
            EscalationStage.TINY_CAP_LIVE_REVIEW_ELIGIBLE,
        }:
            items.append("operator_review_signoff")
        return ServiceOrchestrator._ordered_unique(items)

    @staticmethod
    def _ordered_unique(items: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        ordered: list[str] = []
        for item in items:
            if item and item not in ordered:
                ordered.append(item)
        return tuple(ordered)


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


def escalation_workflow_state_to_dict(state: EscalationWorkflowState) -> dict:
    """Serialize EscalationWorkflowState to a plain dict."""
    return {
        "active": state.active,
        "review_id": state.review_id,
        "status": state.status,
        "allowed_next_step": state.allowed_next_step,
        "progression_state": state.progression_state,
        "previous_allowed_next_step": state.previous_allowed_next_step,
        "history_length": state.history_length,
        "repeatedly_stuck": state.repeatedly_stuck,
        "finalized": state.finalized,
    }


def sleeve_candidate_workflow_state_to_dict(state: SleeveCandidateWorkflowState) -> dict:
    """Serialize SleeveCandidateWorkflowState to a plain dict."""
    return {
        "active": state.active,
        "workflow_id": state.workflow_id,
        "status": state.status,
        "candidate_sleeves": state.candidate_sleeves,
        "supported_candidate_sleeves": state.supported_candidate_sleeves,
        "weak_candidate_sleeves": state.weak_candidate_sleeves,
        "blocked_candidate_sleeves": state.blocked_candidate_sleeves,
        "inconclusive_candidate_sleeves": state.inconclusive_candidate_sleeves,
        "progression_state": state.progression_state,
        "previous_as_of_ns": state.previous_as_of_ns,
        "history_length": state.history_length,
        "repeatedly_weak": state.repeatedly_weak,
        "repeatedly_blocked": state.repeatedly_blocked,
        "repeatedly_inconclusive": state.repeatedly_inconclusive,
        "finalized": state.finalized,
    }


def sleeve_admission_release_state_from_pack(pack: SleeveAdmissionReleasePack) -> SleeveAdmissionReleaseState:
    """Build compact operator snapshot state from a sleeve admission release pack."""
    return SleeveAdmissionReleaseState(
        available=True,
        pack_id=pack.pack_id,
        as_of_ns=pack.as_of_ns,
        overall_release_status=pack.overall_release_status.value,
        admitted_sleeves=len(pack.admitted_sleeves),
        admitted_active_sleeves=len(pack.admitted_active_sleeves),
        admitted_unallocated_sleeves=len(pack.admitted_unallocated_sleeves),
        review_supported_not_admitted_sleeves=len(pack.review_supported_not_admitted_sleeves),
        blocked_sleeves=len(pack.blocked_sleeves),
        inconclusive_sleeves=len(pack.inconclusive_sleeves),
        insufficient_evidence_sleeves=len(pack.insufficient_evidence_sleeves),
        disabled_operator_off_sleeves=len(pack.disabled_operator_off_sleeves),
        evidence_blockers=pack.evidence_blockers,
        governance_blockers=pack.governance_blockers,
    )


def sleeve_admission_release_state_to_dict(state: SleeveAdmissionReleaseState) -> dict:
    """Serialize compact sleeve admission release-pack state to a plain dict."""
    return {
        "available": state.available,
        "pack_id": state.pack_id,
        "as_of_ns": state.as_of_ns,
        "overall_release_status": state.overall_release_status,
        "admitted_sleeves": state.admitted_sleeves,
        "admitted_active_sleeves": state.admitted_active_sleeves,
        "admitted_unallocated_sleeves": state.admitted_unallocated_sleeves,
        "review_supported_not_admitted_sleeves": state.review_supported_not_admitted_sleeves,
        "blocked_sleeves": state.blocked_sleeves,
        "inconclusive_sleeves": state.inconclusive_sleeves,
        "insufficient_evidence_sleeves": state.insufficient_evidence_sleeves,
        "disabled_operator_off_sleeves": state.disabled_operator_off_sleeves,
        "evidence_blockers": list(state.evidence_blockers),
        "governance_blockers": list(state.governance_blockers),
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
        "external_regime_scenario_available": state.external_regime_scenario_available,
        "external_regime_execution_blocked_steps": state.external_regime_execution_blocked_steps,
        "external_regime_activation_blocked_steps": state.external_regime_activation_blocked_steps,
        "external_regime_activation_reduced_steps": state.external_regime_activation_reduced_steps,
        "external_regime_scenario_summary": state.external_regime_scenario_summary,
    }


def external_regime_safety_state_to_dict(state: ExternalRegimeSafetyState) -> dict:
    """Serialize ExternalRegimeSafetyState to a plain dict."""
    return {
        "activation_blocked": state.activation_blocked,
        "activation_reason": state.activation_reason,
        "activation_allocation_scale": state.activation_allocation_scale,
        "execution_blocked": state.execution_blocked,
        "execution_reason": state.execution_reason,
        "evidence": state.evidence,
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
        "sleeve_portfolio": (
            sleeve_portfolio_snapshot_to_dict(snap.sleeve_portfolio) if snap.sleeve_portfolio is not None else None
        ),
        "sleeve_candidate_workflow": (
            sleeve_candidate_workflow_state_to_dict(snap.sleeve_candidate_workflow)
            if snap.sleeve_candidate_workflow is not None
            else None
        ),
        "escalation_review": (
            escalation_workflow_state_to_dict(snap.escalation_review) if snap.escalation_review is not None else None
        ),
        # Phase 15E
        "sleeve_promotion_review": (
            sleeve_promotion_review_snapshot_to_dict(snap.sleeve_promotion_review)
            if snap.sleeve_promotion_review is not None
            else None
        ),
        # Phase 15F
        "sleeve_admission": (
            sleeve_admission_snapshot_to_dict(snap.sleeve_admission) if snap.sleeve_admission is not None else None
        ),
        # Phase 15I
        "sleeve_admission_release": (
            sleeve_admission_release_state_to_dict(snap.sleeve_admission_release)
            if snap.sleeve_admission_release is not None
            else None
        ),
        "readiness_level": snap.readiness_level,
        "readiness_is_supportive": snap.readiness_is_supportive,
        "evidence": evidence_sufficiency_state_to_dict(snap.evidence),
        "provisional_recommendation": snap.provisional_recommendation,
        "recommendation_summary": snap.recommendation_summary,
        "external_regime": (
            _external_regime_snap_to_dict(snap.external_regime) if snap.external_regime is not None else None
        ),
        "external_regime_safety": (
            external_regime_safety_state_to_dict(snap.external_regime_safety)
            if snap.external_regime_safety is not None
            else None
        ),
        "external_regime_scenario": (
            external_regime_scenario_result_to_dict(snap.external_regime_scenario)
            if snap.external_regime_scenario is not None
            else None
        ),
    }


def _external_regime_snap_to_dict(snap: ExternalRegimeSnapshot) -> dict:
    """Serialize ExternalRegimeSnapshot via the external_regime module."""
    from crypto_core.service.external_regime import external_regime_snapshot_to_dict

    return external_regime_snapshot_to_dict(snap)
