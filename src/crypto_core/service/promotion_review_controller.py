"""Promotion review controller — Phase 10C.

Operational lifecycle controller that integrates completed campaigns into
the promotion review workflow.

Provides:
  1. ReviewStatus — deterministic review lifecycle states.
  2. CurrentReviewSnapshot — point-in-time review state for operators.
  3. FinalReviewReport — final promotion review report with full evidence.
  4. CampaignIntakeError — raised on invalid campaign intake.
  5. ReviewWorkflowCorruptError — raised on malformed persisted workflow state.
  6. PromotionReviewController — first-class review lifecycle manager.

Design rules:
  - Fail-closed: invalid intake → raise, never silently count.
  - Deterministic: same campaign set → same review result.
  - Duplicate campaigns rejected deterministically.
  - Review status is explicit and auditable.
  - Reuses promotion_review.py primitives for all evaluation logic.
  - No single lucky campaign can trigger promotion.
  - PAPER-ONLY.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from crypto_core.service.campaign import CampaignReport
from crypto_core.service.evidence_store import EvidenceStore, EvidenceStoreCorruptError, WriteResult
from crypto_core.service.promotion_review import (
    CampaignAggregation,
    PromotionPolicy,
    PromotionResult,
    PromotionReviewStore,
    PromotionThresholds,
    PromotionVerdict,
    build_campaign_aggregation,
    build_promotion_review,
    classify_ext_regime_governance,
    execution_sufficiency_summary,
    ext_regime_governance_summary,
    promotion_reason_summary,
    symbol_participation_summary,
    verdict_distribution,
)
from crypto_core.validation.backtest_replay_admission import (
    BacktestReplayAdmissionStatus,
    backtest_replay_admission_digest,
    backtest_replay_admission_from_dict,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Review lifecycle statuses
# ---------------------------------------------------------------------------


class ReviewStatus(str, Enum):
    """Deterministic promotion review lifecycle states.

    CREATED            → initial, no campaigns added yet.
    COLLECTING         → at least one campaign report added, collecting more.
    READY_TO_EVALUATE  → enough campaigns to produce meaningful evaluation.
    FINALIZED          → final report produced (terminal).
    FAILED             → irrecoverable workflow error (terminal).
    REJECTED           → finalized with REJECT verdict (terminal).
    """

    CREATED = "created"
    COLLECTING = "collecting"
    READY_TO_EVALUATE = "ready_to_evaluate"
    FINALIZED = "finalized"
    FAILED = "failed"
    REJECTED = "rejected"


_TERMINAL_REVIEW_STATUSES = frozenset({ReviewStatus.FINALIZED, ReviewStatus.FAILED, ReviewStatus.REJECTED})

# Campaign eligibility for review intake.
_ELIGIBLE_STATUSES = frozenset({"completed", "rejected"})
_ELIGIBLE_VERDICTS = frozenset({"pass", "pass_with_warnings", "fail", "inconclusive"})

# Readiness levels that support promotion consideration.
_SUPPORTIVE_READINESS_LEVELS = frozenset({"paper_live", "calibrated_paper", "shadow_live", "tiny_cap_live"})

_WORKFLOW_SNAPSHOT_NAME = "promotion_review_workflow"
_WORKFLOW_REQUIRED_FIELDS = frozenset({"review_id", "status", "created_at_ns", "campaign_ids"})
_ADMISSION_EVIDENCE_TYPE = "audit_record"
_ADMISSION_PAYLOAD_TYPE = "backtest_replay_admission"


# ---------------------------------------------------------------------------
# Phase 11B: external regime quality classification
# ---------------------------------------------------------------------------


def _classify_ext_regime_quality(
    agg: CampaignAggregation,
    thresholds: PromotionThresholds | None = None,
) -> str:
    """Classify external regime evidence quality from campaign aggregation.

    Returns one of: supportive, cautionary, insufficient, blocking, unavailable.
    """
    if agg.total_campaigns == 0:
        return "unavailable"

    if agg.campaigns_with_ext_regime_scenario == 0:
        if agg.campaigns_with_ext_regime == 0:
            return "unavailable"
        fresh_ratio = agg.campaigns_ext_regime_fresh / agg.total_campaigns
        if fresh_ratio >= 2.0 / 3.0:
            return "sufficient"
        if fresh_ratio >= 1.0 / 3.0:
            return "marginal"
        return "insufficient"

    return classify_ext_regime_governance(agg, thresholds)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CampaignIntakeError(RuntimeError):
    """Raised when a campaign report fails intake validation."""


class ReviewWorkflowCorruptError(RuntimeError):
    """Raised when persisted review workflow state is malformed."""


class PromotionAdmissionEvidenceError(RuntimeError):
    """Raised when persisted BacktestReplayAdmission evidence fails closed."""


# ---------------------------------------------------------------------------
# Admission evidence precheck
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdmissionEvidencePrecheck:
    """Read-only persisted BacktestReplayAdmission evidence precheck."""

    accepted: bool
    rejection_reasons: tuple[str, ...]
    evidence_digest: str | None = None
    strategy_id: str | None = None
    strategy_digest: str | None = None


def backtest_replay_admission_evidence_precheck(
    evidence_store: EvidenceStore,
    *,
    expected_strategy_id: str | None = None,
    expected_strategy_digest: str | None = None,
) -> AdmissionEvidencePrecheck:
    """Require one accepted persisted BacktestReplayAdmission evidence payload.

    Read-only and fail-closed. Missing, malformed, wrong-type, ambiguous,
    rejected, needs-research, insufficient, and digest-mismatched evidence all
    return deterministic rejection reasons.
    """
    try:
        records = evidence_store.load_evidence()
    except EvidenceStoreCorruptError:
        return _admission_precheck_rejected("backtest_replay_admission_evidence:store_corrupt")

    candidates: list[Mapping[str, Any]] = []
    wrong_payload_type_seen = False
    malformed_audit_seen = False
    for record in records:
        if record.get("evidence_type") != _ADMISSION_EVIDENCE_TYPE:
            continue
        data = record.get("data")
        if not isinstance(data, Mapping):
            malformed_audit_seen = True
            continue
        payload_type = data.get("payload_type")
        if payload_type == _ADMISSION_PAYLOAD_TYPE:
            candidates.append(data)
        elif payload_type is not None:
            wrong_payload_type_seen = True

    if not candidates:
        reasons: list[str] = []
        if malformed_audit_seen:
            reasons.append("backtest_replay_admission_evidence:payload_malformed")
        if wrong_payload_type_seen:
            reasons.append("backtest_replay_admission_evidence:payload_type_wrong")
        reasons.append("backtest_replay_admission_evidence:missing")
        return _admission_precheck_rejected(*reasons)

    if len(candidates) > 1:
        return _admission_precheck_rejected("backtest_replay_admission_evidence:ambiguous")

    payload = candidates[0]
    embedded = payload.get("backtest_replay_admission_result")
    if not isinstance(embedded, Mapping):
        return _admission_precheck_rejected("backtest_replay_admission_evidence:result_payload_malformed")

    result = backtest_replay_admission_from_dict(embedded)
    computed_digest = backtest_replay_admission_digest(result)
    persisted_digest = payload.get("evidence_digest")
    reasons = _admission_payload_rejection_reasons(
        payload=payload,
        result=result,
        computed_digest=computed_digest,
        persisted_digest=persisted_digest,
        expected_strategy_id=expected_strategy_id,
        expected_strategy_digest=expected_strategy_digest,
    )
    if reasons:
        return AdmissionEvidencePrecheck(
            accepted=False,
            rejection_reasons=reasons,
            evidence_digest=persisted_digest if isinstance(persisted_digest, str) else None,
            strategy_id=result.strategy_id,
            strategy_digest=result.strategy_digest,
        )

    return AdmissionEvidencePrecheck(
        accepted=True,
        rejection_reasons=(),
        evidence_digest=computed_digest,
        strategy_id=result.strategy_id,
        strategy_digest=result.strategy_digest,
    )


def _admission_payload_rejection_reasons(
    *,
    payload: Mapping[str, Any],
    result,
    computed_digest: str,
    persisted_digest: object,
    expected_strategy_id: str | None,
    expected_strategy_digest: str | None,
) -> tuple[str, ...]:
    reasons: list[str] = []

    if not _is_sha256_digest(persisted_digest):
        reasons.append("backtest_replay_admission_evidence:evidence_digest_malformed")
    elif persisted_digest != computed_digest:
        reasons.append("backtest_replay_admission_evidence:evidence_digest_mismatch")

    if payload.get("accepted") is not result.accepted:
        reasons.append("backtest_replay_admission_evidence:accepted_mismatch")
    if payload.get("status") != result.status.value:
        reasons.append("backtest_replay_admission_evidence:status_mismatch")
    if payload.get("strategy_id") != result.strategy_id:
        reasons.append("backtest_replay_admission_evidence:strategy_id_mismatch")
    if payload.get("strategy_digest") != result.strategy_digest:
        reasons.append("backtest_replay_admission_evidence:strategy_digest_mismatch")
    if _normalized_mapping(payload.get("decision_ledger_digests")) != dict(
        sorted(result.decision_ledger_digests.items())
    ):
        reasons.append("backtest_replay_admission_evidence:decision_ledger_digests_mismatch")
    if _normalized_mapping(payload.get("evidence_digest_by_stage")) != dict(
        sorted(result.evidence_digest_by_stage.items())
    ):
        reasons.append("backtest_replay_admission_evidence:evidence_digest_by_stage_mismatch")

    if result.status is not BacktestReplayAdmissionStatus.ACCEPTED or result.accepted is not True:
        reasons.append("backtest_replay_admission_evidence:not_accepted")
    if result.status is BacktestReplayAdmissionStatus.REJECTED or result.rejection_reasons:
        reasons.append("backtest_replay_admission_evidence:rejected")
    if result.status is BacktestReplayAdmissionStatus.INSUFFICIENT_EVIDENCE:
        reasons.append("backtest_replay_admission_evidence:insufficient_evidence")
    if result.status is BacktestReplayAdmissionStatus.NEEDS_RESEARCH:
        reasons.append("backtest_replay_admission_evidence:needs_research")
    if result.needs_research_reasons:
        reasons.append("backtest_replay_admission_evidence:needs_research")

    if expected_strategy_id is not None and result.strategy_id != expected_strategy_id:
        reasons.append("backtest_replay_admission_evidence:expected_strategy_id_mismatch")
    if expected_strategy_digest is not None and result.strategy_digest != expected_strategy_digest:
        reasons.append("backtest_replay_admission_evidence:expected_strategy_digest_mismatch")

    return _stable_unique(reasons)


def _admission_precheck_rejected(*reasons: str) -> AdmissionEvidencePrecheck:
    return AdmissionEvidencePrecheck(
        accepted=False,
        rejection_reasons=_stable_unique(reasons),
    )


def _normalized_mapping(value: object) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    parsed: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            return None
        parsed[key] = item
    return dict(sorted(parsed.items()))


def _stable_unique(reasons: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _is_sha256_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower())


# ---------------------------------------------------------------------------
# Current review snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CurrentReviewSnapshot:
    """Point-in-time promotion review state for operator inspection.

    Deterministic and serialization-friendly.
    """

    review_id: str
    status: str  # ReviewStatus.value
    created_at_ns: int
    updated_at_ns: int
    campaign_count: int
    campaign_ids: tuple[str, ...]
    verdict_distribution: dict
    execution_sufficiency: dict
    symbol_breadth: dict
    provisional_verdict: str | None  # PromotionVerdict.value or None
    provisional_summary: str
    insufficient_evidence: tuple[str, ...]
    readiness_level: str
    readiness_is_supportive: bool
    is_ready_to_finalize: bool
    # Phase 11B: external regime evidence quality
    ext_regime_quality: str = "unavailable"
    ext_regime_governance: dict = None


# ---------------------------------------------------------------------------
# Final review report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FinalReviewReport:
    """Final promotion review report with full evidence.

    Immutable artifact produced on finalization.
    Deterministic: same campaign set → same report content.
    """

    review_id: str
    finalized_at_ns: int
    verdict: str  # PromotionVerdict.value
    summary: str
    campaign_ids: tuple[str, ...]
    campaign_count: int
    pass_criteria: tuple[str, ...]
    warning_criteria: tuple[str, ...]
    fail_criteria: tuple[str, ...]
    insufficient_evidence: tuple[str, ...]
    execution_calibration_quality: dict
    coverage_stability_breadth: dict
    readiness_level: str
    readiness_is_supportive: bool
    reason_codes: dict
    # Phase 11B: external regime evidence quality
    ext_regime_quality: str = "unavailable"
    ext_regime_governance: dict = None


# ---------------------------------------------------------------------------
# Promotion review controller
# ---------------------------------------------------------------------------


class PromotionReviewController:
    """First-class promotion review lifecycle manager.

    Orchestrates:
      - Campaign report intake with eligibility validation.
      - Review set management (add, remove, reset).
      - Provisional evaluation and snapshots.
      - Final review production and persistence.
      - Workflow state save/restore.

    Usage::

        controller = PromotionReviewController(
            review_id="rev-001",
            readiness_level="paper_live",
        )
        controller.add_campaign_report(report_1)
        controller.add_campaign_report(report_2)
        controller.add_campaign_report(report_3)
        snapshot = controller.current_snapshot()
        final = controller.finalize_review()

    Thread safety: NOT thread-safe — call from the operator thread only.
    """

    def __init__(
        self,
        *,
        review_id: str | None = None,
        readiness_level: str = "not_assessed",
        thresholds: PromotionThresholds | None = None,
        evidence_store: EvidenceStore | None = None,
        created_at_ns: int | None = None,
        require_admission_evidence: bool = False,
    ) -> None:
        self._review_id = review_id or f"review-{uuid.uuid4().hex[:12]}"
        self._status = ReviewStatus.CREATED
        now = created_at_ns if created_at_ns is not None else time.time_ns()
        self._created_at_ns = now
        self._updated_at_ns = now
        self._readiness_level = readiness_level
        self._thresholds = thresholds or PromotionThresholds()
        self._reports: dict[str, CampaignReport] = {}
        self._final_report: FinalReviewReport | None = None
        self._evidence_store = evidence_store
        self._review_store = PromotionReviewStore(evidence_store) if evidence_store else None
        self._require_admission_evidence = require_admission_evidence

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def review_id(self) -> str:
        return self._review_id

    @property
    def status(self) -> ReviewStatus:
        return self._status

    @property
    def campaign_count(self) -> int:
        return len(self._reports)

    @property
    def campaign_ids(self) -> tuple[str, ...]:
        return tuple(self._reports.keys())

    @property
    def is_finalized(self) -> bool:
        return self._status in _TERMINAL_REVIEW_STATUSES

    @property
    def readiness_level(self) -> str:
        return self._readiness_level

    @property
    def readiness_is_supportive(self) -> bool:
        return self._readiness_level in _SUPPORTIVE_READINESS_LEVELS

    def admission_evidence_precheck(self) -> AdmissionEvidencePrecheck:
        """Read-only gate for persisted BacktestReplayAdmission evidence."""
        if self._evidence_store is None:
            return AdmissionEvidencePrecheck(accepted=True, rejection_reasons=())
        return backtest_replay_admission_evidence_precheck(self._evidence_store)

    # ------------------------------------------------------------------
    # Campaign intake
    # ------------------------------------------------------------------

    def add_campaign_report(self, report: CampaignReport) -> None:
        """Add a completed campaign report to the review set.

        Validates:
          - Review is not in terminal status.
          - Campaign status is terminal (completed/rejected).
          - Campaign verdict is a valid AcceptanceVerdict value.
          - Campaign ID is not already in the review set.

        Args:
            report: completed CampaignReport.

        Raises:
            CampaignIntakeError: if validation fails.
            RuntimeError: if review is already finalized.
        """
        if self._status in _TERMINAL_REVIEW_STATUSES:
            raise RuntimeError(f"Cannot add campaigns to review in terminal status {self._status.value!r}")

        if not report.campaign_id:
            raise CampaignIntakeError("Campaign report has empty campaign_id")

        if report.status not in _ELIGIBLE_STATUSES:
            raise CampaignIntakeError(
                f"Campaign {report.campaign_id!r} has ineligible status "
                f"{report.status!r}; expected one of "
                f"{sorted(_ELIGIBLE_STATUSES)}"
            )

        if report.verdict not in _ELIGIBLE_VERDICTS:
            raise CampaignIntakeError(
                f"Campaign {report.campaign_id!r} has invalid verdict "
                f"{report.verdict!r}; expected one of "
                f"{sorted(_ELIGIBLE_VERDICTS)}"
            )

        if report.campaign_id in self._reports:
            raise CampaignIntakeError(f"Campaign {report.campaign_id!r} already in review set; duplicates rejected")

        self._reports[report.campaign_id] = report
        self._updated_at_ns = time.time_ns()
        self._update_status()
        self._persist_workflow()

    def remove_campaign(self, campaign_id: str) -> None:
        """Remove a campaign from the review set.

        Args:
            campaign_id: campaign to remove.

        Raises:
            RuntimeError: if review is in terminal status.
            KeyError: if campaign_id not in review set.
        """
        if self._status in _TERMINAL_REVIEW_STATUSES:
            raise RuntimeError(f"Cannot modify review in terminal status {self._status.value!r}")
        if campaign_id not in self._reports:
            raise KeyError(f"Campaign {campaign_id!r} not in review set")
        del self._reports[campaign_id]
        self._updated_at_ns = time.time_ns()
        self._update_status()
        self._persist_workflow()

    def reset(self) -> None:
        """Reset the review to CREATED state.

        Clears all campaigns and the final report.
        Can be called from any non-FAILED status.

        Raises:
            RuntimeError: if review is in FAILED status.
        """
        if self._status == ReviewStatus.FAILED:
            raise RuntimeError("Cannot reset a FAILED review")
        self._reports.clear()
        self._final_report = None
        self._status = ReviewStatus.CREATED
        self._updated_at_ns = time.time_ns()
        self._persist_workflow()

    # ------------------------------------------------------------------
    # Evaluation (provisional)
    # ------------------------------------------------------------------

    def evaluate(self) -> PromotionResult:
        """Produce a provisional promotion result from current campaign set.

        Does NOT finalize the review. Read-only evaluation.

        Returns:
            PromotionResult with verdict and criteria.

        Raises:
            RuntimeError: if no campaigns in review set.
        """
        if not self._reports:
            raise RuntimeError("Cannot evaluate empty review set")
        reports_tuple = tuple(self._reports.values())
        aggregation = build_campaign_aggregation(reports_tuple, thresholds=self._thresholds)
        policy = PromotionPolicy(self._thresholds)
        return policy.evaluate(aggregation, readiness_level=self._readiness_level)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def current_snapshot(self) -> CurrentReviewSnapshot:
        """Produce a point-in-time review snapshot for operator inspection.

        Read-only — does NOT mutate review state.

        Returns:
            Frozen CurrentReviewSnapshot.
        """
        if not self._reports:
            return CurrentReviewSnapshot(
                review_id=self._review_id,
                status=self._status.value,
                created_at_ns=self._created_at_ns,
                updated_at_ns=self._updated_at_ns,
                campaign_count=0,
                campaign_ids=(),
                verdict_distribution={},
                execution_sufficiency={},
                symbol_breadth={},
                provisional_verdict=None,
                provisional_summary="No campaigns in review set.",
                insufficient_evidence=(),
                readiness_level=self._readiness_level,
                readiness_is_supportive=self.readiness_is_supportive,
                is_ready_to_finalize=False,
                ext_regime_governance={},
            )

        reports_tuple = tuple(self._reports.values())
        aggregation = build_campaign_aggregation(reports_tuple, thresholds=self._thresholds)
        policy = PromotionPolicy(self._thresholds)
        result = policy.evaluate(aggregation, readiness_level=self._readiness_level)
        admission_precheck = (
            self.admission_evidence_precheck()
            if self._require_admission_evidence
            else AdmissionEvidencePrecheck(accepted=True, rejection_reasons=())
        )
        insufficient_evidence = (
            tuple(c.name for c in result.insufficient_reasons) + admission_precheck.rejection_reasons
        )

        return CurrentReviewSnapshot(
            review_id=self._review_id,
            status=self._status.value,
            created_at_ns=self._created_at_ns,
            updated_at_ns=self._updated_at_ns,
            campaign_count=len(self._reports),
            campaign_ids=tuple(self._reports.keys()),
            verdict_distribution=verdict_distribution(aggregation),
            execution_sufficiency=execution_sufficiency_summary(aggregation),
            symbol_breadth=symbol_participation_summary(aggregation),
            provisional_verdict=result.verdict.value,
            provisional_summary=result.summary,
            insufficient_evidence=insufficient_evidence,
            readiness_level=self._readiness_level,
            readiness_is_supportive=self.readiness_is_supportive,
            is_ready_to_finalize=len(self._reports) > 0 and admission_precheck.accepted,
            ext_regime_quality=_classify_ext_regime_quality(aggregation, self._thresholds),
            ext_regime_governance=ext_regime_governance_summary(aggregation),
        )

    # ------------------------------------------------------------------
    # Finalize
    # ------------------------------------------------------------------

    def finalize_review(self, *, finalized_at_ns: int | None = None) -> FinalReviewReport:
        """Finalize the review and produce the final report.

        Transitions status to FINALIZED or REJECTED (if verdict is REJECT).
        Persists final review and workflow state.

        Idempotent: repeated calls after finalization return existing report.

        Args:
            finalized_at_ns: optional finalization timestamp.

        Returns:
            FinalReviewReport.

        Raises:
            RuntimeError: if review is in FAILED status or has no campaigns.
        """
        if self._final_report is not None and self._status in _TERMINAL_REVIEW_STATUSES:
            return self._final_report

        if self._status == ReviewStatus.FAILED:
            raise RuntimeError("Cannot finalize a FAILED review")

        if not self._reports:
            raise RuntimeError("Cannot finalize review with no campaigns")

        if self._require_admission_evidence:
            admission_precheck = self.admission_evidence_precheck()
            if not admission_precheck.accepted:
                reasons = ",".join(admission_precheck.rejection_reasons)
                raise PromotionAdmissionEvidenceError(f"BacktestReplayAdmission evidence precheck failed: {reasons}")

        ts = finalized_at_ns if finalized_at_ns is not None else time.time_ns()

        reports_tuple = tuple(self._reports.values())
        review = build_promotion_review(
            reports_tuple,
            review_id=self._review_id,
            readiness_level=self._readiness_level,
            thresholds=self._thresholds,
            reviewed_at_ns=ts,
        )

        result = review.result
        aggregation = review.aggregation

        final = FinalReviewReport(
            review_id=self._review_id,
            finalized_at_ns=ts,
            verdict=result.verdict.value,
            summary=result.summary,
            campaign_ids=tuple(self._reports.keys()),
            campaign_count=len(self._reports),
            pass_criteria=tuple(c.name for c in result.pass_reasons),
            warning_criteria=tuple(c.name for c in result.warning_reasons),
            fail_criteria=tuple(c.name for c in result.fail_reasons),
            insufficient_evidence=tuple(c.name for c in result.insufficient_reasons),
            execution_calibration_quality=execution_sufficiency_summary(aggregation),
            coverage_stability_breadth={
                "total_cycles": aggregation.total_cycles,
                "total_fills": aggregation.total_fills,
                "total_events": aggregation.total_events,
                "total_elapsed_seconds": aggregation.total_elapsed_seconds,
                "unique_symbols": list(aggregation.unique_symbols),
                "unique_exchanges": list(aggregation.unique_exchanges),
                "verdict_consistency": aggregation.verdict_consistency.value,
                "total_recovery_incidents": aggregation.total_recovery_incidents,
                "any_ei_degraded": aggregation.any_ei_degraded,
            },
            readiness_level=self._readiness_level,
            readiness_is_supportive=self.readiness_is_supportive,
            reason_codes=promotion_reason_summary(result),
            ext_regime_quality=_classify_ext_regime_quality(aggregation, self._thresholds),
            ext_regime_governance=ext_regime_governance_summary(aggregation),
        )

        self._final_report = final

        if result.verdict == PromotionVerdict.REJECT:
            self._status = ReviewStatus.REJECTED
        else:
            self._status = ReviewStatus.FINALIZED

        self._updated_at_ns = ts

        if self._review_store is not None:
            self._review_store.save_review(review)

        self._persist_workflow()

        return final

    # ------------------------------------------------------------------
    # Reporting API (read-only, deterministic)
    # ------------------------------------------------------------------

    @property
    def final_report(self) -> FinalReviewReport | None:
        """The final review report, or None if not yet finalized."""
        return self._final_report

    def get_verdict_distribution(self) -> dict:
        """Campaign verdict distribution across included campaigns."""
        if not self._reports:
            return {
                "total": 0,
                "passed": 0,
                "warned": 0,
                "failed": 0,
                "inconclusive": 0,
                "consistency": "insufficient",
            }
        agg = build_campaign_aggregation(tuple(self._reports.values()))
        return verdict_distribution(agg)

    def get_execution_sufficiency(self) -> dict:
        """Execution evidence sufficiency summary."""
        if not self._reports:
            return {"total_campaigns": 0, "sufficiency_distribution": {}}
        agg = build_campaign_aggregation(tuple(self._reports.values()))
        return execution_sufficiency_summary(agg)

    def get_symbol_breadth(self) -> dict:
        """Symbol participation breadth summary."""
        if not self._reports:
            return {
                "unique_symbols": [],
                "unique_exchanges": [],
                "max_symbols_with_events": 0,
                "total_campaigns": 0,
            }
        agg = build_campaign_aggregation(tuple(self._reports.values()))
        return symbol_participation_summary(agg)

    def get_missing_evidence(self) -> dict:
        """Current missing evidence summary."""
        if not self._reports:
            return {
                "campaign_count": 0,
                "insufficient_criteria": [],
                "message": "No campaigns in review set.",
            }
        result = self.evaluate()
        return {
            "campaign_count": len(self._reports),
            "insufficient_criteria": [c.name for c in result.insufficient_reasons],
            "warning_criteria": [c.name for c in result.warning_reasons],
            "fail_criteria": [c.name for c in result.fail_reasons],
            "provisional_verdict": result.verdict.value,
            "ext_regime_quality": _classify_ext_regime_quality(
                build_campaign_aggregation(tuple(self._reports.values())), self._thresholds
            ),
            "message": result.summary,
        }

    def get_provisional_recommendation(self) -> dict:
        """Provisional promotion recommendation snapshot."""
        if not self._reports:
            return {
                "verdict": None,
                "summary": "No campaigns in review set.",
                "campaign_count": 0,
            }
        result = self.evaluate()
        return {
            "verdict": result.verdict.value,
            "summary": result.summary,
            "campaign_count": len(self._reports),
            "readiness_level": self._readiness_level,
            "readiness_is_supportive": self.readiness_is_supportive,
            "ext_regime_quality": _classify_ext_regime_quality(
                build_campaign_aggregation(tuple(self._reports.values())), self._thresholds
            ),
        }

    def get_promotion_reason_summary(self) -> dict:
        """Promotion reason summary from current evaluation."""
        if not self._reports:
            return {
                "verdict": None,
                "pass_count": 0,
                "warning_count": 0,
                "fail_count": 0,
                "insufficient_count": 0,
                "pass_reasons": [],
                "warning_reasons": [],
                "fail_reasons": [],
                "insufficient_reasons": [],
                "summary": "No campaigns in review set.",
            }
        result = self.evaluate()
        return promotion_reason_summary(result)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_state(self) -> WriteResult | None:
        """Persist current workflow state via EvidenceStore.

        Returns:
            WriteResult if evidence store is configured, None otherwise.
        """
        if self._evidence_store is None:
            return None
        d = self._workflow_state_to_dict()
        return self._evidence_store.save_snapshot(_WORKFLOW_SNAPSHOT_NAME, d)

    @classmethod
    def restore(
        cls,
        evidence_store: EvidenceStore,
        reports_by_id: dict[str, CampaignReport],
        *,
        thresholds: PromotionThresholds | None = None,
    ) -> PromotionReviewController:
        """Restore a PromotionReviewController from persisted workflow state.

        Args:
            evidence_store: store containing the workflow snapshot.
            reports_by_id: campaign reports keyed by campaign_id.
            thresholds: promotion thresholds (defaults apply if None).

        Returns:
            Reconstructed controller with restored campaign set.

        Raises:
            ReviewWorkflowCorruptError: if persisted state is malformed.
        """
        envelope = evidence_store.load_snapshot(_WORKFLOW_SNAPSHOT_NAME)
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise ReviewWorkflowCorruptError(f"Workflow state 'data' must be a dict, got {type(data).__name__!r}")
        missing = _WORKFLOW_REQUIRED_FIELDS - set(data)
        if missing:
            raise ReviewWorkflowCorruptError(f"Workflow state missing required fields: {sorted(missing)!r}")

        review_id = data["review_id"]
        status_str = data["status"]
        created_at_ns = data["created_at_ns"]
        campaign_ids = data.get("campaign_ids", [])
        readiness_level = data.get("readiness_level", "not_assessed")
        updated_at_ns = data.get("updated_at_ns", created_at_ns)
        require_admission_evidence = data.get("require_admission_evidence", False)
        if not isinstance(require_admission_evidence, bool):
            raise ReviewWorkflowCorruptError("Workflow state 'require_admission_evidence' must be a bool")

        try:
            status = ReviewStatus(status_str)
        except ValueError:
            raise ReviewWorkflowCorruptError(f"Invalid review status {status_str!r}") from None

        missing_reports = [cid for cid in campaign_ids if cid not in reports_by_id]
        if missing_reports:
            raise ReviewWorkflowCorruptError(f"Missing campaign reports for ids: {missing_reports!r}")

        controller = cls(
            review_id=review_id,
            readiness_level=readiness_level,
            thresholds=thresholds,
            evidence_store=evidence_store,
            created_at_ns=created_at_ns,
            require_admission_evidence=require_admission_evidence is True,
        )
        controller._status = status
        controller._updated_at_ns = updated_at_ns
        for cid in campaign_ids:
            controller._reports[cid] = reports_by_id[cid]

        return controller

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update_status(self) -> None:
        """Update review status based on current campaign count."""
        if self._status in _TERMINAL_REVIEW_STATUSES:
            return
        if not self._reports:
            self._status = ReviewStatus.CREATED
        elif len(self._reports) >= self._thresholds.min_completed_campaigns:
            self._status = ReviewStatus.READY_TO_EVALUATE
        else:
            self._status = ReviewStatus.COLLECTING

    def _persist_workflow(self) -> None:
        """Persist workflow state if evidence store is configured."""
        if self._evidence_store is not None:
            self._evidence_store.save_snapshot(_WORKFLOW_SNAPSHOT_NAME, self._workflow_state_to_dict())

    def _workflow_state_to_dict(self) -> dict:
        """Serialize workflow state to a plain dict."""
        return {
            "review_id": self._review_id,
            "status": self._status.value,
            "created_at_ns": self._created_at_ns,
            "updated_at_ns": self._updated_at_ns,
            "readiness_level": self._readiness_level,
            "require_admission_evidence": self._require_admission_evidence,
            "campaign_ids": list(self._reports.keys()),
            "is_finalized": self._status in _TERMINAL_REVIEW_STATUSES,
        }


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def current_review_snapshot_to_dict(snapshot: CurrentReviewSnapshot) -> dict:
    """Serialize CurrentReviewSnapshot to a plain dict."""
    return {
        "review_id": snapshot.review_id,
        "status": snapshot.status,
        "created_at_ns": snapshot.created_at_ns,
        "updated_at_ns": snapshot.updated_at_ns,
        "campaign_count": snapshot.campaign_count,
        "campaign_ids": list(snapshot.campaign_ids),
        "verdict_distribution": snapshot.verdict_distribution,
        "execution_sufficiency": snapshot.execution_sufficiency,
        "symbol_breadth": snapshot.symbol_breadth,
        "provisional_verdict": snapshot.provisional_verdict,
        "provisional_summary": snapshot.provisional_summary,
        "insufficient_evidence": list(snapshot.insufficient_evidence),
        "readiness_level": snapshot.readiness_level,
        "readiness_is_supportive": snapshot.readiness_is_supportive,
        "is_ready_to_finalize": snapshot.is_ready_to_finalize,
        "ext_regime_quality": snapshot.ext_regime_quality,
        "ext_regime_governance": snapshot.ext_regime_governance or {},
    }


def final_review_report_to_dict(report: FinalReviewReport) -> dict:
    """Serialize FinalReviewReport to a plain dict."""
    return {
        "review_id": report.review_id,
        "finalized_at_ns": report.finalized_at_ns,
        "verdict": report.verdict,
        "summary": report.summary,
        "campaign_ids": list(report.campaign_ids),
        "campaign_count": report.campaign_count,
        "pass_criteria": list(report.pass_criteria),
        "warning_criteria": list(report.warning_criteria),
        "fail_criteria": list(report.fail_criteria),
        "insufficient_evidence": list(report.insufficient_evidence),
        "execution_calibration_quality": report.execution_calibration_quality,
        "coverage_stability_breadth": report.coverage_stability_breadth,
        "readiness_level": report.readiness_level,
        "readiness_is_supportive": report.readiness_is_supportive,
        "reason_codes": report.reason_codes,
        "ext_regime_quality": report.ext_regime_quality,
        "ext_regime_governance": report.ext_regime_governance or {},
    }
