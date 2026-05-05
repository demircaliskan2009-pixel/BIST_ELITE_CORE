"""Crypto multi-sleeve portfolio contracts.

Deterministic, serialization-friendly portfolio allocation contracts for the
crypto paper-live control surface.

Phase 14A scope:
  - explicit sleeve identity/state contracts
  - validated allocation decomposition
  - compact operator-facing portfolio snapshot
  - additive governance hooks only

Design rules:
  - frozen dataclasses only
  - fail-closed validation on invalid or ambiguous weights
  - no synthetic alpha, PnL, or performance fields
  - crypto-only sleeve taxonomy
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import TYPE_CHECKING

from crypto_core.service.campaign import CampaignReport, CampaignSleeveLinkSummary
from crypto_core.service.promotion_review import EvidenceSufficiency
from crypto_core.service.readiness import ReadinessLevel, level_at_least
from crypto_core.validation.pipeline import ValidationPipelineResult
from crypto_core.validation.stage4_comparator import (
    Stage4BacktestBaseline,
    Stage4ComparisonResult,
    Stage4PaperSummary,
    build_stage4_backtest_baseline_from_windows,
    compare_stage4,
    stage4_backtest_baseline_from_dict,
    stage4_backtest_baseline_to_dict,
    stage4_comparison_result_from_dict,
    stage4_comparison_result_to_dict,
)
from crypto_core.validation.walk_forward import WalkForwardWindow

if TYPE_CHECKING:
    from crypto_core.service.paper_shadow_session_controller import (
        PaperPnLLedger,
        PaperShadowSessionSnapshot,
    )

_ALLOCATION_EPSILON = 1e-9


class CryptoSleeveType(str, Enum):
    """Research-aligned crypto sleeve categories."""

    MICROSTRUCTURE = "microstructure"
    TREND = "trend"
    CARRY = "carry"
    EVENT_VOL = "event_vol"


class CryptoSleeveStatus(str, Enum):
    """Deterministic sleeve lifecycle state."""

    DEFINED = "defined"
    ENABLED = "enabled"
    ALLOCATED = "allocated"
    BLOCKED = "blocked"
    DISABLED = "disabled"


class SleeveReasonSource(str, Enum):
    """Compact source taxonomy for sleeve gating reasons."""

    CONFIGURATION = "configuration"
    OPERATOR = "operator"
    GOVERNANCE = "governance"
    EVIDENCE = "evidence"


class SleeveInactiveCapitalMode(str, Enum):
    """Deterministic handling for inactive sleeve target capital."""

    CONSERVE = "conserve"
    REDISTRIBUTE_PRO_RATA = "redistribute_pro_rata"


class SleeveQualificationStatus(str, Enum):
    """Operator-facing sleeve qualification state."""

    DEFINED_ONLY = "defined_only"
    WEAK_EVIDENCE = "weak_evidence"
    PAPER_QUALIFIED = "paper_qualified"
    BLOCKED = "blocked"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class SleeveRecommendationStatus(str, Enum):
    """Operator-facing sleeve recommendation state."""

    RECOMMENDED_ACTIVE = "recommended_active"
    ELIGIBLE_BUT_NOT_SELECTED = "eligible_but_not_selected"
    BLOCKED = "blocked"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    DISABLED_OPERATOR_OFF = "disabled_operator_off"


class SleeveCampaignEvidenceStatus(str, Enum):
    """Operator-facing sleeve campaign evidence state."""

    NO_CAMPAIGN_EVIDENCE = "no_campaign_evidence"
    WEAK_CAMPAIGN_EVIDENCE = "weak_campaign_evidence"
    CAMPAIGN_SUPPORTED = "campaign_supported"
    BLOCKED_BY_GOVERNANCE = "blocked_by_governance"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class SleevePromotionSupportStatus(str, Enum):
    """Compact sleeve-level promotion-support posture."""

    SUPPORTIVE = "supportive"
    WEAK_SUPPORT = "weak_support"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"


class SleevePromotionCandidateStatus(str, Enum):
    """Explicit sleeve promotion-candidate posture derived from existing truth."""

    SUPPORTED = "supported"
    WATCHLIST = "watchlist"
    BLOCKED = "blocked"
    NOT_A_CANDIDATE = "not_a_candidate"


class SleeveDecisionPackStatus(str, Enum):
    """Compact operator-facing sleeve decision-pack classification."""

    RECOMMENDED_ACTIVE = "recommended_active"
    ELIGIBLE_BUT_NOT_SELECTED = "eligible_but_not_selected"
    SUPPORTED_CANDIDATE = "supported_candidate"
    WATCHLIST_CANDIDATE = "watchlist_candidate"
    BLOCKED = "blocked"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class SleevePortfolioValidationError(ValueError):
    """Raised when sleeve portfolio state is invalid."""


class SleevePortfolioCorruptError(RuntimeError):
    """Raised when a persisted sleeve portfolio payload is malformed."""


@dataclass(frozen=True)
class SleeveReason:
    """Compact sleeve-level explanation for current workflow state."""

    source: SleeveReasonSource
    code: str
    summary: str
    required_change: str = ""


@dataclass(frozen=True)
class SleeveEvidenceState:
    """Compact deterministic sleeve evidence posture."""

    readiness_support: EvidenceSufficiency = EvidenceSufficiency.UNAVAILABLE
    escalation_support: EvidenceSufficiency = EvidenceSufficiency.UNAVAILABLE
    external_regime_support: EvidenceSufficiency = EvidenceSufficiency.UNAVAILABLE
    allocation_eligibility: EvidenceSufficiency = EvidenceSufficiency.UNAVAILABLE
    missing_evidence: tuple[str, ...] = field(default_factory=tuple)
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    supportive: bool = False
    summary: str = ""


@dataclass(frozen=True)
class SleeveQualificationResult:
    """Sleeve-level qualification result for operator surfaces."""

    status: SleeveQualificationStatus = SleeveQualificationStatus.INSUFFICIENT_EVIDENCE
    qualified_for_paper_allocation: bool = False
    governance_blocked: bool = False
    missing_evidence: tuple[str, ...] = field(default_factory=tuple)
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    reason_summary: str = ""
    next_step: str = "Provide missing governance evidence before paper qualification."
    evidence: SleeveEvidenceState = field(default_factory=SleeveEvidenceState)


@dataclass(frozen=True)
class SleeveRecommendationResult:
    """Sleeve-level recommendation result for current portfolio selection."""

    status: SleeveRecommendationStatus = SleeveRecommendationStatus.INSUFFICIENT_EVIDENCE
    recommended_active: bool = False
    currently_eligible: bool = False
    qualification_status: SleeveQualificationStatus = SleeveQualificationStatus.INSUFFICIENT_EVIDENCE
    effective_allocation: float = 0.0
    target_allocation: float = 0.0
    missing_evidence: tuple[str, ...] = field(default_factory=tuple)
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    reason_summary: str = ""
    exclusion_reason: str = ""
    next_step: str = "Provide missing governance evidence before portfolio selection."


@dataclass(frozen=True)
class SleeveCampaignEvidenceResult:
    """Sleeve-level campaign evidence posture derived from real campaign truth."""

    status: SleeveCampaignEvidenceStatus = SleeveCampaignEvidenceStatus.INSUFFICIENT_EVIDENCE
    campaign_evidence_available: bool = False
    explicit_link_available: bool = False
    linked_in_campaign: bool = False
    supporting_campaign_ids: tuple[str, ...] = field(default_factory=tuple)
    missing_evidence: tuple[str, ...] = field(default_factory=tuple)
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    reason_summary: str = ""
    next_step: str = "Carry sleeve linkage into a paper campaign before using it as sleeve evidence."


@dataclass(frozen=True)
class SleevePromotionSupportResult:
    """Sleeve-level support for future promotion consideration."""

    status: SleevePromotionSupportStatus = SleevePromotionSupportStatus.INCONCLUSIVE
    can_be_considered_later: bool = False
    campaign_evidence_status: SleeveCampaignEvidenceStatus = SleeveCampaignEvidenceStatus.INSUFFICIENT_EVIDENCE
    qualification_status: SleeveQualificationStatus = SleeveQualificationStatus.INSUFFICIENT_EVIDENCE
    recommendation_status: SleeveRecommendationStatus = SleeveRecommendationStatus.INSUFFICIENT_EVIDENCE
    missing_evidence: tuple[str, ...] = field(default_factory=tuple)
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    reason_summary: str = ""
    next_step: str = "Provide stronger sleeve evidence before any future promotion consideration."


@dataclass(frozen=True)
class SleevePromotionCandidateResult:
    """Explicit sleeve promotion-candidate surface for later review only."""

    status: SleevePromotionCandidateStatus = SleevePromotionCandidateStatus.NOT_A_CANDIDATE
    candidate_for_future_review: bool = False
    strongly_supported: bool = False
    campaign_evidence_status: SleeveCampaignEvidenceStatus = SleeveCampaignEvidenceStatus.INSUFFICIENT_EVIDENCE
    promotion_support_status: SleevePromotionSupportStatus = SleevePromotionSupportStatus.INCONCLUSIVE
    qualification_status: SleeveQualificationStatus = SleeveQualificationStatus.INSUFFICIENT_EVIDENCE
    recommendation_status: SleeveRecommendationStatus = SleeveRecommendationStatus.INSUFFICIENT_EVIDENCE
    missing_evidence: tuple[str, ...] = field(default_factory=tuple)
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    reason_summary: str = ""
    next_step: str = "Strengthen sleeve evidence before considering it a later promotion candidate."
    pbo_allocation_cap: float | None = None


@dataclass(frozen=True)
class SleeveDecisionPackResult:
    """Compact per-sleeve decision pack derived from current decision and future evidence."""

    status: SleeveDecisionPackStatus = SleeveDecisionPackStatus.INSUFFICIENT_EVIDENCE
    recommended_active: bool = False
    currently_eligible: bool = False
    promotion_candidate: bool = False
    strongly_supported_candidate: bool = False
    recommendation_status: SleeveRecommendationStatus = SleeveRecommendationStatus.INSUFFICIENT_EVIDENCE
    qualification_status: SleeveQualificationStatus = SleeveQualificationStatus.INSUFFICIENT_EVIDENCE
    campaign_evidence_status: SleeveCampaignEvidenceStatus = SleeveCampaignEvidenceStatus.INSUFFICIENT_EVIDENCE
    promotion_support_status: SleevePromotionSupportStatus = SleevePromotionSupportStatus.INCONCLUSIVE
    promotion_candidate_status: SleevePromotionCandidateStatus = SleevePromotionCandidateStatus.NOT_A_CANDIDATE
    missing_evidence: tuple[str, ...] = field(default_factory=tuple)
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    reason_summary: str = ""
    next_step: str = "Collect stronger sleeve evidence before any operator decision changes."


@dataclass(frozen=True)
class CryptoSleeveState:
    """Single crypto sleeve identity and allocation state.

    Allocation decomposition is explicit:
      target_allocation = active_allocation + blocked_allocation + disabled_allocation

    This keeps the contract additive and truthful without inventing runtime PnL
    or alpha claims.
    """

    sleeve_id: str
    sleeve_type: CryptoSleeveType
    status: CryptoSleeveStatus
    target_allocation: float = 0.0
    active_allocation: float = 0.0
    blocked_allocation: float = 0.0
    disabled_allocation: float = 0.0
    blocked_reasons: tuple[str, ...] = field(default_factory=tuple)
    reason_summary: str = ""
    readiness_level: str | None = None
    escalation_stage: str | None = None
    reasons: tuple[SleeveReason, ...] = field(default_factory=tuple)
    required_changes: tuple[str, ...] = field(default_factory=tuple)
    effective_allocation: float = 0.0
    qualification: SleeveQualificationResult = field(default_factory=SleeveQualificationResult)
    recommendation: SleeveRecommendationResult = field(default_factory=SleeveRecommendationResult)
    campaign_evidence: SleeveCampaignEvidenceResult = field(default_factory=SleeveCampaignEvidenceResult)
    promotion_support: SleevePromotionSupportResult = field(default_factory=SleevePromotionSupportResult)
    promotion_candidate: SleevePromotionCandidateResult = field(default_factory=SleevePromotionCandidateResult)
    decision_pack: SleeveDecisionPackResult = field(default_factory=SleeveDecisionPackResult)
    validation_pipeline_result: ValidationPipelineResult | None = None
    stage4_comparison_result: Stage4ComparisonResult | None = None
    stage4_comparison_required: bool = False
    stage4_backtest_baseline: Stage4BacktestBaseline | None = None


@dataclass(frozen=True)
class SleeveAllocationPolicy:
    """Explicit policy for recomputing effective sleeve deployment."""

    blocked_allocation_mode: SleeveInactiveCapitalMode = SleeveInactiveCapitalMode.CONSERVE
    disabled_allocation_mode: SleeveInactiveCapitalMode = SleeveInactiveCapitalMode.CONSERVE


@dataclass(frozen=True)
class SleeveAllocationSummary:
    """Compact portfolio allocation summary across all sleeves."""

    target_allocated_share: float
    active_allocated_share: float
    blocked_allocated_share: float
    disabled_allocated_share: float
    unallocated_share: float
    total_sleeves: int
    defined_sleeves: int
    enabled_sleeves: int
    allocated_sleeves: int
    blocked_sleeves: int
    disabled_sleeves: int


@dataclass(frozen=True)
class SleeveEffectiveAllocationSummary:
    """Effective post-policy deployment summary across all sleeves."""

    effective_allocated_share: float
    effective_unallocated_share: float
    redistributed_blocked_share: float
    redistributed_disabled_share: float
    conserved_blocked_share: float
    conserved_disabled_share: float
    recipient_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SleeveQualificationSummary:
    """Portfolio-wide sleeve qualification summary."""

    total_sleeves: int
    defined_only_sleeves: int
    weak_evidence_sleeves: int
    paper_qualified_sleeves: int
    blocked_sleeves: int
    insufficient_evidence_sleeves: int
    qualified_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    weak_evidence_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    blocked_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    insufficient_evidence_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""


@dataclass(frozen=True)
class SleevePortfolioDecisionSummary:
    """Portfolio-level current recommendation and exclusion surface."""

    total_sleeves: int
    recommended_active_sleeves: int
    eligible_but_not_selected_sleeves: int
    blocked_sleeves: int
    insufficient_evidence_sleeves: int
    disabled_operator_off_sleeves: int
    recommended_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    eligible_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    excluded_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    missing_evidence: tuple[str, ...] = field(default_factory=tuple)
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    effective_allocated_share: float = 0.0
    effective_unallocated_share: float = 1.0
    conserved_blocked_share: float = 0.0
    conserved_disabled_share: float = 0.0
    summary: str = ""


@dataclass(frozen=True)
class SleevePortfolioEvidenceSummary:
    """Portfolio-wide sleeve campaign evidence and promotion-support surface."""

    total_sleeves: int
    no_campaign_evidence_sleeves: int
    weak_campaign_evidence_sleeves: int
    campaign_supported_sleeves: int
    blocked_evidence_sleeves: int
    inconclusive_sleeves: int
    supportive_promotion_sleeves: int
    weak_support_sleeves: int
    no_campaign_evidence_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    weak_campaign_evidence_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    campaign_supported_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    blocked_evidence_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    inconclusive_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    supportive_promotion_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    weak_support_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    missing_evidence: tuple[str, ...] = field(default_factory=tuple)
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""


@dataclass(frozen=True)
class SleevePortfolioDecisionPackSummary:
    """Portfolio-wide sleeve decision-pack and candidate surface."""

    total_sleeves: int
    recommended_active_sleeves: int
    eligible_but_not_selected_sleeves: int
    supported_candidate_sleeves: int
    watchlist_candidate_sleeves: int
    blocked_sleeves: int
    insufficient_evidence_sleeves: int
    recommended_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    eligible_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    supported_candidate_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    watchlist_candidate_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    blocked_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    insufficient_evidence_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    missing_evidence: tuple[str, ...] = field(default_factory=tuple)
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""


@dataclass(frozen=True)
class SleevePortfolioSnapshot:
    """Operator-facing sleeve portfolio snapshot."""

    as_of_ns: int
    sleeves: tuple[CryptoSleeveState, ...] = field(default_factory=tuple)
    allocation: SleeveAllocationSummary = field(
        default_factory=lambda: SleeveAllocationSummary(
            target_allocated_share=0.0,
            active_allocated_share=0.0,
            blocked_allocated_share=0.0,
            disabled_allocated_share=0.0,
            unallocated_share=1.0,
            total_sleeves=0,
            defined_sleeves=0,
            enabled_sleeves=0,
            allocated_sleeves=0,
            blocked_sleeves=0,
            disabled_sleeves=0,
        )
    )
    allocation_policy: SleeveAllocationPolicy = field(default_factory=SleeveAllocationPolicy)
    effective_allocation: SleeveEffectiveAllocationSummary = field(
        default_factory=lambda: SleeveEffectiveAllocationSummary(
            effective_allocated_share=0.0,
            effective_unallocated_share=1.0,
            redistributed_blocked_share=0.0,
            redistributed_disabled_share=0.0,
            conserved_blocked_share=0.0,
            conserved_disabled_share=0.0,
            recipient_sleeve_ids=(),
        )
    )
    qualification: SleeveQualificationSummary = field(
        default_factory=lambda: SleeveQualificationSummary(
            total_sleeves=0,
            defined_only_sleeves=0,
            weak_evidence_sleeves=0,
            paper_qualified_sleeves=0,
            blocked_sleeves=0,
            insufficient_evidence_sleeves=0,
            qualified_sleeve_ids=(),
            weak_evidence_sleeve_ids=(),
            blocked_sleeve_ids=(),
            insufficient_evidence_sleeve_ids=(),
            summary="No sleeve qualification available.",
        )
    )
    decision: SleevePortfolioDecisionSummary = field(
        default_factory=lambda: SleevePortfolioDecisionSummary(
            total_sleeves=0,
            recommended_active_sleeves=0,
            eligible_but_not_selected_sleeves=0,
            blocked_sleeves=0,
            insufficient_evidence_sleeves=0,
            disabled_operator_off_sleeves=0,
            recommended_sleeve_ids=(),
            eligible_sleeve_ids=(),
            excluded_sleeve_ids=(),
            missing_evidence=(),
            blocking_reasons=(),
            effective_allocated_share=0.0,
            effective_unallocated_share=1.0,
            conserved_blocked_share=0.0,
            conserved_disabled_share=0.0,
            summary="No sleeve recommendation available.",
        )
    )
    evidence: SleevePortfolioEvidenceSummary = field(
        default_factory=lambda: SleevePortfolioEvidenceSummary(
            total_sleeves=0,
            no_campaign_evidence_sleeves=0,
            weak_campaign_evidence_sleeves=0,
            campaign_supported_sleeves=0,
            blocked_evidence_sleeves=0,
            inconclusive_sleeves=0,
            supportive_promotion_sleeves=0,
            weak_support_sleeves=0,
            no_campaign_evidence_sleeve_ids=(),
            weak_campaign_evidence_sleeve_ids=(),
            campaign_supported_sleeve_ids=(),
            blocked_evidence_sleeve_ids=(),
            inconclusive_sleeve_ids=(),
            supportive_promotion_sleeve_ids=(),
            weak_support_sleeve_ids=(),
            missing_evidence=(),
            blocking_reasons=(),
            summary="No sleeve campaign evidence available.",
        )
    )
    decision_pack: SleevePortfolioDecisionPackSummary = field(
        default_factory=lambda: SleevePortfolioDecisionPackSummary(
            total_sleeves=0,
            recommended_active_sleeves=0,
            eligible_but_not_selected_sleeves=0,
            supported_candidate_sleeves=0,
            watchlist_candidate_sleeves=0,
            blocked_sleeves=0,
            insufficient_evidence_sleeves=0,
            recommended_sleeve_ids=(),
            eligible_sleeve_ids=(),
            supported_candidate_sleeve_ids=(),
            watchlist_candidate_sleeve_ids=(),
            blocked_sleeve_ids=(),
            insufficient_evidence_sleeve_ids=(),
            missing_evidence=(),
            blocking_reasons=(),
            summary="No sleeve decision pack available.",
        )
    )
    enabled_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    blocked_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    allocated_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    blocked_reason_summaries: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""
    readiness_level: str | None = None
    readiness_is_supportive: bool = False
    escalation_allowed_next_step: str | None = None
    external_regime_execution_blocked: bool | None = None
    workflow_status: str = "static"
    comparison_to_previous: dict = field(default_factory=dict)
    history_summary: dict = field(default_factory=dict)


_ESCALATION_STAGE_RANK = {
    "hold": 0,
    "inconclusive": 1,
    "reject": 2,
    "paper_only": 3,
    "calibrated_paper": 4,
    "shadow_live_review_eligible": 5,
    "tiny_cap_live_review_eligible": 6,
}


def _require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SleevePortfolioCorruptError(f"Sleeve portfolio field {field_name!r} must be a non-empty str")
    return value


def _require_int(value: object, field_name: str) -> int:
    if not isinstance(value, int):
        raise SleevePortfolioCorruptError(f"Sleeve portfolio field {field_name!r} must be an int")
    return value


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise SleevePortfolioCorruptError(f"Sleeve portfolio field {field_name!r} must be a bool")
    return value


def _optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SleevePortfolioCorruptError(f"Sleeve portfolio field {field_name!r} must be a str or None")
    return value


def _tuple_of_strings(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise SleevePortfolioCorruptError(f"Sleeve portfolio field {field_name!r} must be a list/tuple of str")
    return tuple(value)


def _tuple_of_reasons(value: object, field_name: str) -> tuple[SleeveReason, ...]:
    if not isinstance(value, (list, tuple)):
        raise SleevePortfolioCorruptError(f"Sleeve portfolio field {field_name!r} must be a list/tuple")
    return tuple(item if isinstance(item, SleeveReason) else sleeve_reason_from_dict(item) for item in value)


def _tuple_of_evidence_sufficiency(value: object, field_name: str) -> EvidenceSufficiency:
    if isinstance(value, EvidenceSufficiency):
        return value
    if not isinstance(value, str) or not value:
        raise SleevePortfolioCorruptError(f"Sleeve portfolio field {field_name!r} must be a non-empty str")
    try:
        return EvidenceSufficiency(value)
    except ValueError as exc:
        raise SleevePortfolioCorruptError(f"Sleeve portfolio field {field_name!r} is invalid") from exc


def _require_float_like(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SleevePortfolioValidationError(f"Sleeve allocation field {field_name!r} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise SleevePortfolioValidationError(f"Sleeve allocation field {field_name!r} must be finite")
    if result < -_ALLOCATION_EPSILON:
        raise SleevePortfolioValidationError(f"Sleeve allocation field {field_name!r} cannot be negative")
    if result > 1.0 + _ALLOCATION_EPSILON:
        raise SleevePortfolioValidationError(f"Sleeve allocation field {field_name!r} cannot exceed 1.0")
    return 0.0 if abs(result) <= _ALLOCATION_EPSILON else result


def _nearly_equal(left: float, right: float) -> bool:
    return abs(left - right) <= _ALLOCATION_EPSILON


def _validate_sleeve_state(state: CryptoSleeveState) -> CryptoSleeveState:
    if not state.sleeve_id:
        raise SleevePortfolioValidationError("sleeve_id must be non-empty")

    target = _require_float_like(state.target_allocation, "target_allocation")
    active = _require_float_like(state.active_allocation, "active_allocation")
    blocked = _require_float_like(state.blocked_allocation, "blocked_allocation")
    disabled = _require_float_like(state.disabled_allocation, "disabled_allocation")
    effective_allocation = _require_float_like(state.effective_allocation, "effective_allocation")

    decomposition_total = active + blocked + disabled
    if not _nearly_equal(target, decomposition_total):
        raise SleevePortfolioValidationError(
            f"Sleeve {state.sleeve_id!r} target_allocation must equal active + blocked + disabled"
        )

    if state.status == CryptoSleeveStatus.DEFINED:
        if any(value > 0.0 for value in (target, active, blocked, disabled)):
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'defined' cannot carry allocation"
            )
    elif state.status == CryptoSleeveStatus.ENABLED:
        if any(value > 0.0 for value in (target, active, blocked, disabled)):
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'enabled' cannot carry allocation until allocated"
            )
    elif state.status == CryptoSleeveStatus.ALLOCATED:
        if active <= 0.0 or blocked > 0.0 or disabled > 0.0:
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'allocated' must have only active allocation"
            )
    elif state.status == CryptoSleeveStatus.BLOCKED:
        if active > 0.0 or disabled > 0.0:
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'blocked' must have only blocked allocation"
            )
        if not _nearly_equal(blocked, target):
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'blocked' must map target allocation to blocked allocation"
            )
        if not state.blocked_reasons and not state.reason_summary and not state.reasons:
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'blocked' requires a blocking reason"
            )
    elif state.status == CryptoSleeveStatus.DISABLED:
        if active > 0.0 or blocked > 0.0:
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'disabled' must have only disabled allocation"
            )
        if not _nearly_equal(disabled, target):
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'disabled' must map target allocation to disabled allocation"
            )

    if state.status != CryptoSleeveStatus.BLOCKED and state.blocked_reasons:
        raise SleevePortfolioValidationError(
            f"Sleeve {state.sleeve_id!r} cannot carry blocked_reasons unless status is 'blocked'"
        )

    required_changes = tuple(item for item in state.required_changes if item)
    reasons = tuple(state.reasons)
    qualification = (
        state.qualification
        if isinstance(state.qualification, SleeveQualificationResult)
        else SleeveQualificationResult()
    )
    recommendation = (
        state.recommendation
        if isinstance(state.recommendation, SleeveRecommendationResult)
        else SleeveRecommendationResult()
    )
    campaign_evidence = (
        state.campaign_evidence
        if isinstance(state.campaign_evidence, SleeveCampaignEvidenceResult)
        else SleeveCampaignEvidenceResult()
    )
    promotion_support = (
        state.promotion_support
        if isinstance(state.promotion_support, SleevePromotionSupportResult)
        else SleevePromotionSupportResult()
    )
    promotion_candidate = (
        state.promotion_candidate
        if isinstance(state.promotion_candidate, SleevePromotionCandidateResult)
        else SleevePromotionCandidateResult()
    )
    decision_pack = (
        state.decision_pack if isinstance(state.decision_pack, SleeveDecisionPackResult) else SleeveDecisionPackResult()
    )
    if reasons:
        for item in reasons:
            if not item.code:
                raise SleevePortfolioValidationError(f"Sleeve {state.sleeve_id!r} reason code must be non-empty")
            if not item.summary:
                raise SleevePortfolioValidationError(f"Sleeve {state.sleeve_id!r} reason summary must be non-empty")
        if not required_changes:
            required_changes = tuple(item.required_change for item in reasons if item.required_change)

    return CryptoSleeveState(
        sleeve_id=state.sleeve_id,
        sleeve_type=state.sleeve_type,
        status=state.status,
        target_allocation=target,
        active_allocation=active,
        blocked_allocation=blocked,
        disabled_allocation=disabled,
        blocked_reasons=tuple(state.blocked_reasons),
        reason_summary=state.reason_summary,
        readiness_level=state.readiness_level,
        escalation_stage=state.escalation_stage,
        reasons=reasons,
        required_changes=required_changes,
        effective_allocation=effective_allocation,
        qualification=qualification,
        recommendation=recommendation,
        campaign_evidence=campaign_evidence,
        promotion_support=promotion_support,
        promotion_candidate=promotion_candidate,
        decision_pack=decision_pack,
        validation_pipeline_result=state.validation_pipeline_result,
        stage4_comparison_result=state.stage4_comparison_result,
        stage4_comparison_required=bool(state.stage4_comparison_required),
        stage4_backtest_baseline=state.stage4_backtest_baseline,
    )


def _readiness_sufficiency(
    required_level: str | None, readiness_level: str | None, readiness_is_supportive: bool
) -> EvidenceSufficiency:
    if not required_level:
        return EvidenceSufficiency.SUFFICIENT
    if readiness_level is None:
        return EvidenceSufficiency.UNAVAILABLE
    try:
        current_level = ReadinessLevel(readiness_level)
    except ValueError:
        current_level = ReadinessLevel.NOT_ASSESSED
    if current_level == ReadinessLevel.NOT_ASSESSED:
        return EvidenceSufficiency.UNAVAILABLE
    try:
        minimum_level = ReadinessLevel(required_level)
    except ValueError:
        return EvidenceSufficiency.INSUFFICIENT
    if readiness_is_supportive and level_at_least(current_level, minimum_level):
        return EvidenceSufficiency.SUFFICIENT
    return EvidenceSufficiency.INSUFFICIENT


def _escalation_sufficiency(
    required_stage: str | None, escalation_allowed_next_step: str | None
) -> EvidenceSufficiency:
    if not required_stage:
        return EvidenceSufficiency.SUFFICIENT
    required_rank = _ESCALATION_STAGE_RANK.get(required_stage, -1)
    paper_only_rank = _ESCALATION_STAGE_RANK["paper_only"]
    if escalation_allowed_next_step is None:
        if required_rank > paper_only_rank:
            return EvidenceSufficiency.UNAVAILABLE
        return EvidenceSufficiency.SUFFICIENT
    current_rank = _ESCALATION_STAGE_RANK.get(escalation_allowed_next_step, -1)
    if required_rank >= 0 and current_rank >= required_rank:
        return EvidenceSufficiency.SUFFICIENT
    return EvidenceSufficiency.INSUFFICIENT


def _external_regime_sufficiency(external_regime_execution_blocked: bool | None) -> EvidenceSufficiency:
    if external_regime_execution_blocked is None:
        return EvidenceSufficiency.UNAVAILABLE
    if external_regime_execution_blocked:
        return EvidenceSufficiency.INSUFFICIENT
    return EvidenceSufficiency.SUFFICIENT


def _allocation_eligibility_sufficiency(status: CryptoSleeveStatus) -> EvidenceSufficiency:
    if status == CryptoSleeveStatus.ALLOCATED:
        return EvidenceSufficiency.SUFFICIENT
    if status == CryptoSleeveStatus.ENABLED:
        return EvidenceSufficiency.MARGINAL
    if status == CryptoSleeveStatus.DEFINED:
        return EvidenceSufficiency.UNAVAILABLE
    return EvidenceSufficiency.INSUFFICIENT


def _build_sleeve_evidence_state(
    sleeve: CryptoSleeveState,
    *,
    readiness_level: str | None,
    readiness_is_supportive: bool,
    escalation_allowed_next_step: str | None,
    external_regime_execution_blocked: bool | None,
) -> SleeveEvidenceState:
    readiness_support = _readiness_sufficiency(sleeve.readiness_level, readiness_level, readiness_is_supportive)
    escalation_support = _escalation_sufficiency(sleeve.escalation_stage, escalation_allowed_next_step)
    external_regime_support = _external_regime_sufficiency(external_regime_execution_blocked)
    allocation_eligibility = _allocation_eligibility_sufficiency(sleeve.status)

    missing_evidence = [item.code for item in sleeve.reasons if item.source == SleeveReasonSource.EVIDENCE]
    if readiness_support == EvidenceSufficiency.UNAVAILABLE:
        missing_evidence.append("readiness_unavailable")
    elif readiness_support == EvidenceSufficiency.INSUFFICIENT:
        missing_evidence.append("readiness_not_supportive")
    if escalation_support == EvidenceSufficiency.UNAVAILABLE:
        missing_evidence.append("escalation_unavailable")
    elif escalation_support == EvidenceSufficiency.INSUFFICIENT:
        missing_evidence.append("escalation_not_supportive")
    if external_regime_support == EvidenceSufficiency.UNAVAILABLE:
        missing_evidence.append("external_regime_unavailable")
    elif external_regime_support == EvidenceSufficiency.INSUFFICIENT:
        missing_evidence.append("external_regime_not_supportive")
    if allocation_eligibility == EvidenceSufficiency.UNAVAILABLE:
        missing_evidence.append("allocation_not_requested")

    blocking_reasons = tuple(
        dict.fromkeys(
            item.code
            for item in sleeve.reasons
            if item.source
            in {
                SleeveReasonSource.CONFIGURATION,
                SleeveReasonSource.OPERATOR,
                SleeveReasonSource.GOVERNANCE,
            }
        )
    )
    if not blocking_reasons and sleeve.status == CryptoSleeveStatus.BLOCKED:
        blocking_reasons = tuple(sleeve.blocked_reasons) or ("configured_blocked",)
    if not blocking_reasons and sleeve.status == CryptoSleeveStatus.DISABLED:
        blocking_reasons = ("configured_disabled",)
    supportive = (
        readiness_support == EvidenceSufficiency.SUFFICIENT
        and escalation_support == EvidenceSufficiency.SUFFICIENT
        and external_regime_support == EvidenceSufficiency.SUFFICIENT
        and not blocking_reasons
    )
    parts = [
        f"readiness={readiness_support.value}",
        f"escalation={escalation_support.value}",
        f"external_regime={external_regime_support.value}",
        f"allocation={allocation_eligibility.value}",
    ]
    if blocking_reasons:
        parts.append(f"blocking={','.join(blocking_reasons)}")
    if missing_evidence:
        parts.append(f"missing={','.join(dict.fromkeys(missing_evidence))}")
    return SleeveEvidenceState(
        readiness_support=readiness_support,
        escalation_support=escalation_support,
        external_regime_support=external_regime_support,
        allocation_eligibility=allocation_eligibility,
        missing_evidence=tuple(dict.fromkeys(missing_evidence)),
        blocking_reasons=blocking_reasons,
        supportive=supportive,
        summary="; ".join(parts),
    )


def _build_sleeve_qualification_result(
    sleeve: CryptoSleeveState,
    *,
    readiness_level: str | None,
    readiness_is_supportive: bool,
    escalation_allowed_next_step: str | None,
    external_regime_execution_blocked: bool | None,
) -> SleeveQualificationResult:
    evidence = _build_sleeve_evidence_state(
        sleeve,
        readiness_level=readiness_level,
        readiness_is_supportive=readiness_is_supportive,
        escalation_allowed_next_step=escalation_allowed_next_step,
        external_regime_execution_blocked=external_regime_execution_blocked,
    )
    blocking_reasons = evidence.blocking_reasons
    missing_evidence = evidence.missing_evidence
    governance_blocked = sleeve.status == CryptoSleeveStatus.BLOCKED and any(
        item.source == SleeveReasonSource.GOVERNANCE for item in sleeve.reasons
    )

    if sleeve.status == CryptoSleeveStatus.DEFINED:
        status = SleeveQualificationStatus.DEFINED_ONLY
    elif sleeve.status in {CryptoSleeveStatus.BLOCKED, CryptoSleeveStatus.DISABLED}:
        status = SleeveQualificationStatus.BLOCKED
    elif any(
        item in {EvidenceSufficiency.UNAVAILABLE, EvidenceSufficiency.INSUFFICIENT}
        for item in (evidence.readiness_support, evidence.escalation_support, evidence.external_regime_support)
    ):
        status = SleeveQualificationStatus.INSUFFICIENT_EVIDENCE
    elif evidence.allocation_eligibility == EvidenceSufficiency.MARGINAL:
        status = SleeveQualificationStatus.WEAK_EVIDENCE
    else:
        status = SleeveQualificationStatus.PAPER_QUALIFIED

    if sleeve.required_changes:
        next_step = sleeve.required_changes[0]
    elif status == SleeveQualificationStatus.DEFINED_ONLY:
        next_step = "Enable sleeve after operator review."
    elif status == SleeveQualificationStatus.WEAK_EVIDENCE:
        next_step = "Assign explicit paper allocation after operator review."
    elif status == SleeveQualificationStatus.PAPER_QUALIFIED:
        next_step = "Continue paper monitoring and governance revalidation."
    elif status == SleeveQualificationStatus.BLOCKED:
        next_step = (
            "Use enable_sleeve or unblock_sleeve after review."
            if sleeve.status == CryptoSleeveStatus.BLOCKED
            else "Clear the blocking condition before paper qualification."
        )
    else:
        next_step = "Provide missing governance evidence before paper qualification."

    reason_parts = [sleeve.reason_summary or evidence.summary]
    if missing_evidence and not sleeve.reason_summary:
        reason_parts.append(f"missing={','.join(missing_evidence)}")
    reason_summary = "; ".join(part for part in reason_parts if part)
    return SleeveQualificationResult(
        status=status,
        qualified_for_paper_allocation=status == SleeveQualificationStatus.PAPER_QUALIFIED,
        governance_blocked=governance_blocked,
        missing_evidence=missing_evidence,
        blocking_reasons=blocking_reasons,
        reason_summary=reason_summary,
        next_step=next_step,
        evidence=evidence,
    )


def _apply_sleeve_qualification(
    sleeves: tuple[CryptoSleeveState, ...],
    *,
    readiness_level: str | None,
    readiness_is_supportive: bool,
    escalation_allowed_next_step: str | None,
    external_regime_execution_blocked: bool | None,
) -> tuple[tuple[CryptoSleeveState, ...], SleeveQualificationSummary]:
    qualified_sleeves: list[CryptoSleeveState] = []
    for sleeve in sleeves:
        qualification = _build_sleeve_qualification_result(
            sleeve,
            readiness_level=readiness_level,
            readiness_is_supportive=readiness_is_supportive,
            escalation_allowed_next_step=escalation_allowed_next_step,
            external_regime_execution_blocked=external_regime_execution_blocked,
        )
        qualified_sleeves.append(replace(sleeve, qualification=qualification))

    resolved = tuple(qualified_sleeves)
    summary = SleeveQualificationSummary(
        total_sleeves=len(resolved),
        defined_only_sleeves=sum(
            1 for sleeve in resolved if sleeve.qualification.status == SleeveQualificationStatus.DEFINED_ONLY
        ),
        weak_evidence_sleeves=sum(
            1 for sleeve in resolved if sleeve.qualification.status == SleeveQualificationStatus.WEAK_EVIDENCE
        ),
        paper_qualified_sleeves=sum(
            1 for sleeve in resolved if sleeve.qualification.status == SleeveQualificationStatus.PAPER_QUALIFIED
        ),
        blocked_sleeves=sum(
            1 for sleeve in resolved if sleeve.qualification.status == SleeveQualificationStatus.BLOCKED
        ),
        insufficient_evidence_sleeves=sum(
            1 for sleeve in resolved if sleeve.qualification.status == SleeveQualificationStatus.INSUFFICIENT_EVIDENCE
        ),
        qualified_sleeve_ids=tuple(
            sleeve.sleeve_id
            for sleeve in resolved
            if sleeve.qualification.status == SleeveQualificationStatus.PAPER_QUALIFIED
        ),
        weak_evidence_sleeve_ids=tuple(
            sleeve.sleeve_id
            for sleeve in resolved
            if sleeve.qualification.status == SleeveQualificationStatus.WEAK_EVIDENCE
        ),
        blocked_sleeve_ids=tuple(
            sleeve.sleeve_id for sleeve in resolved if sleeve.qualification.status == SleeveQualificationStatus.BLOCKED
        ),
        insufficient_evidence_sleeve_ids=tuple(
            sleeve.sleeve_id
            for sleeve in resolved
            if sleeve.qualification.status == SleeveQualificationStatus.INSUFFICIENT_EVIDENCE
        ),
        summary=(
            f"qualified={sum(1 for sleeve in resolved if sleeve.qualification.status == SleeveQualificationStatus.PAPER_QUALIFIED)}; "
            f"weak={sum(1 for sleeve in resolved if sleeve.qualification.status == SleeveQualificationStatus.WEAK_EVIDENCE)}; "
            f"blocked={sum(1 for sleeve in resolved if sleeve.qualification.status == SleeveQualificationStatus.BLOCKED)}; "
            f"insufficient={sum(1 for sleeve in resolved if sleeve.qualification.status == SleeveQualificationStatus.INSUFFICIENT_EVIDENCE)}"
        )
        if resolved
        else "No sleeve qualification available.",
    )
    return resolved, summary


def _build_sleeve_recommendation_result(sleeve: CryptoSleeveState) -> SleeveRecommendationResult:
    qualification = sleeve.qualification
    blocking_reasons = tuple(dict.fromkeys(qualification.blocking_reasons))
    missing_evidence = tuple(dict.fromkeys(qualification.missing_evidence))
    governance_supportive = qualification.evidence.supportive

    if sleeve.status == CryptoSleeveStatus.DISABLED:
        status = SleeveRecommendationStatus.DISABLED_OPERATOR_OFF
        reason_summary = sleeve.reason_summary or "Sleeve is explicitly disabled at the operator/configuration layer."
        exclusion_reason = "disabled_operator_off"
        next_step = (
            sleeve.required_changes[0] if sleeve.required_changes else "Use enable_sleeve after operator review."
        )
    elif sleeve.status == CryptoSleeveStatus.BLOCKED or qualification.status == SleeveQualificationStatus.BLOCKED:
        status = SleeveRecommendationStatus.BLOCKED
        if not blocking_reasons:
            blocking_reasons = tuple(sleeve.blocked_reasons) or ("configured_blocked",)
        reason_summary = qualification.reason_summary or sleeve.reason_summary or "Sleeve is currently blocked."
        exclusion_reason = blocking_reasons[0]
        next_step = qualification.next_step
    elif (
        qualification.status == SleeveQualificationStatus.PAPER_QUALIFIED
        and sleeve.effective_allocation > _ALLOCATION_EPSILON
    ):
        status = SleeveRecommendationStatus.RECOMMENDED_ACTIVE
        reason_summary = (
            qualification.reason_summary
            or f"Sleeve is qualified and carries effective allocation {sleeve.effective_allocation:.3f}."
        )
        exclusion_reason = ""
        next_step = "Continue paper monitoring and revalidate before any higher promotion step."
    elif qualification.status == SleeveQualificationStatus.PAPER_QUALIFIED or (
        sleeve.status == CryptoSleeveStatus.ENABLED and governance_supportive and not blocking_reasons
    ):
        status = SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED
        reason_summary = (
            qualification.reason_summary
            or "Sleeve is governance-supportive but currently carries no active paper allocation."
        )
        exclusion_reason = "not_selected_for_active_allocation"
        next_step = "Assign explicit paper allocation if the operator wants this sleeve active."
    else:
        status = SleeveRecommendationStatus.INSUFFICIENT_EVIDENCE
        reason_summary = qualification.reason_summary or sleeve.reason_summary or qualification.evidence.summary
        exclusion_reason = missing_evidence[0] if missing_evidence else qualification.status.value
        next_step = qualification.next_step

    return SleeveRecommendationResult(
        status=status,
        recommended_active=status == SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
        currently_eligible=status
        in {
            SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
            SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
        },
        qualification_status=qualification.status,
        effective_allocation=sleeve.effective_allocation,
        target_allocation=sleeve.target_allocation,
        missing_evidence=missing_evidence,
        blocking_reasons=blocking_reasons,
        reason_summary=reason_summary,
        exclusion_reason=exclusion_reason,
        next_step=next_step,
    )


def _apply_sleeve_recommendations(
    sleeves: tuple[CryptoSleeveState, ...],
    effective_allocation: SleeveEffectiveAllocationSummary,
) -> tuple[tuple[CryptoSleeveState, ...], SleevePortfolioDecisionSummary]:
    recommended_sleeves: list[CryptoSleeveState] = []
    for sleeve in sleeves:
        recommendation = _build_sleeve_recommendation_result(sleeve)
        recommended_sleeves.append(replace(sleeve, recommendation=recommendation))

    resolved = tuple(recommended_sleeves)
    recommended_ids = tuple(
        sleeve.sleeve_id
        for sleeve in resolved
        if sleeve.recommendation.status == SleeveRecommendationStatus.RECOMMENDED_ACTIVE
    )
    eligible_ids = tuple(
        sleeve.sleeve_id
        for sleeve in resolved
        if sleeve.recommendation.status == SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED
    )
    excluded_ids = tuple(
        sleeve.sleeve_id
        for sleeve in resolved
        if sleeve.recommendation.status != SleeveRecommendationStatus.RECOMMENDED_ACTIVE
    )
    missing_evidence = tuple(
        dict.fromkeys(
            code
            for sleeve in resolved
            for code in sleeve.recommendation.missing_evidence
            if sleeve.recommendation.status != SleeveRecommendationStatus.RECOMMENDED_ACTIVE
        )
    )
    blocking_reasons = tuple(
        dict.fromkeys(
            code
            for sleeve in resolved
            for code in sleeve.recommendation.blocking_reasons
            if sleeve.recommendation.status
            in {
                SleeveRecommendationStatus.BLOCKED,
                SleeveRecommendationStatus.DISABLED_OPERATOR_OFF,
            }
        )
    )
    summary = (
        f"recommended={len(recommended_ids)}; eligible={len(eligible_ids)}; "
        f"blocked={sum(1 for sleeve in resolved if sleeve.recommendation.status == SleeveRecommendationStatus.BLOCKED)}; "
        f"insufficient={sum(1 for sleeve in resolved if sleeve.recommendation.status == SleeveRecommendationStatus.INSUFFICIENT_EVIDENCE)}; "
        f"disabled={sum(1 for sleeve in resolved if sleeve.recommendation.status == SleeveRecommendationStatus.DISABLED_OPERATOR_OFF)}"
    )
    if recommended_ids:
        summary += f"; active={','.join(recommended_ids)}"
    elif eligible_ids:
        summary += f"; possible={','.join(eligible_ids)}"
    else:
        summary += "; active=none"

    return resolved, SleevePortfolioDecisionSummary(
        total_sleeves=len(resolved),
        recommended_active_sleeves=sum(
            1 for sleeve in resolved if sleeve.recommendation.status == SleeveRecommendationStatus.RECOMMENDED_ACTIVE
        ),
        eligible_but_not_selected_sleeves=sum(
            1
            for sleeve in resolved
            if sleeve.recommendation.status == SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED
        ),
        blocked_sleeves=sum(
            1 for sleeve in resolved if sleeve.recommendation.status == SleeveRecommendationStatus.BLOCKED
        ),
        insufficient_evidence_sleeves=sum(
            1 for sleeve in resolved if sleeve.recommendation.status == SleeveRecommendationStatus.INSUFFICIENT_EVIDENCE
        ),
        disabled_operator_off_sleeves=sum(
            1 for sleeve in resolved if sleeve.recommendation.status == SleeveRecommendationStatus.DISABLED_OPERATOR_OFF
        ),
        recommended_sleeve_ids=recommended_ids,
        eligible_sleeve_ids=eligible_ids,
        excluded_sleeve_ids=excluded_ids,
        missing_evidence=missing_evidence,
        blocking_reasons=blocking_reasons,
        effective_allocated_share=effective_allocation.effective_allocated_share,
        effective_unallocated_share=effective_allocation.effective_unallocated_share,
        conserved_blocked_share=effective_allocation.conserved_blocked_share,
        conserved_disabled_share=effective_allocation.conserved_disabled_share,
        summary=summary if resolved else "No sleeve recommendation available.",
    )


def _campaign_report_supportive(report: CampaignReport | None) -> bool:
    if report is None:
        return False
    return report.verdict in {"pass", "pass_with_warnings"}


def _campaign_report_inconclusive(report: CampaignReport | None) -> bool:
    return bool(report is not None and report.verdict == "inconclusive")


def _campaign_sleeve_link(report: CampaignReport | None) -> CampaignSleeveLinkSummary:
    link = None if report is None else getattr(report, "sleeve_link", None)
    return link if isinstance(link, CampaignSleeveLinkSummary) else CampaignSleeveLinkSummary()


def _build_sleeve_campaign_evidence_result(
    sleeve: CryptoSleeveState,
    campaign_report: CampaignReport | None,
) -> SleeveCampaignEvidenceResult:
    qualification = sleeve.qualification
    recommendation = sleeve.recommendation
    link = _campaign_sleeve_link(campaign_report)
    campaign_available = campaign_report is not None
    campaign_supportive = _campaign_report_supportive(campaign_report)
    campaign_inconclusive = _campaign_report_inconclusive(campaign_report)
    linked_in_campaign = sleeve.sleeve_id in link.configured_sleeve_ids
    qualified_link = sleeve.sleeve_id in link.qualified_sleeve_ids
    recommended_link = sleeve.sleeve_id in link.recommended_sleeve_ids
    blocked_link = sleeve.sleeve_id in link.blocked_sleeve_ids
    missing_evidence: tuple[str, ...] = ()
    blocking_reasons = tuple(
        dict.fromkeys(
            (
                *qualification.blocking_reasons,
                *recommendation.blocking_reasons,
                *(("blocked_in_campaign_link",) if blocked_link else ()),
            )
        )
    )

    if not campaign_available:
        status = SleeveCampaignEvidenceStatus.NO_CAMPAIGN_EVIDENCE
        missing_evidence = ("campaign_report_unavailable", "sleeve_campaign_link_unavailable")
        reason_summary = "No finalized campaign report is available for sleeve-level evidence."
        next_step = "Finalize a paper campaign before using this sleeve as evidence."
    elif (
        sleeve.status in {CryptoSleeveStatus.BLOCKED, CryptoSleeveStatus.DISABLED}
        or qualification.status == SleeveQualificationStatus.BLOCKED
        or recommendation.status == SleeveRecommendationStatus.BLOCKED
        or blocked_link
    ):
        status = SleeveCampaignEvidenceStatus.BLOCKED_BY_GOVERNANCE
        if not blocking_reasons:
            blocking_reasons = ("sleeve_governance_blocked",)
        reason_summary = (
            qualification.reason_summary
            or recommendation.reason_summary
            or "Campaign evidence exists but the sleeve is blocked by current governance."
        )
        next_step = qualification.next_step or recommendation.next_step
    elif not link.linkage_available:
        status = (
            SleeveCampaignEvidenceStatus.WEAK_CAMPAIGN_EVIDENCE
            if campaign_supportive
            else SleeveCampaignEvidenceStatus.INSUFFICIENT_EVIDENCE
        )
        missing_evidence = ("sleeve_campaign_link_unavailable",)
        reason_summary = "Campaign evidence exists, but it does not carry explicit sleeve linkage."
        next_step = "Carry the sleeve portfolio surface into finalized campaign artifacts."
    elif not linked_in_campaign:
        status = SleeveCampaignEvidenceStatus.NO_CAMPAIGN_EVIDENCE
        missing_evidence = ("sleeve_absent_from_campaign_surface",)
        reason_summary = "Sleeve is configured now but absent from the captured campaign sleeve surface."
        next_step = "Run a new campaign while this sleeve is configured if operator wants sleeve evidence."
    elif campaign_supportive and (qualified_link or recommended_link):
        status = SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED
        reason_summary = "Campaign carried this sleeve as qualified or recommended under supportive evidence."
        next_step = "Continue paper evidence collection before any later sleeve competition review."
    elif campaign_inconclusive:
        status = SleeveCampaignEvidenceStatus.INSUFFICIENT_EVIDENCE
        missing_evidence = ("campaign_verdict_inconclusive",)
        reason_summary = "Campaign carried the sleeve, but the campaign verdict remained inconclusive."
        next_step = "Accumulate more campaign coverage before using this sleeve as promotion support."
    else:
        status = SleeveCampaignEvidenceStatus.WEAK_CAMPAIGN_EVIDENCE
        missing_evidence = ("sleeve_not_yet_supported_by_campaign",)
        reason_summary = (
            "Sleeve was present in campaign evidence but only as configured, not as qualified or recommended."
            if campaign_supportive
            else "Campaign carried the sleeve, but the campaign verdict was not supportive."
        )
        next_step = "Strengthen sleeve-linked campaign evidence before relying on this sleeve for promotion support."

    supporting_campaign_ids = (
        ()
        if campaign_report is None or not (linked_in_campaign or qualified_link or recommended_link or blocked_link)
        else (campaign_report.campaign_id,)
    )
    return SleeveCampaignEvidenceResult(
        status=status,
        campaign_evidence_available=campaign_available,
        explicit_link_available=link.linkage_available,
        linked_in_campaign=linked_in_campaign,
        supporting_campaign_ids=supporting_campaign_ids,
        missing_evidence=missing_evidence,
        blocking_reasons=blocking_reasons,
        reason_summary=reason_summary,
        next_step=next_step,
    )


def _apply_sleeve_campaign_evidence(
    sleeves: tuple[CryptoSleeveState, ...],
    campaign_report: CampaignReport | None,
) -> tuple[tuple[CryptoSleeveState, ...], tuple[CryptoSleeveState, ...]]:
    resolved: list[CryptoSleeveState] = []
    for sleeve in sleeves:
        campaign_evidence = _build_sleeve_campaign_evidence_result(sleeve, campaign_report)
        resolved.append(replace(sleeve, campaign_evidence=campaign_evidence))
    result = tuple(resolved)
    return result, result


def _build_sleeve_promotion_support_result(sleeve: CryptoSleeveState) -> SleevePromotionSupportResult:
    campaign_evidence = sleeve.campaign_evidence
    qualification = sleeve.qualification
    recommendation = sleeve.recommendation
    missing_evidence = tuple(
        dict.fromkeys(
            (
                *campaign_evidence.missing_evidence,
                *qualification.missing_evidence,
                *recommendation.missing_evidence,
            )
        )
    )
    blocking_reasons = tuple(
        dict.fromkeys(
            (
                *campaign_evidence.blocking_reasons,
                *qualification.blocking_reasons,
                *recommendation.blocking_reasons,
            )
        )
    )

    if (
        campaign_evidence.status == SleeveCampaignEvidenceStatus.BLOCKED_BY_GOVERNANCE
        or recommendation.status
        in {
            SleeveRecommendationStatus.BLOCKED,
            SleeveRecommendationStatus.DISABLED_OPERATOR_OFF,
        }
        or qualification.status == SleeveQualificationStatus.BLOCKED
    ):
        status = SleevePromotionSupportStatus.BLOCKED
        can_be_considered_later = False
        reason_summary = (
            campaign_evidence.reason_summary
            or recommendation.reason_summary
            or qualification.reason_summary
            or "Sleeve is blocked and cannot be considered for later promotion review."
        )
        next_step = qualification.next_step or recommendation.next_step or campaign_evidence.next_step
    elif (
        campaign_evidence.status == SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED
        and qualification.status == SleeveQualificationStatus.PAPER_QUALIFIED
        and recommendation.currently_eligible
    ):
        status = SleevePromotionSupportStatus.SUPPORTIVE
        can_be_considered_later = True
        reason_summary = "Sleeve has campaign support and remains qualified for later promotion consideration."
        next_step = "Continue paper monitoring and keep sleeve-linked campaign evidence current."
    elif campaign_evidence.status in {
        SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
        SleeveCampaignEvidenceStatus.WEAK_CAMPAIGN_EVIDENCE,
    } and qualification.status in {
        SleeveQualificationStatus.DEFINED_ONLY,
        SleeveQualificationStatus.WEAK_EVIDENCE,
        SleeveQualificationStatus.PAPER_QUALIFIED,
    }:
        status = SleevePromotionSupportStatus.WEAK_SUPPORT
        can_be_considered_later = True
        reason_summary = (
            campaign_evidence.reason_summary or "Sleeve has some campaign support, but evidence remains thin."
        )
        next_step = (
            "Strengthen sleeve-linked campaign evidence before treating this sleeve as a strong promotion candidate."
        )
    else:
        status = SleevePromotionSupportStatus.INCONCLUSIVE
        can_be_considered_later = False
        reason_summary = (
            campaign_evidence.reason_summary
            or qualification.reason_summary
            or recommendation.reason_summary
            or "Sleeve evidence remains too thin for truthful promotion support."
        )
        next_step = campaign_evidence.next_step or qualification.next_step or recommendation.next_step

    return SleevePromotionSupportResult(
        status=status,
        can_be_considered_later=can_be_considered_later,
        campaign_evidence_status=campaign_evidence.status,
        qualification_status=qualification.status,
        recommendation_status=recommendation.status,
        missing_evidence=missing_evidence,
        blocking_reasons=blocking_reasons,
        reason_summary=reason_summary,
        next_step=next_step,
    )


def _apply_sleeve_promotion_support(
    sleeves: tuple[CryptoSleeveState, ...],
) -> tuple[tuple[CryptoSleeveState, ...], SleevePortfolioEvidenceSummary]:
    resolved_sleeves: list[CryptoSleeveState] = []
    for sleeve in sleeves:
        promotion_support = _build_sleeve_promotion_support_result(sleeve)
        resolved_sleeves.append(replace(sleeve, promotion_support=promotion_support))

    resolved = tuple(resolved_sleeves)
    missing_evidence = tuple(
        dict.fromkeys(code for sleeve in resolved for code in sleeve.promotion_support.missing_evidence)
    )
    blocking_reasons = tuple(
        dict.fromkeys(code for sleeve in resolved for code in sleeve.promotion_support.blocking_reasons)
    )
    summary = (
        f"supported={sum(1 for sleeve in resolved if sleeve.campaign_evidence.status == SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED)}; "
        f"weak={sum(1 for sleeve in resolved if sleeve.campaign_evidence.status == SleeveCampaignEvidenceStatus.WEAK_CAMPAIGN_EVIDENCE)}; "
        f"no_campaign={sum(1 for sleeve in resolved if sleeve.campaign_evidence.status == SleeveCampaignEvidenceStatus.NO_CAMPAIGN_EVIDENCE)}; "
        f"blocked={sum(1 for sleeve in resolved if sleeve.campaign_evidence.status == SleeveCampaignEvidenceStatus.BLOCKED_BY_GOVERNANCE)}; "
        f"inconclusive={sum(1 for sleeve in resolved if sleeve.promotion_support.status == SleevePromotionSupportStatus.INCONCLUSIVE)}"
    )
    return resolved, SleevePortfolioEvidenceSummary(
        total_sleeves=len(resolved),
        no_campaign_evidence_sleeves=sum(
            1
            for sleeve in resolved
            if sleeve.campaign_evidence.status == SleeveCampaignEvidenceStatus.NO_CAMPAIGN_EVIDENCE
        ),
        weak_campaign_evidence_sleeves=sum(
            1
            for sleeve in resolved
            if sleeve.campaign_evidence.status == SleeveCampaignEvidenceStatus.WEAK_CAMPAIGN_EVIDENCE
        ),
        campaign_supported_sleeves=sum(
            1
            for sleeve in resolved
            if sleeve.campaign_evidence.status == SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED
        ),
        blocked_evidence_sleeves=sum(
            1
            for sleeve in resolved
            if sleeve.campaign_evidence.status == SleeveCampaignEvidenceStatus.BLOCKED_BY_GOVERNANCE
        ),
        inconclusive_sleeves=sum(
            1 for sleeve in resolved if sleeve.promotion_support.status == SleevePromotionSupportStatus.INCONCLUSIVE
        ),
        supportive_promotion_sleeves=sum(
            1 for sleeve in resolved if sleeve.promotion_support.status == SleevePromotionSupportStatus.SUPPORTIVE
        ),
        weak_support_sleeves=sum(
            1 for sleeve in resolved if sleeve.promotion_support.status == SleevePromotionSupportStatus.WEAK_SUPPORT
        ),
        no_campaign_evidence_sleeve_ids=tuple(
            sleeve.sleeve_id
            for sleeve in resolved
            if sleeve.campaign_evidence.status == SleeveCampaignEvidenceStatus.NO_CAMPAIGN_EVIDENCE
        ),
        weak_campaign_evidence_sleeve_ids=tuple(
            sleeve.sleeve_id
            for sleeve in resolved
            if sleeve.campaign_evidence.status == SleeveCampaignEvidenceStatus.WEAK_CAMPAIGN_EVIDENCE
        ),
        campaign_supported_sleeve_ids=tuple(
            sleeve.sleeve_id
            for sleeve in resolved
            if sleeve.campaign_evidence.status == SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED
        ),
        blocked_evidence_sleeve_ids=tuple(
            sleeve.sleeve_id
            for sleeve in resolved
            if sleeve.campaign_evidence.status == SleeveCampaignEvidenceStatus.BLOCKED_BY_GOVERNANCE
        ),
        inconclusive_sleeve_ids=tuple(
            sleeve.sleeve_id
            for sleeve in resolved
            if sleeve.promotion_support.status == SleevePromotionSupportStatus.INCONCLUSIVE
        ),
        supportive_promotion_sleeve_ids=tuple(
            sleeve.sleeve_id
            for sleeve in resolved
            if sleeve.promotion_support.status == SleevePromotionSupportStatus.SUPPORTIVE
        ),
        weak_support_sleeve_ids=tuple(
            sleeve.sleeve_id
            for sleeve in resolved
            if sleeve.promotion_support.status == SleevePromotionSupportStatus.WEAK_SUPPORT
        ),
        missing_evidence=missing_evidence,
        blocking_reasons=blocking_reasons,
        summary=summary if resolved else "No sleeve campaign evidence available.",
    )


def _validation_pipeline_missing_evidence(
    validation_pipeline_result: ValidationPipelineResult | None,
) -> tuple[str, ...]:
    if validation_pipeline_result is None:
        return ()
    if not isinstance(validation_pipeline_result, ValidationPipelineResult):
        return ("validation_pipeline_malformed",)
    if validation_pipeline_result.validation_ready is True:
        return ()
    if validation_pipeline_result.validation_ready is not False:
        return ("validation_pipeline_malformed",)
    if not isinstance(validation_pipeline_result.rejection_reasons, tuple):
        return ("validation_pipeline_rejection_reasons_malformed",)
    if any(not isinstance(reason, str) or not reason for reason in validation_pipeline_result.rejection_reasons):
        return ("validation_pipeline_rejection_reasons_malformed",)
    if not validation_pipeline_result.rejection_reasons:
        return ("validation_pipeline_not_ready",)
    return validation_pipeline_result.rejection_reasons


def _validation_pipeline_pbo_allocation_cap(
    validation_pipeline_result: ValidationPipelineResult | None,
) -> float | None:
    if not isinstance(validation_pipeline_result, ValidationPipelineResult):
        return None
    return validation_pipeline_result.pbo_allocation_cap


def _stage4_missing_evidence(
    result: Stage4ComparisonResult | None,
    *,
    required: bool,
) -> tuple[str, ...]:
    from crypto_core.validation.stage4_comparator import stage4_admission_blockers

    return stage4_admission_blockers(result, required=required)


def _stage4_effectively_required(state: CryptoSleeveState) -> bool:
    return bool(state.stage4_comparison_required) or (
        isinstance(state.validation_pipeline_result, ValidationPipelineResult)
        and state.validation_pipeline_result.validation_ready is True
    )


def build_sleeve_with_stage4_comparison(
    sleeve: CryptoSleeveState,
    baseline: Stage4BacktestBaseline | None,
    paper_summary: Stage4PaperSummary | None,
    *,
    min_duration_days: float = 30.0,
    min_sharpe_retention_ratio: float = 0.5,
) -> CryptoSleeveState:
    effective_baseline = baseline if baseline is not None else sleeve.stage4_backtest_baseline
    result = compare_stage4(
        effective_baseline,
        paper_summary,
        min_duration_days=min_duration_days,
        min_sharpe_retention_ratio=min_sharpe_retention_ratio,
    )
    return replace(sleeve, stage4_comparison_result=result)


def build_sleeve_with_stage4_baseline(
    sleeve: CryptoSleeveState,
    windows: tuple[WalkForwardWindow, ...] | list[WalkForwardWindow],
    *,
    baseline_id: str,
    edge_id: str,
    as_of_ns: int,
    backtest_slippage_bps: float | None = None,
    backtest_fill_rate: float | None = None,
) -> CryptoSleeveState:
    baseline = build_stage4_backtest_baseline_from_windows(
        windows,
        baseline_id=baseline_id,
        edge_id=edge_id,
        as_of_ns=as_of_ns,
        backtest_slippage_bps=backtest_slippage_bps,
        backtest_fill_rate=backtest_fill_rate,
    )
    return replace(sleeve, stage4_backtest_baseline=baseline)


def build_sleeve_with_stage4_artifacts(
    sleeve: CryptoSleeveState,
    *,
    windows: tuple[WalkForwardWindow, ...] | list[WalkForwardWindow] | None = None,
    baseline: Stage4BacktestBaseline | None = None,
    ledger: PaperPnLLedger | None = None,
    snapshot: PaperShadowSessionSnapshot | None = None,
    paper_summary: Stage4PaperSummary | None = None,
    baseline_id: str,
    edge_id: str,
    as_of_ns: int,
    paper_id: str | None = None,
    min_duration_days: float = 30.0,
    min_sharpe_retention_ratio: float = 0.5,
) -> CryptoSleeveState:
    """Attach Stage4 baseline/comparison evidence from explicit production artifacts."""

    resolved_sleeve = sleeve
    effective_baseline = baseline
    if effective_baseline is not None:
        resolved_sleeve = replace(resolved_sleeve, stage4_backtest_baseline=effective_baseline)
    elif windows is not None:
        resolved_sleeve = build_sleeve_with_stage4_baseline(
            resolved_sleeve,
            windows,
            baseline_id=baseline_id,
            edge_id=edge_id,
            as_of_ns=as_of_ns,
        )
        effective_baseline = resolved_sleeve.stage4_backtest_baseline
    else:
        effective_baseline = resolved_sleeve.stage4_backtest_baseline

    effective_paper_summary = paper_summary
    if effective_paper_summary is None and ledger is not None and snapshot is not None:
        from crypto_core.service.paper_shadow_session_controller import build_stage4_paper_summary_from_pnl_ledger

        effective_paper_summary = build_stage4_paper_summary_from_pnl_ledger(
            ledger,
            snapshot,
            edge_id=edge_id,
            paper_id=paper_id,
        )

    return build_sleeve_with_stage4_comparison(
        resolved_sleeve,
        effective_baseline,
        effective_paper_summary,
        min_duration_days=min_duration_days,
        min_sharpe_retention_ratio=min_sharpe_retention_ratio,
    )


def _build_sleeve_promotion_candidate_result(sleeve: CryptoSleeveState) -> SleevePromotionCandidateResult:
    campaign_evidence = sleeve.campaign_evidence
    qualification = sleeve.qualification
    recommendation = sleeve.recommendation
    promotion_support = sleeve.promotion_support
    validation_missing_evidence = _validation_pipeline_missing_evidence(sleeve.validation_pipeline_result)
    stage4_missing_evidence = _stage4_missing_evidence(
        sleeve.stage4_comparison_result,
        required=_stage4_effectively_required(sleeve),
    )
    pbo_allocation_cap = _validation_pipeline_pbo_allocation_cap(sleeve.validation_pipeline_result)
    missing_evidence = tuple(
        dict.fromkeys(
            (
                *promotion_support.missing_evidence,
                *campaign_evidence.missing_evidence,
                *qualification.missing_evidence,
                *recommendation.missing_evidence,
                *validation_missing_evidence,
                *stage4_missing_evidence,
            )
        )
    )
    blocking_reasons = tuple(
        dict.fromkeys(
            (
                *promotion_support.blocking_reasons,
                *campaign_evidence.blocking_reasons,
                *qualification.blocking_reasons,
                *recommendation.blocking_reasons,
            )
        )
    )

    if (
        promotion_support.status == SleevePromotionSupportStatus.BLOCKED
        or campaign_evidence.status == SleeveCampaignEvidenceStatus.BLOCKED_BY_GOVERNANCE
        or qualification.status == SleeveQualificationStatus.BLOCKED
        or recommendation.status
        in {
            SleeveRecommendationStatus.BLOCKED,
            SleeveRecommendationStatus.DISABLED_OPERATOR_OFF,
        }
    ):
        status = SleevePromotionCandidateStatus.BLOCKED
        candidate_for_future_review = False
        strongly_supported = False
        reason_summary = (
            promotion_support.reason_summary
            or campaign_evidence.reason_summary
            or recommendation.reason_summary
            or qualification.reason_summary
            or "Sleeve is blocked and cannot enter the promotion-candidate surface."
        )
        next_step = promotion_support.next_step or recommendation.next_step or qualification.next_step
    elif (
        promotion_support.status == SleevePromotionSupportStatus.SUPPORTIVE
        and campaign_evidence.status == SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED
        and qualification.status == SleeveQualificationStatus.PAPER_QUALIFIED
        and recommendation.currently_eligible
    ):
        status = SleevePromotionCandidateStatus.SUPPORTED
        candidate_for_future_review = True
        strongly_supported = True
        reason_summary = (
            "Sleeve has supportive campaign evidence and remains eligible for later promotion competition review."
        )
        next_step = "Keep sleeve-linked campaign evidence current and continue paper monitoring."
    elif (
        promotion_support.can_be_considered_later
        or promotion_support.status == SleevePromotionSupportStatus.WEAK_SUPPORT
    ):
        status = SleevePromotionCandidateStatus.WATCHLIST
        candidate_for_future_review = True
        strongly_supported = False
        reason_summary = (
            promotion_support.reason_summary
            or "Sleeve can be watched as a future candidate, but current evidence remains thin."
        )
        next_step = (
            "Strengthen sleeve-linked campaign evidence before treating this sleeve as a strong promotion candidate."
        )
    else:
        status = SleevePromotionCandidateStatus.NOT_A_CANDIDATE
        candidate_for_future_review = False
        strongly_supported = False
        reason_summary = (
            promotion_support.reason_summary
            or campaign_evidence.reason_summary
            or recommendation.reason_summary
            or "Sleeve does not yet have enough truthful evidence to appear as a promotion candidate."
        )
        next_step = promotion_support.next_step or campaign_evidence.next_step or recommendation.next_step

    return SleevePromotionCandidateResult(
        status=status,
        candidate_for_future_review=candidate_for_future_review,
        strongly_supported=strongly_supported,
        campaign_evidence_status=campaign_evidence.status,
        promotion_support_status=promotion_support.status,
        qualification_status=qualification.status,
        recommendation_status=recommendation.status,
        missing_evidence=missing_evidence,
        blocking_reasons=blocking_reasons,
        reason_summary=reason_summary,
        next_step=next_step,
        pbo_allocation_cap=pbo_allocation_cap,
    )


def _build_sleeve_decision_pack_result(sleeve: CryptoSleeveState) -> SleeveDecisionPackResult:
    recommendation = sleeve.recommendation
    qualification = sleeve.qualification
    campaign_evidence = sleeve.campaign_evidence
    promotion_support = sleeve.promotion_support
    promotion_candidate = sleeve.promotion_candidate
    missing_evidence = tuple(
        dict.fromkeys(
            (
                *recommendation.missing_evidence,
                *promotion_candidate.missing_evidence,
            )
        )
    )
    blocking_reasons = tuple(
        dict.fromkeys(
            (
                *recommendation.blocking_reasons,
                *promotion_candidate.blocking_reasons,
            )
        )
    )

    if recommendation.status == SleeveRecommendationStatus.RECOMMENDED_ACTIVE:
        status = SleeveDecisionPackStatus.RECOMMENDED_ACTIVE
        reason_summary = recommendation.reason_summary
        next_step = recommendation.next_step
    elif recommendation.status == SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED:
        status = SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED
        reason_summary = recommendation.reason_summary
        next_step = recommendation.next_step
    elif promotion_candidate.status == SleevePromotionCandidateStatus.SUPPORTED:
        status = SleeveDecisionPackStatus.SUPPORTED_CANDIDATE
        reason_summary = promotion_candidate.reason_summary
        next_step = promotion_candidate.next_step
    elif promotion_candidate.status == SleevePromotionCandidateStatus.WATCHLIST:
        status = SleeveDecisionPackStatus.WATCHLIST_CANDIDATE
        reason_summary = promotion_candidate.reason_summary
        next_step = promotion_candidate.next_step
    elif promotion_candidate.status == SleevePromotionCandidateStatus.BLOCKED:
        status = SleeveDecisionPackStatus.BLOCKED
        reason_summary = promotion_candidate.reason_summary or recommendation.reason_summary
        next_step = promotion_candidate.next_step or recommendation.next_step
    else:
        status = SleeveDecisionPackStatus.INSUFFICIENT_EVIDENCE
        reason_summary = (
            recommendation.reason_summary
            or promotion_candidate.reason_summary
            or campaign_evidence.reason_summary
            or promotion_support.reason_summary
        )
        next_step = (
            recommendation.next_step
            or promotion_candidate.next_step
            or campaign_evidence.next_step
            or promotion_support.next_step
        )

    return SleeveDecisionPackResult(
        status=status,
        recommended_active=recommendation.recommended_active,
        currently_eligible=recommendation.currently_eligible,
        promotion_candidate=promotion_candidate.candidate_for_future_review,
        strongly_supported_candidate=promotion_candidate.strongly_supported,
        recommendation_status=recommendation.status,
        qualification_status=qualification.status,
        campaign_evidence_status=campaign_evidence.status,
        promotion_support_status=promotion_support.status,
        promotion_candidate_status=promotion_candidate.status,
        missing_evidence=missing_evidence,
        blocking_reasons=blocking_reasons,
        reason_summary=reason_summary,
        next_step=next_step,
    )


def _apply_sleeve_decision_pack(
    sleeves: tuple[CryptoSleeveState, ...],
) -> tuple[tuple[CryptoSleeveState, ...], SleevePortfolioDecisionPackSummary]:
    resolved_sleeves: list[CryptoSleeveState] = []
    for sleeve in sleeves:
        promotion_candidate = _build_sleeve_promotion_candidate_result(sleeve)
        enriched = replace(sleeve, promotion_candidate=promotion_candidate)
        decision_pack = _build_sleeve_decision_pack_result(enriched)
        resolved_sleeves.append(replace(enriched, decision_pack=decision_pack))

    resolved = tuple(resolved_sleeves)
    missing_evidence = tuple(
        dict.fromkeys(code for sleeve in resolved for code in sleeve.decision_pack.missing_evidence)
    )
    blocking_reasons = tuple(
        dict.fromkeys(code for sleeve in resolved for code in sleeve.decision_pack.blocking_reasons)
    )
    summary = (
        f"recommended={sum(1 for sleeve in resolved if sleeve.decision_pack.status == SleeveDecisionPackStatus.RECOMMENDED_ACTIVE)}; "
        f"eligible={sum(1 for sleeve in resolved if sleeve.decision_pack.status == SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED)}; "
        f"supported_candidates={sum(1 for sleeve in resolved if sleeve.promotion_candidate.status == SleevePromotionCandidateStatus.SUPPORTED)}; "
        f"watchlist={sum(1 for sleeve in resolved if sleeve.promotion_candidate.status == SleevePromotionCandidateStatus.WATCHLIST)}; "
        f"blocked={sum(1 for sleeve in resolved if sleeve.decision_pack.status == SleeveDecisionPackStatus.BLOCKED)}; "
        f"insufficient={sum(1 for sleeve in resolved if sleeve.decision_pack.status == SleeveDecisionPackStatus.INSUFFICIENT_EVIDENCE)}"
    )
    return resolved, SleevePortfolioDecisionPackSummary(
        total_sleeves=len(resolved),
        recommended_active_sleeves=sum(
            1 for sleeve in resolved if sleeve.decision_pack.status == SleeveDecisionPackStatus.RECOMMENDED_ACTIVE
        ),
        eligible_but_not_selected_sleeves=sum(
            1
            for sleeve in resolved
            if sleeve.decision_pack.status == SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED
        ),
        supported_candidate_sleeves=sum(
            1 for sleeve in resolved if sleeve.promotion_candidate.status == SleevePromotionCandidateStatus.SUPPORTED
        ),
        watchlist_candidate_sleeves=sum(
            1 for sleeve in resolved if sleeve.promotion_candidate.status == SleevePromotionCandidateStatus.WATCHLIST
        ),
        blocked_sleeves=sum(
            1 for sleeve in resolved if sleeve.decision_pack.status == SleeveDecisionPackStatus.BLOCKED
        ),
        insufficient_evidence_sleeves=sum(
            1 for sleeve in resolved if sleeve.decision_pack.status == SleeveDecisionPackStatus.INSUFFICIENT_EVIDENCE
        ),
        recommended_sleeve_ids=tuple(
            sleeve.sleeve_id
            for sleeve in resolved
            if sleeve.decision_pack.status == SleeveDecisionPackStatus.RECOMMENDED_ACTIVE
        ),
        eligible_sleeve_ids=tuple(
            sleeve.sleeve_id
            for sleeve in resolved
            if sleeve.decision_pack.status == SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED
        ),
        supported_candidate_sleeve_ids=tuple(
            sleeve.sleeve_id
            for sleeve in resolved
            if sleeve.promotion_candidate.status == SleevePromotionCandidateStatus.SUPPORTED
        ),
        watchlist_candidate_sleeve_ids=tuple(
            sleeve.sleeve_id
            for sleeve in resolved
            if sleeve.promotion_candidate.status == SleevePromotionCandidateStatus.WATCHLIST
        ),
        blocked_sleeve_ids=tuple(
            sleeve.sleeve_id for sleeve in resolved if sleeve.decision_pack.status == SleeveDecisionPackStatus.BLOCKED
        ),
        insufficient_evidence_sleeve_ids=tuple(
            sleeve.sleeve_id
            for sleeve in resolved
            if sleeve.decision_pack.status == SleeveDecisionPackStatus.INSUFFICIENT_EVIDENCE
        ),
        missing_evidence=missing_evidence,
        blocking_reasons=blocking_reasons,
        summary=summary if resolved else "No sleeve decision pack available.",
    )


def _compute_effective_allocation(
    sleeves: tuple[CryptoSleeveState, ...],
    allocation: SleeveAllocationSummary,
    allocation_policy: SleeveAllocationPolicy,
) -> tuple[tuple[CryptoSleeveState, ...], SleeveEffectiveAllocationSummary]:
    allocated_sleeves = tuple(
        sleeve for sleeve in sleeves if sleeve.status == CryptoSleeveStatus.ALLOCATED and sleeve.active_allocation > 0.0
    )
    allocated_share = sum(sleeve.active_allocation for sleeve in allocated_sleeves)

    redistribute_blocked = (
        allocation.blocked_allocated_share
        if allocation_policy.blocked_allocation_mode == SleeveInactiveCapitalMode.REDISTRIBUTE_PRO_RATA
        and allocated_share > 0.0
        else 0.0
    )
    redistribute_disabled = (
        allocation.disabled_allocated_share
        if allocation_policy.disabled_allocation_mode == SleeveInactiveCapitalMode.REDISTRIBUTE_PRO_RATA
        and allocated_share > 0.0
        else 0.0
    )
    redistributed_share = redistribute_blocked + redistribute_disabled

    effective_sleeves: list[CryptoSleeveState] = []
    for sleeve in sleeves:
        effective_allocation = sleeve.active_allocation
        if redistributed_share > 0.0 and sleeve.status == CryptoSleeveStatus.ALLOCATED and allocated_share > 0.0:
            effective_allocation += redistributed_share * (sleeve.active_allocation / allocated_share)
        effective_sleeves.append(replace(sleeve, effective_allocation=effective_allocation))

    effective_summary = SleeveEffectiveAllocationSummary(
        effective_allocated_share=allocated_share + redistributed_share,
        effective_unallocated_share=allocation.unallocated_share,
        redistributed_blocked_share=redistribute_blocked,
        redistributed_disabled_share=redistribute_disabled,
        conserved_blocked_share=allocation.blocked_allocated_share - redistribute_blocked,
        conserved_disabled_share=allocation.disabled_allocated_share - redistribute_disabled,
        recipient_sleeve_ids=tuple(sleeve.sleeve_id for sleeve in allocated_sleeves),
    )
    return tuple(effective_sleeves), effective_summary


def build_sleeve_portfolio_snapshot(
    *,
    sleeves: tuple[CryptoSleeveState, ...] = (),
    as_of_ns: int,
    campaign_report: CampaignReport | None = None,
    readiness_level: str | None = None,
    readiness_is_supportive: bool = False,
    escalation_allowed_next_step: str | None = None,
    external_regime_execution_blocked: bool | None = None,
    allocation_policy: SleeveAllocationPolicy | None = None,
    workflow_status: str = "static",
    comparison_to_previous: dict | None = None,
    history_summary: dict | None = None,
) -> SleevePortfolioSnapshot:
    """Build a validated sleeve portfolio snapshot."""
    if not isinstance(as_of_ns, int) or as_of_ns < 0:
        raise SleevePortfolioValidationError("as_of_ns must be a non-negative int")

    validated: list[CryptoSleeveState] = []
    seen_ids: set[str] = set()
    for sleeve in sleeves:
        checked = _validate_sleeve_state(sleeve)
        if checked.sleeve_id in seen_ids:
            raise SleevePortfolioValidationError(f"Duplicate sleeve_id {checked.sleeve_id!r}")
        seen_ids.add(checked.sleeve_id)
        validated.append(checked)

    total_target = sum(sleeve.target_allocation for sleeve in validated)
    total_active = sum(sleeve.active_allocation for sleeve in validated)
    total_blocked = sum(sleeve.blocked_allocation for sleeve in validated)
    total_disabled = sum(sleeve.disabled_allocation for sleeve in validated)

    if total_target > 1.0 + _ALLOCATION_EPSILON:
        raise SleevePortfolioValidationError("Total target allocation cannot exceed 1.0")
    if not _nearly_equal(total_target, total_active + total_blocked + total_disabled):
        raise SleevePortfolioValidationError("Portfolio allocation decomposition is inconsistent")

    unallocated_share = 1.0 - total_target
    if unallocated_share < -_ALLOCATION_EPSILON:
        raise SleevePortfolioValidationError("Unallocated share cannot be negative")
    if abs(unallocated_share) <= _ALLOCATION_EPSILON:
        unallocated_share = 0.0

    enabled_ids = tuple(
        sleeve.sleeve_id
        for sleeve in validated
        if sleeve.status in {CryptoSleeveStatus.ENABLED, CryptoSleeveStatus.ALLOCATED}
    )
    blocked_ids = tuple(sleeve.sleeve_id for sleeve in validated if sleeve.status == CryptoSleeveStatus.BLOCKED)
    allocated_ids = tuple(sleeve.sleeve_id for sleeve in validated if sleeve.status == CryptoSleeveStatus.ALLOCATED)
    blocked_reason_summaries = tuple(
        f"{sleeve.sleeve_id}:{sleeve.reason_summary or ', '.join(sleeve.blocked_reasons)}"
        for sleeve in validated
        if sleeve.status == CryptoSleeveStatus.BLOCKED
    )

    allocation = SleeveAllocationSummary(
        target_allocated_share=total_target,
        active_allocated_share=total_active,
        blocked_allocated_share=total_blocked,
        disabled_allocated_share=total_disabled,
        unallocated_share=unallocated_share,
        total_sleeves=len(validated),
        defined_sleeves=sum(1 for sleeve in validated if sleeve.status == CryptoSleeveStatus.DEFINED),
        enabled_sleeves=sum(
            1 for sleeve in validated if sleeve.status in {CryptoSleeveStatus.ENABLED, CryptoSleeveStatus.ALLOCATED}
        ),
        allocated_sleeves=sum(1 for sleeve in validated if sleeve.status == CryptoSleeveStatus.ALLOCATED),
        blocked_sleeves=sum(1 for sleeve in validated if sleeve.status == CryptoSleeveStatus.BLOCKED),
        disabled_sleeves=sum(1 for sleeve in validated if sleeve.status == CryptoSleeveStatus.DISABLED),
    )
    resolved_policy = SleeveAllocationPolicy() if allocation_policy is None else allocation_policy
    effective_sleeves, effective_allocation = _compute_effective_allocation(
        tuple(validated),
        allocation,
        resolved_policy,
    )
    qualified_sleeves, qualification = _apply_sleeve_qualification(
        effective_sleeves,
        readiness_level=readiness_level,
        readiness_is_supportive=readiness_is_supportive,
        escalation_allowed_next_step=escalation_allowed_next_step,
        external_regime_execution_blocked=external_regime_execution_blocked,
    )
    recommended_sleeves, decision = _apply_sleeve_recommendations(qualified_sleeves, effective_allocation)
    if campaign_report is None and any(
        sleeve.campaign_evidence != SleeveCampaignEvidenceResult() for sleeve in recommended_sleeves
    ):
        campaign_evidenced_sleeves = recommended_sleeves
    else:
        campaign_evidenced_sleeves, _ = _apply_sleeve_campaign_evidence(recommended_sleeves, campaign_report)
    supported_sleeves, evidence = _apply_sleeve_promotion_support(campaign_evidenced_sleeves)
    decision_packed_sleeves, decision_pack = _apply_sleeve_decision_pack(supported_sleeves)

    if not decision_packed_sleeves:
        summary = "No explicit sleeves configured; sleeve-level capital remains fully unallocated."
    else:
        summary = (
            f"sleeves={allocation.total_sleeves}; enabled={allocation.enabled_sleeves}; "
            f"blocked={allocation.blocked_sleeves}; allocated_share={allocation.target_allocated_share:.3f}; "
            f"unallocated_share={allocation.unallocated_share:.3f}"
        )
        if not _nearly_equal(allocation.active_allocated_share, effective_allocation.effective_allocated_share):
            summary += f"; effective_allocated_share={effective_allocation.effective_allocated_share:.3f}"
        summary += f"; qualified={qualification.paper_qualified_sleeves}; insufficient={qualification.insufficient_evidence_sleeves}"
        summary += f"; recommended={decision.recommended_active_sleeves}; eligible={decision.eligible_but_not_selected_sleeves}"
        summary += (
            f"; campaign_supported={evidence.campaign_supported_sleeves}; weak_support={evidence.weak_support_sleeves}"
        )
        summary += (
            f"; supported_candidates={decision_pack.supported_candidate_sleeves}; "
            f"watchlist={decision_pack.watchlist_candidate_sleeves}"
        )

    return SleevePortfolioSnapshot(
        as_of_ns=as_of_ns,
        sleeves=decision_packed_sleeves,
        allocation=allocation,
        allocation_policy=resolved_policy,
        effective_allocation=effective_allocation,
        qualification=qualification,
        decision=decision,
        evidence=evidence,
        decision_pack=decision_pack,
        enabled_sleeve_ids=enabled_ids,
        blocked_sleeve_ids=blocked_ids,
        allocated_sleeve_ids=allocated_ids,
        blocked_reason_summaries=blocked_reason_summaries,
        summary=summary,
        readiness_level=readiness_level,
        readiness_is_supportive=readiness_is_supportive,
        escalation_allowed_next_step=escalation_allowed_next_step,
        external_regime_execution_blocked=external_regime_execution_blocked,
        workflow_status=workflow_status,
        comparison_to_previous={} if comparison_to_previous is None else dict(comparison_to_previous),
        history_summary={} if history_summary is None else dict(history_summary),
    )


def sleeve_reason_to_dict(reason: SleeveReason) -> dict:
    """Serialize SleeveReason to a plain dict."""
    return {
        "source": reason.source.value,
        "code": reason.code,
        "summary": reason.summary,
        "required_change": reason.required_change,
    }


def sleeve_reason_from_dict(data: dict) -> SleeveReason:
    """Deserialize SleeveReason from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(f"Sleeve reason payload must be a dict, got {type(data).__name__!r}")
    source = SleeveReasonSource(_require_non_empty_str(data.get("source"), "source"))
    code = _require_non_empty_str(data.get("code"), "code")
    summary = _require_non_empty_str(data.get("summary"), "summary")
    required_change = "" if data.get("required_change", "") is None else str(data.get("required_change", ""))
    return SleeveReason(
        source=source,
        code=code,
        summary=summary,
        required_change=required_change,
    )


