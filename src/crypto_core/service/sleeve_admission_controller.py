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

from dataclasses import dataclass
from enum import Enum

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
