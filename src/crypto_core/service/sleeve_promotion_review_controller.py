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
        self.history_limit = max(1, history_limit)
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
        self.history = list(snapshot.history[-self.history_limit :])
        if any(not isinstance(item, SleevePromotionReviewHistoryEntry) for item in self.history):
            raise SleevePromotionReviewCorruptError("restore history must contain SleevePromotionReviewHistoryEntry")
        self._validate()

    def reset(self):
        self.history = []

    def to_dict(self) -> dict:
        return sleeve_promotion_review_snapshot_to_dict(self.snapshot())


def sleeve_promotion_review_result_to_dict(result: SleevePromotionReviewResult) -> dict:
    return {
        "sleeve_id": result.sleeve_id,
        "verdict": result.verdict.value,
        "reason": result.reason,
        "next_step": result.next_step,
        "repeated_weak": result.repeated_weak,
        "repeated_blocked": result.repeated_blocked,
        "repeated_inconclusive": result.repeated_inconclusive,
        "missing_evidence": list(result.missing_evidence),
        "governance_blockers": list(result.governance_blockers),
        "last_verdict": None if result.last_verdict is None else result.last_verdict.value,
    }


def sleeve_promotion_review_result_from_dict(data: dict) -> SleevePromotionReviewResult:
    if not isinstance(data, dict):
        raise SleevePromotionReviewCorruptError(
            f"Sleeve promotion review result must be a dict, got {type(data).__name__!r}"
        )
    return SleevePromotionReviewResult(
        sleeve_id=_require_non_empty_str(data.get("sleeve_id"), "sleeve_id"),
        verdict=_enum_value(SleevePromotionReviewVerdict, data.get("verdict"), "verdict"),
        reason="" if data.get("reason", "") is None else str(data.get("reason", "")),
        next_step="" if data.get("next_step", "") is None else str(data.get("next_step", "")),
        repeated_weak=_require_bool(data.get("repeated_weak", False), "repeated_weak"),
        repeated_blocked=_require_bool(data.get("repeated_blocked", False), "repeated_blocked"),
        repeated_inconclusive=_require_bool(data.get("repeated_inconclusive", False), "repeated_inconclusive"),
        missing_evidence=_tuple_of_strings(data.get("missing_evidence", ()), "missing_evidence"),
        governance_blockers=_tuple_of_strings(data.get("governance_blockers", ()), "governance_blockers"),
        last_verdict=_optional_enum(SleevePromotionReviewVerdict, data.get("last_verdict"), "last_verdict"),
    )


def sleeve_promotion_review_portfolio_summary_to_dict(summary: SleevePromotionReviewPortfolioSummary) -> dict:
    return {
        "as_of_ns": summary.as_of_ns,
        "review_results": [sleeve_promotion_review_result_to_dict(result) for result in summary.review_results],
        "supported": list(summary.supported),
        "hold": list(summary.hold),
        "reject": list(summary.reject),
        "inconclusive": list(summary.inconclusive),
        "repeated_weak": list(summary.repeated_weak),
        "repeated_blocked": list(summary.repeated_blocked),
        "repeated_inconclusive": list(summary.repeated_inconclusive),
        "missing_evidence": list(summary.missing_evidence),
        "governance_blockers": list(summary.governance_blockers),
        "operator_summary": summary.operator_summary,
    }