def crypto_sleeve_state_to_dict(state: CryptoSleeveState) -> dict:
    """Serialize CryptoSleeveState to a plain dict."""
    effective_stage4_required = _stage4_effectively_required(state)
    return {
        "sleeve_id": state.sleeve_id,
        "sleeve_type": state.sleeve_type.value,
        "status": state.status.value,
        "target_allocation": state.target_allocation,
        "active_allocation": state.active_allocation,
        "blocked_allocation": state.blocked_allocation,
        "disabled_allocation": state.disabled_allocation,
        "blocked_reasons": list(state.blocked_reasons),
        "reason_summary": state.reason_summary,
        "readiness_level": state.readiness_level,
        "escalation_stage": state.escalation_stage,
        "reasons": [sleeve_reason_to_dict(item) for item in state.reasons],
        "required_changes": list(state.required_changes),
        "effective_allocation": state.effective_allocation,
        "qualification": sleeve_qualification_result_to_dict(state.qualification),
        "recommendation": sleeve_recommendation_result_to_dict(state.recommendation),
        "campaign_evidence": sleeve_campaign_evidence_result_to_dict(state.campaign_evidence),
        "promotion_support": sleeve_promotion_support_result_to_dict(state.promotion_support),
        "promotion_candidate": sleeve_promotion_candidate_result_to_dict(state.promotion_candidate),
        "decision_pack": sleeve_decision_pack_result_to_dict(state.decision_pack),
        "stage4_comparison_result": (
            None
            if state.stage4_comparison_result is None
            else stage4_comparison_result_to_dict(state.stage4_comparison_result)
        ),
        "stage4_comparison_required": effective_stage4_required,
        "stage4_backtest_baseline": (
            None
            if state.stage4_backtest_baseline is None
            else stage4_backtest_baseline_to_dict(state.stage4_backtest_baseline)
        ),
    }


