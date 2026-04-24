"""Crypto sleeve admission controller and models - Phase 15F.

Deterministic, serialization-friendly controller for managed sleeve admission gating.

Design rules:
  - Uses only existing sleeve portfolio and promotion review truth.
  - No new promotion engine, ranking, allocation optimizer, or alpha logic.
  - Missing review or portfolio truth fails closed into non-admission.
  - Bounded finalized history only; malformed restored state fails closed.
  - PAPER-ONLY.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from enum import Enum

from crypto_core.service.campaign import AcceptanceVerdict, CampaignReport
from crypto_core.service.sleeve_candidate_workflow import SleeveCandidateWorkflowSnapshot
from crypto_core.service.sleeve_portfolio import (
    CryptoSleeveState,
    CryptoSleeveStatus,
    SleeveCampaignEvidenceStatus,
    SleeveDecisionPackStatus,
    SleevePortfolioSnapshot,
    SleevePromotionCandidateStatus,
    SleevePromotionSupportStatus,
    SleeveQualificationStatus,
    SleeveRecommendationStatus,
)
from crypto_core.service.sleeve_promotion_review_controller import (
    SleevePromotionReviewPortfolioSummary,
    SleevePromotionReviewResult,
    SleevePromotionReviewSnapshot,
    SleevePromotionReviewVerdict,
)

_ALLOCATION_EPSILON = 1e-9


class SleeveAdmissionVerdict(str, Enum):
    ADMITTED_ACTIVE = "admitted_active"
    ADMITTED_UNALLOCATED = "admitted_unallocated"
    REVIEW_SUPPORTED_NOT_ADMITTED = "review_supported_not_admitted"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    DISABLED_OPERATOR_OFF = "disabled_operator_off"
    # Backward-compatible aliases for older Phase 15F snapshot payloads.
    NOT_ADMITTED_BLOCKED = "not_admitted_blocked"
    NOT_ADMITTED_INCONCLUSIVE = "not_admitted_inconclusive"


class SleeveAdmissionReleaseStatus(str, Enum):
    READY_FOR_PAPER_MANAGED_SET = "ready_for_paper_managed_set"
    PARTIAL_READY = "partial_ready"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    NO_CANDIDATES = "no_candidates"


class SleeveAdmissionReleaseEvidenceStatus(str, Enum):
    EVIDENCE_READY = "evidence_ready"
    EVIDENCE_PARTIAL = "evidence_partial"
    EVIDENCE_BLOCKED = "evidence_blocked"
    EVIDENCE_MISSING = "evidence_missing"


class ManagedSleeveSetDryRunStatus(str, Enum):
    READY_FOR_PAPER_DRY_RUN = "ready_for_paper_dry_run"
    PARTIAL_PAPER_DRY_RUN = "partial_paper_dry_run"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    EMPTY = "empty"


class PaperShadowActivationStatus(str, Enum):
    READY_FOR_PAPER_SHADOW = "ready_for_paper_shadow"
    PARTIAL_READY = "partial_ready"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    EMPTY = "empty"


@dataclass(frozen=True)
class SleeveAdmissionResult:
    sleeve_id: str
    verdict: SleeveAdmissionVerdict
    reason: str
    next_step: str
    admitted: bool = False
    active: bool = False
    effective_allocation: float = 0.0
    target_allocation: float = 0.0
    governance_blockers: tuple[str, ...] = ()
    evidence_blockers: tuple[str, ...] = ()
    last_review_verdict: SleevePromotionReviewVerdict | None = None
    qualification_status: SleeveQualificationStatus | None = None
    recommendation_status: SleeveRecommendationStatus | None = None
    campaign_evidence_status: SleeveCampaignEvidenceStatus | None = None
    promotion_support_status: SleevePromotionSupportStatus | None = None
    promotion_candidate_status: SleevePromotionCandidateStatus | None = None
    decision_pack_status: SleeveDecisionPackStatus | None = None


@dataclass(frozen=True)
class SleeveAdmissionPortfolioSummary:
    as_of_ns: int
    admission_results: tuple[SleeveAdmissionResult, ...]
    admitted_active_count: int
    admitted_unallocated_count: int
    review_supported_not_admitted_count: int
    blocked_count: int
    inconclusive_count: int
    admitted_active: tuple[str, ...]
    admitted_unallocated: tuple[str, ...]
    review_supported_not_admitted: tuple[str, ...]
    blocked: tuple[str, ...]
    inconclusive: tuple[str, ...]
    governance_blockers: tuple[str, ...]
    evidence_blockers: tuple[str, ...]
    next_step_summary: str
    operator_summary: str
    insufficient_evidence: tuple[str, ...] = ()
    disabled_operator_off: tuple[str, ...] = ()
    insufficient_evidence_count: int = 0
    disabled_operator_off_count: int = 0


@dataclass(frozen=True)
class SleeveAdmissionHistoryEntry:
    as_of_ns: int
    summary: str
    portfolio_summary: SleeveAdmissionPortfolioSummary


@dataclass(frozen=True)
class SleeveAdmissionSnapshot:
    as_of_ns: int
    status: str
    admission_results: tuple[SleeveAdmissionResult, ...]
    portfolio_summary: SleeveAdmissionPortfolioSummary
    history: tuple[SleeveAdmissionHistoryEntry, ...] = ()


@dataclass(frozen=True)
class SleeveAdmissionReleaseAction:
    sleeve_id: str
    admission_verdict: SleeveAdmissionVerdict
    next_action: str
    evidence_blockers: tuple[str, ...] = ()
    governance_blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class SleeveAdmissionReleaseSleeveEvidence:
    sleeve_id: str
    evidence_blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class SleeveAdmissionReleasePack:
    pack_id: str
    as_of_ns: int
    overall_release_status: SleeveAdmissionReleaseStatus
    portfolio_summary: SleeveAdmissionPortfolioSummary
    per_sleeve_admission_results: tuple[SleeveAdmissionResult, ...]
    admitted_sleeves: tuple[str, ...]
    admitted_active_sleeves: tuple[str, ...]
    admitted_unallocated_sleeves: tuple[str, ...]
    review_supported_not_admitted_sleeves: tuple[str, ...]
    blocked_sleeves: tuple[str, ...]
    inconclusive_sleeves: tuple[str, ...]
    evidence_blockers: tuple[str, ...]
    governance_blockers: tuple[str, ...]
    next_actions: tuple[SleeveAdmissionReleaseAction, ...]
    deterministic_replay_key: str
    source_admission_as_of_ns: int = 0
    source_promotion_review_as_of_ns: int | None = None
    source_candidate_workflow_as_of_ns: int | None = None
    source_portfolio_as_of_ns: int | None = None
    admission_snapshot_status: str = ""
    promotion_review_status: str | None = None
    candidate_workflow_status: str | None = None
    portfolio_sleeve_count: int | None = None
    operator_summary: str = ""
    insufficient_evidence_sleeves: tuple[str, ...] = ()
    disabled_operator_off_sleeves: tuple[str, ...] = ()
    paper_campaign_evidence_available: bool = False
    sleeve_campaign_link_available: bool = False
    promotion_review_evidence_available: bool = False
    readiness_evidence_supportive: bool = False
    tca_or_markout_evidence_supportive: bool = False
    external_regime_evidence_supportive: bool = False
    evidence_gate_status: SleeveAdmissionReleaseEvidenceStatus = SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_MISSING
    evidence_gate_summary: str = "Paper evidence gate not evaluated."
    paper_evidence_blockers: tuple[str, ...] = ()
    per_sleeve_evidence_blockers: tuple[SleeveAdmissionReleaseSleeveEvidence, ...] = ()


@dataclass(frozen=True)
class _ReleaseEvidenceGate:
    paper_campaign_evidence_available: bool
    sleeve_campaign_link_available: bool
    promotion_review_evidence_available: bool
    readiness_evidence_supportive: bool
    tca_or_markout_evidence_supportive: bool
    external_regime_evidence_supportive: bool
    status: SleeveAdmissionReleaseEvidenceStatus
    blockers: tuple[str, ...]
    per_sleeve_blockers: tuple[SleeveAdmissionReleaseSleeveEvidence, ...]
    summary: str


@dataclass(frozen=True)
class ManagedSleeveAllocation:
    sleeve_id: str
    effective_allocation: float


@dataclass(frozen=True)
class ManagedSleeveSetManifest:
    manifest_id: str
    as_of_ns: int
    source_release_pack_status: SleeveAdmissionReleaseStatus
    source_release_pack_id: str
    source_release_pack_as_of_ns: int
    source_release_pack_replay_key: str
    source_release_pack_hash: str
    source_evidence_gate_status: SleeveAdmissionReleaseEvidenceStatus
    active_sleeves: tuple[str, ...]
    admitted_unallocated_sleeves: tuple[str, ...]
    blocked_sleeves: tuple[str, ...]
    inconclusive_sleeves: tuple[str, ...]
    effective_allocations: tuple[ManagedSleeveAllocation, ...]
    unallocated_share: float
    activation_blockers: tuple[str, ...]
    evidence_blockers: tuple[str, ...]
    governance_blockers: tuple[str, ...]
    dry_run_status: ManagedSleeveSetDryRunStatus
    next_actions: tuple[SleeveAdmissionReleaseAction, ...]
    operator_summary: str = ""


@dataclass(frozen=True)
class PaperShadowActivationPlan:
    plan_id: str
    as_of_ns: int
    source_manifest_status: ManagedSleeveSetDryRunStatus
    source_manifest_id: str
    source_manifest_as_of_ns: int
    source_manifest_hash: str
    paper_only: bool
    real_orders_enabled: bool
    real_money_enabled: bool
    active_sleeves: tuple[str, ...]
    inactive_sleeves: tuple[str, ...]
    admitted_unallocated_sleeves: tuple[str, ...]
    effective_allocations: tuple[ManagedSleeveAllocation, ...]
    preflight_gates: tuple[str, ...]
    activation_blockers: tuple[str, ...]
    evidence_blockers: tuple[str, ...]
    governance_blockers: tuple[str, ...]
    runtime_monitoring_requirements: tuple[str, ...]
    kill_switch_requirements: tuple[str, ...]
    next_actions: tuple[SleeveAdmissionReleaseAction, ...]
    activation_status: PaperShadowActivationStatus
    operator_summary: str = ""


class SleeveAdmissionCorruptError(RuntimeError):
    pass


class SleeveAdmissionController:
    """Managed controller for crypto sleeve admission gating."""

    def __init__(
        self,
        review_portfolio_summary: SleevePromotionReviewPortfolioSummary | None = None,
        *,
        portfolio_snapshot: SleevePortfolioSnapshot | None = None,
        history_limit: int = 5,
    ):
        self.review_portfolio_summary = review_portfolio_summary
        self.portfolio_snapshot = portfolio_snapshot
        self.history_limit = max(1, history_limit)
        self.history: list[SleeveAdmissionHistoryEntry] = []
        self._validate()

    def configure(
        self,
        review_portfolio_summary: SleevePromotionReviewPortfolioSummary | None = None,
        *,
        portfolio_snapshot: SleevePortfolioSnapshot | None = None,
    ) -> None:
        self.review_portfolio_summary = review_portfolio_summary
        self.portfolio_snapshot = portfolio_snapshot
        self._validate()

    def _validate(self) -> None:
        if self.review_portfolio_summary is not None and not hasattr(self.review_portfolio_summary, "review_results"):
            raise SleeveAdmissionCorruptError("Malformed review portfolio summary.")
        if self.portfolio_snapshot is not None and not hasattr(self.portfolio_snapshot, "sleeves"):
            raise SleeveAdmissionCorruptError("Malformed sleeve portfolio snapshot.")

    def build_admission_results(self) -> tuple[SleeveAdmissionResult, ...]:
        reviews = {review.sleeve_id: review for review in getattr(self.review_portfolio_summary, "review_results", ())}
        sleeves = {sleeve.sleeve_id: sleeve for sleeve in getattr(self.portfolio_snapshot, "sleeves", ())}
        ordered_ids = tuple(dict.fromkeys((*sleeves.keys(), *reviews.keys())))

        results: list[SleeveAdmissionResult] = []
        for sleeve_id in ordered_ids:
            results.append(self._derive_result(sleeve_id, sleeves.get(sleeve_id), reviews.get(sleeve_id)))
        return tuple(results)

    def _derive_result(
        self,
        sleeve_id: str,
        sleeve: CryptoSleeveState | None,
        review: SleevePromotionReviewResult | None,
    ) -> SleeveAdmissionResult:
        governance_blockers = _collect_governance_blockers(sleeve, review)
        evidence_blockers = _collect_evidence_blockers(sleeve, review)

        if review is None:
            evidence_blockers = _unique((*evidence_blockers, "promotion_review_unavailable"))
            return _result(
                sleeve_id=sleeve_id,
                sleeve=sleeve,
                review=review,
                verdict=SleeveAdmissionVerdict.INSUFFICIENT_EVIDENCE,
                reason="No sleeve promotion review evidence is available for admission.",
                next_step="Complete sleeve promotion review before admitting this sleeve.",
                governance_blockers=governance_blockers,
                evidence_blockers=evidence_blockers,
            )

        if _is_disabled_operator_off(sleeve):
            governance_blockers = _unique((*governance_blockers, "disabled_operator_off"))
            return _result(
                sleeve_id=sleeve_id,
                sleeve=sleeve,
                review=review,
                verdict=SleeveAdmissionVerdict.DISABLED_OPERATOR_OFF,
                reason="Sleeve is explicitly disabled at the operator/configuration layer.",
                next_step=_first_next_step(sleeve, review, "Use enable_sleeve after operator review."),
                governance_blockers=governance_blockers,
                evidence_blockers=evidence_blockers,
            )

        if review.verdict == SleevePromotionReviewVerdict.REVIEW_SUPPORTED:
            return self._derive_supported_review_result(
                sleeve_id,
                sleeve,
                review,
                governance_blockers,
                evidence_blockers,
            )

        if review.verdict == SleevePromotionReviewVerdict.REJECT or governance_blockers:
            return _result(
                sleeve_id=sleeve_id,
                sleeve=sleeve,
                review=review,
                verdict=SleeveAdmissionVerdict.BLOCKED,
                reason="Sleeve is blocked by promotion review or governance evidence.",
                next_step=_first_next_step(sleeve, review, "Clear blockers before admission."),
                governance_blockers=governance_blockers,
                evidence_blockers=evidence_blockers,
            )

        if review.verdict in {SleevePromotionReviewVerdict.HOLD, SleevePromotionReviewVerdict.INCONCLUSIVE}:
            return _result(
                sleeve_id=sleeve_id,
                sleeve=sleeve,
                review=review,
                verdict=SleeveAdmissionVerdict.INCONCLUSIVE,
                reason="Sleeve review is not strong enough for admission.",
                next_step=_first_next_step(sleeve, review, "Gather stronger sleeve evidence before admission."),
                governance_blockers=governance_blockers,
                evidence_blockers=evidence_blockers,
            )

        return _result(
            sleeve_id=sleeve_id,
            sleeve=sleeve,
            review=review,
            verdict=SleeveAdmissionVerdict.INCONCLUSIVE,
            reason="Sleeve admission state is inconclusive.",
            next_step="Investigate sleeve admission evidence before admission.",
            governance_blockers=governance_blockers,
            evidence_blockers=evidence_blockers,
        )

    def _derive_supported_review_result(
        self,
        sleeve_id: str,
        sleeve: CryptoSleeveState | None,
        review: SleevePromotionReviewResult,
        governance_blockers: tuple[str, ...],
        evidence_blockers: tuple[str, ...],
    ) -> SleeveAdmissionResult:
        if sleeve is None:
            evidence_blockers = _unique((*evidence_blockers, "sleeve_portfolio_unavailable"))
            return _result(
                sleeve_id=sleeve_id,
                sleeve=sleeve,
                review=review,
                verdict=SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED,
                reason="Review is supportive, but no sleeve portfolio truth is available.",
                next_step="Rebuild sleeve portfolio snapshot before admission.",
                governance_blockers=governance_blockers,
                evidence_blockers=evidence_blockers,
            )

        if governance_blockers or evidence_blockers:
            return _result(
                sleeve_id=sleeve_id,
                sleeve=sleeve,
                review=review,
                verdict=SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED,
                reason="Review is supportive, but governance or evidence blockers remain.",
                next_step=_first_next_step(sleeve, review, "Resolve blockers before admission."),
                governance_blockers=governance_blockers,
                evidence_blockers=evidence_blockers,
            )

        if (
            sleeve.recommendation.status == SleeveRecommendationStatus.RECOMMENDED_ACTIVE
            and sleeve.effective_allocation > _ALLOCATION_EPSILON
        ):
            return _result(
                sleeve_id=sleeve_id,
                sleeve=sleeve,
                review=review,
                verdict=SleeveAdmissionVerdict.ADMITTED_ACTIVE,
                reason="Review is supportive and sleeve has active effective paper allocation.",
                next_step="Continue paper monitoring under existing governance.",
                governance_blockers=governance_blockers,
                evidence_blockers=evidence_blockers,
            )

        if (
            sleeve.recommendation.status
            in {
                SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
                SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
            }
            or sleeve.qualification.status == SleeveQualificationStatus.PAPER_QUALIFIED
        ):
            return _result(
                sleeve_id=sleeve_id,
                sleeve=sleeve,
                review=review,
                verdict=SleeveAdmissionVerdict.ADMITTED_UNALLOCATED,
                reason="Review is supportive and sleeve is admitted, but it has no effective paper allocation.",
                next_step="Assign explicit paper allocation before treating the sleeve as active.",
                governance_blockers=governance_blockers,
                evidence_blockers=evidence_blockers,
            )

        evidence_blockers = _unique((*evidence_blockers, "sleeve_not_currently_eligible"))
        return _result(
            sleeve_id=sleeve_id,
            sleeve=sleeve,
            review=review,
            verdict=SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED,
            reason="Review is supportive, but current sleeve state is not admission-eligible.",
            next_step=_first_next_step(sleeve, review, "Recompute sleeve qualification before admission."),
            governance_blockers=governance_blockers,
            evidence_blockers=evidence_blockers,
        )

    def build_portfolio_summary(self) -> SleeveAdmissionPortfolioSummary:
        results = self.build_admission_results()
        admitted_active = tuple(r.sleeve_id for r in results if r.verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE)
        admitted_unallocated = tuple(
            r.sleeve_id for r in results if r.verdict == SleeveAdmissionVerdict.ADMITTED_UNALLOCATED
        )
        review_supported_not_admitted = tuple(
            r.sleeve_id for r in results if r.verdict == SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED
        )
        blocked = tuple(r.sleeve_id for r in results if r.verdict in _BLOCKED_VERDICTS)
        inconclusive = tuple(r.sleeve_id for r in results if r.verdict == SleeveAdmissionVerdict.INCONCLUSIVE)
        insufficient = tuple(r.sleeve_id for r in results if r.verdict == SleeveAdmissionVerdict.INSUFFICIENT_EVIDENCE)
        disabled = tuple(r.sleeve_id for r in results if r.verdict == SleeveAdmissionVerdict.DISABLED_OPERATOR_OFF)
        governance_blockers = tuple(sorted({b for r in results for b in r.governance_blockers}))
        evidence_blockers = tuple(sorted({b for r in results for b in r.evidence_blockers}))
        next_step_summary = _next_step_summary(results)
        operator_summary = (
            f"admitted_active={len(admitted_active)}; "
            f"admitted_unallocated={len(admitted_unallocated)}; "
            f"review_supported_not_admitted={len(review_supported_not_admitted)}; "
            f"blocked={len(blocked)}; "
            f"inconclusive={len(inconclusive)}; "
            f"insufficient_evidence={len(insufficient)}; "
            f"disabled_operator_off={len(disabled)}"
        )
        return SleeveAdmissionPortfolioSummary(
            as_of_ns=self._as_of_ns(),
            admission_results=results,
            admitted_active_count=len(admitted_active),
            admitted_unallocated_count=len(admitted_unallocated),
            review_supported_not_admitted_count=len(review_supported_not_admitted),
            blocked_count=len(blocked),
            inconclusive_count=len(inconclusive),
            admitted_active=admitted_active,
            admitted_unallocated=admitted_unallocated,
            review_supported_not_admitted=review_supported_not_admitted,
            blocked=blocked,
            inconclusive=inconclusive,
            governance_blockers=governance_blockers,
            evidence_blockers=evidence_blockers,
            next_step_summary=next_step_summary,
            operator_summary=operator_summary,
            insufficient_evidence=insufficient,
            disabled_operator_off=disabled,
            insufficient_evidence_count=len(insufficient),
            disabled_operator_off_count=len(disabled),
        )

    def snapshot(self, status: str = "active") -> SleeveAdmissionSnapshot:
        summary = self.build_portfolio_summary()
        return SleeveAdmissionSnapshot(
            as_of_ns=summary.as_of_ns,
            status=status,
            admission_results=summary.admission_results,
            portfolio_summary=summary,
            history=tuple(self.history[-self.history_limit :]),
        )

    def finalize(self) -> SleeveAdmissionSnapshot:
        summary = self.build_portfolio_summary()
        entry = SleeveAdmissionHistoryEntry(
            as_of_ns=summary.as_of_ns,
            summary=summary.operator_summary,
            portfolio_summary=summary,
        )
        self.history.append(entry)
        if len(self.history) > self.history_limit:
            self.history = self.history[-self.history_limit :]
        return SleeveAdmissionSnapshot(
            as_of_ns=summary.as_of_ns,
            status="finalized",
            admission_results=summary.admission_results,
            portfolio_summary=summary,
            history=tuple(self.history),
        )

    def restore(self, snapshot: SleeveAdmissionSnapshot) -> None:
        if not isinstance(snapshot, SleeveAdmissionSnapshot):
            raise SleeveAdmissionCorruptError("Sleeve admission restore requires a SleeveAdmissionSnapshot.")
        self.history = list(snapshot.history[-self.history_limit :])
        self._validate()

    def reset(self) -> None:
        self.history = []

    def _as_of_ns(self) -> int:
        candidates = []
        if self.review_portfolio_summary is not None:
            candidates.append(self.review_portfolio_summary.as_of_ns)
        if self.portfolio_snapshot is not None:
            candidates.append(self.portfolio_snapshot.as_of_ns)
        return max(candidates) if candidates else 0


def sleeve_admission_result_to_dict(result: SleeveAdmissionResult) -> dict:
    return {
        "sleeve_id": result.sleeve_id,
        "verdict": result.verdict.value,
        "reason": result.reason,
        "next_step": result.next_step,
        "admitted": result.admitted,
        "active": result.active,
        "effective_allocation": result.effective_allocation,
        "target_allocation": result.target_allocation,
        "governance_blockers": list(result.governance_blockers),
        "evidence_blockers": list(result.evidence_blockers),
        "last_review_verdict": None if result.last_review_verdict is None else result.last_review_verdict.value,
        "qualification_status": _enum_value(result.qualification_status),
        "recommendation_status": _enum_value(result.recommendation_status),
        "campaign_evidence_status": _enum_value(result.campaign_evidence_status),
        "promotion_support_status": _enum_value(result.promotion_support_status),
        "promotion_candidate_status": _enum_value(result.promotion_candidate_status),
        "decision_pack_status": _enum_value(result.decision_pack_status),
    }


def sleeve_admission_result_from_dict(data: dict) -> SleeveAdmissionResult:
    if not isinstance(data, dict):
        raise SleeveAdmissionCorruptError(f"Sleeve admission result must be a dict, got {type(data).__name__!r}")
    verdict = SleeveAdmissionVerdict(_require_non_empty_str(data.get("verdict"), "verdict"))
    return SleeveAdmissionResult(
        sleeve_id=_require_non_empty_str(data.get("sleeve_id"), "sleeve_id"),
        verdict=verdict,
        reason="" if data.get("reason", "") is None else str(data.get("reason", "")),
        next_step="" if data.get("next_step", "") is None else str(data.get("next_step", "")),
        admitted=_require_bool(data.get("admitted", verdict in _ADMITTED_VERDICTS), "admitted"),
        active=_require_bool(data.get("active", verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE), "active"),
        effective_allocation=_require_float(data.get("effective_allocation", 0.0), "effective_allocation"),
        target_allocation=_require_float(data.get("target_allocation", 0.0), "target_allocation"),
        governance_blockers=_tuple_of_strings(data.get("governance_blockers", ()), "governance_blockers"),
        evidence_blockers=_tuple_of_strings(data.get("evidence_blockers", ()), "evidence_blockers"),
        last_review_verdict=_optional_enum(
            SleevePromotionReviewVerdict, data.get("last_review_verdict"), "last_review_verdict"
        ),
        qualification_status=_optional_enum(
            SleeveQualificationStatus, data.get("qualification_status"), "qualification_status"
        ),
        recommendation_status=_optional_enum(
            SleeveRecommendationStatus, data.get("recommendation_status"), "recommendation_status"
        ),
        campaign_evidence_status=_optional_enum(
            SleeveCampaignEvidenceStatus, data.get("campaign_evidence_status"), "campaign_evidence_status"
        ),
        promotion_support_status=_optional_enum(
            SleevePromotionSupportStatus, data.get("promotion_support_status"), "promotion_support_status"
        ),
        promotion_candidate_status=_optional_enum(
            SleevePromotionCandidateStatus, data.get("promotion_candidate_status"), "promotion_candidate_status"
        ),
        decision_pack_status=_optional_enum(
            SleeveDecisionPackStatus, data.get("decision_pack_status"), "decision_pack_status"
        ),
    )


def sleeve_admission_portfolio_summary_to_dict(summary: SleeveAdmissionPortfolioSummary) -> dict:
    return {
        "as_of_ns": summary.as_of_ns,
        "admission_results": [sleeve_admission_result_to_dict(result) for result in summary.admission_results],
        "admitted_active_count": summary.admitted_active_count,
        "admitted_unallocated_count": summary.admitted_unallocated_count,
        "review_supported_not_admitted_count": summary.review_supported_not_admitted_count,
        "blocked_count": summary.blocked_count,
        "inconclusive_count": summary.inconclusive_count,
        "insufficient_evidence_count": summary.insufficient_evidence_count,
        "disabled_operator_off_count": summary.disabled_operator_off_count,
        "admitted_active": list(summary.admitted_active),
        "admitted_unallocated": list(summary.admitted_unallocated),
        "review_supported_not_admitted": list(summary.review_supported_not_admitted),
        "blocked": list(summary.blocked),
        "inconclusive": list(summary.inconclusive),
        "insufficient_evidence": list(summary.insufficient_evidence),
        "disabled_operator_off": list(summary.disabled_operator_off),
        "governance_blockers": list(summary.governance_blockers),
        "evidence_blockers": list(summary.evidence_blockers),
        "next_step_summary": summary.next_step_summary,
        "operator_summary": summary.operator_summary,
    }


def sleeve_admission_portfolio_summary_from_dict(data: dict) -> SleeveAdmissionPortfolioSummary:
    if not isinstance(data, dict):
        raise SleeveAdmissionCorruptError(
            f"Sleeve admission portfolio summary must be a dict, got {type(data).__name__!r}"
        )
    results_value = data.get("admission_results", ())
    if not isinstance(results_value, (list, tuple)):
        raise SleeveAdmissionCorruptError("Sleeve admission field 'admission_results' must be a list/tuple")
    results = tuple(sleeve_admission_result_from_dict(dict(item)) for item in results_value)
    admitted_active = _tuple_or_derive(data, "admitted_active", results, {SleeveAdmissionVerdict.ADMITTED_ACTIVE})
    admitted_unallocated = _tuple_or_derive(
        data, "admitted_unallocated", results, {SleeveAdmissionVerdict.ADMITTED_UNALLOCATED}
    )
    review_supported_not_admitted = _tuple_or_derive(
        data,
        "review_supported_not_admitted",
        results,
        {SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED},
    )
    blocked = _tuple_or_derive(data, "blocked", results, _BLOCKED_VERDICTS)
    inconclusive = _tuple_or_derive(data, "inconclusive", results, _INCONCLUSIVE_VERDICTS)
    insufficient = _tuple_or_derive(
        data, "insufficient_evidence", results, {SleeveAdmissionVerdict.INSUFFICIENT_EVIDENCE}
    )
    disabled = _tuple_or_derive(data, "disabled_operator_off", results, {SleeveAdmissionVerdict.DISABLED_OPERATOR_OFF})
    summary = SleeveAdmissionPortfolioSummary(
        as_of_ns=_require_int(data.get("as_of_ns"), "as_of_ns"),
        admission_results=results,
        admitted_active_count=_count_or_default(data, "admitted_active_count", admitted_active),
        admitted_unallocated_count=_count_or_default(data, "admitted_unallocated_count", admitted_unallocated),
        review_supported_not_admitted_count=_count_or_default(
            data, "review_supported_not_admitted_count", review_supported_not_admitted
        ),
        blocked_count=_count_or_default(data, "blocked_count", blocked),
        inconclusive_count=_count_or_default(data, "inconclusive_count", inconclusive),
        admitted_active=admitted_active,
        admitted_unallocated=admitted_unallocated,
        review_supported_not_admitted=review_supported_not_admitted,
        blocked=blocked,
        inconclusive=inconclusive,
        governance_blockers=_tuple_of_strings(data.get("governance_blockers", ()), "governance_blockers"),
        evidence_blockers=_tuple_of_strings(data.get("evidence_blockers", ()), "evidence_blockers"),
        next_step_summary="" if data.get("next_step_summary", "") is None else str(data.get("next_step_summary", "")),
        operator_summary="" if data.get("operator_summary", "") is None else str(data.get("operator_summary", "")),
        insufficient_evidence=insufficient,
        disabled_operator_off=disabled,
        insufficient_evidence_count=_count_or_default(data, "insufficient_evidence_count", insufficient),
        disabled_operator_off_count=_count_or_default(data, "disabled_operator_off_count", disabled),
    )
    _validate_summary_counts(summary)
    return summary


def sleeve_admission_history_entry_to_dict(entry: SleeveAdmissionHistoryEntry) -> dict:
    return {
        "as_of_ns": entry.as_of_ns,
        "summary": entry.summary,
        "portfolio_summary": sleeve_admission_portfolio_summary_to_dict(entry.portfolio_summary),
    }


def sleeve_admission_history_entry_from_dict(data: dict) -> SleeveAdmissionHistoryEntry:
    if not isinstance(data, dict):
        raise SleeveAdmissionCorruptError(f"Sleeve admission history entry must be a dict, got {type(data).__name__!r}")
    summary = sleeve_admission_portfolio_summary_from_dict(dict(data.get("portfolio_summary")))
    as_of_ns = _require_int(data.get("as_of_ns"), "as_of_ns")
    if as_of_ns != summary.as_of_ns:
        raise SleeveAdmissionCorruptError("Sleeve admission history timestamp does not match portfolio summary")
    return SleeveAdmissionHistoryEntry(
        as_of_ns=as_of_ns,
        summary="" if data.get("summary", "") is None else str(data.get("summary", "")),
        portfolio_summary=summary,
    )


def sleeve_admission_snapshot_to_dict(snapshot: SleeveAdmissionSnapshot) -> dict:
    return {
        "as_of_ns": snapshot.as_of_ns,
        "status": snapshot.status,
        "admission_results": [sleeve_admission_result_to_dict(result) for result in snapshot.admission_results],
        "portfolio_summary": sleeve_admission_portfolio_summary_to_dict(snapshot.portfolio_summary),
        "history": [sleeve_admission_history_entry_to_dict(entry) for entry in snapshot.history],
    }


def sleeve_admission_snapshot_from_dict(data: dict) -> SleeveAdmissionSnapshot:
    if not isinstance(data, dict):
        raise SleeveAdmissionCorruptError(f"Sleeve admission snapshot must be a dict, got {type(data).__name__!r}")
    summary = sleeve_admission_portfolio_summary_from_dict(dict(data.get("portfolio_summary")))
    as_of_ns = _require_int(data.get("as_of_ns"), "as_of_ns")
    if as_of_ns != summary.as_of_ns:
        raise SleeveAdmissionCorruptError("Sleeve admission timestamp does not match portfolio summary")
    results_value = data.get("admission_results")
    if results_value is None:
        results = summary.admission_results
    elif isinstance(results_value, (list, tuple)):
        results = tuple(sleeve_admission_result_from_dict(dict(item)) for item in results_value)
    else:
        raise SleeveAdmissionCorruptError("Sleeve admission field 'admission_results' must be a list/tuple")
    if results != summary.admission_results:
        raise SleeveAdmissionCorruptError("Sleeve admission results do not match portfolio summary")
    history_value = data.get("history", ())
    if not isinstance(history_value, (list, tuple)):
        raise SleeveAdmissionCorruptError("Sleeve admission field 'history' must be a list/tuple")
    return SleeveAdmissionSnapshot(
        as_of_ns=as_of_ns,
        status=_require_non_empty_str(data.get("status"), "status"),
        admission_results=results,
        portfolio_summary=summary,
        history=tuple(sleeve_admission_history_entry_from_dict(dict(item)) for item in history_value),
    )


def build_sleeve_admission_release_pack(
    admission_snapshot: SleeveAdmissionSnapshot,
    *,
    promotion_review_snapshot: SleevePromotionReviewSnapshot | None = None,
    candidate_workflow_snapshot: SleeveCandidateWorkflowSnapshot | None = None,
    portfolio_snapshot: SleevePortfolioSnapshot | None = None,
    campaign_report: CampaignReport | None = None,
    readiness_flags: dict[str, bool] | None = None,
    pack_id: str | None = None,
) -> SleeveAdmissionReleasePack:
    """Build one deterministic operator-facing sleeve admission release artifact."""
    _validate_admission_snapshot(admission_snapshot)
    if promotion_review_snapshot is not None and not isinstance(
        promotion_review_snapshot, SleevePromotionReviewSnapshot
    ):
        raise SleeveAdmissionCorruptError("promotion_review_snapshot must be a SleevePromotionReviewSnapshot")
    if candidate_workflow_snapshot is not None and not isinstance(
        candidate_workflow_snapshot, SleeveCandidateWorkflowSnapshot
    ):
        raise SleeveAdmissionCorruptError("candidate_workflow_snapshot must be a SleeveCandidateWorkflowSnapshot")
    if portfolio_snapshot is not None and not isinstance(portfolio_snapshot, SleevePortfolioSnapshot):
        raise SleeveAdmissionCorruptError("portfolio_snapshot must be a SleevePortfolioSnapshot")
    if campaign_report is not None and not isinstance(campaign_report, CampaignReport):
        raise SleeveAdmissionCorruptError("campaign_report must be a CampaignReport")
    if readiness_flags is not None and not isinstance(readiness_flags, dict):
        raise SleeveAdmissionCorruptError("readiness_flags must be a dict")

    summary = admission_snapshot.portfolio_summary
    source_promotion_review_as_of_ns = None if promotion_review_snapshot is None else promotion_review_snapshot.as_of_ns
    source_candidate_workflow_as_of_ns = (
        None if candidate_workflow_snapshot is None else candidate_workflow_snapshot.as_of_ns
    )
    source_portfolio_as_of_ns = None if portfolio_snapshot is None else portfolio_snapshot.as_of_ns
    as_of_ns = max(
        item
        for item in (
            admission_snapshot.as_of_ns,
            summary.as_of_ns,
            source_promotion_review_as_of_ns,
            source_candidate_workflow_as_of_ns,
            source_portfolio_as_of_ns,
        )
        if item is not None
    )
    evidence_gate = _build_release_evidence_gate(
        summary,
        promotion_review_snapshot=promotion_review_snapshot,
        portfolio_snapshot=portfolio_snapshot,
        campaign_report=campaign_report,
        readiness_flags=readiness_flags,
    )
    status = _evidence_gated_release_status(_derive_release_status(summary), evidence_gate.status, summary)
    evidence_blockers = _combined_release_evidence_blockers(summary.evidence_blockers, evidence_gate.blockers)
    deterministic_replay_key = _release_replay_key(
        as_of_ns=as_of_ns,
        overall_release_status=status,
        portfolio_summary=summary,
        evidence_gate_status=evidence_gate.status,
        paper_campaign_evidence_available=evidence_gate.paper_campaign_evidence_available,
        sleeve_campaign_link_available=evidence_gate.sleeve_campaign_link_available,
        promotion_review_evidence_available=evidence_gate.promotion_review_evidence_available,
        readiness_evidence_supportive=evidence_gate.readiness_evidence_supportive,
        tca_or_markout_evidence_supportive=evidence_gate.tca_or_markout_evidence_supportive,
        external_regime_evidence_supportive=evidence_gate.external_regime_evidence_supportive,
        paper_evidence_blockers=evidence_gate.blockers,
        per_sleeve_evidence_blockers=evidence_gate.per_sleeve_blockers,
        source_admission_as_of_ns=admission_snapshot.as_of_ns,
        source_promotion_review_as_of_ns=source_promotion_review_as_of_ns,
        source_candidate_workflow_as_of_ns=source_candidate_workflow_as_of_ns,
        source_portfolio_as_of_ns=source_portfolio_as_of_ns,
        admission_snapshot_status=admission_snapshot.status,
        promotion_review_status=None if promotion_review_snapshot is None else promotion_review_snapshot.status,
        candidate_workflow_status=None if candidate_workflow_snapshot is None else candidate_workflow_snapshot.status,
    )
    release_pack = SleeveAdmissionReleasePack(
        pack_id=pack_id or _release_pack_id(as_of_ns, summary.admission_results),
        as_of_ns=as_of_ns,
        overall_release_status=status,
        portfolio_summary=summary,
        per_sleeve_admission_results=admission_snapshot.admission_results,
        admitted_sleeves=_admitted_sleeves(summary),
        admitted_active_sleeves=summary.admitted_active,
        admitted_unallocated_sleeves=summary.admitted_unallocated,
        review_supported_not_admitted_sleeves=summary.review_supported_not_admitted,
        blocked_sleeves=summary.blocked,
        inconclusive_sleeves=summary.inconclusive,
        evidence_blockers=evidence_blockers,
        governance_blockers=summary.governance_blockers,
        next_actions=_release_next_actions(summary.admission_results),
        deterministic_replay_key=deterministic_replay_key,
        source_admission_as_of_ns=admission_snapshot.as_of_ns,
        source_promotion_review_as_of_ns=source_promotion_review_as_of_ns,
        source_candidate_workflow_as_of_ns=source_candidate_workflow_as_of_ns,
        source_portfolio_as_of_ns=source_portfolio_as_of_ns,
        admission_snapshot_status=admission_snapshot.status,
        promotion_review_status=None if promotion_review_snapshot is None else promotion_review_snapshot.status,
        candidate_workflow_status=None if candidate_workflow_snapshot is None else candidate_workflow_snapshot.status,
        portfolio_sleeve_count=None if portfolio_snapshot is None else len(portfolio_snapshot.sleeves),
        operator_summary=_release_operator_summary(status, summary, evidence_gate.status),
        insufficient_evidence_sleeves=summary.insufficient_evidence,
        disabled_operator_off_sleeves=summary.disabled_operator_off,
        paper_campaign_evidence_available=evidence_gate.paper_campaign_evidence_available,
        sleeve_campaign_link_available=evidence_gate.sleeve_campaign_link_available,
        promotion_review_evidence_available=evidence_gate.promotion_review_evidence_available,
        readiness_evidence_supportive=evidence_gate.readiness_evidence_supportive,
        tca_or_markout_evidence_supportive=evidence_gate.tca_or_markout_evidence_supportive,
        external_regime_evidence_supportive=evidence_gate.external_regime_evidence_supportive,
        evidence_gate_status=evidence_gate.status,
        evidence_gate_summary=evidence_gate.summary,
        paper_evidence_blockers=evidence_gate.blockers,
        per_sleeve_evidence_blockers=evidence_gate.per_sleeve_blockers,
    )
    _validate_release_pack(release_pack)
    return release_pack


def sleeve_admission_release_action_to_dict(action: SleeveAdmissionReleaseAction) -> dict:
    return {
        "sleeve_id": action.sleeve_id,
        "admission_verdict": action.admission_verdict.value,
        "next_action": action.next_action,
        "evidence_blockers": list(action.evidence_blockers),
        "governance_blockers": list(action.governance_blockers),
    }


def sleeve_admission_release_action_from_dict(data: dict) -> SleeveAdmissionReleaseAction:
    if not isinstance(data, dict):
        raise SleeveAdmissionCorruptError(
            f"Sleeve admission release action must be a dict, got {type(data).__name__!r}"
        )
    return SleeveAdmissionReleaseAction(
        sleeve_id=_require_non_empty_str(data.get("sleeve_id"), "sleeve_id"),
        admission_verdict=_admission_verdict(data.get("admission_verdict"), "admission_verdict"),
        next_action="" if data.get("next_action", "") is None else str(data.get("next_action", "")),
        evidence_blockers=_tuple_of_strings(data.get("evidence_blockers", ()), "evidence_blockers"),
        governance_blockers=_tuple_of_strings(data.get("governance_blockers", ()), "governance_blockers"),
    )


def sleeve_admission_release_sleeve_evidence_to_dict(evidence: SleeveAdmissionReleaseSleeveEvidence) -> dict:
    return {
        "sleeve_id": evidence.sleeve_id,
        "evidence_blockers": list(evidence.evidence_blockers),
    }


def sleeve_admission_release_sleeve_evidence_from_dict(data: dict) -> SleeveAdmissionReleaseSleeveEvidence:
    if not isinstance(data, dict):
        raise SleeveAdmissionCorruptError(
            f"Sleeve admission release sleeve evidence must be a dict, got {type(data).__name__!r}"
        )
    return SleeveAdmissionReleaseSleeveEvidence(
        sleeve_id=_require_non_empty_str(data.get("sleeve_id"), "sleeve_id"),
        evidence_blockers=_tuple_of_strings(data.get("evidence_blockers", ()), "evidence_blockers"),
    )


def sleeve_admission_release_pack_to_dict(pack: SleeveAdmissionReleasePack) -> dict:
    return {
        "pack_id": pack.pack_id,
        "as_of_ns": pack.as_of_ns,
        "overall_release_status": pack.overall_release_status.value,
        "portfolio_summary": sleeve_admission_portfolio_summary_to_dict(pack.portfolio_summary),
        "per_sleeve_admission_results": [
            sleeve_admission_result_to_dict(result) for result in pack.per_sleeve_admission_results
        ],
        "admitted_sleeves": list(pack.admitted_sleeves),
        "admitted_active_sleeves": list(pack.admitted_active_sleeves),
        "admitted_unallocated_sleeves": list(pack.admitted_unallocated_sleeves),
        "review_supported_not_admitted_sleeves": list(pack.review_supported_not_admitted_sleeves),
        "blocked_sleeves": list(pack.blocked_sleeves),
        "inconclusive_sleeves": list(pack.inconclusive_sleeves),
        "insufficient_evidence_sleeves": list(pack.insufficient_evidence_sleeves),
        "disabled_operator_off_sleeves": list(pack.disabled_operator_off_sleeves),
        "evidence_blockers": list(pack.evidence_blockers),
        "governance_blockers": list(pack.governance_blockers),
        "next_actions": [sleeve_admission_release_action_to_dict(action) for action in pack.next_actions],
        "paper_campaign_evidence_available": pack.paper_campaign_evidence_available,
        "sleeve_campaign_link_available": pack.sleeve_campaign_link_available,
        "promotion_review_evidence_available": pack.promotion_review_evidence_available,
        "readiness_evidence_supportive": pack.readiness_evidence_supportive,
        "tca_or_markout_evidence_supportive": pack.tca_or_markout_evidence_supportive,
        "external_regime_evidence_supportive": pack.external_regime_evidence_supportive,
        "evidence_gate_status": pack.evidence_gate_status.value,
        "evidence_gate_summary": pack.evidence_gate_summary,
        "paper_evidence_blockers": list(pack.paper_evidence_blockers),
        "per_sleeve_evidence_blockers": [
            sleeve_admission_release_sleeve_evidence_to_dict(evidence) for evidence in pack.per_sleeve_evidence_blockers
        ],
        "overall_release_summary": pack.operator_summary,
        "operator_summary": pack.operator_summary,
        "deterministic_replay_key": pack.deterministic_replay_key,
        "source_admission_as_of_ns": pack.source_admission_as_of_ns,
        "source_promotion_review_as_of_ns": pack.source_promotion_review_as_of_ns,
        "source_candidate_workflow_as_of_ns": pack.source_candidate_workflow_as_of_ns,
        "source_portfolio_as_of_ns": pack.source_portfolio_as_of_ns,
        "admission_snapshot_status": pack.admission_snapshot_status,
        "promotion_review_status": pack.promotion_review_status,
        "candidate_workflow_status": pack.candidate_workflow_status,
        "portfolio_sleeve_count": pack.portfolio_sleeve_count,
    }


def sleeve_admission_release_pack_from_dict(data: dict) -> SleeveAdmissionReleasePack:
    if not isinstance(data, dict):
        raise SleeveAdmissionCorruptError(f"Sleeve admission release pack must be a dict, got {type(data).__name__!r}")
    summary = sleeve_admission_portfolio_summary_from_dict(
        _dict_value(data.get("portfolio_summary"), "portfolio_summary")
    )
    results_value = data.get("per_sleeve_admission_results")
    if results_value is None:
        results = summary.admission_results
    elif isinstance(results_value, (list, tuple)):
        results = tuple(_admission_result_from_value(item) for item in results_value)
    else:
        raise SleeveAdmissionCorruptError(
            "Sleeve admission release field 'per_sleeve_admission_results' must be a list/tuple"
        )
    if results != summary.admission_results:
        raise SleeveAdmissionCorruptError("Sleeve admission release results do not match portfolio summary")

    source_admission_as_of_ns = _require_int(
        data.get("source_admission_as_of_ns", summary.as_of_ns),
        "source_admission_as_of_ns",
    )
    source_promotion_review_as_of_ns = _optional_int(
        data.get("source_promotion_review_as_of_ns"),
        "source_promotion_review_as_of_ns",
    )
    source_candidate_workflow_as_of_ns = _optional_int(
        data.get("source_candidate_workflow_as_of_ns"),
        "source_candidate_workflow_as_of_ns",
    )
    source_portfolio_as_of_ns = _optional_int(data.get("source_portfolio_as_of_ns"), "source_portfolio_as_of_ns")
    as_of_ns = _require_int(
        data.get(
            "as_of_ns",
            max(
                item
                for item in (
                    source_admission_as_of_ns,
                    source_promotion_review_as_of_ns,
                    source_candidate_workflow_as_of_ns,
                    source_portfolio_as_of_ns,
                )
                if item is not None
            ),
        ),
        "as_of_ns",
    )
    admission_snapshot_status = _string_or_default(data.get("admission_snapshot_status"), "unknown")
    promotion_review_status = _optional_string_value(data.get("promotion_review_status"), "promotion_review_status")
    candidate_workflow_status = _optional_string_value(
        data.get("candidate_workflow_status"), "candidate_workflow_status"
    )
    portfolio_sleeve_count = _optional_int(data.get("portfolio_sleeve_count"), "portfolio_sleeve_count")
    explicit_evidence_fields = _has_release_evidence_fields(data)
    paper_campaign_evidence_available = _bool_or_default(data, "paper_campaign_evidence_available", False)
    sleeve_campaign_link_available = _bool_or_default(data, "sleeve_campaign_link_available", False)
    promotion_review_evidence_available = _bool_or_default(data, "promotion_review_evidence_available", False)
    readiness_evidence_supportive = _bool_or_default(data, "readiness_evidence_supportive", False)
    tca_or_markout_evidence_supportive = _bool_or_default(data, "tca_or_markout_evidence_supportive", False)
    external_regime_evidence_supportive = _bool_or_default(data, "external_regime_evidence_supportive", False)
    paper_evidence_blockers = _tuple_or_default(
        data,
        "paper_evidence_blockers",
        _legacy_missing_release_evidence_blockers(summary),
    )
    per_sleeve_evidence_blockers = _release_sleeve_evidence_or_default(data, results, paper_evidence_blockers)
    evidence_gate_status = _release_evidence_status_or_default(
        data.get("evidence_gate_status"),
        _infer_release_evidence_status(
            summary,
            paper_evidence_blockers,
            paper_campaign_evidence_available=paper_campaign_evidence_available,
            sleeve_campaign_link_available=sleeve_campaign_link_available,
            promotion_review_evidence_available=promotion_review_evidence_available,
            readiness_evidence_supportive=readiness_evidence_supportive,
            tca_or_markout_evidence_supportive=tca_or_markout_evidence_supportive,
            external_regime_evidence_supportive=external_regime_evidence_supportive,
        ),
    )
    base_status = _release_status_or_default(data.get("overall_release_status"), summary)
    status = _evidence_gated_release_status(base_status, evidence_gate_status, summary)
    if explicit_evidence_fields and base_status != status:
        raise SleeveAdmissionCorruptError("Sleeve admission release status does not match evidence gate")
    evidence_blockers = _combined_release_evidence_blockers(summary.evidence_blockers, paper_evidence_blockers)
    deterministic_replay_key = _string_or_default(
        data.get("deterministic_replay_key") if explicit_evidence_fields else None,
        _release_replay_key(
            as_of_ns=as_of_ns,
            overall_release_status=status,
            portfolio_summary=summary,
            evidence_gate_status=evidence_gate_status,
            paper_campaign_evidence_available=paper_campaign_evidence_available,
            sleeve_campaign_link_available=sleeve_campaign_link_available,
            promotion_review_evidence_available=promotion_review_evidence_available,
            readiness_evidence_supportive=readiness_evidence_supportive,
            tca_or_markout_evidence_supportive=tca_or_markout_evidence_supportive,
            external_regime_evidence_supportive=external_regime_evidence_supportive,
            paper_evidence_blockers=paper_evidence_blockers,
            per_sleeve_evidence_blockers=per_sleeve_evidence_blockers,
            source_admission_as_of_ns=source_admission_as_of_ns,
            source_promotion_review_as_of_ns=source_promotion_review_as_of_ns,
            source_candidate_workflow_as_of_ns=source_candidate_workflow_as_of_ns,
            source_portfolio_as_of_ns=source_portfolio_as_of_ns,
            admission_snapshot_status=admission_snapshot_status,
            promotion_review_status=promotion_review_status,
            candidate_workflow_status=candidate_workflow_status,
        ),
    )
    release_pack = SleeveAdmissionReleasePack(
        pack_id=_string_or_default(data.get("pack_id"), _release_pack_id(as_of_ns, results)),
        as_of_ns=as_of_ns,
        overall_release_status=status,
        portfolio_summary=summary,
        per_sleeve_admission_results=results,
        admitted_sleeves=_tuple_or_default(data, "admitted_sleeves", _admitted_sleeves(summary)),
        admitted_active_sleeves=_tuple_or_default(data, "admitted_active_sleeves", summary.admitted_active),
        admitted_unallocated_sleeves=_tuple_or_default(
            data,
            "admitted_unallocated_sleeves",
            summary.admitted_unallocated,
        ),
        review_supported_not_admitted_sleeves=_tuple_or_default(
            data,
            "review_supported_not_admitted_sleeves",
            summary.review_supported_not_admitted,
        ),
        blocked_sleeves=_tuple_or_default(data, "blocked_sleeves", summary.blocked),
        inconclusive_sleeves=_tuple_or_default(data, "inconclusive_sleeves", summary.inconclusive),
        evidence_blockers=(
            _tuple_or_default(data, "evidence_blockers", evidence_blockers)
            if explicit_evidence_fields
            else evidence_blockers
        ),
        governance_blockers=_tuple_or_default(data, "governance_blockers", summary.governance_blockers),
        next_actions=_release_actions_or_default(data, results),
        deterministic_replay_key=deterministic_replay_key,
        source_admission_as_of_ns=source_admission_as_of_ns,
        source_promotion_review_as_of_ns=source_promotion_review_as_of_ns,
        source_candidate_workflow_as_of_ns=source_candidate_workflow_as_of_ns,
        source_portfolio_as_of_ns=source_portfolio_as_of_ns,
        admission_snapshot_status=admission_snapshot_status,
        promotion_review_status=promotion_review_status,
        candidate_workflow_status=candidate_workflow_status,
        portfolio_sleeve_count=portfolio_sleeve_count,
        operator_summary=_string_or_default(
            data.get("operator_summary", data.get("overall_release_summary")) if explicit_evidence_fields else None,
            _release_operator_summary(status, summary, evidence_gate_status),
        ),
        insufficient_evidence_sleeves=_tuple_or_default(
            data,
            "insufficient_evidence_sleeves",
            summary.insufficient_evidence,
        ),
        disabled_operator_off_sleeves=_tuple_or_default(
            data,
            "disabled_operator_off_sleeves",
            summary.disabled_operator_off,
        ),
        paper_campaign_evidence_available=paper_campaign_evidence_available,
        sleeve_campaign_link_available=sleeve_campaign_link_available,
        promotion_review_evidence_available=promotion_review_evidence_available,
        readiness_evidence_supportive=readiness_evidence_supportive,
        tca_or_markout_evidence_supportive=tca_or_markout_evidence_supportive,
        external_regime_evidence_supportive=external_regime_evidence_supportive,
        evidence_gate_status=evidence_gate_status,
        evidence_gate_summary=_string_or_default(
            data.get("evidence_gate_summary") if explicit_evidence_fields else None,
            _release_evidence_summary(evidence_gate_status, paper_evidence_blockers),
        ),
        paper_evidence_blockers=paper_evidence_blockers,
        per_sleeve_evidence_blockers=per_sleeve_evidence_blockers,
    )
    _validate_release_pack(release_pack)
    return release_pack


def build_managed_sleeve_set_manifest(
    release_pack: SleeveAdmissionReleasePack,
    *,
    portfolio_snapshot: SleevePortfolioSnapshot | None = None,
    manifest_id: str | None = None,
) -> ManagedSleeveSetManifest:
    """Build a deterministic paper-only activation manifest from release truth."""
    if not isinstance(release_pack, SleeveAdmissionReleasePack):
        raise SleeveAdmissionCorruptError("managed sleeve manifest requires a SleeveAdmissionReleasePack")
    _validate_release_pack(release_pack)
    if portfolio_snapshot is not None and not isinstance(portfolio_snapshot, SleevePortfolioSnapshot):
        raise SleeveAdmissionCorruptError("portfolio_snapshot must be a SleevePortfolioSnapshot")

    allocations = _manifest_effective_allocations(release_pack)
    active_sleeves = tuple(item.sleeve_id for item in allocations)
    admitted_unallocated = _sorted_unique(release_pack.admitted_unallocated_sleeves)
    blocked_sleeves = _sorted_unique((*release_pack.blocked_sleeves, *release_pack.disabled_operator_off_sleeves))
    inconclusive_sleeves = _sorted_unique(
        (
            *release_pack.inconclusive_sleeves,
            *release_pack.review_supported_not_admitted_sleeves,
            *release_pack.insufficient_evidence_sleeves,
        )
    )
    unallocated_share = _manifest_unallocated_share(portfolio_snapshot, allocations)
    activation_blockers = _manifest_activation_blockers(
        release_pack,
        allocations=allocations,
        unallocated_share=unallocated_share,
    )
    dry_run_status = _derive_manifest_dry_run_status(
        source_release_pack_status=release_pack.overall_release_status,
        source_evidence_gate_status=release_pack.evidence_gate_status,
        active_sleeves=active_sleeves,
        activation_blockers=activation_blockers,
        candidate_count=len(release_pack.per_sleeve_admission_results),
    )
    source_hash = _release_pack_hash(release_pack)
    manifest = ManagedSleeveSetManifest(
        manifest_id=manifest_id or _managed_sleeve_manifest_id(release_pack.as_of_ns, source_hash),
        as_of_ns=release_pack.as_of_ns,
        source_release_pack_status=release_pack.overall_release_status,
        source_release_pack_id=release_pack.pack_id,
        source_release_pack_as_of_ns=release_pack.as_of_ns,
        source_release_pack_replay_key=release_pack.deterministic_replay_key,
        source_release_pack_hash=source_hash,
        source_evidence_gate_status=release_pack.evidence_gate_status,
        active_sleeves=active_sleeves,
        admitted_unallocated_sleeves=admitted_unallocated,
        blocked_sleeves=blocked_sleeves,
        inconclusive_sleeves=inconclusive_sleeves,
        effective_allocations=allocations,
        unallocated_share=unallocated_share,
        activation_blockers=activation_blockers,
        evidence_blockers=_sorted_unique((*release_pack.evidence_blockers, *release_pack.paper_evidence_blockers)),
        governance_blockers=_sorted_unique(release_pack.governance_blockers),
        dry_run_status=dry_run_status,
        next_actions=tuple(sorted(release_pack.next_actions, key=lambda item: item.sleeve_id)),
        operator_summary=_manifest_operator_summary(
            dry_run_status, active_sleeves, admitted_unallocated, blocked_sleeves
        ),
    )
    _validate_managed_sleeve_set_manifest(manifest)
    return manifest


def managed_sleeve_allocation_to_dict(allocation: ManagedSleeveAllocation) -> dict:
    return {
        "sleeve_id": allocation.sleeve_id,
        "effective_allocation": allocation.effective_allocation,
    }


def managed_sleeve_allocation_from_dict(data: dict) -> ManagedSleeveAllocation:
    if not isinstance(data, dict):
        raise SleeveAdmissionCorruptError(f"Managed sleeve allocation must be a dict, got {type(data).__name__!r}")
    allocation = ManagedSleeveAllocation(
        sleeve_id=_require_non_empty_str(data.get("sleeve_id"), "sleeve_id"),
        effective_allocation=_require_float(data.get("effective_allocation"), "effective_allocation"),
    )
    _validate_manifest_allocation(allocation)
    return allocation


def managed_sleeve_set_manifest_to_dict(manifest: ManagedSleeveSetManifest) -> dict:
    _validate_managed_sleeve_set_manifest(manifest)
    return {
        "manifest_id": manifest.manifest_id,
        "as_of_ns": manifest.as_of_ns,
        "source_release_pack_status": manifest.source_release_pack_status.value,
        "source_release_pack_id": manifest.source_release_pack_id,
        "source_release_pack_as_of_ns": manifest.source_release_pack_as_of_ns,
        "source_release_pack_replay_key": manifest.source_release_pack_replay_key,
        "source_release_pack_hash": manifest.source_release_pack_hash,
        "source_evidence_gate_status": manifest.source_evidence_gate_status.value,
        "active_sleeves": list(manifest.active_sleeves),
        "admitted_unallocated_sleeves": list(manifest.admitted_unallocated_sleeves),
        "blocked_sleeves": list(manifest.blocked_sleeves),
        "inconclusive_sleeves": list(manifest.inconclusive_sleeves),
        "effective_allocations": [
            managed_sleeve_allocation_to_dict(allocation) for allocation in manifest.effective_allocations
        ],
        "unallocated_share": manifest.unallocated_share,
        "activation_blockers": list(manifest.activation_blockers),
        "evidence_blockers": list(manifest.evidence_blockers),
        "governance_blockers": list(manifest.governance_blockers),
        "dry_run_status": manifest.dry_run_status.value,
        "next_actions": [sleeve_admission_release_action_to_dict(action) for action in manifest.next_actions],
        "operator_summary": manifest.operator_summary,
    }


def managed_sleeve_set_manifest_from_dict(data: dict) -> ManagedSleeveSetManifest:
    if not isinstance(data, dict):
        raise SleeveAdmissionCorruptError(f"Managed sleeve set manifest must be a dict, got {type(data).__name__!r}")

    source_release_pack_status = _manifest_release_status_or_default(
        data.get("source_release_pack_status"),
        SleeveAdmissionReleaseStatus.INCONCLUSIVE,
    )
    source_evidence_gate_status = _release_evidence_status_or_default(
        data.get("source_evidence_gate_status"),
        SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_MISSING,
    )
    source_release_pack_as_of_ns = _require_int(
        data.get("source_release_pack_as_of_ns", data.get("as_of_ns", 0)),
        "source_release_pack_as_of_ns",
    )
    as_of_ns = _require_int(data.get("as_of_ns", source_release_pack_as_of_ns), "as_of_ns")
    source_release_pack_replay_key = _string_or_default(data.get("source_release_pack_replay_key"), "unknown")
    source_release_pack_hash = _string_or_default(
        data.get("source_release_pack_hash"),
        hashlib.sha256(source_release_pack_replay_key.encode("utf-8")).hexdigest(),
    )
    allocations = _manifest_allocations_from_data(data)
    has_explicit_allocations = "effective_allocations" in data
    if not has_explicit_allocations:
        active_sleeves = ()
    elif "active_sleeves" in data:
        active_sleeves = _sorted_unique(data.get("active_sleeves", ()))
    else:
        active_sleeves = tuple(item.sleeve_id for item in allocations)
    admitted_unallocated = _sorted_unique(data.get("admitted_unallocated_sleeves", ()))
    blocked_sleeves = _sorted_unique(data.get("blocked_sleeves", ()))
    inconclusive_sleeves = _sorted_unique(data.get("inconclusive_sleeves", ()))
    unallocated_share = _require_float(data.get("unallocated_share", 1.0), "unallocated_share")
    candidate_count = len(active_sleeves) + len(admitted_unallocated) + len(blocked_sleeves) + len(inconclusive_sleeves)
    activation_blockers = _manifest_activation_blockers_from_fields(
        source_release_pack_status=source_release_pack_status,
        source_evidence_gate_status=source_evidence_gate_status,
        active_sleeves=active_sleeves,
        allocations=allocations,
        unallocated_share=unallocated_share,
        candidate_count=candidate_count,
        explicit_blockers=_sorted_unique(data.get("activation_blockers", ())),
    )
    dry_run_status = _manifest_dry_run_status_or_default(
        data.get("dry_run_status"),
        _derive_manifest_dry_run_status(
            source_release_pack_status=source_release_pack_status,
            source_evidence_gate_status=source_evidence_gate_status,
            active_sleeves=active_sleeves,
            activation_blockers=activation_blockers,
            candidate_count=candidate_count,
        ),
    )
    manifest = ManagedSleeveSetManifest(
        manifest_id=_string_or_default(
            data.get("manifest_id"),
            _managed_sleeve_manifest_id(as_of_ns, source_release_pack_hash),
        ),
        as_of_ns=as_of_ns,
        source_release_pack_status=source_release_pack_status,
        source_release_pack_id=_string_or_default(data.get("source_release_pack_id"), "unknown"),
        source_release_pack_as_of_ns=source_release_pack_as_of_ns,
        source_release_pack_replay_key=source_release_pack_replay_key,
        source_release_pack_hash=source_release_pack_hash,
        source_evidence_gate_status=source_evidence_gate_status,
        active_sleeves=active_sleeves,
        admitted_unallocated_sleeves=admitted_unallocated,
        blocked_sleeves=blocked_sleeves,
        inconclusive_sleeves=inconclusive_sleeves,
        effective_allocations=allocations,
        unallocated_share=unallocated_share,
        activation_blockers=activation_blockers,
        evidence_blockers=_sorted_unique(data.get("evidence_blockers", ())),
        governance_blockers=_sorted_unique(data.get("governance_blockers", ())),
        dry_run_status=dry_run_status,
        next_actions=tuple(sorted(_release_actions_or_default(data, ()), key=lambda item: item.sleeve_id)),
        operator_summary=_string_or_default(
            data.get("operator_summary"),
            _manifest_operator_summary(dry_run_status, active_sleeves, admitted_unallocated, blocked_sleeves),
        ),
    )
    _validate_managed_sleeve_set_manifest(manifest)
    return manifest


def build_paper_shadow_activation_plan(
    manifest: ManagedSleeveSetManifest,
    *,
    plan_id: str | None = None,
) -> PaperShadowActivationPlan:
    """Build a deterministic paper/shadow-only activation contract from a manifest."""
    if not isinstance(manifest, ManagedSleeveSetManifest):
        raise SleeveAdmissionCorruptError("paper/shadow activation plan requires a ManagedSleeveSetManifest")
    _validate_managed_sleeve_set_manifest(manifest)

    source_manifest_hash = _managed_sleeve_manifest_hash(manifest)
    inactive_sleeves = _sorted_unique(
        (
            *manifest.admitted_unallocated_sleeves,
            *manifest.blocked_sleeves,
            *manifest.inconclusive_sleeves,
        )
    )
    activation_blockers = _paper_shadow_activation_blockers(manifest)
    activation_status = _derive_paper_shadow_activation_status(
        source_manifest_status=manifest.dry_run_status,
        active_sleeves=manifest.active_sleeves,
        activation_blockers=activation_blockers,
    )
    plan = PaperShadowActivationPlan(
        plan_id=plan_id or _paper_shadow_activation_plan_id(manifest.as_of_ns, source_manifest_hash),
        as_of_ns=manifest.as_of_ns,
        source_manifest_status=manifest.dry_run_status,
        source_manifest_id=manifest.manifest_id,
        source_manifest_as_of_ns=manifest.as_of_ns,
        source_manifest_hash=source_manifest_hash,
        paper_only=True,
        real_orders_enabled=False,
        real_money_enabled=False,
        active_sleeves=manifest.active_sleeves,
        inactive_sleeves=inactive_sleeves,
        admitted_unallocated_sleeves=manifest.admitted_unallocated_sleeves,
        effective_allocations=manifest.effective_allocations,
        preflight_gates=_paper_shadow_preflight_gates(manifest),
        activation_blockers=activation_blockers,
        evidence_blockers=manifest.evidence_blockers,
        governance_blockers=manifest.governance_blockers,
        runtime_monitoring_requirements=_paper_shadow_runtime_monitoring_requirements(),
        kill_switch_requirements=_paper_shadow_kill_switch_requirements(),
        next_actions=manifest.next_actions,
        activation_status=activation_status,
        operator_summary=_paper_shadow_operator_summary(activation_status, manifest.active_sleeves, inactive_sleeves),
    )
    _validate_paper_shadow_activation_plan(plan)
    return plan


def paper_shadow_activation_plan_to_dict(plan: PaperShadowActivationPlan) -> dict:
    _validate_paper_shadow_activation_plan(plan)
    return {
        "plan_id": plan.plan_id,
        "as_of_ns": plan.as_of_ns,
        "source_manifest_status": plan.source_manifest_status.value,
        "source_manifest_id": plan.source_manifest_id,
        "source_manifest_as_of_ns": plan.source_manifest_as_of_ns,
        "source_manifest_hash": plan.source_manifest_hash,
        "paper_only": plan.paper_only,
        "real_orders_enabled": plan.real_orders_enabled,
        "real_money_enabled": plan.real_money_enabled,
        "active_sleeves": list(plan.active_sleeves),
        "inactive_sleeves": list(plan.inactive_sleeves),
        "admitted_unallocated_sleeves": list(plan.admitted_unallocated_sleeves),
        "effective_allocations": [
            managed_sleeve_allocation_to_dict(allocation) for allocation in plan.effective_allocations
        ],
        "preflight_gates": list(plan.preflight_gates),
        "activation_blockers": list(plan.activation_blockers),
        "evidence_blockers": list(plan.evidence_blockers),
        "governance_blockers": list(plan.governance_blockers),
        "runtime_monitoring_requirements": list(plan.runtime_monitoring_requirements),
        "kill_switch_requirements": list(plan.kill_switch_requirements),
        "next_actions": [sleeve_admission_release_action_to_dict(action) for action in plan.next_actions],
        "activation_status": plan.activation_status.value,
        "operator_summary": plan.operator_summary,
    }


def paper_shadow_activation_plan_from_dict(data: dict) -> PaperShadowActivationPlan:
    if not isinstance(data, dict):
        raise SleeveAdmissionCorruptError(f"Paper/shadow activation plan must be a dict, got {type(data).__name__!r}")
    source_manifest_status = _manifest_dry_run_status_or_default(
        data.get("source_manifest_status"),
        ManagedSleeveSetDryRunStatus.INCONCLUSIVE,
    )
    active_sleeves = _sorted_unique(data.get("active_sleeves", ()))
    allocations = _manifest_allocations_from_data(data)
    inactive_sleeves = _sorted_unique(data.get("inactive_sleeves", ()))
    admitted_unallocated = _sorted_unique(data.get("admitted_unallocated_sleeves", ()))
    activation_blockers = _sorted_unique(
        data.get(
            "activation_blockers",
            _paper_shadow_activation_blockers_from_fields(
                source_manifest_status=source_manifest_status,
                active_sleeves=active_sleeves,
                evidence_blockers=_sorted_unique(data.get("evidence_blockers", ())),
                governance_blockers=_sorted_unique(data.get("governance_blockers", ())),
            ),
        )
    )
    activation_status = _paper_shadow_activation_status_or_default(
        data.get("activation_status"),
        _derive_paper_shadow_activation_status(
            source_manifest_status=source_manifest_status,
            active_sleeves=active_sleeves,
            activation_blockers=activation_blockers,
        ),
    )
    plan = PaperShadowActivationPlan(
        plan_id=_string_or_default(data.get("plan_id"), _paper_shadow_activation_plan_id(0, "unknown")),
        as_of_ns=_require_int(data.get("as_of_ns", data.get("source_manifest_as_of_ns", 0)), "as_of_ns"),
        source_manifest_status=source_manifest_status,
        source_manifest_id=_string_or_default(data.get("source_manifest_id"), "unknown"),
        source_manifest_as_of_ns=_require_int(
            data.get("source_manifest_as_of_ns", data.get("as_of_ns", 0)),
            "source_manifest_as_of_ns",
        ),
        source_manifest_hash=_string_or_default(data.get("source_manifest_hash"), "unknown"),
        paper_only=_bool_or_default(data, "paper_only", True),
        real_orders_enabled=_bool_or_default(data, "real_orders_enabled", False),
        real_money_enabled=_bool_or_default(data, "real_money_enabled", False),
        active_sleeves=active_sleeves,
        inactive_sleeves=inactive_sleeves,
        admitted_unallocated_sleeves=admitted_unallocated,
        effective_allocations=allocations,
        preflight_gates=_sorted_unique(data.get("preflight_gates", _paper_shadow_preflight_gates_from_fields())),
        activation_blockers=activation_blockers,
        evidence_blockers=_sorted_unique(data.get("evidence_blockers", ())),
        governance_blockers=_sorted_unique(data.get("governance_blockers", ())),
        runtime_monitoring_requirements=_sorted_unique(
            data.get("runtime_monitoring_requirements", _paper_shadow_runtime_monitoring_requirements())
        ),
        kill_switch_requirements=_sorted_unique(
            data.get("kill_switch_requirements", _paper_shadow_kill_switch_requirements())
        ),
        next_actions=tuple(sorted(_release_actions_or_default(data, ()), key=lambda item: item.sleeve_id)),
        activation_status=activation_status,
        operator_summary=_string_or_default(
            data.get("operator_summary"),
            _paper_shadow_operator_summary(activation_status, active_sleeves, inactive_sleeves),
        ),
    )
    _validate_paper_shadow_activation_plan(plan)
    return plan


_ADMITTED_VERDICTS = {
    SleeveAdmissionVerdict.ADMITTED_ACTIVE,
    SleeveAdmissionVerdict.ADMITTED_UNALLOCATED,
}
_BLOCKED_VERDICTS = {
    SleeveAdmissionVerdict.BLOCKED,
    SleeveAdmissionVerdict.NOT_ADMITTED_BLOCKED,
}
_INCONCLUSIVE_VERDICTS = {
    SleeveAdmissionVerdict.INCONCLUSIVE,
    SleeveAdmissionVerdict.NOT_ADMITTED_INCONCLUSIVE,
}


def _validate_admission_snapshot(snapshot: SleeveAdmissionSnapshot) -> None:
    if not isinstance(snapshot, SleeveAdmissionSnapshot):
        raise SleeveAdmissionCorruptError("Sleeve admission release requires a SleeveAdmissionSnapshot")
    if snapshot.as_of_ns != snapshot.portfolio_summary.as_of_ns:
        raise SleeveAdmissionCorruptError("Sleeve admission snapshot timestamp does not match portfolio summary")
    if snapshot.admission_results != snapshot.portfolio_summary.admission_results:
        raise SleeveAdmissionCorruptError("Sleeve admission snapshot results do not match portfolio summary")
    _validate_summary_counts(snapshot.portfolio_summary)


def _derive_release_status(summary: SleeveAdmissionPortfolioSummary) -> SleeveAdmissionReleaseStatus:
    result_count = len(summary.admission_results)
    admitted_count = summary.admitted_active_count + summary.admitted_unallocated_count
    hard_blocked_count = summary.blocked_count + summary.disabled_operator_off_count
    unresolved_count = (
        hard_blocked_count
        + summary.review_supported_not_admitted_count
        + summary.inconclusive_count
        + summary.insufficient_evidence_count
    )
    if result_count == 0:
        return SleeveAdmissionReleaseStatus.NO_CANDIDATES
    if admitted_count > 0 and unresolved_count == 0:
        return SleeveAdmissionReleaseStatus.READY_FOR_PAPER_MANAGED_SET
    if admitted_count > 0:
        return SleeveAdmissionReleaseStatus.PARTIAL_READY
    if hard_blocked_count > 0:
        return SleeveAdmissionReleaseStatus.BLOCKED
    return SleeveAdmissionReleaseStatus.INCONCLUSIVE


def _build_release_evidence_gate(
    summary: SleeveAdmissionPortfolioSummary,
    *,
    promotion_review_snapshot: SleevePromotionReviewSnapshot | None,
    portfolio_snapshot: SleevePortfolioSnapshot | None,
    campaign_report: CampaignReport | None,
    readiness_flags: dict[str, bool] | None,
) -> _ReleaseEvidenceGate:
    blockers: list[str] = []
    admitted = _admitted_sleeves(summary)
    paper_campaign_available, paper_campaign_blocker = _paper_campaign_evidence_state(campaign_report)
    if paper_campaign_blocker:
        blockers.append(paper_campaign_blocker)

    sleeve_link_available, missing_link_sleeves = _sleeve_campaign_link_state(
        admitted,
        portfolio_snapshot=portfolio_snapshot,
        campaign_report=campaign_report,
    )
    if admitted and not sleeve_link_available:
        blockers.append("sleeve_campaign_link_unavailable")

    promotion_review_available = _promotion_review_evidence_available(summary, promotion_review_snapshot)
    if len(summary.admission_results) > 0 and not promotion_review_available:
        blockers.append("promotion_review_evidence_unavailable")

    readiness_supportive = _readiness_evidence_supportive(portfolio_snapshot)
    if len(summary.admission_results) > 0 and not readiness_supportive:
        blockers.append("readiness_evidence_not_supportive")

    tca_or_markout_supportive = _tca_or_markout_evidence_supportive(campaign_report, readiness_flags)
    if paper_campaign_available and not tca_or_markout_supportive:
        blockers.append("tca_or_markout_evidence_unavailable")

    external_supportive, external_blockers = _external_regime_evidence_state(campaign_report, readiness_flags)
    blockers.extend(external_blockers)

    paper_blockers = tuple(sorted(dict.fromkeys(blockers)))
    status = _infer_release_evidence_status(
        summary,
        paper_blockers,
        paper_campaign_evidence_available=paper_campaign_available,
        sleeve_campaign_link_available=sleeve_link_available,
        promotion_review_evidence_available=promotion_review_available,
        readiness_evidence_supportive=readiness_supportive,
        tca_or_markout_evidence_supportive=tca_or_markout_supportive,
        external_regime_evidence_supportive=external_supportive,
    )
    per_sleeve = _release_per_sleeve_evidence_blockers(
        summary.admission_results,
        paper_blockers,
        missing_link_sleeves=missing_link_sleeves,
    )
    return _ReleaseEvidenceGate(
        paper_campaign_evidence_available=paper_campaign_available,
        sleeve_campaign_link_available=sleeve_link_available,
        promotion_review_evidence_available=promotion_review_available,
        readiness_evidence_supportive=readiness_supportive,
        tca_or_markout_evidence_supportive=tca_or_markout_supportive,
        external_regime_evidence_supportive=external_supportive,
        status=status,
        blockers=paper_blockers,
        per_sleeve_blockers=per_sleeve,
        summary=_release_evidence_summary(status, paper_blockers),
    )


def _paper_campaign_evidence_state(campaign_report: CampaignReport | None) -> tuple[bool, str | None]:
    if campaign_report is None:
        return False, "paper_campaign_evidence_unavailable"
    if campaign_report.status not in {"completed", "finalized"}:
        return False, "paper_campaign_evidence_unavailable"
    verdict = campaign_report.acceptance.verdict
    if verdict == AcceptanceVerdict.FAIL:
        return False, "paper_campaign_evidence_failed"
    if verdict == AcceptanceVerdict.INCONCLUSIVE:
        return False, "paper_campaign_evidence_inconclusive"
    if verdict not in {AcceptanceVerdict.PASS, AcceptanceVerdict.PASS_WITH_WARNINGS}:
        return False, "paper_campaign_evidence_unavailable"
    snap = campaign_report.snapshot
    if snap.total_cycles <= 0 and snap.total_events_enqueued <= 0:
        return False, "paper_campaign_evidence_unavailable"
    return True, None


def _sleeve_campaign_link_state(
    admitted_sleeves: tuple[str, ...],
    *,
    portfolio_snapshot: SleevePortfolioSnapshot | None,
    campaign_report: CampaignReport | None,
) -> tuple[bool, tuple[str, ...]]:
    if not admitted_sleeves:
        return False, ()
    if campaign_report is None or not campaign_report.sleeve_link.linkage_available:
        return False, admitted_sleeves
    linked_ids: set[str] = set(campaign_report.sleeve_link.qualified_sleeve_ids)
    linked_ids.update(campaign_report.sleeve_link.recommended_sleeve_ids)
    missing: list[str] = [sleeve_id for sleeve_id in admitted_sleeves if sleeve_id not in linked_ids]
    if portfolio_snapshot is not None:
        by_id = {sleeve.sleeve_id: sleeve for sleeve in portfolio_snapshot.sleeves}
        missing.extend(
            sleeve_id
            for sleeve_id in admitted_sleeves
            if sleeve_id in by_id
            and not (
                by_id[sleeve_id].campaign_evidence.explicit_link_available
                and by_id[sleeve_id].campaign_evidence.linked_in_campaign
            )
        )
    missing_tuple = tuple(sorted(dict.fromkeys(missing)))
    return len(missing_tuple) == 0, missing_tuple


def _promotion_review_evidence_available(
    summary: SleeveAdmissionPortfolioSummary,
    promotion_review_snapshot: SleevePromotionReviewSnapshot | None,
) -> bool:
    if promotion_review_snapshot is None or not promotion_review_snapshot.review_results:
        return False
    reviewed_ids = {result.sleeve_id for result in promotion_review_snapshot.review_results}
    return all(result.sleeve_id in reviewed_ids for result in summary.admission_results)


def _readiness_evidence_supportive(portfolio_snapshot: SleevePortfolioSnapshot | None) -> bool:
    return bool(portfolio_snapshot is not None and portfolio_snapshot.readiness_is_supportive)


def _tca_or_markout_evidence_supportive(
    campaign_report: CampaignReport | None,
    readiness_flags: dict[str, bool] | None,
) -> bool:
    if readiness_flags is not None and bool(readiness_flags.get("tca_records_sufficient", False)):
        return True
    if campaign_report is None:
        return False
    snap = campaign_report.snapshot
    return bool(getattr(snap, "persisted_tca_count", 0) > 0 or getattr(snap, "completed_markout_count", 0) > 0)


def _external_regime_evidence_state(
    campaign_report: CampaignReport | None,
    readiness_flags: dict[str, bool] | None,
) -> tuple[bool, tuple[str, ...]]:
    if campaign_report is None:
        return False, ("external_regime_evidence_unavailable",)
    if readiness_flags is None:
        readiness_flags = {}
    scenario_step_count = int(getattr(campaign_report, "ext_regime_scenario_step_count", 0) or 0)
    external_available = bool(
        readiness_flags.get("external_regime_evidence_available", False)
        or getattr(campaign_report, "ext_regime_available", False)
        or getattr(campaign_report, "ext_regime_scenario_available", False)
    )
    nontrivial = bool(
        readiness_flags.get("external_regime_scenario_nontrivial_coverage", False)
        or (getattr(campaign_report, "ext_regime_scenario_available", False) and scenario_step_count > 0)
    )
    stale_ok = bool(
        readiness_flags.get("external_regime_not_stale_dominated", _not_dominated(campaign_report, "stale"))
    )
    unavailable_ok = bool(
        readiness_flags.get(
            "external_regime_not_unavailable_dominated",
            _not_dominated(campaign_report, "unavailable"),
        )
    )
    high_risk_ok = bool(
        readiness_flags.get("external_regime_not_high_risk_dominated", _not_dominated(campaign_report, "high_risk"))
    )
    gating_ok = bool(
        readiness_flags.get(
            "external_regime_gating_not_dominant", _external_regime_gating_not_dominant(campaign_report)
        )
    )
    evidence_sufficient = bool(
        readiness_flags.get("external_regime_evidence_sufficient", False)
        or getattr(campaign_report, "ext_regime_evidence_sufficient", False)
    )
    blocked = bool(
        getattr(campaign_report, "ext_regime_high_risk", False)
        or not high_risk_ok
        or not unavailable_ok
        or not stale_ok
        or not gating_ok
        or int(getattr(campaign_report, "ext_regime_execution_blocked_steps", 0) or 0) > 0
    )
    if blocked:
        return False, ("external_regime_governance_blocked",)
    supportive = (
        external_available and nontrivial and evidence_sufficient and high_risk_ok and stale_ok and unavailable_ok
    )
    if supportive:
        return True, ()
    return False, ("external_regime_evidence_unavailable",)


def _not_dominated(campaign_report: CampaignReport, field_name: str) -> bool:
    scenario_step_count = int(getattr(campaign_report, "ext_regime_scenario_step_count", 0) or 0)
    if scenario_step_count <= 0:
        return False
    steps = int(getattr(campaign_report, f"ext_regime_{field_name}_steps", 0) or 0)
    return steps * 2 < scenario_step_count


def _external_regime_gating_not_dominant(campaign_report: CampaignReport) -> bool:
    scenario_step_count = int(getattr(campaign_report, "ext_regime_scenario_step_count", 0) or 0)
    if scenario_step_count <= 0:
        return False
    gating_steps = (
        int(getattr(campaign_report, "ext_regime_activation_blocked_steps", 0) or 0)
        + int(getattr(campaign_report, "ext_regime_execution_blocked_steps", 0) or 0)
        + int(getattr(campaign_report, "ext_regime_activation_reduced_steps", 0) or 0)
    )
    return gating_steps * 2 < scenario_step_count


def _infer_release_evidence_status(
    summary: SleeveAdmissionPortfolioSummary,
    blockers: tuple[str, ...],
    *,
    paper_campaign_evidence_available: bool,
    sleeve_campaign_link_available: bool,
    promotion_review_evidence_available: bool,
    readiness_evidence_supportive: bool,
    tca_or_markout_evidence_supportive: bool,
    external_regime_evidence_supportive: bool,
) -> SleeveAdmissionReleaseEvidenceStatus:
    if len(summary.admission_results) == 0:
        return SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_MISSING
    if any(blocker in blockers for blocker in ("paper_campaign_evidence_failed", "external_regime_governance_blocked")):
        return SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_BLOCKED
    required = (
        paper_campaign_evidence_available,
        sleeve_campaign_link_available,
        promotion_review_evidence_available,
        readiness_evidence_supportive,
        tca_or_markout_evidence_supportive,
        external_regime_evidence_supportive,
    )
    if all(required):
        return SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_READY
    if (
        not paper_campaign_evidence_available
        or not sleeve_campaign_link_available
        or not promotion_review_evidence_available
    ):
        return SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_MISSING
    return SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_PARTIAL


def _evidence_gated_release_status(
    base_status: SleeveAdmissionReleaseStatus,
    evidence_status: SleeveAdmissionReleaseEvidenceStatus,
    summary: SleeveAdmissionPortfolioSummary,
) -> SleeveAdmissionReleaseStatus:
    if base_status == SleeveAdmissionReleaseStatus.NO_CANDIDATES:
        return base_status
    if evidence_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_READY:
        return base_status
    if evidence_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_BLOCKED:
        return SleeveAdmissionReleaseStatus.BLOCKED
    if base_status == SleeveAdmissionReleaseStatus.READY_FOR_PAPER_MANAGED_SET:
        if summary.admitted_active_count + summary.admitted_unallocated_count > 0:
            return SleeveAdmissionReleaseStatus.PARTIAL_READY
        return SleeveAdmissionReleaseStatus.INCONCLUSIVE
    return base_status


def _combined_release_evidence_blockers(
    admission_blockers: tuple[str, ...],
    paper_blockers: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys((*admission_blockers, *paper_blockers))))


def _legacy_missing_release_evidence_blockers(summary: SleeveAdmissionPortfolioSummary) -> tuple[str, ...]:
    if len(summary.admission_results) == 0:
        return ()
    return (
        "external_regime_evidence_unavailable",
        "paper_campaign_evidence_unavailable",
        "promotion_review_evidence_unavailable",
        "readiness_evidence_not_supportive",
        "sleeve_campaign_link_unavailable",
        "tca_or_markout_evidence_unavailable",
    )


def _release_per_sleeve_evidence_blockers(
    results: tuple[SleeveAdmissionResult, ...],
    paper_blockers: tuple[str, ...],
    *,
    missing_link_sleeves: tuple[str, ...],
) -> tuple[SleeveAdmissionReleaseSleeveEvidence, ...]:
    missing_link = set(missing_link_sleeves)
    entries: list[SleeveAdmissionReleaseSleeveEvidence] = []
    for result in results:
        blockers = list(result.evidence_blockers)
        blockers.extend(blocker for blocker in paper_blockers if blocker != "sleeve_campaign_link_unavailable")
        if result.sleeve_id in missing_link:
            blockers.append("sleeve_campaign_link_unavailable")
        entries.append(
            SleeveAdmissionReleaseSleeveEvidence(
                sleeve_id=result.sleeve_id,
                evidence_blockers=tuple(sorted(dict.fromkeys(blockers))),
            )
        )
    return tuple(entries)


def _release_evidence_summary(
    evidence_status: SleeveAdmissionReleaseEvidenceStatus,
    blockers: tuple[str, ...],
) -> str:
    if evidence_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_READY:
        return "Release pack evidence gate is ready."
    if blockers:
        return f"Release pack evidence gate is {evidence_status.value}: {', '.join(blockers)}."
    return f"Release pack evidence gate is {evidence_status.value}."


def _admitted_sleeves(summary: SleeveAdmissionPortfolioSummary) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*summary.admitted_active, *summary.admitted_unallocated)))


def _release_next_actions(
    results: tuple[SleeveAdmissionResult, ...],
) -> tuple[SleeveAdmissionReleaseAction, ...]:
    return tuple(
        SleeveAdmissionReleaseAction(
            sleeve_id=result.sleeve_id,
            admission_verdict=result.verdict,
            next_action=result.next_step,
            evidence_blockers=result.evidence_blockers,
            governance_blockers=result.governance_blockers,
        )
        for result in results
    )


def _release_operator_summary(
    status: SleeveAdmissionReleaseStatus,
    summary: SleeveAdmissionPortfolioSummary,
    evidence_status: SleeveAdmissionReleaseEvidenceStatus | None = None,
) -> str:
    evidence_part = "" if evidence_status is None else f"; evidence_status={evidence_status.value}"
    return (
        f"status={status.value}; "
        f"admitted={summary.admitted_active_count + summary.admitted_unallocated_count}; "
        f"admitted_active={summary.admitted_active_count}; "
        f"admitted_unallocated={summary.admitted_unallocated_count}; "
        f"review_supported_not_admitted={summary.review_supported_not_admitted_count}; "
        f"blocked={summary.blocked_count}; "
        f"inconclusive={summary.inconclusive_count}; "
        f"insufficient_evidence={summary.insufficient_evidence_count}; "
        f"disabled_operator_off={summary.disabled_operator_off_count}"
        f"{evidence_part}"
    )


def _release_pack_id(as_of_ns: int, results: tuple[SleeveAdmissionResult, ...]) -> str:
    digest = hashlib.sha256(_release_results_signature(results).encode("utf-8")).hexdigest()[:12]
    return f"sleeve-admission-release-{as_of_ns}-{digest}"


def _release_replay_key(
    *,
    as_of_ns: int,
    overall_release_status: SleeveAdmissionReleaseStatus,
    portfolio_summary: SleeveAdmissionPortfolioSummary,
    evidence_gate_status: SleeveAdmissionReleaseEvidenceStatus,
    paper_campaign_evidence_available: bool,
    sleeve_campaign_link_available: bool,
    promotion_review_evidence_available: bool,
    readiness_evidence_supportive: bool,
    tca_or_markout_evidence_supportive: bool,
    external_regime_evidence_supportive: bool,
    paper_evidence_blockers: tuple[str, ...],
    per_sleeve_evidence_blockers: tuple[SleeveAdmissionReleaseSleeveEvidence, ...],
    source_admission_as_of_ns: int,
    source_promotion_review_as_of_ns: int | None,
    source_candidate_workflow_as_of_ns: int | None,
    source_portfolio_as_of_ns: int | None,
    admission_snapshot_status: str,
    promotion_review_status: str | None,
    candidate_workflow_status: str | None,
) -> str:
    parts = [
        f"as_of_ns={as_of_ns}",
        f"overall_release_status={overall_release_status.value}",
        f"evidence_gate_status={evidence_gate_status.value}",
        f"paper_campaign_evidence_available={paper_campaign_evidence_available}",
        f"sleeve_campaign_link_available={sleeve_campaign_link_available}",
        f"promotion_review_evidence_available={promotion_review_evidence_available}",
        f"readiness_evidence_supportive={readiness_evidence_supportive}",
        f"tca_or_markout_evidence_supportive={tca_or_markout_evidence_supportive}",
        f"external_regime_evidence_supportive={external_regime_evidence_supportive}",
        f"paper_evidence_blockers={','.join(paper_evidence_blockers)}",
        _release_sleeve_evidence_signature(per_sleeve_evidence_blockers),
        f"source_admission_as_of_ns={source_admission_as_of_ns}",
        f"source_promotion_review_as_of_ns={source_promotion_review_as_of_ns}",
        f"source_candidate_workflow_as_of_ns={source_candidate_workflow_as_of_ns}",
        f"source_portfolio_as_of_ns={source_portfolio_as_of_ns}",
        f"admission_snapshot_status={admission_snapshot_status}",
        f"promotion_review_status={promotion_review_status}",
        f"candidate_workflow_status={candidate_workflow_status}",
        f"admitted_active={','.join(portfolio_summary.admitted_active)}",
        f"admitted_unallocated={','.join(portfolio_summary.admitted_unallocated)}",
        f"review_supported_not_admitted={','.join(portfolio_summary.review_supported_not_admitted)}",
        f"blocked={','.join(portfolio_summary.blocked)}",
        f"inconclusive={','.join(portfolio_summary.inconclusive)}",
        f"insufficient_evidence={','.join(portfolio_summary.insufficient_evidence)}",
        f"disabled_operator_off={','.join(portfolio_summary.disabled_operator_off)}",
        f"governance_blockers={','.join(portfolio_summary.governance_blockers)}",
        f"evidence_blockers={','.join(portfolio_summary.evidence_blockers)}",
        _release_results_signature(portfolio_summary.admission_results),
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _release_results_signature(results: tuple[SleeveAdmissionResult, ...]) -> str:
    return "|".join(
        ":".join(
            (
                result.sleeve_id,
                result.verdict.value,
                result.reason,
                result.next_step,
                ",".join(result.evidence_blockers),
                ",".join(result.governance_blockers),
            )
        )
        for result in results
    )


def _release_sleeve_evidence_signature(
    evidence: tuple[SleeveAdmissionReleaseSleeveEvidence, ...],
) -> str:
    return "|".join(":".join((item.sleeve_id, ",".join(item.evidence_blockers))) for item in evidence)


def _validate_release_pack(pack: SleeveAdmissionReleasePack) -> None:
    summary = pack.portfolio_summary
    _validate_summary_counts(summary)
    _validate_release_blocker_order(summary)
    if pack.per_sleeve_admission_results != summary.admission_results:
        raise SleeveAdmissionCorruptError("Sleeve admission release results do not match portfolio summary")
    if pack.source_admission_as_of_ns != summary.as_of_ns:
        raise SleeveAdmissionCorruptError("Sleeve admission release source timestamp does not match summary")
    expected_status = _evidence_gated_release_status(
        _derive_release_status(summary), pack.evidence_gate_status, summary
    )
    if pack.overall_release_status != expected_status:
        raise SleeveAdmissionCorruptError("Sleeve admission release status does not match admission summary")
    if pack.admitted_sleeves != _admitted_sleeves(summary):
        raise SleeveAdmissionCorruptError("Sleeve admission release admitted sleeves do not match summary")
    expected_evidence_blockers = _combined_release_evidence_blockers(
        summary.evidence_blockers,
        pack.paper_evidence_blockers,
    )
    expected_groups = {
        "admitted_active_sleeves": summary.admitted_active,
        "admitted_unallocated_sleeves": summary.admitted_unallocated,
        "review_supported_not_admitted_sleeves": summary.review_supported_not_admitted,
        "blocked_sleeves": summary.blocked,
        "inconclusive_sleeves": summary.inconclusive,
        "insufficient_evidence_sleeves": summary.insufficient_evidence,
        "disabled_operator_off_sleeves": summary.disabled_operator_off,
        "evidence_blockers": expected_evidence_blockers,
        "governance_blockers": summary.governance_blockers,
    }
    for field_name, expected in expected_groups.items():
        if getattr(pack, field_name) != expected:
            raise SleeveAdmissionCorruptError(f"Sleeve admission release {field_name} does not match summary")
    if pack.next_actions != _release_next_actions(summary.admission_results):
        raise SleeveAdmissionCorruptError("Sleeve admission release next actions do not match admission results")
    _validate_release_evidence_fields(pack)
    _validate_release_timestamps(pack)
    expected_key = _release_replay_key(
        as_of_ns=pack.as_of_ns,
        overall_release_status=pack.overall_release_status,
        portfolio_summary=pack.portfolio_summary,
        evidence_gate_status=pack.evidence_gate_status,
        paper_campaign_evidence_available=pack.paper_campaign_evidence_available,
        sleeve_campaign_link_available=pack.sleeve_campaign_link_available,
        promotion_review_evidence_available=pack.promotion_review_evidence_available,
        readiness_evidence_supportive=pack.readiness_evidence_supportive,
        tca_or_markout_evidence_supportive=pack.tca_or_markout_evidence_supportive,
        external_regime_evidence_supportive=pack.external_regime_evidence_supportive,
        paper_evidence_blockers=pack.paper_evidence_blockers,
        per_sleeve_evidence_blockers=pack.per_sleeve_evidence_blockers,
        source_admission_as_of_ns=pack.source_admission_as_of_ns,
        source_promotion_review_as_of_ns=pack.source_promotion_review_as_of_ns,
        source_candidate_workflow_as_of_ns=pack.source_candidate_workflow_as_of_ns,
        source_portfolio_as_of_ns=pack.source_portfolio_as_of_ns,
        admission_snapshot_status=pack.admission_snapshot_status,
        promotion_review_status=pack.promotion_review_status,
        candidate_workflow_status=pack.candidate_workflow_status,
    )
    if pack.deterministic_replay_key != expected_key:
        raise SleeveAdmissionCorruptError("Sleeve admission release replay key does not match pack contents")


def _validate_release_timestamps(pack: SleeveAdmissionReleasePack) -> None:
    for field_name in (
        "source_admission_as_of_ns",
        "source_promotion_review_as_of_ns",
        "source_candidate_workflow_as_of_ns",
        "source_portfolio_as_of_ns",
    ):
        value = getattr(pack, field_name)
        if value is not None and pack.as_of_ns < value:
            raise SleeveAdmissionCorruptError(f"Sleeve admission release as_of_ns is older than {field_name}")


def _validate_release_evidence_fields(pack: SleeveAdmissionReleasePack) -> None:
    if pack.paper_evidence_blockers != tuple(sorted(dict.fromkeys(pack.paper_evidence_blockers))):
        raise SleeveAdmissionCorruptError("Sleeve admission release paper evidence blockers are not ordered")
    expected_evidence_status = _infer_release_evidence_status(
        pack.portfolio_summary,
        pack.paper_evidence_blockers,
        paper_campaign_evidence_available=pack.paper_campaign_evidence_available,
        sleeve_campaign_link_available=pack.sleeve_campaign_link_available,
        promotion_review_evidence_available=pack.promotion_review_evidence_available,
        readiness_evidence_supportive=pack.readiness_evidence_supportive,
        tca_or_markout_evidence_supportive=pack.tca_or_markout_evidence_supportive,
        external_regime_evidence_supportive=pack.external_regime_evidence_supportive,
    )
    if pack.evidence_gate_status != expected_evidence_status:
        raise SleeveAdmissionCorruptError("Sleeve admission release evidence status does not match evidence fields")
    expected_sleeve_ids = tuple(result.sleeve_id for result in pack.portfolio_summary.admission_results)
    if tuple(item.sleeve_id for item in pack.per_sleeve_evidence_blockers) != expected_sleeve_ids:
        raise SleeveAdmissionCorruptError("Sleeve admission release per-sleeve evidence ids do not match results")
    for item in pack.per_sleeve_evidence_blockers:
        if item.evidence_blockers != tuple(sorted(dict.fromkeys(item.evidence_blockers))):
            raise SleeveAdmissionCorruptError("Sleeve admission release per-sleeve blockers are not ordered")


def _validate_release_blocker_order(summary: SleeveAdmissionPortfolioSummary) -> None:
    for field_name in ("evidence_blockers", "governance_blockers"):
        values = getattr(summary, field_name)
        if values != tuple(sorted(dict.fromkeys(values))):
            raise SleeveAdmissionCorruptError(
                f"Sleeve admission release {field_name} are not deterministically ordered"
            )


def _release_status_or_default(
    value: object,
    summary: SleeveAdmissionPortfolioSummary,
) -> SleeveAdmissionReleaseStatus:
    if value is None:
        return _derive_release_status(summary)
    if isinstance(value, SleeveAdmissionReleaseStatus):
        return value
    try:
        return SleeveAdmissionReleaseStatus(_require_non_empty_str(value, "overall_release_status"))
    except ValueError as exc:
        raise SleeveAdmissionCorruptError(f"Invalid overall_release_status: {value!r}") from exc


def _release_actions_or_default(
    data: dict,
    results: tuple[SleeveAdmissionResult, ...],
) -> tuple[SleeveAdmissionReleaseAction, ...]:
    if "next_actions" not in data:
        return _release_next_actions(results)
    value = data.get("next_actions")
    if not isinstance(value, (list, tuple)):
        raise SleeveAdmissionCorruptError("Sleeve admission release field 'next_actions' must be a list/tuple")
    return tuple(sleeve_admission_release_action_from_dict(_dict_value(item, "next_actions")) for item in value)


def _tuple_or_default(data: dict, field_name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    if field_name not in data:
        return default
    return _tuple_of_strings(data.get(field_name), field_name)


def _bool_or_default(data: dict, field_name: str, default: bool) -> bool:
    if field_name not in data:
        return default
    return _require_bool(data.get(field_name), field_name)


def _release_evidence_status_or_default(
    value: object,
    default: SleeveAdmissionReleaseEvidenceStatus,
) -> SleeveAdmissionReleaseEvidenceStatus:
    if value is None:
        return default
    if isinstance(value, SleeveAdmissionReleaseEvidenceStatus):
        return value
    try:
        return SleeveAdmissionReleaseEvidenceStatus(_require_non_empty_str(value, "evidence_gate_status"))
    except ValueError as exc:
        raise SleeveAdmissionCorruptError(f"Invalid evidence_gate_status: {value!r}") from exc


def _release_sleeve_evidence_or_default(
    data: dict,
    results: tuple[SleeveAdmissionResult, ...],
    paper_blockers: tuple[str, ...],
) -> tuple[SleeveAdmissionReleaseSleeveEvidence, ...]:
    if "per_sleeve_evidence_blockers" not in data:
        return _release_per_sleeve_evidence_blockers(results, paper_blockers, missing_link_sleeves=())
    value = data.get("per_sleeve_evidence_blockers")
    if not isinstance(value, (list, tuple)):
        raise SleeveAdmissionCorruptError(
            "Sleeve admission release field 'per_sleeve_evidence_blockers' must be a list/tuple"
        )
    return tuple(
        sleeve_admission_release_sleeve_evidence_from_dict(_dict_value(item, "per_sleeve_evidence_blockers"))
        for item in value
    )


def _has_release_evidence_fields(data: dict) -> bool:
    return any(
        field_name in data
        for field_name in (
            "paper_campaign_evidence_available",
            "sleeve_campaign_link_available",
            "promotion_review_evidence_available",
            "readiness_evidence_supportive",
            "tca_or_markout_evidence_supportive",
            "external_regime_evidence_supportive",
            "evidence_gate_status",
            "paper_evidence_blockers",
            "per_sleeve_evidence_blockers",
        )
    )


def _manifest_effective_allocations(release_pack: SleeveAdmissionReleasePack) -> tuple[ManagedSleeveAllocation, ...]:
    return tuple(
        ManagedSleeveAllocation(
            sleeve_id=result.sleeve_id,
            effective_allocation=result.effective_allocation,
        )
        for result in sorted(release_pack.per_sleeve_admission_results, key=lambda item: item.sleeve_id)
        if result.verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE
        and result.active
        and _valid_manifest_allocation_value(result.effective_allocation)
    )


def _manifest_invalid_active_allocation_ids(release_pack: SleeveAdmissionReleasePack) -> tuple[str, ...]:
    return _sorted_unique(
        result.sleeve_id
        for result in release_pack.per_sleeve_admission_results
        if result.verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE
        and (not result.active or not _valid_manifest_allocation_value(result.effective_allocation))
    )


def _manifest_unallocated_share(
    portfolio_snapshot: SleevePortfolioSnapshot | None,
    allocations: tuple[ManagedSleeveAllocation, ...],
) -> float:
    if portfolio_snapshot is not None:
        return float(portfolio_snapshot.effective_allocation.effective_unallocated_share)
    allocated = sum(item.effective_allocation for item in allocations)
    return max(0.0, 1.0 - allocated)


def _manifest_activation_blockers(
    release_pack: SleeveAdmissionReleasePack,
    *,
    allocations: tuple[ManagedSleeveAllocation, ...],
    unallocated_share: float,
) -> tuple[str, ...]:
    invalid_active_allocations = tuple(
        f"invalid_effective_allocation:{sleeve_id}"
        for sleeve_id in _manifest_invalid_active_allocation_ids(release_pack)
    )
    return _manifest_activation_blockers_from_fields(
        source_release_pack_status=release_pack.overall_release_status,
        source_evidence_gate_status=release_pack.evidence_gate_status,
        active_sleeves=tuple(item.sleeve_id for item in allocations),
        allocations=allocations,
        unallocated_share=unallocated_share,
        candidate_count=len(release_pack.per_sleeve_admission_results),
        explicit_blockers=_sorted_unique(
            (
                *invalid_active_allocations,
                *release_pack.evidence_blockers,
                *release_pack.governance_blockers,
            )
        ),
    )


def _manifest_activation_blockers_from_fields(
    *,
    source_release_pack_status: SleeveAdmissionReleaseStatus,
    source_evidence_gate_status: SleeveAdmissionReleaseEvidenceStatus,
    active_sleeves: tuple[str, ...],
    allocations: tuple[ManagedSleeveAllocation, ...],
    unallocated_share: float,
    candidate_count: int,
    explicit_blockers: tuple[str, ...],
) -> tuple[str, ...]:
    blockers = list(explicit_blockers)
    if candidate_count == 0 or source_release_pack_status == SleeveAdmissionReleaseStatus.NO_CANDIDATES:
        blockers.append("no_admission_candidates")
    elif source_release_pack_status != SleeveAdmissionReleaseStatus.READY_FOR_PAPER_MANAGED_SET:
        blockers.append("release_pack_not_ready_for_managed_set")
    if source_evidence_gate_status != SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_READY:
        blockers.append("release_pack_evidence_not_ready")
    if candidate_count > 0 and not active_sleeves:
        blockers.append("no_active_sleeves_for_paper_dry_run")
    invalid_allocations = tuple(
        allocation.sleeve_id
        for allocation in allocations
        if not _valid_manifest_allocation_value(allocation.effective_allocation)
    )
    for sleeve_id in invalid_allocations:
        blockers.append(f"invalid_effective_allocation:{sleeve_id}")
    allocation_total = sum(item.effective_allocation for item in allocations)
    if allocation_total > 1.0 + _ALLOCATION_EPSILON:
        blockers.append("effective_allocation_exceeds_one")
    if allocation_total + unallocated_share > 1.0 + _ALLOCATION_EPSILON:
        blockers.append("effective_allocation_plus_unallocated_exceeds_one")
    if not _valid_unallocated_share(unallocated_share):
        blockers.append("invalid_unallocated_share")
    return _sorted_unique(blockers)


def _derive_manifest_dry_run_status(
    *,
    source_release_pack_status: SleeveAdmissionReleaseStatus,
    source_evidence_gate_status: SleeveAdmissionReleaseEvidenceStatus,
    active_sleeves: tuple[str, ...],
    activation_blockers: tuple[str, ...],
    candidate_count: int,
) -> ManagedSleeveSetDryRunStatus:
    if candidate_count == 0 or source_release_pack_status == SleeveAdmissionReleaseStatus.NO_CANDIDATES:
        return ManagedSleeveSetDryRunStatus.EMPTY
    if (
        source_release_pack_status == SleeveAdmissionReleaseStatus.BLOCKED
        or source_evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_BLOCKED
        or _manifest_has_hard_blockers(activation_blockers)
    ):
        return ManagedSleeveSetDryRunStatus.BLOCKED
    if (
        source_release_pack_status == SleeveAdmissionReleaseStatus.READY_FOR_PAPER_MANAGED_SET
        and source_evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_READY
        and active_sleeves
        and not activation_blockers
    ):
        return ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN
    if active_sleeves and source_release_pack_status in {
        SleeveAdmissionReleaseStatus.READY_FOR_PAPER_MANAGED_SET,
        SleeveAdmissionReleaseStatus.PARTIAL_READY,
    }:
        return ManagedSleeveSetDryRunStatus.PARTIAL_PAPER_DRY_RUN
    return ManagedSleeveSetDryRunStatus.INCONCLUSIVE


def _release_pack_hash(pack: SleeveAdmissionReleasePack) -> str:
    parts = (
        pack.pack_id,
        str(pack.as_of_ns),
        pack.overall_release_status.value,
        pack.evidence_gate_status.value,
        pack.deterministic_replay_key,
    )
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _managed_sleeve_manifest_id(as_of_ns: int, source_release_pack_hash: str) -> str:
    return f"managed-sleeve-set-manifest-{as_of_ns}-{source_release_pack_hash[:12]}"


def _manifest_operator_summary(
    status: ManagedSleeveSetDryRunStatus,
    active_sleeves: tuple[str, ...],
    admitted_unallocated: tuple[str, ...],
    blocked_sleeves: tuple[str, ...],
) -> str:
    return (
        f"dry_run_status={status.value}; "
        f"active={len(active_sleeves)}; "
        f"admitted_unallocated={len(admitted_unallocated)}; "
        f"blocked={len(blocked_sleeves)}"
    )


def _manifest_allocations_from_data(data: dict) -> tuple[ManagedSleeveAllocation, ...]:
    if "effective_allocations" not in data:
        return ()
    value = data.get("effective_allocations")
    if not isinstance(value, (list, tuple)):
        raise SleeveAdmissionCorruptError("Managed sleeve manifest field 'effective_allocations' must be a list/tuple")
    return tuple(
        sorted(
            (managed_sleeve_allocation_from_dict(_dict_value(item, "effective_allocations")) for item in value),
            key=lambda item: item.sleeve_id,
        )
    )


def _validate_managed_sleeve_set_manifest(manifest: ManagedSleeveSetManifest) -> None:
    if not isinstance(manifest, ManagedSleeveSetManifest):
        raise SleeveAdmissionCorruptError("managed sleeve set manifest must be a ManagedSleeveSetManifest")
    if manifest.as_of_ns < manifest.source_release_pack_as_of_ns:
        raise SleeveAdmissionCorruptError("Managed sleeve manifest as_of_ns is older than release pack")
    for field_name in (
        "active_sleeves",
        "admitted_unallocated_sleeves",
        "blocked_sleeves",
        "inconclusive_sleeves",
        "activation_blockers",
        "evidence_blockers",
        "governance_blockers",
    ):
        value = getattr(manifest, field_name)
        if value != _sorted_unique(value):
            raise SleeveAdmissionCorruptError(f"Managed sleeve manifest {field_name} are not sorted unique")
    allocation_ids = tuple(item.sleeve_id for item in manifest.effective_allocations)
    if allocation_ids != tuple(sorted(allocation_ids)) or len(allocation_ids) != len(set(allocation_ids)):
        raise SleeveAdmissionCorruptError("Managed sleeve manifest allocations are not sorted unique")
    if allocation_ids != manifest.active_sleeves:
        raise SleeveAdmissionCorruptError("Managed sleeve manifest active sleeves must match effective allocations")
    for allocation in manifest.effective_allocations:
        _validate_manifest_allocation(allocation)
    if not _valid_unallocated_share(manifest.unallocated_share):
        raise SleeveAdmissionCorruptError("Managed sleeve manifest unallocated_share must be between 0 and 1")
    if set(manifest.active_sleeves) & set(manifest.blocked_sleeves):
        raise SleeveAdmissionCorruptError("Managed sleeve manifest active sleeves overlap blocked sleeves")
    if set(manifest.active_sleeves) & set(manifest.inconclusive_sleeves):
        raise SleeveAdmissionCorruptError("Managed sleeve manifest active sleeves overlap inconclusive sleeves")
    candidate_count = (
        len(manifest.active_sleeves)
        + len(manifest.admitted_unallocated_sleeves)
        + len(manifest.blocked_sleeves)
        + len(manifest.inconclusive_sleeves)
    )
    expected_status = _derive_manifest_dry_run_status(
        source_release_pack_status=manifest.source_release_pack_status,
        source_evidence_gate_status=manifest.source_evidence_gate_status,
        active_sleeves=manifest.active_sleeves,
        activation_blockers=manifest.activation_blockers,
        candidate_count=candidate_count,
    )
    if manifest.dry_run_status != expected_status:
        raise SleeveAdmissionCorruptError("Managed sleeve manifest dry-run status does not match activation state")
    if manifest.dry_run_status == ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN:
        if manifest.source_release_pack_status != SleeveAdmissionReleaseStatus.READY_FOR_PAPER_MANAGED_SET:
            raise SleeveAdmissionCorruptError("Managed sleeve manifest cannot be ready from non-ready release pack")
        if manifest.source_evidence_gate_status != SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_READY:
            raise SleeveAdmissionCorruptError("Managed sleeve manifest cannot be ready without evidence-ready pack")
        if not manifest.active_sleeves or manifest.activation_blockers:
            raise SleeveAdmissionCorruptError(
                "Managed sleeve manifest ready state requires active sleeves and no blockers"
            )
    if tuple(action.sleeve_id for action in manifest.next_actions) != tuple(
        sorted(action.sleeve_id for action in manifest.next_actions)
    ):
        raise SleeveAdmissionCorruptError("Managed sleeve manifest next actions are not sorted")


def _validate_manifest_allocation(allocation: ManagedSleeveAllocation) -> None:
    if not allocation.sleeve_id:
        raise SleeveAdmissionCorruptError("Managed sleeve allocation sleeve_id must be non-empty")
    if not _valid_manifest_allocation_value(allocation.effective_allocation):
        raise SleeveAdmissionCorruptError("Managed sleeve allocation must be finite and greater than zero")


def _valid_manifest_allocation_value(value: float) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and 0.0 < float(value) <= 1.0
    )


def _valid_unallocated_share(value: float) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    )


def _manifest_has_hard_blockers(blockers: tuple[str, ...]) -> bool:
    hard_codes = {
        "effective_allocation_exceeds_one",
        "effective_allocation_plus_unallocated_exceeds_one",
        "invalid_unallocated_share",
    }
    return any(code in hard_codes or code.startswith("invalid_effective_allocation:") for code in blockers)


def _manifest_release_status_or_default(
    value: object,
    default: SleeveAdmissionReleaseStatus,
) -> SleeveAdmissionReleaseStatus:
    if value is None:
        return default
    if isinstance(value, SleeveAdmissionReleaseStatus):
        return value
    try:
        return SleeveAdmissionReleaseStatus(_require_non_empty_str(value, "source_release_pack_status"))
    except ValueError as exc:
        raise SleeveAdmissionCorruptError(f"Invalid source_release_pack_status: {value!r}") from exc


def _manifest_dry_run_status_or_default(
    value: object,
    default: ManagedSleeveSetDryRunStatus,
) -> ManagedSleeveSetDryRunStatus:
    if value is None:
        return default
    if isinstance(value, ManagedSleeveSetDryRunStatus):
        return value
    try:
        return ManagedSleeveSetDryRunStatus(_require_non_empty_str(value, "dry_run_status"))
    except ValueError as exc:
        raise SleeveAdmissionCorruptError(f"Invalid dry_run_status: {value!r}") from exc


def _sorted_unique(values) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        raw_values = (values,)
    elif isinstance(values, (list, tuple, set)):
        raw_values = values
    else:
        raw_values = tuple(values)
    return tuple(sorted(dict.fromkeys(str(value) for value in raw_values if value)))


def _managed_sleeve_manifest_hash(manifest: ManagedSleeveSetManifest) -> str:
    parts = [
        f"manifest_id={manifest.manifest_id}",
        f"as_of_ns={manifest.as_of_ns}",
        f"dry_run_status={manifest.dry_run_status.value}",
        f"source_release_pack_hash={manifest.source_release_pack_hash}",
        f"source_evidence_gate_status={manifest.source_evidence_gate_status.value}",
        f"active_sleeves={','.join(manifest.active_sleeves)}",
        f"admitted_unallocated_sleeves={','.join(manifest.admitted_unallocated_sleeves)}",
        f"blocked_sleeves={','.join(manifest.blocked_sleeves)}",
        f"inconclusive_sleeves={','.join(manifest.inconclusive_sleeves)}",
        _manifest_allocations_signature(manifest.effective_allocations),
        f"activation_blockers={','.join(manifest.activation_blockers)}",
        f"evidence_blockers={','.join(manifest.evidence_blockers)}",
        f"governance_blockers={','.join(manifest.governance_blockers)}",
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _manifest_allocations_signature(allocations: tuple[ManagedSleeveAllocation, ...]) -> str:
    return "|".join(f"{item.sleeve_id}:{item.effective_allocation:.12g}" for item in allocations)


def _paper_shadow_activation_plan_id(as_of_ns: int, source_manifest_hash: str) -> str:
    digest = hashlib.sha256(source_manifest_hash.encode("utf-8")).hexdigest()[:12]
    return f"paper-shadow-activation-plan-{as_of_ns}-{digest}"


def _paper_shadow_preflight_gates(manifest: ManagedSleeveSetManifest) -> tuple[str, ...]:
    gates = list(_paper_shadow_preflight_gates_from_fields())
    if manifest.dry_run_status == ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN:
        gates.append("source_manifest_ready")
    else:
        gates.append("source_manifest_not_ready")
    return _sorted_unique(gates)


def _paper_shadow_preflight_gates_from_fields() -> tuple[str, ...]:
    return _sorted_unique(
        (
            "effective_allocations_valid",
            "kill_switch_controls_confirmed",
            "managed_sleeve_manifest_present",
            "paper_only_mode_confirmed",
            "real_money_disabled",
            "real_orders_disabled",
            "release_evidence_ready",
            "runtime_monitoring_configured",
        )
    )


def _paper_shadow_runtime_monitoring_requirements() -> tuple[str, ...]:
    return _sorted_unique(
        (
            "monitor_admission_status_drift",
            "monitor_external_regime_governance",
            "monitor_manifest_hash_drift",
            "monitor_paper_fill_and_markout_evidence",
            "monitor_readiness_state",
            "record_paper_shadow_artifacts",
        )
    )


def _paper_shadow_kill_switch_requirements() -> tuple[str, ...]:
    return _sorted_unique(
        (
            "disable_on_evidence_regression",
            "disable_on_governance_blocker",
            "disable_on_manifest_hash_mismatch",
            "disable_on_readiness_regression",
            "operator_can_disable_sleeve",
        )
    )


def _paper_shadow_activation_blockers(manifest: ManagedSleeveSetManifest) -> tuple[str, ...]:
    return _paper_shadow_activation_blockers_from_fields(
        source_manifest_status=manifest.dry_run_status,
        active_sleeves=manifest.active_sleeves,
        evidence_blockers=manifest.evidence_blockers,
        governance_blockers=manifest.governance_blockers,
        explicit_blockers=manifest.activation_blockers,
    )


def _paper_shadow_activation_blockers_from_fields(
    *,
    source_manifest_status: ManagedSleeveSetDryRunStatus,
    active_sleeves: tuple[str, ...],
    evidence_blockers: tuple[str, ...],
    governance_blockers: tuple[str, ...],
    explicit_blockers: tuple[str, ...] = (),
) -> tuple[str, ...]:
    blockers = list(explicit_blockers)
    if source_manifest_status == ManagedSleeveSetDryRunStatus.EMPTY:
        blockers.append("source_manifest_empty")
    elif source_manifest_status != ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN:
        blockers.append("source_manifest_not_ready_for_paper_shadow")
    if source_manifest_status != ManagedSleeveSetDryRunStatus.EMPTY and not active_sleeves:
        blockers.append("no_active_sleeves_for_paper_shadow")
    if evidence_blockers:
        blockers.append("evidence_blockers_present")
    if governance_blockers:
        blockers.append("governance_blockers_present")
    return _sorted_unique(blockers)


def _derive_paper_shadow_activation_status(
    *,
    source_manifest_status: ManagedSleeveSetDryRunStatus,
    active_sleeves: tuple[str, ...],
    activation_blockers: tuple[str, ...],
) -> PaperShadowActivationStatus:
    if source_manifest_status == ManagedSleeveSetDryRunStatus.EMPTY:
        return PaperShadowActivationStatus.EMPTY
    if source_manifest_status == ManagedSleeveSetDryRunStatus.BLOCKED:
        return PaperShadowActivationStatus.BLOCKED
    if (
        source_manifest_status == ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN
        and active_sleeves
        and not activation_blockers
    ):
        return PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW
    if (
        source_manifest_status
        in {
            ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN,
            ManagedSleeveSetDryRunStatus.PARTIAL_PAPER_DRY_RUN,
        }
        and active_sleeves
    ):
        return PaperShadowActivationStatus.PARTIAL_READY
    if source_manifest_status == ManagedSleeveSetDryRunStatus.INCONCLUSIVE:
        return PaperShadowActivationStatus.INCONCLUSIVE
    if activation_blockers:
        return PaperShadowActivationStatus.BLOCKED
    return PaperShadowActivationStatus.INCONCLUSIVE


def _paper_shadow_operator_summary(
    status: PaperShadowActivationStatus,
    active_sleeves: tuple[str, ...],
    inactive_sleeves: tuple[str, ...],
) -> str:
    return f"activation_status={status.value}; active={len(active_sleeves)}; inactive={len(inactive_sleeves)}"


def _validate_paper_shadow_activation_plan(plan: PaperShadowActivationPlan) -> None:
    if not isinstance(plan, PaperShadowActivationPlan):
        raise SleeveAdmissionCorruptError("paper/shadow activation plan must be a PaperShadowActivationPlan")
    if plan.as_of_ns < plan.source_manifest_as_of_ns:
        raise SleeveAdmissionCorruptError("Paper/shadow activation plan as_of_ns is older than manifest")
    if not plan.paper_only:
        raise SleeveAdmissionCorruptError("Paper/shadow activation plan must remain paper_only")
    if plan.real_orders_enabled:
        raise SleeveAdmissionCorruptError("Paper/shadow activation plan cannot enable real orders")
    if plan.real_money_enabled:
        raise SleeveAdmissionCorruptError("Paper/shadow activation plan cannot enable real money")
    for field_name in (
        "active_sleeves",
        "inactive_sleeves",
        "admitted_unallocated_sleeves",
        "preflight_gates",
        "activation_blockers",
        "evidence_blockers",
        "governance_blockers",
        "runtime_monitoring_requirements",
        "kill_switch_requirements",
    ):
        value = getattr(plan, field_name)
        if value != _sorted_unique(value):
            raise SleeveAdmissionCorruptError(f"Paper/shadow activation plan {field_name} are not sorted unique")
    allocation_ids = tuple(item.sleeve_id for item in plan.effective_allocations)
    if allocation_ids != tuple(sorted(allocation_ids)) or len(allocation_ids) != len(set(allocation_ids)):
        raise SleeveAdmissionCorruptError("Paper/shadow activation plan allocations are not sorted unique")
    if allocation_ids != plan.active_sleeves:
        raise SleeveAdmissionCorruptError("Paper/shadow activation plan active sleeves must match allocations")
    if set(plan.active_sleeves) & set(plan.inactive_sleeves):
        raise SleeveAdmissionCorruptError("Paper/shadow activation plan active and inactive sleeves overlap")
    if not set(plan.admitted_unallocated_sleeves).issubset(set(plan.inactive_sleeves)):
        raise SleeveAdmissionCorruptError("Admitted unallocated sleeves must be inactive in activation plan")
    for allocation in plan.effective_allocations:
        _validate_manifest_allocation(allocation)
    if not plan.preflight_gates:
        raise SleeveAdmissionCorruptError("Paper/shadow activation plan requires preflight gates")
    if not plan.runtime_monitoring_requirements:
        raise SleeveAdmissionCorruptError("Paper/shadow activation plan requires runtime monitoring")
    if not plan.kill_switch_requirements:
        raise SleeveAdmissionCorruptError("Paper/shadow activation plan requires kill-switch requirements")
    expected_status = _derive_paper_shadow_activation_status(
        source_manifest_status=plan.source_manifest_status,
        active_sleeves=plan.active_sleeves,
        activation_blockers=plan.activation_blockers,
    )
    if plan.activation_status != expected_status:
        raise SleeveAdmissionCorruptError("Paper/shadow activation plan status does not match manifest state")
    if plan.activation_status == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW:
        if plan.source_manifest_status != ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN:
            raise SleeveAdmissionCorruptError("Paper/shadow activation plan cannot be ready from non-ready manifest")
        if not plan.active_sleeves or plan.activation_blockers:
            raise SleeveAdmissionCorruptError(
                "Paper/shadow activation plan ready state requires active sleeves and no blockers"
            )
    if tuple(action.sleeve_id for action in plan.next_actions) != tuple(
        sorted(action.sleeve_id for action in plan.next_actions)
    ):
        raise SleeveAdmissionCorruptError("Paper/shadow activation plan next actions are not sorted")


def _paper_shadow_activation_status_or_default(
    value: object,
    default: PaperShadowActivationStatus,
) -> PaperShadowActivationStatus:
    if value is None:
        return default
    if isinstance(value, PaperShadowActivationStatus):
        return value
    try:
        return PaperShadowActivationStatus(_require_non_empty_str(value, "activation_status"))
    except ValueError as exc:
        raise SleeveAdmissionCorruptError(f"Invalid activation_status: {value!r}") from exc


def _dict_value(value: object, field_name: str) -> dict:
    if not isinstance(value, dict):
        raise SleeveAdmissionCorruptError(f"{field_name} must be a dict")
    return dict(value)


def _admission_result_from_value(value: object) -> SleeveAdmissionResult:
    if isinstance(value, SleeveAdmissionResult):
        return value
    return sleeve_admission_result_from_dict(_dict_value(value, "per_sleeve_admission_results"))


def _admission_verdict(value: object, field_name: str) -> SleeveAdmissionVerdict:
    if isinstance(value, SleeveAdmissionVerdict):
        return value
    try:
        return SleeveAdmissionVerdict(_require_non_empty_str(value, field_name))
    except ValueError as exc:
        raise SleeveAdmissionCorruptError(f"Invalid {field_name}: {value!r}") from exc


def _string_or_default(value: object, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or not value:
        raise SleeveAdmissionCorruptError("string field must be a non-empty string")
    return value


def _optional_string_value(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SleeveAdmissionCorruptError(f"{field_name} must be a str or None")
    return value


def _optional_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _require_int(value, field_name)


def _result(
    *,
    sleeve_id: str,
    sleeve: CryptoSleeveState | None,
    review: SleevePromotionReviewResult | None,
    verdict: SleeveAdmissionVerdict,
    reason: str,
    next_step: str,
    governance_blockers: tuple[str, ...],
    evidence_blockers: tuple[str, ...],
) -> SleeveAdmissionResult:
    return SleeveAdmissionResult(
        sleeve_id=sleeve_id,
        verdict=verdict,
        reason=reason,
        next_step=next_step,
        admitted=verdict in _ADMITTED_VERDICTS,
        active=verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE,
        effective_allocation=0.0 if sleeve is None else sleeve.effective_allocation,
        target_allocation=0.0 if sleeve is None else sleeve.target_allocation,
        governance_blockers=governance_blockers,
        evidence_blockers=evidence_blockers,
        last_review_verdict=None if review is None else review.verdict,
        qualification_status=None if sleeve is None else sleeve.qualification.status,
        recommendation_status=None if sleeve is None else sleeve.recommendation.status,
        campaign_evidence_status=None if sleeve is None else sleeve.campaign_evidence.status,
        promotion_support_status=None if sleeve is None else sleeve.promotion_support.status,
        promotion_candidate_status=None if sleeve is None else sleeve.promotion_candidate.status,
        decision_pack_status=None if sleeve is None else sleeve.decision_pack.status,
    )


def _collect_governance_blockers(
    sleeve: CryptoSleeveState | None,
    review: SleevePromotionReviewResult | None,
) -> tuple[str, ...]:
    items: list[str] = []
    if review is not None:
        items.extend(review.governance_blockers)
    if sleeve is not None:
        items.extend(sleeve.blocked_reasons)
        items.extend(sleeve.qualification.blocking_reasons)
        items.extend(sleeve.recommendation.blocking_reasons)
        items.extend(sleeve.campaign_evidence.blocking_reasons)
        items.extend(sleeve.promotion_support.blocking_reasons)
        items.extend(sleeve.promotion_candidate.blocking_reasons)
        items.extend(sleeve.decision_pack.blocking_reasons)
        if sleeve.status == CryptoSleeveStatus.BLOCKED and not items:
            items.append("sleeve_status_blocked")
    return _unique(items)


def _collect_evidence_blockers(
    sleeve: CryptoSleeveState | None,
    review: SleevePromotionReviewResult | None,
) -> tuple[str, ...]:
    items: list[str] = []
    if review is not None:
        items.extend(review.missing_evidence)
    if sleeve is not None:
        items.extend(sleeve.qualification.missing_evidence)
        items.extend(sleeve.recommendation.missing_evidence)
        items.extend(sleeve.campaign_evidence.missing_evidence)
        items.extend(sleeve.promotion_support.missing_evidence)
        items.extend(sleeve.promotion_candidate.missing_evidence)
        items.extend(sleeve.decision_pack.missing_evidence)
    return _unique(items)


def _is_disabled_operator_off(sleeve: CryptoSleeveState | None) -> bool:
    if sleeve is None:
        return False
    return (
        sleeve.status == CryptoSleeveStatus.DISABLED
        or sleeve.recommendation.status == SleeveRecommendationStatus.DISABLED_OPERATOR_OFF
    )


def _first_next_step(
    sleeve: CryptoSleeveState | None,
    review: SleevePromotionReviewResult | None,
    fallback: str,
) -> str:
    candidates = []
    if review is not None:
        candidates.append(review.next_step)
    if sleeve is not None:
        candidates.extend(
            (
                sleeve.decision_pack.next_step,
                sleeve.promotion_candidate.next_step,
                sleeve.promotion_support.next_step,
                sleeve.campaign_evidence.next_step,
                sleeve.recommendation.next_step,
                sleeve.qualification.next_step,
            )
        )
        candidates.extend(sleeve.required_changes)
    return next((item for item in candidates if item), fallback)


def _next_step_summary(results: tuple[SleeveAdmissionResult, ...]) -> str:
    actionable = tuple(
        dict.fromkeys(
            result.next_step for result in results if result.verdict != SleeveAdmissionVerdict.ADMITTED_ACTIVE
        )
    )
    if actionable:
        return "; ".join(actionable)
    if results:
        return "Continue paper monitoring for admitted active sleeves."
    return "No sleeve admission candidates available."


def _unique(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if value))


def _enum_value(value) -> str | None:
    return None if value is None else value.value


def _optional_enum(enum_type, value: object, field_name: str):
    if value is None:
        return None
    try:
        return enum_type(_require_non_empty_str(value, field_name))
    except ValueError as exc:
        raise SleeveAdmissionCorruptError(f"Invalid {field_name}: {value!r}") from exc


def _tuple_or_derive(
    data: dict,
    field_name: str,
    results: tuple[SleeveAdmissionResult, ...],
    verdicts: set[SleeveAdmissionVerdict],
) -> tuple[str, ...]:
    if field_name in data:
        return _tuple_of_strings(data.get(field_name, ()), field_name)
    return tuple(result.sleeve_id for result in results if result.verdict in verdicts)


def _count_or_default(data: dict, field_name: str, sleeve_ids: tuple[str, ...]) -> int:
    if field_name not in data:
        return len(sleeve_ids)
    count = _require_int(data.get(field_name), field_name)
    if count != len(sleeve_ids):
        raise SleeveAdmissionCorruptError(f"Sleeve admission {field_name} does not match ids")
    return count


def _validate_summary_counts(summary: SleeveAdmissionPortfolioSummary) -> None:
    expected_membership = {
        "admitted_active": tuple(
            result.sleeve_id
            for result in summary.admission_results
            if result.verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE
        ),
        "admitted_unallocated": tuple(
            result.sleeve_id
            for result in summary.admission_results
            if result.verdict == SleeveAdmissionVerdict.ADMITTED_UNALLOCATED
        ),
        "review_supported_not_admitted": tuple(
            result.sleeve_id
            for result in summary.admission_results
            if result.verdict == SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED
        ),
        "blocked": tuple(
            result.sleeve_id for result in summary.admission_results if result.verdict in _BLOCKED_VERDICTS
        ),
        "inconclusive": tuple(
            result.sleeve_id for result in summary.admission_results if result.verdict in _INCONCLUSIVE_VERDICTS
        ),
        "insufficient_evidence": tuple(
            result.sleeve_id
            for result in summary.admission_results
            if result.verdict == SleeveAdmissionVerdict.INSUFFICIENT_EVIDENCE
        ),
        "disabled_operator_off": tuple(
            result.sleeve_id
            for result in summary.admission_results
            if result.verdict == SleeveAdmissionVerdict.DISABLED_OPERATOR_OFF
        ),
    }
    for field_name, sleeve_ids in expected_membership.items():
        if getattr(summary, field_name) != sleeve_ids:
            raise SleeveAdmissionCorruptError(f"Sleeve admission {field_name} ids do not match results")

    expected = {
        "admitted_active_count": len(summary.admitted_active),
        "admitted_unallocated_count": len(summary.admitted_unallocated),
        "review_supported_not_admitted_count": len(summary.review_supported_not_admitted),
        "blocked_count": len(summary.blocked),
        "inconclusive_count": len(summary.inconclusive),
        "insufficient_evidence_count": len(summary.insufficient_evidence),
        "disabled_operator_off_count": len(summary.disabled_operator_off),
    }
    for field_name, count in expected.items():
        if getattr(summary, field_name) != count:
            raise SleeveAdmissionCorruptError(f"Sleeve admission {field_name} does not match ids")


def _tuple_of_strings(value: object, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise SleeveAdmissionCorruptError(f"{field_name} must be a list/tuple")
    return tuple(str(item) for item in value)


def _require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SleeveAdmissionCorruptError(f"{field_name} must be a non-empty string")
    return value


def _require_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise SleeveAdmissionCorruptError(f"{field_name} must be a non-negative int")
    return value


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise SleeveAdmissionCorruptError(f"{field_name} must be a bool")
    return value


def _require_float(value: object, field_name: str) -> float:
    if not isinstance(value, (int, float)):
        raise SleeveAdmissionCorruptError(f"{field_name} must be numeric")
    return float(value)