def sleeve_promotion_review_portfolio_summary_from_dict(data: dict) -> SleevePromotionReviewPortfolioSummary:
    if not isinstance(data, dict):
        raise SleevePromotionReviewCorruptError(
            f"Sleeve promotion review portfolio summary must be a dict, got {type(data).__name__!r}"
        )
    results_value = data.get("review_results", ())
    if not isinstance(results_value, (list, tuple)):
        raise SleevePromotionReviewCorruptError("Sleeve promotion review field 'review_results' must be a list/tuple")
    results = tuple(_review_result_from_value(item) for item in results_value)
    summary = SleevePromotionReviewPortfolioSummary(
        as_of_ns=_require_non_negative_int(data.get("as_of_ns"), "as_of_ns"),
        review_results=results,
        supported=_tuple_or_derive(data, "supported", results, {SleevePromotionReviewVerdict.REVIEW_SUPPORTED}),
        hold=_tuple_or_derive(data, "hold", results, {SleevePromotionReviewVerdict.HOLD}),
        reject=_tuple_or_derive(data, "reject", results, {SleevePromotionReviewVerdict.REJECT}),
        inconclusive=_tuple_or_derive(data, "inconclusive", results, {SleevePromotionReviewVerdict.INCONCLUSIVE}),
        repeated_weak=_tuple_or_repeated(data, "repeated_weak", results, "repeated_weak"),
        repeated_blocked=_tuple_or_repeated(data, "repeated_blocked", results, "repeated_blocked"),
        repeated_inconclusive=_tuple_or_repeated(data, "repeated_inconclusive", results, "repeated_inconclusive"),
        missing_evidence=_tuple_or_derive_values(data, "missing_evidence", results, "missing_evidence"),
        governance_blockers=_tuple_or_derive_values(data, "governance_blockers", results, "governance_blockers"),
        operator_summary="" if data.get("operator_summary", "") is None else str(data.get("operator_summary", "")),
    )
    _validate_portfolio_summary(summary)
    return summary


def sleeve_promotion_review_history_entry_to_dict(entry: SleevePromotionReviewHistoryEntry) -> dict:
    return {
        "as_of_ns": entry.as_of_ns,
        "summary": entry.summary,
        "portfolio_summary": sleeve_promotion_review_portfolio_summary_to_dict(entry.portfolio_summary),
    }


def sleeve_promotion_review_history_entry_from_dict(data: dict) -> SleevePromotionReviewHistoryEntry:
    if not isinstance(data, dict):
        raise SleevePromotionReviewCorruptError(
            f"Sleeve promotion review history entry must be a dict, got {type(data).__name__!r}"
        )
    summary = sleeve_promotion_review_portfolio_summary_from_dict(
        _dict_value(data.get("portfolio_summary"), "portfolio_summary")
    )
    as_of_ns = _require_non_negative_int(data.get("as_of_ns"), "as_of_ns")
    if as_of_ns != summary.as_of_ns:
        raise SleevePromotionReviewCorruptError("Sleeve promotion review history timestamp does not match summary")
    return SleevePromotionReviewHistoryEntry(
        as_of_ns=as_of_ns,
        summary="" if data.get("summary", "") is None else str(data.get("summary", "")),
        portfolio_summary=summary,
    )


def sleeve_promotion_review_snapshot_to_dict(snapshot: SleevePromotionReviewSnapshot) -> dict:
    return {
        "as_of_ns": snapshot.as_of_ns,
        "status": snapshot.status,
        "review_results": [sleeve_promotion_review_result_to_dict(result) for result in snapshot.review_results],
        "portfolio_summary": sleeve_promotion_review_portfolio_summary_to_dict(snapshot.portfolio_summary),
        "history": [sleeve_promotion_review_history_entry_to_dict(entry) for entry in snapshot.history],
    }


def sleeve_promotion_review_snapshot_from_dict(data: dict) -> SleevePromotionReviewSnapshot:
    if not isinstance(data, dict):
        raise SleevePromotionReviewCorruptError(
            f"Sleeve promotion review snapshot must be a dict, got {type(data).__name__!r}"
        )
    summary = sleeve_promotion_review_portfolio_summary_from_dict(
        _dict_value(data.get("portfolio_summary"), "portfolio_summary")
    )
    results_value = data.get("review_results")
    if results_value is None:
        results = summary.review_results
    elif isinstance(results_value, (list, tuple)):
        results = tuple(_review_result_from_value(item) for item in results_value)
    else:
        raise SleevePromotionReviewCorruptError("Sleeve promotion review field 'review_results' must be a list/tuple")
    if results != summary.review_results:
        raise SleevePromotionReviewCorruptError("Sleeve promotion review results do not match portfolio summary")
    as_of_ns = _require_non_negative_int(data.get("as_of_ns"), "as_of_ns")
    if as_of_ns != summary.as_of_ns:
        raise SleevePromotionReviewCorruptError("Sleeve promotion review timestamp does not match portfolio summary")
    history_value = data.get("history", ())
    if not isinstance(history_value, (list, tuple)):
        raise SleevePromotionReviewCorruptError("Sleeve promotion review field 'history' must be a list/tuple")
    return SleevePromotionReviewSnapshot(
        as_of_ns=as_of_ns,
        status=_require_non_empty_str(data.get("status"), "status"),
        review_results=results,
        portfolio_summary=summary,
        history=tuple(_history_entry_from_value(item) for item in history_value),
    )