def crypto_sleeve_state_from_dict(data: dict) -> CryptoSleeveState:
    """Deserialize CryptoSleeveState from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(f"Sleeve state payload must be a dict, got {type(data).__name__!r}")

    try:
        state = CryptoSleeveState(
            sleeve_id=_require_non_empty_str(data.get("sleeve_id"), "sleeve_id"),
            sleeve_type=CryptoSleeveType(_require_non_empty_str(data.get("sleeve_type"), "sleeve_type")),
            status=CryptoSleeveStatus(_require_non_empty_str(data.get("status"), "status")),
            target_allocation=_require_float_like(data.get("target_allocation", 0.0), "target_allocation"),
            active_allocation=_require_float_like(data.get("active_allocation", 0.0), "active_allocation"),
            blocked_allocation=_require_float_like(data.get("blocked_allocation", 0.0), "blocked_allocation"),
            disabled_allocation=_require_float_like(data.get("disabled_allocation", 0.0), "disabled_allocation"),
            blocked_reasons=_tuple_of_strings(data.get("blocked_reasons", ()), "blocked_reasons"),
            reason_summary=("" if data.get("reason_summary", "") is None else str(data.get("reason_summary", ""))),
            readiness_level=_optional_str(data.get("readiness_level"), "readiness_level"),
            escalation_stage=_optional_str(data.get("escalation_stage"), "escalation_stage"),
            reasons=_tuple_of_reasons(data.get("reasons", ()), "reasons"),
            required_changes=_tuple_of_strings(data.get("required_changes", ()), "required_changes"),
            effective_allocation=_require_float_like(data.get("effective_allocation", 0.0), "effective_allocation"),
            qualification=(
                SleeveQualificationResult()
                if data.get("qualification") is None
                else sleeve_qualification_result_from_dict(dict(data.get("qualification")))
            ),
            recommendation=(
                SleeveRecommendationResult()
                if data.get("recommendation") is None
                else sleeve_recommendation_result_from_dict(dict(data.get("recommendation")))
            ),
            campaign_evidence=(
                SleeveCampaignEvidenceResult()
                if data.get("campaign_evidence") is None
                else sleeve_campaign_evidence_result_from_dict(dict(data.get("campaign_evidence")))
            ),
            promotion_support=(
                SleevePromotionSupportResult()
                if data.get("promotion_support") is None
                else sleeve_promotion_support_result_from_dict(dict(data.get("promotion_support")))
            ),
            promotion_candidate=(
                SleevePromotionCandidateResult()
                if data.get("promotion_candidate") is None
                else sleeve_promotion_candidate_result_from_dict(dict(data.get("promotion_candidate")))
            ),
            decision_pack=(
                SleeveDecisionPackResult()
                if data.get("decision_pack") is None
                else sleeve_decision_pack_result_from_dict(dict(data.get("decision_pack")))
            ),
            stage4_comparison_result=(
                None
                if data.get("stage4_comparison_result") is None
                else stage4_comparison_result_from_dict(data.get("stage4_comparison_result"))
            ),
            stage4_comparison_required=bool(data.get("stage4_comparison_required", False)),
            stage4_backtest_baseline=(
                None
                if data.get("stage4_backtest_baseline") is None
                else stage4_backtest_baseline_from_dict(data.get("stage4_backtest_baseline"))
            ),
        )
    except (SleevePortfolioValidationError, ValueError) as exc:
        raise SleevePortfolioCorruptError(str(exc)) from exc

    try:
        return _validate_sleeve_state(state)
    except SleevePortfolioValidationError as exc:
        raise SleevePortfolioCorruptError(str(exc)) from exc


def sleeve_allocation_summary_to_dict(summary: SleeveAllocationSummary) -> dict:
    """Serialize SleeveAllocationSummary to a plain dict."""
    return {
        "target_allocated_share": summary.target_allocated_share,
        "active_allocated_share": summary.active_allocated_share,
        "blocked_allocated_share": summary.blocked_allocated_share,
        "disabled_allocated_share": summary.disabled_allocated_share,
        "unallocated_share": summary.unallocated_share,
        "total_sleeves": summary.total_sleeves,
        "defined_sleeves": summary.defined_sleeves,
        "enabled_sleeves": summary.enabled_sleeves,
        "allocated_sleeves": summary.allocated_sleeves,
        "blocked_sleeves": summary.blocked_sleeves,
        "disabled_sleeves": summary.disabled_sleeves,
    }


def sleeve_allocation_policy_to_dict(policy: SleeveAllocationPolicy) -> dict:
    """Serialize SleeveAllocationPolicy to a plain dict."""
    return {
        "blocked_allocation_mode": policy.blocked_allocation_mode.value,
        "disabled_allocation_mode": policy.disabled_allocation_mode.value,
    }


def sleeve_allocation_policy_from_dict(data: dict) -> SleeveAllocationPolicy:
    """Deserialize SleeveAllocationPolicy from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve allocation policy payload must be a dict, got {type(data).__name__!r}"
        )
    return SleeveAllocationPolicy(
        blocked_allocation_mode=SleeveInactiveCapitalMode(
            _require_non_empty_str(
                data.get("blocked_allocation_mode", SleeveInactiveCapitalMode.CONSERVE.value), "blocked_allocation_mode"
            )
        ),
        disabled_allocation_mode=SleeveInactiveCapitalMode(
            _require_non_empty_str(
                data.get("disabled_allocation_mode", SleeveInactiveCapitalMode.CONSERVE.value),
                "disabled_allocation_mode",
            )
        ),
    )


