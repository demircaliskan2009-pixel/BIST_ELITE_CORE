"""Crypto sleeve admission controller and models — Phase 15F.

Deterministic, serialization-friendly controller for managed sleeve admission gating.

Design rules:
  - Uses only existing sleeve promotion review, readiness, escalation, and governance truth.
  - No new promotion engine, ranking, or allocation logic.
  - Bounded finalized history only; malformed persisted state fails closed.
  - PAPER-ONLY.

PRD reference: §2 System Orchestration, §7 Execution Engine, Phase 15F.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from crypto_core.service.sleeve_promotion_review_controller import (
    SleevePromotionReviewPortfolioSummary,
    SleevePromotionReviewResult,
    SleevePromotionReviewVerdict,
)


class SleeveAdmissionVerdict(str, Enum):
    ADMITTED_ACTIVE = "admitted_active"
    ADMITTED_UNALLOCATED = "admitted_unallocated"
    REVIEW_SUPPORTED_NOT_ADMITTED = "review_supported_not_admitted"
    NOT_ADMITTED_BLOCKED = "not_admitted_blocked"
    NOT_ADMITTED_INCONCLUSIVE = "not_admitted_inconclusive"


@dataclass(frozen=True)
class SleeveAdmissionResult:
    sleeve_id: str
    verdict: SleeveAdmissionVerdict
    reason: str
    next_step: str
    governance_blockers: Tuple[str, ...] = ()
    evidence_blockers: Tuple[str, ...] = ()
    last_review_verdict: Optional[SleevePromotionReviewVerdict] = None


@dataclass(frozen=True)
class SleeveAdmissionPortfolioSummary:
    as_of_ns: int
    admission_results: Tuple[SleeveAdmissionResult, ...]
    admitted_active: Tuple[str, ...]
    admitted_unallocated: Tuple[str, ...]
    review_supported_not_admitted: Tuple[str, ...]
    blocked: Tuple[str, ...]
    inconclusive: Tuple[str, ...]
    governance_blockers: Tuple[str, ...]
    evidence_blockers: Tuple[str, ...]
    operator_summary: str


@dataclass(frozen=True)
class SleeveAdmissionHistoryEntry:
    as_of_ns: int
    summary: str
    portfolio_summary: SleeveAdmissionPortfolioSummary


@dataclass(frozen=True)
class SleeveAdmissionSnapshot:
    as_of_ns: int
    status: str
    admission_results: Tuple[SleeveAdmissionResult, ...]
    portfolio_summary: SleeveAdmissionPortfolioSummary
    history: Tuple[SleeveAdmissionHistoryEntry, ...] = ()


class SleeveAdmissionCorruptError(RuntimeError):
    pass


class SleeveAdmissionController:
    """Managed controller for crypto sleeve admission gating."""

    def __init__(self, review_portfolio_summary: SleevePromotionReviewPortfolioSummary, history_limit: int = 5):
        self.review_portfolio_summary = review_portfolio_summary
        self.history_limit = history_limit
        self.history = []
        self._validate()

    def _validate(self):
        if not self.review_portfolio_summary or not hasattr(self.review_portfolio_summary, "review_results"):
            raise SleeveAdmissionCorruptError("Malformed review portfolio summary.")

    def build_admission_results(self) -> Tuple[SleeveAdmissionResult, ...]:
        results = []
        for review in getattr(self.review_portfolio_summary, "review_results", []):
            verdict, reason, next_step = self._derive_verdict(review)
            results.append(
                SleeveAdmissionResult(
                    sleeve_id=review.sleeve_id,
                    verdict=verdict,
                    reason=reason,
                    next_step=next_step,
                    governance_blockers=review.governance_blockers,
                    evidence_blockers=review.missing_evidence,
                    last_review_verdict=review.verdict,
                )
            )
        return tuple(results)

    def _derive_verdict(self, review: SleevePromotionReviewResult):
        # Deterministic mapping from review verdict and blockers to admission verdict
        if (
            review.verdict == SleevePromotionReviewVerdict.REVIEW_SUPPORTED
            and not review.governance_blockers
            and not review.missing_evidence
        ):
            return (
                SleeveAdmissionVerdict.ADMITTED_ACTIVE,
                "Admitted and active.",
                "Monitor allocation and governance.",
            )
        if (
            review.verdict == SleevePromotionReviewVerdict.REVIEW_SUPPORTED
            and not review.governance_blockers
            and review.missing_evidence
        ):
            return (
                SleeveAdmissionVerdict.ADMITTED_UNALLOCATED,
                "Admitted but unallocated due to missing evidence.",
                "Complete evidence for allocation.",
            )
        if review.verdict == SleevePromotionReviewVerdict.REVIEW_SUPPORTED and review.governance_blockers:
            return (
                SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED,
                "Review supported but governance blocked.",
                "Resolve governance blockers.",
            )
        if review.verdict == SleevePromotionReviewVerdict.HOLD:
            return (SleeveAdmissionVerdict.NOT_ADMITTED_BLOCKED, "Not admitted: hold verdict.", "Address hold reasons.")
        if review.verdict == SleevePromotionReviewVerdict.REJECT:
            return (
                SleeveAdmissionVerdict.NOT_ADMITTED_BLOCKED,
                "Not admitted: rejected.",
                "Review rejection rationale.",
            )
        if review.verdict == SleevePromotionReviewVerdict.INCONCLUSIVE:
            return (
                SleeveAdmissionVerdict.NOT_ADMITTED_INCONCLUSIVE,
                "Not admitted: inconclusive.",
                "Gather more evidence.",
            )
        return (
            SleeveAdmissionVerdict.NOT_ADMITTED_INCONCLUSIVE,
            "Not admitted: unknown state.",
            "Investigate admission logic.",
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
        blocked = tuple(r.sleeve_id for r in results if r.verdict == SleeveAdmissionVerdict.NOT_ADMITTED_BLOCKED)
        inconclusive = tuple(
            r.sleeve_id for r in results if r.verdict == SleeveAdmissionVerdict.NOT_ADMITTED_INCONCLUSIVE
        )
        governance_blockers = tuple(sorted({b for r in results for b in r.governance_blockers}))
        evidence_blockers = tuple(sorted({b for r in results for b in r.evidence_blockers}))
        operator_summary = f"Admitted: {len(admitted_active)}, Unallocated: {len(admitted_unallocated)}, Supported/Blocked: {len(review_supported_not_admitted)}, Blocked: {len(blocked)}, Inconclusive: {len(inconclusive)}"
        return SleeveAdmissionPortfolioSummary(
            as_of_ns=int(time.time_ns()),
            admission_results=results,
            admitted_active=admitted_active,
            admitted_unallocated=admitted_unallocated,
            review_supported_not_admitted=review_supported_not_admitted,
            blocked=blocked,
            inconclusive=inconclusive,
            governance_blockers=governance_blockers,
            evidence_blockers=evidence_blockers,
            operator_summary=operator_summary,
        )

    def snapshot(self, status: str = "active") -> SleeveAdmissionSnapshot:
        summary = self.build_portfolio_summary()
        history = tuple(self.history[-self.history_limit :])
        entry = SleeveAdmissionHistoryEntry(
            as_of_ns=summary.as_of_ns,
            summary=summary.operator_summary,
            portfolio_summary=summary,
        )
        history = history + (entry,)
        return SleeveAdmissionSnapshot(
            as_of_ns=summary.as_of_ns,
            status=status,
            admission_results=summary.admission_results,
            portfolio_summary=summary,
            history=history,
        )
