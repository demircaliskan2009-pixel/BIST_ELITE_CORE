"""Crypto sleeve promotion-review controller — Phase 15E.

Deterministic, serialization-friendly controller for managed sleeve promotion review.

Design rules:
  - Uses only existing sleeve qualification, recommendation, decision-pack, candidate workflow, and governance truth.
  - No new promotion engine or synthetic maturity state.
  - Bounded finalized history only; malformed persisted state fails closed.
  - PAPER-ONLY.

PRD reference: §2 System Orchestration, §7 Execution Engine, Phase 15E.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from crypto_core.service.sleeve_candidate_workflow import (
    SleeveCandidateWorkflowEntry,
    SleeveCandidateWorkflowSnapshot,
)
from crypto_core.service.sleeve_portfolio import (
    SleevePromotionCandidateStatus,
    SleevePromotionSupportStatus,
)


# --- Promotion Review Verdicts ---
class SleevePromotionReviewVerdict(str, Enum):
    REVIEW_SUPPORTED = "review_supported"
    HOLD = "hold"
    REJECT = "reject"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class SleevePromotionReviewResult:
    sleeve_id: str
    verdict: SleevePromotionReviewVerdict
    reason: str
    next_step: str
    repeated_weak: bool = False
    repeated_blocked: bool = False
    repeated_inconclusive: bool = False
    missing_evidence: tuple[str, ...] = ()
    governance_blockers: tuple[str, ...] = ()
    last_verdict: SleevePromotionReviewVerdict | None = None


@dataclass(frozen=True)
class SleevePromotionReviewPortfolioSummary:
    as_of_ns: int
    review_results: tuple[SleevePromotionReviewResult, ...]
    supported: tuple[str, ...]
    hold: tuple[str, ...]
    reject: tuple[str, ...]
    inconclusive: tuple[str, ...]
    repeated_weak: tuple[str, ...]
    repeated_blocked: tuple[str, ...]
    repeated_inconclusive: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    governance_blockers: tuple[str, ...]
    operator_summary: str


@dataclass(frozen=True)
class SleevePromotionReviewHistoryEntry:
    as_of_ns: int
    summary: str
    portfolio_summary: SleevePromotionReviewPortfolioSummary


@dataclass(frozen=True)
class SleevePromotionReviewSnapshot:
    as_of_ns: int
    status: str
    review_results: tuple[SleevePromotionReviewResult, ...]
    portfolio_summary: SleevePromotionReviewPortfolioSummary
    history: tuple[SleevePromotionReviewHistoryEntry, ...] = ()


class SleevePromotionReviewCorruptError(RuntimeError):
    pass


class SleevePromotionReviewController:
    """Managed controller for crypto sleeve promotion review."""

    def __init__(
        self,
        workflow_snapshot: SleeveCandidateWorkflowSnapshot,
        history_limit: int = 5,
        clock_ns: Callable[[], int] | None = None,
    ):
        self.workflow_snapshot = workflow_snapshot
        self.history_limit = history_limit
        self.history = []
        self._clock_ns = time.time_ns if clock_ns is None else clock_ns
        self._validate()

    def _validate(self):
        if not self.workflow_snapshot or not hasattr(self.workflow_snapshot, "sleeves"):
            raise SleevePromotionReviewCorruptError("Malformed workflow snapshot.")

    def _now_ns(self) -> int:
        now = self._clock_ns()
        if not isinstance(now, int) or now < 0:
            raise SleevePromotionReviewCorruptError("clock_ns must return a non-negative int")
        return now

    def build_review_results(self) -> tuple[SleevePromotionReviewResult, ...]:
        results = []
        for entry in getattr(self.workflow_snapshot, "sleeves", []):
            verdict, reason, next_step = self._derive_verdict(entry)
            results.append(
                SleevePromotionReviewResult(
                    sleeve_id=entry.sleeve_id,
                    verdict=verdict,
                    reason=reason,
                    next_step=next_step,
                    repeated_weak=entry.repeated_weak,
                    repeated_blocked=entry.repeated_blocked,
                    repeated_inconclusive=entry.repeated_inconclusive,
                    missing_evidence=entry.missing_evidence,
                    governance_blockers=entry.blocking_reasons,
                    last_verdict=None,
                )
            )
        return tuple(results)

    def _derive_verdict(self, entry: SleeveCandidateWorkflowEntry) -> tuple[SleevePromotionReviewVerdict, str, str]:
        # Deterministic mapping from candidate workflow entry to review verdict
        if (
            entry.candidate_status == SleevePromotionCandidateStatus.SUPPORTED
            and entry.promotion_support_status == SleevePromotionSupportStatus.SUPPORTIVE
        ):
            return (SleevePromotionReviewVerdict.REVIEW_SUPPORTED, entry.reason_summary, entry.next_step)
        if (
            entry.candidate_status == SleevePromotionCandidateStatus.BLOCKED
            or entry.promotion_support_status == SleevePromotionSupportStatus.BLOCKED
        ):
            return (SleevePromotionReviewVerdict.REJECT, entry.reason_summary, entry.next_step)
        if (
            entry.candidate_status == SleevePromotionCandidateStatus.WATCHLIST
            or entry.promotion_support_status == SleevePromotionSupportStatus.WEAK_SUPPORT
        ):
            return (SleevePromotionReviewVerdict.HOLD, entry.reason_summary, entry.next_step)
        return (SleevePromotionReviewVerdict.INCONCLUSIVE, entry.reason_summary, entry.next_step)

    def build_portfolio_summary(
        self,
        review_results: tuple[SleevePromotionReviewResult, ...],
        *,
        as_of_ns: int | None = None,
    ) -> SleevePromotionReviewPortfolioSummary:
        supported, hold, reject, inconclusive = [], [], [], []
        repeated_weak, repeated_blocked, repeated_inconclusive = [], [], []
        missing_evidence, governance_blockers = [], []
        for r in review_results:
            if r.verdict == SleevePromotionReviewVerdict.REVIEW_SUPPORTED:
                supported.append(r.sleeve_id)
            elif r.verdict == SleevePromotionReviewVerdict.HOLD:
                hold.append(r.sleeve_id)
            elif r.verdict == SleevePromotionReviewVerdict.REJECT:
                reject.append(r.sleeve_id)
            elif r.verdict == SleevePromotionReviewVerdict.INCONCLUSIVE:
                inconclusive.append(r.sleeve_id)
            if r.repeated_weak:
                repeated_weak.append(r.sleeve_id)
            if r.repeated_blocked:
                repeated_blocked.append(r.sleeve_id)
            if r.repeated_inconclusive:
                repeated_inconclusive.append(r.sleeve_id)
            _append_unique(missing_evidence, r.missing_evidence)
            _append_unique(governance_blockers, r.governance_blockers)
        operator_summary = self._build_operator_summary(
            supported,
            hold,
            reject,
            inconclusive,
            repeated_weak,
            repeated_blocked,
            repeated_inconclusive,
            missing_evidence,
            governance_blockers,
        )
        return SleevePromotionReviewPortfolioSummary(
            as_of_ns=self._now_ns() if as_of_ns is None else as_of_ns,
            review_results=review_results,
            supported=tuple(supported),
            hold=tuple(hold),
            reject=tuple(reject),
            inconclusive=tuple(inconclusive),
            repeated_weak=tuple(repeated_weak),
            repeated_blocked=tuple(repeated_blocked),
            repeated_inconclusive=tuple(repeated_inconclusive),
            missing_evidence=tuple(missing_evidence),
            governance_blockers=tuple(governance_blockers),
            operator_summary=operator_summary,
        )

    def _build_operator_summary(
        self,
        supported,
        hold,
        reject,
        inconclusive,
        repeated_weak,
        repeated_blocked,
        repeated_inconclusive,
        missing_evidence,
        governance_blockers,
    ):
        return (
            f"Supported: {supported}. Hold: {hold}. Reject: {reject}. Inconclusive: {inconclusive}. "
            f"Repeated weak: {repeated_weak}. Repeated blocked: {repeated_blocked}. Repeated inconclusive: {repeated_inconclusive}. "
            f"Missing evidence: {missing_evidence}. Governance blockers: {governance_blockers}."
        )

    def snapshot(self) -> SleevePromotionReviewSnapshot:
        now = self._now_ns()
        review_results = self.build_review_results()
        portfolio_summary = self.build_portfolio_summary(review_results, as_of_ns=now)
        return SleevePromotionReviewSnapshot(
            as_of_ns=now,
            status="active",
            review_results=review_results,
            portfolio_summary=portfolio_summary,
            history=tuple(self.history),
        )

    def finalize(self):
        # Build the new history entry
        now = self._now_ns()
        review_results = self.build_review_results()
        portfolio_summary = self.build_portfolio_summary(review_results, as_of_ns=now)
        entry = SleevePromotionReviewHistoryEntry(
            as_of_ns=now,
            summary=portfolio_summary.operator_summary,
            portfolio_summary=portfolio_summary,
        )
        self.history.append(entry)
        if len(self.history) > self.history_limit:
            self.history = self.history[-self.history_limit :]
        # Return a snapshot with the updated history
        return SleevePromotionReviewSnapshot(
            as_of_ns=entry.as_of_ns,
            status="active",
            review_results=review_results,
            portfolio_summary=portfolio_summary,
            history=tuple(self.history),
        )

    def restore(self, snapshot: SleevePromotionReviewSnapshot):
        if not isinstance(snapshot, SleevePromotionReviewSnapshot):
            raise SleevePromotionReviewCorruptError("restore snapshot must be a SleevePromotionReviewSnapshot")
        self.workflow_snapshot = self.workflow_snapshot  # No-op for now; extend as needed
        self.history = list(snapshot.history)
        if any(not isinstance(item, SleevePromotionReviewHistoryEntry) for item in self.history):
            raise SleevePromotionReviewCorruptError("restore history must contain SleevePromotionReviewHistoryEntry")
        self._validate()

    def reset(self):
        self.history = []

    def to_dict(self) -> dict:
        snap = self.snapshot()
        return {
            "as_of_ns": snap.as_of_ns,
            "status": snap.status,
            "review_results": [r.__dict__ for r in snap.review_results],
            "portfolio_summary": snap.portfolio_summary.__dict__,
            "history": [
                {
                    "as_of_ns": h.as_of_ns,
                    "summary": h.summary,
                    "portfolio_summary": h.portfolio_summary.__dict__,
                }
                for h in snap.history
            ],
        }


def _append_unique(target: list[str], values: tuple[str, ...]) -> None:
    for value in values:
        if value not in target:
            target.append(value)