def sleeve_effective_allocation_summary_to_dict(summary: SleeveEffectiveAllocationSummary) -> dict:
    """Serialize SleeveEffectiveAllocationSummary to a plain dict."""
    return {
        "effective_allocated_share": summary.effective_allocated_share,
        "effective_unallocated_share": summary.effective_unallocated_share,
        "redistributed_blocked_share": summary.redistributed_blocked_share,
        "redistributed_disabled_share": summary.redistributed_disabled_share,
        "conserved_blocked_share": summary.conserved_blocked_share,
        "conserved_disabled_share": summary.conserved_disabled_share,
        "recipient_sleeve_ids": list(summary.recipient_sleeve_ids),
    }


def sleeve_effective_allocation_summary_from_dict(data: dict) -> SleeveEffectiveAllocationSummary:
    """Deserialize SleeveEffectiveAllocationSummary from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve effective allocation payload must be a dict, got {type(data).__name__!r}"
        )
    try:
        return SleeveEffectiveAllocationSummary(
            effective_allocated_share=_require_float_like(
                data.get("effective_allocated_share", 0.0), "effective_allocated_share"
            ),
            effective_unallocated_share=_require_float_like(
                data.get("effective_unallocated_share", 0.0), "effective_unallocated_share"
            ),
            redistributed_blocked_share=_require_float_like(
                data.get("redistributed_blocked_share", 0.0), "redistributed_blocked_share"
            ),
            redistributed_disabled_share=_require_float_like(
                data.get("redistributed_disabled_share", 0.0), "redistributed_disabled_share"
            ),
            conserved_blocked_share=_require_float_like(
                data.get("conserved_blocked_share", 0.0), "conserved_blocked_share"
            ),
            conserved_disabled_share=_require_float_like(
                data.get("conserved_disabled_share", 0.0), "conserved_disabled_share"
            ),
            recipient_sleeve_ids=_tuple_of_strings(data.get("recipient_sleeve_ids", ()), "recipient_sleeve_ids"),
        )
    except SleevePortfolioValidationError as exc:
        raise SleevePortfolioCorruptError(str(exc)) from exc


def sleeve_evidence_state_to_dict(state: SleeveEvidenceState) -> dict:
    """Serialize SleeveEvidenceState to a plain dict."""
    return {
        "readiness_support": state.readiness_support.value,
        "escalation_support": state.escalation_support.value,
        "external_regime_support": state.external_regime_support.value,
        "allocation_eligibility": state.allocation_eligibility.value,
        "missing_evidence": list(state.missing_evidence),
        "blocking_reasons": list(state.blocking_reasons),
        "supportive": state.supportive,
        "summary": state.summary,
    }


def sleeve_evidence_state_from_dict(data: dict) -> SleeveEvidenceState:
    """Deserialize SleeveEvidenceState from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(f"Sleeve evidence state payload must be a dict, got {type(data).__name__!r}")
    return SleeveEvidenceState(
        readiness_support=_tuple_of_evidence_sufficiency(data.get("readiness_support"), "readiness_support"),
        escalation_support=_tuple_of_evidence_sufficiency(data.get("escalation_support"), "escalation_support"),
        external_regime_support=_tuple_of_evidence_sufficiency(
            data.get("external_regime_support"), "external_regime_support"
        ),
        allocation_eligibility=_tuple_of_evidence_sufficiency(
            data.get("allocation_eligibility"), "allocation_eligibility"
        ),
        missing_evidence=_tuple_of_strings(data.get("missing_evidence", ()), "missing_evidence"),
        blocking_reasons=_tuple_of_strings(data.get("blocking_reasons", ()), "blocking_reasons"),
        supportive=_require_bool(data.get("supportive", False), "supportive"),
        summary="" if data.get("summary", "") is None else str(data.get("summary", "")),
    )