def _append_unique(target: list[str], values: tuple[str, ...]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _review_result_from_value(value: object) -> SleevePromotionReviewResult:
    if isinstance(value, SleevePromotionReviewResult):
        return value
    return sleeve_promotion_review_result_from_dict(_dict_value(value, "review_results"))


def _history_entry_from_value(value: object) -> SleevePromotionReviewHistoryEntry:
    if isinstance(value, SleevePromotionReviewHistoryEntry):
        return value
    return sleeve_promotion_review_history_entry_from_dict(_dict_value(value, "history"))


def _dict_value(value: object, field_name: str) -> dict:
    if not isinstance(value, dict):
        raise SleevePromotionReviewCorruptError(f"{field_name} must be a dict")
    return dict(value)


def _tuple_or_derive(
    data: dict,
    field_name: str,
    results: tuple[SleevePromotionReviewResult, ...],
    verdicts: set[SleevePromotionReviewVerdict],
) -> tuple[str, ...]:
    if field_name in data:
        return _tuple_of_strings(data.get(field_name, ()), field_name)
    return tuple(result.sleeve_id for result in results if result.verdict in verdicts)


def _tuple_or_repeated(
    data: dict,
    field_name: str,
    results: tuple[SleevePromotionReviewResult, ...],
    attr_name: str,
) -> tuple[str, ...]:
    if field_name in data:
        return _tuple_of_strings(data.get(field_name, ()), field_name)
    return tuple(result.sleeve_id for result in results if getattr(result, attr_name))


def _tuple_or_derive_values(
    data: dict,
    field_name: str,
    results: tuple[SleevePromotionReviewResult, ...],
    attr_name: str,
) -> tuple[str, ...]:
    if field_name in data:
        return _tuple_of_strings(data.get(field_name, ()), field_name)
    ordered: list[str] = []
    for result in results:
        _append_unique(ordered, getattr(result, attr_name))
    return tuple(ordered)


def _validate_portfolio_summary(summary: SleevePromotionReviewPortfolioSummary) -> None:
    expected = {
        "supported": tuple(
            result.sleeve_id
            for result in summary.review_results
            if result.verdict == SleevePromotionReviewVerdict.REVIEW_SUPPORTED
        ),
        "hold": tuple(
            result.sleeve_id for result in summary.review_results if result.verdict == SleevePromotionReviewVerdict.HOLD
        ),
        "reject": tuple(
            result.sleeve_id
            for result in summary.review_results
            if result.verdict == SleevePromotionReviewVerdict.REJECT
        ),
        "inconclusive": tuple(
            result.sleeve_id
            for result in summary.review_results
            if result.verdict == SleevePromotionReviewVerdict.INCONCLUSIVE
        ),
    }
    for field_name, sleeve_ids in expected.items():
        if getattr(summary, field_name) != sleeve_ids:
            raise SleevePromotionReviewCorruptError(f"Sleeve promotion review {field_name} ids do not match results")


def _enum_value(enum_type, value: object, field_name: str):
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(_require_non_empty_str(value, field_name))
    except ValueError as exc:
        raise SleevePromotionReviewCorruptError(f"Invalid {field_name}: {value!r}") from exc


def _optional_enum(enum_type, value: object, field_name: str):
    if value is None:
        return None
    return _enum_value(enum_type, value, field_name)


def _tuple_of_strings(value: object, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise SleevePromotionReviewCorruptError(f"{field_name} must be a list/tuple")
    return tuple(str(item) for item in value)


def _require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SleevePromotionReviewCorruptError(f"{field_name} must be a non-empty string")
    return value


def _require_non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise SleevePromotionReviewCorruptError(f"{field_name} must be a non-negative int")
    return value


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise SleevePromotionReviewCorruptError(f"{field_name} must be a bool")
    return value