def sleeve_qualification_result_to_dict(result: SleeveQualificationResult) -> dict:
    """Serialize SleeveQualificationResult to a plain dict."""
    return {
        "status": result.status.value,
        "qualified_for_paper_allocation": result.qualified_for_paper_allocation,
        "governance_blocked": result.governance_blocked,
        "missing_evidence": list(result.missing_evidence),
        "blocking_reasons": list(result.blocking_reasons),
        "reason_summary": result.reason_summary,
        "next_step": result.next_step,
        "evidence": sleeve_evidence_state_to_dict(result.evidence),
    }


def sleeve_qualification_result_from_dict(data: dict) -> SleeveQualificationResult:
    """Deserialize SleeveQualificationResult from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve qualification result payload must be a dict, got {type(data).__name__!r}"
        )
    return SleeveQualificationResult(
        status=SleeveQualificationStatus(_require_non_empty_str(data.get("status"), "status")),
        qualified_for_paper_allocation=_require_bool(
            data.get("qualified_for_paper_allocation", False), "qualified_for_paper_allocation"
        ),
        governance_blocked=_require_bool(data.get("governance_blocked", False), "governance_blocked"),
        missing_evidence=_tuple_of_strings(data.get("missing_evidence", ()), "missing_evidence"),
        blocking_reasons=_tuple_of_strings(data.get("blocking_reasons", ()), "blocking_reasons"),
        reason_summary="" if data.get("reason_summary", "") is None else str(data.get("reason_summary", "")),
        next_step=_require_non_empty_str(data.get("next_step"), "next_step"),
        evidence=(
            SleeveEvidenceState()
            if data.get("evidence") is None
            else sleeve_evidence_state_from_dict(dict(data.get("evidence")))
        ),
    )


def sleeve_qualification_summary_to_dict(summary: SleeveQualificationSummary) -> dict:
    """Serialize SleeveQualificationSummary to a plain dict."""
    return {
        "total_sleeves": summary.total_sleeves,
        "defined_only_sleeves": summary.defined_only_sleeves,
        "weak_evidence_sleeves": summary.weak_evidence_sleeves,
        "paper_qualified_sleeves": summary.paper_qualified_sleeves,
        "blocked_sleeves": summary.blocked_sleeves,
        "insufficient_evidence_sleeves": summary.insufficient_evidence_sleeves,
        "qualified_sleeve_ids": list(summary.qualified_sleeve_ids),
        "weak_evidence_sleeve_ids": list(summary.weak_evidence_sleeve_ids),
        "blocked_sleeve_ids": list(summary.blocked_sleeve_ids),
        "insufficient_evidence_sleeve_ids": list(summary.insufficient_evidence_sleeve_ids),
        "summary": summary.summary,
    }


def sleeve_qualification_summary_from_dict(data: dict) -> SleeveQualificationSummary:
    """Deserialize SleeveQualificationSummary from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve qualification summary payload must be a dict, got {type(data).__name__!r}"
        )
    return SleeveQualificationSummary(
        total_sleeves=_require_int(data.get("total_sleeves"), "total_sleeves"),
        defined_only_sleeves=_require_int(data.get("defined_only_sleeves"), "defined_only_sleeves"),
        weak_evidence_sleeves=_require_int(data.get("weak_evidence_sleeves"), "weak_evidence_sleeves"),
        paper_qualified_sleeves=_require_int(data.get("paper_qualified_sleeves"), "paper_qualified_sleeves"),
        blocked_sleeves=_require_int(data.get("blocked_sleeves"), "blocked_sleeves"),
        insufficient_evidence_sleeves=_require_int(
            data.get("insufficient_evidence_sleeves"), "insufficient_evidence_sleeves"
        ),
        qualified_sleeve_ids=_tuple_of_strings(data.get("qualified_sleeve_ids", ()), "qualified_sleeve_ids"),
        weak_evidence_sleeve_ids=_tuple_of_strings(
            data.get("weak_evidence_sleeve_ids", ()), "weak_evidence_sleeve_ids"
        ),
        blocked_sleeve_ids=_tuple_of_strings(data.get("blocked_sleeve_ids", ()), "blocked_sleeve_ids"),
        insufficient_evidence_sleeve_ids=_tuple_of_strings(
            data.get("insufficient_evidence_sleeve_ids", ()), "insufficient_evidence_sleeve_ids"
        ),
        summary="" if data.get("summary", "") is None else str(data.get("summary", "")),
    )


def sleeve_recommendation_result_to_dict(result: SleeveRecommendationResult) -> dict:
    """Serialize SleeveRecommendationResult to a plain dict."""
    return {
        "status": result.status.value,
        "recommended_active": result.recommended_active,
        "currently_eligible": result.currently_eligible,
        "qualification_status": result.qualification_status.value,
        "effective_allocation": result.effective_allocation,
        "target_allocation": result.target_allocation,
        "missing_evidence": list(result.missing_evidence),
        "blocking_reasons": list(result.blocking_reasons),
        "reason_summary": result.reason_summary,
        "exclusion_reason": result.exclusion_reason,
        "next_step": result.next_step,
    }


def sleeve_recommendation_result_from_dict(data: dict) -> SleeveRecommendationResult:
    """Deserialize SleeveRecommendationResult from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve recommendation result payload must be a dict, got {type(data).__name__!r}"
        )
    return SleeveRecommendationResult(
        status=SleeveRecommendationStatus(_require_non_empty_str(data.get("status"), "status")),
        recommended_active=_require_bool(data.get("recommended_active", False), "recommended_active"),
        currently_eligible=_require_bool(data.get("currently_eligible", False), "currently_eligible"),
        qualification_status=SleeveQualificationStatus(
            _require_non_empty_str(data.get("qualification_status"), "qualification_status")
        ),
        effective_allocation=_require_float_like(data.get("effective_allocation", 0.0), "effective_allocation"),
        target_allocation=_require_float_like(data.get("target_allocation", 0.0), "target_allocation"),
        missing_evidence=_tuple_of_strings(data.get("missing_evidence", ()), "missing_evidence"),
        blocking_reasons=_tuple_of_strings(data.get("blocking_reasons", ()), "blocking_reasons"),
        reason_summary="" if data.get("reason_summary", "") is None else str(data.get("reason_summary", "")),
        exclusion_reason=("" if data.get("exclusion_reason", "") is None else str(data.get("exclusion_reason", ""))),
        next_step=_require_non_empty_str(data.get("next_step"), "next_step"),
    )


def sleeve_campaign_evidence_result_to_dict(result: SleeveCampaignEvidenceResult) -> dict:
    """Serialize SleeveCampaignEvidenceResult to a plain dict."""
    return {
        "status": result.status.value,
        "campaign_evidence_available": result.campaign_evidence_available,
        "explicit_link_available": result.explicit_link_available,
        "linked_in_campaign": result.linked_in_campaign,
        "supporting_campaign_ids": list(result.supporting_campaign_ids),
        "missing_evidence": list(result.missing_evidence),
        "blocking_reasons": list(result.blocking_reasons),
        "reason_summary": result.reason_summary,
        "next_step": result.next_step,
    }


def sleeve_campaign_evidence_result_from_dict(data: dict) -> SleeveCampaignEvidenceResult:
    """Deserialize SleeveCampaignEvidenceResult from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve campaign evidence payload must be a dict, got {type(data).__name__!r}"
        )
    return SleeveCampaignEvidenceResult(
        status=SleeveCampaignEvidenceStatus(_require_non_empty_str(data.get("status"), "status")),
        campaign_evidence_available=_require_bool(
            data.get("campaign_evidence_available", False), "campaign_evidence_available"
        ),
        explicit_link_available=_require_bool(data.get("explicit_link_available", False), "explicit_link_available"),
        linked_in_campaign=_require_bool(data.get("linked_in_campaign", False), "linked_in_campaign"),
        supporting_campaign_ids=_tuple_of_strings(data.get("supporting_campaign_ids", ()), "supporting_campaign_ids"),
        missing_evidence=_tuple_of_strings(data.get("missing_evidence", ()), "missing_evidence"),
        blocking_reasons=_tuple_of_strings(data.get("blocking_reasons", ()), "blocking_reasons"),
        reason_summary="" if data.get("reason_summary", "") is None else str(data.get("reason_summary", "")),
        next_step=_require_non_empty_str(data.get("next_step"), "next_step"),
    )


def sleeve_promotion_support_result_to_dict(result: SleevePromotionSupportResult) -> dict:
    """Serialize SleevePromotionSupportResult to a plain dict."""
    return {
        "status": result.status.value,
        "can_be_considered_later": result.can_be_considered_later,
        "campaign_evidence_status": result.campaign_evidence_status.value,
        "qualification_status": result.qualification_status.value,
        "recommendation_status": result.recommendation_status.value,
        "missing_evidence": list(result.missing_evidence),
        "blocking_reasons": list(result.blocking_reasons),
        "reason_summary": result.reason_summary,
        "next_step": result.next_step,
    }


def sleeve_promotion_support_result_from_dict(data: dict) -> SleevePromotionSupportResult:
    """Deserialize SleevePromotionSupportResult from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve promotion support payload must be a dict, got {type(data).__name__!r}"
        )
    return SleevePromotionSupportResult(
        status=SleevePromotionSupportStatus(_require_non_empty_str(data.get("status"), "status")),
        can_be_considered_later=_require_bool(data.get("can_be_considered_later", False), "can_be_considered_later"),
        campaign_evidence_status=SleeveCampaignEvidenceStatus(
            _require_non_empty_str(data.get("campaign_evidence_status"), "campaign_evidence_status")
        ),
        qualification_status=SleeveQualificationStatus(
            _require_non_empty_str(data.get("qualification_status"), "qualification_status")
        ),
        recommendation_status=SleeveRecommendationStatus(
            _require_non_empty_str(data.get("recommendation_status"), "recommendation_status")
        ),
        missing_evidence=_tuple_of_strings(data.get("missing_evidence", ()), "missing_evidence"),
        blocking_reasons=_tuple_of_strings(data.get("blocking_reasons", ()), "blocking_reasons"),
        reason_summary="" if data.get("reason_summary", "") is None else str(data.get("reason_summary", "")),
        next_step=_require_non_empty_str(data.get("next_step"), "next_step"),
    )


def sleeve_promotion_candidate_result_to_dict(result: SleevePromotionCandidateResult) -> dict:
    """Serialize SleevePromotionCandidateResult to a plain dict."""
    return {
        "status": result.status.value,
        "candidate_for_future_review": result.candidate_for_future_review,
        "strongly_supported": result.strongly_supported,
        "campaign_evidence_status": result.campaign_evidence_status.value,
        "promotion_support_status": result.promotion_support_status.value,
        "qualification_status": result.qualification_status.value,
        "recommendation_status": result.recommendation_status.value,
        "missing_evidence": list(result.missing_evidence),
        "blocking_reasons": list(result.blocking_reasons),
        "reason_summary": result.reason_summary,
        "next_step": result.next_step,
        "pbo_allocation_cap": result.pbo_allocation_cap,
    }


def sleeve_promotion_candidate_result_from_dict(data: dict) -> SleevePromotionCandidateResult:
    """Deserialize SleevePromotionCandidateResult from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve promotion candidate payload must be a dict, got {type(data).__name__!r}"
        )
    return SleevePromotionCandidateResult(
        status=SleevePromotionCandidateStatus(_require_non_empty_str(data.get("status"), "status")),
        candidate_for_future_review=_require_bool(
            data.get("candidate_for_future_review", False), "candidate_for_future_review"
        ),
        strongly_supported=_require_bool(data.get("strongly_supported", False), "strongly_supported"),
        campaign_evidence_status=SleeveCampaignEvidenceStatus(
            _require_non_empty_str(data.get("campaign_evidence_status"), "campaign_evidence_status")
        ),
        promotion_support_status=SleevePromotionSupportStatus(
            _require_non_empty_str(data.get("promotion_support_status"), "promotion_support_status")
        ),
        qualification_status=SleeveQualificationStatus(
            _require_non_empty_str(data.get("qualification_status"), "qualification_status")
        ),
        recommendation_status=SleeveRecommendationStatus(
            _require_non_empty_str(data.get("recommendation_status"), "recommendation_status")
        ),
        missing_evidence=_tuple_of_strings(data.get("missing_evidence", ()), "missing_evidence"),
        blocking_reasons=_tuple_of_strings(data.get("blocking_reasons", ()), "blocking_reasons"),
        reason_summary="" if data.get("reason_summary", "") is None else str(data.get("reason_summary", "")),
        next_step=_require_non_empty_str(data.get("next_step"), "next_step"),
        pbo_allocation_cap=data.get("pbo_allocation_cap"),
    )


def sleeve_decision_pack_result_to_dict(result: SleeveDecisionPackResult) -> dict:
    """Serialize SleeveDecisionPackResult to a plain dict."""
    return {
        "status": result.status.value,
        "recommended_active": result.recommended_active,
        "currently_eligible": result.currently_eligible,
        "promotion_candidate": result.promotion_candidate,
        "strongly_supported_candidate": result.strongly_supported_candidate,
        "recommendation_status": result.recommendation_status.value,
        "qualification_status": result.qualification_status.value,
        "campaign_evidence_status": result.campaign_evidence_status.value,
        "promotion_support_status": result.promotion_support_status.value,
        "promotion_candidate_status": result.promotion_candidate_status.value,
        "missing_evidence": list(result.missing_evidence),
        "blocking_reasons": list(result.blocking_reasons),
        "reason_summary": result.reason_summary,
        "next_step": result.next_step,
    }


def sleeve_decision_pack_result_from_dict(data: dict) -> SleeveDecisionPackResult:
    """Deserialize SleeveDecisionPackResult from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(f"Sleeve decision pack payload must be a dict, got {type(data).__name__!r}")
    return SleeveDecisionPackResult(
        status=SleeveDecisionPackStatus(_require_non_empty_str(data.get("status"), "status")),
        recommended_active=_require_bool(data.get("recommended_active", False), "recommended_active"),
        currently_eligible=_require_bool(data.get("currently_eligible", False), "currently_eligible"),
        promotion_candidate=_require_bool(data.get("promotion_candidate", False), "promotion_candidate"),
        strongly_supported_candidate=_require_bool(
            data.get("strongly_supported_candidate", False), "strongly_supported_candidate"
        ),
        recommendation_status=SleeveRecommendationStatus(
            _require_non_empty_str(data.get("recommendation_status"), "recommendation_status")
        ),
        qualification_status=SleeveQualificationStatus(
            _require_non_empty_str(data.get("qualification_status"), "qualification_status")
        ),
        campaign_evidence_status=SleeveCampaignEvidenceStatus(
            _require_non_empty_str(data.get("campaign_evidence_status"), "campaign_evidence_status")
        ),
        promotion_support_status=SleevePromotionSupportStatus(
            _require_non_empty_str(data.get("promotion_support_status"), "promotion_support_status")
        ),
        promotion_candidate_status=SleevePromotionCandidateStatus(
            _require_non_empty_str(data.get("promotion_candidate_status"), "promotion_candidate_status")
        ),
        missing_evidence=_tuple_of_strings(data.get("missing_evidence", ()), "missing_evidence"),
        blocking_reasons=_tuple_of_strings(data.get("blocking_reasons", ()), "blocking_reasons"),
        reason_summary="" if data.get("reason_summary", "") is None else str(data.get("reason_summary", "")),
        next_step=_require_non_empty_str(data.get("next_step"), "next_step"),
    )


def sleeve_portfolio_evidence_summary_to_dict(summary: SleevePortfolioEvidenceSummary) -> dict:
    """Serialize SleevePortfolioEvidenceSummary to a plain dict."""
    return {
        "total_sleeves": summary.total_sleeves,
        "no_campaign_evidence_sleeves": summary.no_campaign_evidence_sleeves,
        "weak_campaign_evidence_sleeves": summary.weak_campaign_evidence_sleeves,
        "campaign_supported_sleeves": summary.campaign_supported_sleeves,
        "blocked_evidence_sleeves": summary.blocked_evidence_sleeves,
        "inconclusive_sleeves": summary.inconclusive_sleeves,
        "supportive_promotion_sleeves": summary.supportive_promotion_sleeves,
        "weak_support_sleeves": summary.weak_support_sleeves,
        "no_campaign_evidence_sleeve_ids": list(summary.no_campaign_evidence_sleeve_ids),
        "weak_campaign_evidence_sleeve_ids": list(summary.weak_campaign_evidence_sleeve_ids),
        "campaign_supported_sleeve_ids": list(summary.campaign_supported_sleeve_ids),
        "blocked_evidence_sleeve_ids": list(summary.blocked_evidence_sleeve_ids),
        "inconclusive_sleeve_ids": list(summary.inconclusive_sleeve_ids),
        "supportive_promotion_sleeve_ids": list(summary.supportive_promotion_sleeve_ids),
        "weak_support_sleeve_ids": list(summary.weak_support_sleeve_ids),
        "missing_evidence": list(summary.missing_evidence),
        "blocking_reasons": list(summary.blocking_reasons),
        "summary": summary.summary,
    }


def sleeve_portfolio_evidence_summary_from_dict(data: dict) -> SleevePortfolioEvidenceSummary:
    """Deserialize SleevePortfolioEvidenceSummary from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve portfolio evidence payload must be a dict, got {type(data).__name__!r}"
        )
    return SleevePortfolioEvidenceSummary(
        total_sleeves=_require_int(data.get("total_sleeves"), "total_sleeves"),
        no_campaign_evidence_sleeves=_require_int(
            data.get("no_campaign_evidence_sleeves"), "no_campaign_evidence_sleeves"
        ),
        weak_campaign_evidence_sleeves=_require_int(
            data.get("weak_campaign_evidence_sleeves"), "weak_campaign_evidence_sleeves"
        ),
        campaign_supported_sleeves=_require_int(data.get("campaign_supported_sleeves"), "campaign_supported_sleeves"),
        blocked_evidence_sleeves=_require_int(data.get("blocked_evidence_sleeves"), "blocked_evidence_sleeves"),
        inconclusive_sleeves=_require_int(data.get("inconclusive_sleeves"), "inconclusive_sleeves"),
        supportive_promotion_sleeves=_require_int(
            data.get("supportive_promotion_sleeves"), "supportive_promotion_sleeves"
        ),
        weak_support_sleeves=_require_int(data.get("weak_support_sleeves"), "weak_support_sleeves"),
        no_campaign_evidence_sleeve_ids=_tuple_of_strings(
            data.get("no_campaign_evidence_sleeve_ids", ()), "no_campaign_evidence_sleeve_ids"
        ),
        weak_campaign_evidence_sleeve_ids=_tuple_of_strings(
            data.get("weak_campaign_evidence_sleeve_ids", ()), "weak_campaign_evidence_sleeve_ids"
        ),
        campaign_supported_sleeve_ids=_tuple_of_strings(
            data.get("campaign_supported_sleeve_ids", ()), "campaign_supported_sleeve_ids"
        ),
        blocked_evidence_sleeve_ids=_tuple_of_strings(
            data.get("blocked_evidence_sleeve_ids", ()), "blocked_evidence_sleeve_ids"
        ),
        inconclusive_sleeve_ids=_tuple_of_strings(data.get("inconclusive_sleeve_ids", ()), "inconclusive_sleeve_ids"),
        supportive_promotion_sleeve_ids=_tuple_of_strings(
            data.get("supportive_promotion_sleeve_ids", ()), "supportive_promotion_sleeve_ids"
        ),
        weak_support_sleeve_ids=_tuple_of_strings(data.get("weak_support_sleeve_ids", ()), "weak_support_sleeve_ids"),
        missing_evidence=_tuple_of_strings(data.get("missing_evidence", ()), "missing_evidence"),
        blocking_reasons=_tuple_of_strings(data.get("blocking_reasons", ()), "blocking_reasons"),
        summary="" if data.get("summary", "") is None else str(data.get("summary", "")),
    )


def sleeve_portfolio_decision_summary_to_dict(summary: SleevePortfolioDecisionSummary) -> dict:
    """Serialize SleevePortfolioDecisionSummary to a plain dict."""
    return {
        "total_sleeves": summary.total_sleeves,
        "recommended_active_sleeves": summary.recommended_active_sleeves,
        "eligible_but_not_selected_sleeves": summary.eligible_but_not_selected_sleeves,
        "blocked_sleeves": summary.blocked_sleeves,
        "insufficient_evidence_sleeves": summary.insufficient_evidence_sleeves,
        "disabled_operator_off_sleeves": summary.disabled_operator_off_sleeves,
        "recommended_sleeve_ids": list(summary.recommended_sleeve_ids),
        "eligible_sleeve_ids": list(summary.eligible_sleeve_ids),
        "excluded_sleeve_ids": list(summary.excluded_sleeve_ids),
        "missing_evidence": list(summary.missing_evidence),
        "blocking_reasons": list(summary.blocking_reasons),
        "effective_allocated_share": summary.effective_allocated_share,
        "effective_unallocated_share": summary.effective_unallocated_share,
        "conserved_blocked_share": summary.conserved_blocked_share,
        "conserved_disabled_share": summary.conserved_disabled_share,
        "summary": summary.summary,
    }


def sleeve_portfolio_decision_summary_from_dict(data: dict) -> SleevePortfolioDecisionSummary:
    """Deserialize SleevePortfolioDecisionSummary from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve portfolio decision payload must be a dict, got {type(data).__name__!r}"
        )
    return SleevePortfolioDecisionSummary(
        total_sleeves=_require_int(data.get("total_sleeves"), "total_sleeves"),
        recommended_active_sleeves=_require_int(data.get("recommended_active_sleeves"), "recommended_active_sleeves"),
        eligible_but_not_selected_sleeves=_require_int(
            data.get("eligible_but_not_selected_sleeves"), "eligible_but_not_selected_sleeves"
        ),
        blocked_sleeves=_require_int(data.get("blocked_sleeves"), "blocked_sleeves"),
        insufficient_evidence_sleeves=_require_int(
            data.get("insufficient_evidence_sleeves"), "insufficient_evidence_sleeves"
        ),
        disabled_operator_off_sleeves=_require_int(
            data.get("disabled_operator_off_sleeves"), "disabled_operator_off_sleeves"
        ),
        recommended_sleeve_ids=_tuple_of_strings(data.get("recommended_sleeve_ids", ()), "recommended_sleeve_ids"),
        eligible_sleeve_ids=_tuple_of_strings(data.get("eligible_sleeve_ids", ()), "eligible_sleeve_ids"),
        excluded_sleeve_ids=_tuple_of_strings(data.get("excluded_sleeve_ids", ()), "excluded_sleeve_ids"),
        missing_evidence=_tuple_of_strings(data.get("missing_evidence", ()), "missing_evidence"),
        blocking_reasons=_tuple_of_strings(data.get("blocking_reasons", ()), "blocking_reasons"),
        effective_allocated_share=_require_float_like(
            data.get("effective_allocated_share", 0.0), "effective_allocated_share"
        ),
        effective_unallocated_share=_require_float_like(
            data.get("effective_unallocated_share", 0.0), "effective_unallocated_share"
        ),
        conserved_blocked_share=_require_float_like(
            data.get("conserved_blocked_share", 0.0), "conserved_blocked_share"
        ),
        conserved_disabled_share=_require_float_like(
            data.get("conserved_disabled_share", 0.0), "conserved_disabled_share"
        ),
        summary="" if data.get("summary", "") is None else str(data.get("summary", "")),
    )


def sleeve_portfolio_decision_pack_summary_to_dict(summary: SleevePortfolioDecisionPackSummary) -> dict:
    """Serialize SleevePortfolioDecisionPackSummary to a plain dict."""
    return {
        "total_sleeves": summary.total_sleeves,
        "recommended_active_sleeves": summary.recommended_active_sleeves,
        "eligible_but_not_selected_sleeves": summary.eligible_but_not_selected_sleeves,
        "supported_candidate_sleeves": summary.supported_candidate_sleeves,
        "watchlist_candidate_sleeves": summary.watchlist_candidate_sleeves,
        "blocked_sleeves": summary.blocked_sleeves,
        "insufficient_evidence_sleeves": summary.insufficient_evidence_sleeves,
        "recommended_sleeve_ids": list(summary.recommended_sleeve_ids),
        "eligible_sleeve_ids": list(summary.eligible_sleeve_ids),
        "supported_candidate_sleeve_ids": list(summary.supported_candidate_sleeve_ids),
        "watchlist_candidate_sleeve_ids": list(summary.watchlist_candidate_sleeve_ids),
        "blocked_sleeve_ids": list(summary.blocked_sleeve_ids),
        "insufficient_evidence_sleeve_ids": list(summary.insufficient_evidence_sleeve_ids),
        "missing_evidence": list(summary.missing_evidence),
        "blocking_reasons": list(summary.blocking_reasons),
        "summary": summary.summary,
    }


def sleeve_portfolio_decision_pack_summary_from_dict(data: dict) -> SleevePortfolioDecisionPackSummary:
    """Deserialize SleevePortfolioDecisionPackSummary from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve portfolio decision pack payload must be a dict, got {type(data).__name__!r}"
        )
    return SleevePortfolioDecisionPackSummary(
        total_sleeves=_require_int(data.get("total_sleeves"), "total_sleeves"),
        recommended_active_sleeves=_require_int(data.get("recommended_active_sleeves"), "recommended_active_sleeves"),
        eligible_but_not_selected_sleeves=_require_int(
            data.get("eligible_but_not_selected_sleeves"), "eligible_but_not_selected_sleeves"
        ),
        supported_candidate_sleeves=_require_int(
            data.get("supported_candidate_sleeves"), "supported_candidate_sleeves"
        ),
        watchlist_candidate_sleeves=_require_int(
            data.get("watchlist_candidate_sleeves"), "watchlist_candidate_sleeves"
        ),
        blocked_sleeves=_require_int(data.get("blocked_sleeves"), "blocked_sleeves"),
        insufficient_evidence_sleeves=_require_int(
            data.get("insufficient_evidence_sleeves"), "insufficient_evidence_sleeves"
        ),
        recommended_sleeve_ids=_tuple_of_strings(data.get("recommended_sleeve_ids", ()), "recommended_sleeve_ids"),
        eligible_sleeve_ids=_tuple_of_strings(data.get("eligible_sleeve_ids", ()), "eligible_sleeve_ids"),
        supported_candidate_sleeve_ids=_tuple_of_strings(
            data.get("supported_candidate_sleeve_ids", ()), "supported_candidate_sleeve_ids"
        ),
        watchlist_candidate_sleeve_ids=_tuple_of_strings(
            data.get("watchlist_candidate_sleeve_ids", ()), "watchlist_candidate_sleeve_ids"
        ),
        blocked_sleeve_ids=_tuple_of_strings(data.get("blocked_sleeve_ids", ()), "blocked_sleeve_ids"),
        insufficient_evidence_sleeve_ids=_tuple_of_strings(
            data.get("insufficient_evidence_sleeve_ids", ()), "insufficient_evidence_sleeve_ids"
        ),
        missing_evidence=_tuple_of_strings(data.get("missing_evidence", ()), "missing_evidence"),
        blocking_reasons=_tuple_of_strings(data.get("blocking_reasons", ()), "blocking_reasons"),
        summary="" if data.get("summary", "") is None else str(data.get("summary", "")),
    )


def sleeve_allocation_summary_from_dict(data: dict) -> SleeveAllocationSummary:
    """Deserialize SleeveAllocationSummary from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve allocation summary payload must be a dict, got {type(data).__name__!r}"
        )
    try:
        return SleeveAllocationSummary(
            target_allocated_share=_require_float_like(
                data.get("target_allocated_share", 0.0), "target_allocated_share"
            ),
            active_allocated_share=_require_float_like(
                data.get("active_allocated_share", 0.0), "active_allocated_share"
            ),
            blocked_allocated_share=_require_float_like(
                data.get("blocked_allocated_share", 0.0), "blocked_allocated_share"
            ),
            disabled_allocated_share=_require_float_like(
                data.get("disabled_allocated_share", 0.0), "disabled_allocated_share"
            ),
            unallocated_share=_require_float_like(data.get("unallocated_share", 0.0), "unallocated_share"),
            total_sleeves=_require_int(data.get("total_sleeves"), "total_sleeves"),
            defined_sleeves=_require_int(data.get("defined_sleeves"), "defined_sleeves"),
            enabled_sleeves=_require_int(data.get("enabled_sleeves"), "enabled_sleeves"),
            allocated_sleeves=_require_int(data.get("allocated_sleeves"), "allocated_sleeves"),
            blocked_sleeves=_require_int(data.get("blocked_sleeves"), "blocked_sleeves"),
            disabled_sleeves=_require_int(data.get("disabled_sleeves"), "disabled_sleeves"),
        )
    except SleevePortfolioValidationError as exc:
        raise SleevePortfolioCorruptError(str(exc)) from exc


def sleeve_portfolio_snapshot_to_dict(snapshot: SleevePortfolioSnapshot) -> dict:
    """Serialize SleevePortfolioSnapshot to a plain dict."""
    return {
        "as_of_ns": snapshot.as_of_ns,
        "sleeves": [crypto_sleeve_state_to_dict(sleeve) for sleeve in snapshot.sleeves],
        "allocation": sleeve_allocation_summary_to_dict(snapshot.allocation),
        "allocation_policy": sleeve_allocation_policy_to_dict(snapshot.allocation_policy),
        "effective_allocation": sleeve_effective_allocation_summary_to_dict(snapshot.effective_allocation),
        "qualification": sleeve_qualification_summary_to_dict(snapshot.qualification),
        "decision": sleeve_portfolio_decision_summary_to_dict(snapshot.decision),
        "evidence": sleeve_portfolio_evidence_summary_to_dict(snapshot.evidence),
        "decision_pack": sleeve_portfolio_decision_pack_summary_to_dict(snapshot.decision_pack),
        "enabled_sleeve_ids": list(snapshot.enabled_sleeve_ids),
        "blocked_sleeve_ids": list(snapshot.blocked_sleeve_ids),
        "allocated_sleeve_ids": list(snapshot.allocated_sleeve_ids),
        "blocked_reason_summaries": list(snapshot.blocked_reason_summaries),
        "summary": snapshot.summary,
        "readiness_level": snapshot.readiness_level,
        "readiness_is_supportive": snapshot.readiness_is_supportive,
        "escalation_allowed_next_step": snapshot.escalation_allowed_next_step,
        "external_regime_execution_blocked": snapshot.external_regime_execution_blocked,
        "workflow_status": snapshot.workflow_status,
        "comparison_to_previous": dict(snapshot.comparison_to_previous),
        "history_summary": dict(snapshot.history_summary),
    }


def sleeve_portfolio_snapshot_from_dict(data: dict) -> SleevePortfolioSnapshot:
    """Deserialize SleevePortfolioSnapshot from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve portfolio snapshot payload must be a dict, got {type(data).__name__!r}"
        )

    sleeves_value = data.get("sleeves", ())
    if not isinstance(sleeves_value, (list, tuple)):
        raise SleevePortfolioCorruptError("Sleeve portfolio field 'sleeves' must be a list/tuple")

    sleeves = tuple(crypto_sleeve_state_from_dict(item) for item in sleeves_value)
    snapshot = build_sleeve_portfolio_snapshot(
        sleeves=sleeves,
        as_of_ns=_require_int(data.get("as_of_ns"), "as_of_ns"),
        readiness_level=_optional_str(data.get("readiness_level"), "readiness_level"),
        readiness_is_supportive=_require_bool(data.get("readiness_is_supportive", False), "readiness_is_supportive"),
        escalation_allowed_next_step=_optional_str(
            data.get("escalation_allowed_next_step"), "escalation_allowed_next_step"
        ),
        external_regime_execution_blocked=(
            None
            if data.get("external_regime_execution_blocked") is None
            else _require_bool(data.get("external_regime_execution_blocked"), "external_regime_execution_blocked")
        ),
        allocation_policy=(
            SleeveAllocationPolicy()
            if data.get("allocation_policy") is None
            else sleeve_allocation_policy_from_dict(dict(data.get("allocation_policy")))
        ),
        workflow_status=(
            "static" if data.get("workflow_status", "static") is None else str(data.get("workflow_status", "static"))
        ),
        comparison_to_previous=(
            {} if data.get("comparison_to_previous") is None else dict(data.get("comparison_to_previous"))
        ),
        history_summary={} if data.get("history_summary") is None else dict(data.get("history_summary")),
    )

    allocation_value = data.get("allocation")
    if allocation_value is not None:
        restored_allocation = sleeve_allocation_summary_from_dict(allocation_value)
        if restored_allocation != snapshot.allocation:
            raise SleevePortfolioCorruptError("Sleeve portfolio allocation summary does not match sleeve decomposition")

    effective_allocation_value = data.get("effective_allocation")
    if effective_allocation_value is not None:
        restored_effective = sleeve_effective_allocation_summary_from_dict(effective_allocation_value)
        if restored_effective != snapshot.effective_allocation:
            raise SleevePortfolioCorruptError("Sleeve effective allocation summary does not match policy recompute")

    qualification_value = data.get("qualification")
    if qualification_value is not None:
        restored_qualification = sleeve_qualification_summary_from_dict(qualification_value)
        if restored_qualification != snapshot.qualification:
            raise SleevePortfolioCorruptError("Sleeve qualification summary does not match qualification recompute")

    decision_value = data.get("decision")
    if decision_value is not None:
        restored_decision = sleeve_portfolio_decision_summary_from_dict(decision_value)
        if restored_decision != snapshot.decision:
            raise SleevePortfolioCorruptError(
                "Sleeve portfolio decision summary does not match recommendation recompute"
            )

    evidence_value = data.get("evidence")
    if evidence_value is not None:
        restored_evidence = sleeve_portfolio_evidence_summary_from_dict(evidence_value)
        if restored_evidence != snapshot.evidence:
            raise SleevePortfolioCorruptError(
                "Sleeve portfolio evidence summary does not match campaign evidence recompute"
            )

    decision_pack_value = data.get("decision_pack")
    if decision_pack_value is not None:
        restored_decision_pack = sleeve_portfolio_decision_pack_summary_from_dict(decision_pack_value)
        if restored_decision_pack != snapshot.decision_pack:
            raise SleevePortfolioCorruptError("Sleeve portfolio decision pack does not match candidate recompute")

    enabled_ids = _tuple_of_strings(data.get("enabled_sleeve_ids", ()), "enabled_sleeve_ids")
    blocked_ids = _tuple_of_strings(data.get("blocked_sleeve_ids", ()), "blocked_sleeve_ids")
    allocated_ids = _tuple_of_strings(data.get("allocated_sleeve_ids", ()), "allocated_sleeve_ids")
    blocked_reason_summaries = _tuple_of_strings(data.get("blocked_reason_summaries", ()), "blocked_reason_summaries")

    if enabled_ids and enabled_ids != snapshot.enabled_sleeve_ids:
        raise SleevePortfolioCorruptError("Enabled sleeve ids do not match sleeve statuses")
    if blocked_ids and blocked_ids != snapshot.blocked_sleeve_ids:
        raise SleevePortfolioCorruptError("Blocked sleeve ids do not match sleeve statuses")
    if allocated_ids and allocated_ids != snapshot.allocated_sleeve_ids:
        raise SleevePortfolioCorruptError("Allocated sleeve ids do not match sleeve statuses")
    if blocked_reason_summaries and blocked_reason_summaries != snapshot.blocked_reason_summaries:
        raise SleevePortfolioCorruptError("Blocked reason summaries do not match sleeve states")

    return snapshot
