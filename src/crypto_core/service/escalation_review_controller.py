"""Escalation review controller — Phase 13B.

Operational lifecycle controller for crypto paper-live escalation reviews.

Provides:
  1. EscalationReviewStatus — deterministic escalation workflow states.
  2. EscalationAttemptSummary — bounded compact finalized history entry.
  3. CurrentEscalationReviewSnapshot — point-in-time escalation workflow view.
  4. FinalEscalationReviewReport — finalized escalation review artifact.
  5. EscalationWorkflowCorruptError — fail-closed persistence error.
  6. EscalationReviewController — first-class workflow manager.

Design rules:
  - Reuses the existing EscalationDecision builder as source of truth.
  - Fail-closed: malformed state raises, never silently upgrades progression.
  - Deterministic: same evaluator input produces same workflow artifacts.
  - Bounded history only — no generic timeline engine.
  - PAPER-ONLY.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from crypto_core.service.artifact_export import (
    EscalationDecision,
    EscalationStage,
    escalation_decision_from_dict,
    escalation_decision_to_dict,
)
from crypto_core.service.evidence_store import EvidenceStore, WriteResult


class EscalationReviewStatus(str, Enum):
    """Deterministic escalation review lifecycle states."""

    CREATED = "created"
    EVALUATING = "evaluating"
    FINALIZED = "finalized"
    FAILED = "failed"
    REJECTED = "rejected"


_TERMINAL_ESCALATION_REVIEW_STATUSES = frozenset(
    {
        EscalationReviewStatus.FINALIZED,
        EscalationReviewStatus.FAILED,
        EscalationReviewStatus.REJECTED,
    }
)
_WORKFLOW_SNAPSHOT_NAME = "escalation_review_workflow"
_WORKFLOW_REQUIRED_FIELDS = frozenset({"review_id", "status", "created_at_ns", "updated_at_ns"})
_DEFAULT_HISTORY_LIMIT = 5
_STUCK_STAGES = frozenset({EscalationStage.HOLD, EscalationStage.INCONCLUSIVE, EscalationStage.REJECT})
_STAGE_RANK = {
    EscalationStage.REJECT: 0,
    EscalationStage.INCONCLUSIVE: 1,
    EscalationStage.HOLD: 2,
    EscalationStage.PAPER_ONLY: 3,
    EscalationStage.CALIBRATED_PAPER: 4,
    EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE: 5,
    EscalationStage.TINY_CAP_LIVE_REVIEW_ELIGIBLE: 6,
}


class EscalationWorkflowCorruptError(RuntimeError):
    """Raised when persisted escalation workflow state is malformed."""


@dataclass(frozen=True)
class EscalationAttemptSummary:
    """Compact bounded history entry for one finalized escalation review."""

    review_id: str
    finalized_at_ns: int
    allowed_next_step: str
    promotion_verdict: str
    operator_disposition: str
    progression_state: str
    previous_allowed_next_step: str | None = None
    changed: bool = False
    blocking_reason_count: int = 0
    missing_evidence_count: int = 0


@dataclass(frozen=True)
class CurrentEscalationReviewSnapshot:
    """Point-in-time escalation review state for operators."""

    review_id: str
    status: str
    created_at_ns: int
    updated_at_ns: int
    latest_decision: EscalationDecision | None
    comparison_to_previous: dict
    progression_state: str
    history_summary: dict
    recent_history: tuple[EscalationAttemptSummary, ...] = field(default_factory=tuple)
    is_ready_to_finalize: bool = False


@dataclass(frozen=True)
class FinalEscalationReviewReport:
    """Finalized escalation workflow artifact."""

    review_id: str
    finalized_at_ns: int
    status: str
    decision: EscalationDecision
    comparison_to_previous: dict
    progression_state: str
    history_summary: dict
    recent_history: tuple[EscalationAttemptSummary, ...] = field(default_factory=tuple)


class EscalationReviewController:
    """First-class crypto paper-live escalation workflow manager."""

    def __init__(
        self,
        *,
        decision_builder: Callable[[], EscalationDecision],
        review_id: str | None = None,
        evidence_store: EvidenceStore | None = None,
        created_at_ns: int | None = None,
        history_limit: int = _DEFAULT_HISTORY_LIMIT,
        history: tuple[EscalationAttemptSummary, ...] = (),
    ) -> None:
        self._decision_builder = decision_builder
        self._review_id = review_id or f"escalation-{uuid.uuid4().hex[:12]}"
        now = created_at_ns if created_at_ns is not None else time.time_ns()
        self._created_at_ns = now
        self._updated_at_ns = now
        self._status = EscalationReviewStatus.CREATED
        self._current_decision: EscalationDecision | None = None
        self._final_report: FinalEscalationReviewReport | None = None
        self._history_limit = max(1, history_limit)
        self._history = self._bounded_history(history)
        self._evidence_store = evidence_store

    @property
    def review_id(self) -> str:
        return self._review_id

    @property
    def status(self) -> EscalationReviewStatus:
        return self._status

    @property
    def is_finalized(self) -> bool:
        return self._status in _TERMINAL_ESCALATION_REVIEW_STATUSES

    @property
    def final_report(self) -> FinalEscalationReviewReport | None:
        return self._final_report

    @property
    def history(self) -> tuple[EscalationAttemptSummary, ...]:
        return self._history

    def evaluate_current(self, *, evaluated_at_ns: int | None = None) -> EscalationDecision:
        """Evaluate current escalation state using the configured source of truth."""
        if self._status == EscalationReviewStatus.FAILED:
            raise RuntimeError("Cannot evaluate a FAILED escalation review")
        if self._final_report is not None and self._status in _TERMINAL_ESCALATION_REVIEW_STATUSES:
            return self._final_report.decision

        decision = self._decision_builder()
        ts = evaluated_at_ns if evaluated_at_ns is not None else decision.review_timestamp_ns
        self._current_decision = decision
        self._status = EscalationReviewStatus.EVALUATING
        self._updated_at_ns = ts
        self._persist_workflow()
        return decision

    def current_snapshot(self) -> CurrentEscalationReviewSnapshot:
        """Read-only operator view of the current escalation workflow."""
        decision = self._final_report.decision if self._final_report is not None else self._current_decision
        comparison = self.compare_to_previous(decision)
        progression_state = self.progression_state(decision)
        return CurrentEscalationReviewSnapshot(
            review_id=self._review_id,
            status=self._status.value,
            created_at_ns=self._created_at_ns,
            updated_at_ns=self._updated_at_ns,
            latest_decision=decision,
            comparison_to_previous=comparison,
            progression_state=progression_state,
            history_summary=self.history_summary(decision),
            recent_history=self._history,
            is_ready_to_finalize=decision is not None,
        )

    def finalize_review(self, *, finalized_at_ns: int | None = None) -> FinalEscalationReviewReport:
        """Finalize the current escalation review and append bounded history."""
        if self._final_report is not None and self._status in _TERMINAL_ESCALATION_REVIEW_STATUSES:
            return self._final_report
        if self._status == EscalationReviewStatus.FAILED:
            raise RuntimeError("Cannot finalize a FAILED escalation review")

        decision = self._current_decision or self.evaluate_current()
        ts = finalized_at_ns if finalized_at_ns is not None else decision.review_timestamp_ns
        comparison = self.compare_to_previous(decision)
        progression_state = self.progression_state(decision)
        history_before_append = self._history
        attempt = EscalationAttemptSummary(
            review_id=self._review_id,
            finalized_at_ns=ts,
            allowed_next_step=decision.escalation_stage.value,
            promotion_verdict=decision.promotion_verdict,
            operator_disposition=decision.operator_disposition,
            progression_state=progression_state,
            previous_allowed_next_step=comparison.get("previous_allowed_next_step"),
            changed=bool(comparison.get("changed", False)),
            blocking_reason_count=len(decision.blocking_reasons),
            missing_evidence_count=len(decision.missing_evidence),
        )
        self._history = self._bounded_history(history_before_append + (attempt,))

        self._final_report = FinalEscalationReviewReport(
            review_id=self._review_id,
            finalized_at_ns=ts,
            status=(
                EscalationReviewStatus.REJECTED.value
                if decision.escalation_stage == EscalationStage.REJECT
                else EscalationReviewStatus.FINALIZED.value
            ),
            decision=decision,
            comparison_to_previous=comparison,
            progression_state=progression_state,
            history_summary=self.history_summary(decision, history_override=self._history),
            recent_history=self._history,
        )
        self._status = (
            EscalationReviewStatus.REJECTED
            if decision.escalation_stage == EscalationStage.REJECT
            else EscalationReviewStatus.FINALIZED
        )
        self._updated_at_ns = ts
        self._persist_workflow()
        return self._final_report

    def reset(self) -> None:
        """Clear current review state while preserving bounded finalized history."""
        if self._status == EscalationReviewStatus.FAILED:
            raise RuntimeError("Cannot reset a FAILED escalation review")
        self._current_decision = None
        self._final_report = None
        self._status = EscalationReviewStatus.CREATED
        self._updated_at_ns = time.time_ns()
        self._persist_workflow()

    def latest_decision(self) -> EscalationDecision | None:
        """Latest available escalation decision, finalized or provisional."""
        if self._final_report is not None:
            return self._final_report.decision
        return self._current_decision

    def compare_to_previous(self, decision: EscalationDecision | None = None) -> dict:
        """Compare a current or finalized decision with the previous finalized attempt."""
        decision = decision or self.latest_decision()
        previous = self._history[-1] if self._history else None
        if previous is not None and previous.review_id == self._review_id:
            previous = self._history[-2] if len(self._history) >= 2 else None
        if decision is None:
            return {
                "available": False,
                "direction": "not_assessed",
                "changed": False,
                "previous_review_id": previous.review_id if previous is not None else None,
                "previous_allowed_next_step": previous.allowed_next_step if previous is not None else None,
                "current_allowed_next_step": None,
            }
        if previous is None:
            return {
                "available": False,
                "direction": "first_attempt",
                "changed": False,
                "previous_review_id": None,
                "previous_allowed_next_step": None,
                "current_allowed_next_step": decision.escalation_stage.value,
            }

        current_stage = decision.escalation_stage
        previous_stage = EscalationStage(previous.allowed_next_step)
        current_rank = _STAGE_RANK[current_stage]
        previous_rank = _STAGE_RANK[previous_stage]
        direction = "unchanged"
        if current_rank > previous_rank:
            direction = "progressed"
        elif current_rank < previous_rank:
            direction = "regressed"
        elif current_stage in _STUCK_STAGES:
            direction = "stalled"

        return {
            "available": True,
            "direction": direction,
            "changed": current_stage.value != previous.allowed_next_step,
            "previous_review_id": previous.review_id,
            "previous_allowed_next_step": previous.allowed_next_step,
            "current_allowed_next_step": current_stage.value,
        }

    def progression_state(self, decision: EscalationDecision | None = None) -> str:
        """Single-field operator summary of progression vs the previous attempt."""
        return str(self.compare_to_previous(decision).get("direction", "not_assessed"))

    def history_summary(
        self,
        decision: EscalationDecision | None = None,
        *,
        history_override: tuple[EscalationAttemptSummary, ...] | None = None,
    ) -> dict:
        """Compact operator-facing bounded history summary."""
        history = history_override if history_override is not None else self._history
        latest = history[-1] if history else None
        stuck_count = 0
        for attempt in reversed(history):
            if attempt.allowed_next_step not in {stage.value for stage in _STUCK_STAGES}:
                break
            stuck_count += 1
        return {
            "total_finalized_reviews": len(history),
            "latest_review_id": latest.review_id if latest is not None else None,
            "latest_allowed_next_step": latest.allowed_next_step if latest is not None else None,
            "current_allowed_next_step": None if decision is None else decision.escalation_stage.value,
            "repeated_stuck_count": stuck_count,
            "repeatedly_stuck": stuck_count >= 2,
        }

    def save_state(self) -> WriteResult | None:
        """Persist escalation workflow state via EvidenceStore."""
        if self._evidence_store is None:
            return None
        return self._evidence_store.save_snapshot(_WORKFLOW_SNAPSHOT_NAME, self._workflow_state_to_dict())

    @classmethod
    def restore(
        cls,
        evidence_store: EvidenceStore,
        *,
        decision_builder: Callable[[], EscalationDecision],
        history_limit: int = _DEFAULT_HISTORY_LIMIT,
    ) -> EscalationReviewController:
        """Restore controller state from persisted workflow snapshot."""
        envelope = evidence_store.load_snapshot(_WORKFLOW_SNAPSHOT_NAME)
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise EscalationWorkflowCorruptError(
                f"Escalation workflow 'data' must be a dict, got {type(data).__name__!r}"
            )
        missing = _WORKFLOW_REQUIRED_FIELDS - set(data)
        if missing:
            raise EscalationWorkflowCorruptError(f"Escalation workflow missing required fields: {sorted(missing)!r}")

        review_id = data["review_id"]
        status_str = data["status"]
        created_at_ns = data["created_at_ns"]
        updated_at_ns = data["updated_at_ns"]
        try:
            status = EscalationReviewStatus(status_str)
        except ValueError:
            raise EscalationWorkflowCorruptError(f"Invalid escalation review status {status_str!r}") from None

        controller = cls(
            decision_builder=decision_builder,
            review_id=review_id,
            evidence_store=evidence_store,
            created_at_ns=created_at_ns,
            history_limit=history_limit,
        )
        controller._status = status
        controller._updated_at_ns = updated_at_ns
        controller._history = _tuple_of_attempt_summaries(
            data.get("history", ()), history_limit=controller._history_limit
        )

        current_decision_payload = data.get("current_decision")
        if current_decision_payload is not None:
            if not isinstance(current_decision_payload, dict):
                raise EscalationWorkflowCorruptError("Escalation workflow field 'current_decision' must be a dict")
            controller._current_decision = escalation_decision_from_dict(current_decision_payload)

        final_report_payload = data.get("final_report")
        if final_report_payload is not None:
            if not isinstance(final_report_payload, dict):
                raise EscalationWorkflowCorruptError("Escalation workflow field 'final_report' must be a dict")
            controller._final_report = final_escalation_review_report_from_dict(final_report_payload)

        if controller._final_report is None and status in _TERMINAL_ESCALATION_REVIEW_STATUSES:
            raise EscalationWorkflowCorruptError("Terminal escalation workflow state requires a final_report")

        return controller

    def _persist_workflow(self) -> None:
        if self._evidence_store is not None:
            self._evidence_store.save_snapshot(_WORKFLOW_SNAPSHOT_NAME, self._workflow_state_to_dict())

    def _workflow_state_to_dict(self) -> dict:
        return {
            "review_id": self._review_id,
            "status": self._status.value,
            "created_at_ns": self._created_at_ns,
            "updated_at_ns": self._updated_at_ns,
            "current_decision": (
                None if self._current_decision is None else escalation_decision_to_dict(self._current_decision)
            ),
            "final_report": (
                None if self._final_report is None else final_escalation_review_report_to_dict(self._final_report)
            ),
            "history": [escalation_attempt_summary_to_dict(item) for item in self._history],
            "history_limit": self._history_limit,
        }

    def _bounded_history(
        self,
        history: tuple[EscalationAttemptSummary, ...],
    ) -> tuple[EscalationAttemptSummary, ...]:
        if len(history) <= self._history_limit:
            return history
        return history[-self._history_limit :]


def escalation_attempt_summary_to_dict(summary: EscalationAttemptSummary) -> dict:
    return {
        "review_id": summary.review_id,
        "finalized_at_ns": summary.finalized_at_ns,
        "allowed_next_step": summary.allowed_next_step,
        "promotion_verdict": summary.promotion_verdict,
        "operator_disposition": summary.operator_disposition,
        "progression_state": summary.progression_state,
        "previous_allowed_next_step": summary.previous_allowed_next_step,
        "changed": summary.changed,
        "blocking_reason_count": summary.blocking_reason_count,
        "missing_evidence_count": summary.missing_evidence_count,
    }


def escalation_attempt_summary_from_dict(d: dict) -> EscalationAttemptSummary:
    if not isinstance(d, dict):
        raise EscalationWorkflowCorruptError(f"Escalation attempt summary must be a dict, got {type(d).__name__!r}")
    try:
        return EscalationAttemptSummary(
            review_id=str(d["review_id"]),
            finalized_at_ns=int(d["finalized_at_ns"]),
            allowed_next_step=str(d["allowed_next_step"]),
            promotion_verdict=str(d["promotion_verdict"]),
            operator_disposition=str(d["operator_disposition"]),
            progression_state=str(d["progression_state"]),
            previous_allowed_next_step=(
                None if d.get("previous_allowed_next_step") is None else str(d.get("previous_allowed_next_step"))
            ),
            changed=bool(d.get("changed", False)),
            blocking_reason_count=int(d.get("blocking_reason_count", 0)),
            missing_evidence_count=int(d.get("missing_evidence_count", 0)),
        )
    except KeyError as exc:
        raise EscalationWorkflowCorruptError(
            f"Escalation attempt summary missing required field {exc.args[0]!r}"
        ) from None
    except (TypeError, ValueError) as exc:
        raise EscalationWorkflowCorruptError(f"Invalid escalation attempt summary payload: {exc}") from None


def current_escalation_review_snapshot_to_dict(snapshot: CurrentEscalationReviewSnapshot) -> dict:
    return {
        "review_id": snapshot.review_id,
        "status": snapshot.status,
        "created_at_ns": snapshot.created_at_ns,
        "updated_at_ns": snapshot.updated_at_ns,
        "latest_decision": (
            None if snapshot.latest_decision is None else escalation_decision_to_dict(snapshot.latest_decision)
        ),
        "comparison_to_previous": snapshot.comparison_to_previous,
        "progression_state": snapshot.progression_state,
        "history_summary": snapshot.history_summary,
        "recent_history": [escalation_attempt_summary_to_dict(item) for item in snapshot.recent_history],
        "is_ready_to_finalize": snapshot.is_ready_to_finalize,
    }


def final_escalation_review_report_to_dict(report: FinalEscalationReviewReport) -> dict:
    return {
        "review_id": report.review_id,
        "finalized_at_ns": report.finalized_at_ns,
        "status": report.status,
        "decision": escalation_decision_to_dict(report.decision),
        "comparison_to_previous": report.comparison_to_previous,
        "progression_state": report.progression_state,
        "history_summary": report.history_summary,
        "recent_history": [escalation_attempt_summary_to_dict(item) for item in report.recent_history],
    }


def final_escalation_review_report_from_dict(d: dict) -> FinalEscalationReviewReport:
    if not isinstance(d, dict):
        raise EscalationWorkflowCorruptError(f"Final escalation review report must be a dict, got {type(d).__name__!r}")
    try:
        return FinalEscalationReviewReport(
            review_id=str(d["review_id"]),
            finalized_at_ns=int(d["finalized_at_ns"]),
            status=str(d["status"]),
            decision=escalation_decision_from_dict(d["decision"]),
            comparison_to_previous=dict(d.get("comparison_to_previous", {})),
            progression_state=str(d.get("progression_state", "not_assessed")),
            history_summary=dict(d.get("history_summary", {})),
            recent_history=_tuple_of_attempt_summaries(d.get("recent_history", ())),
        )
    except KeyError as exc:
        raise EscalationWorkflowCorruptError(
            f"Final escalation report missing required field {exc.args[0]!r}"
        ) from None
    except (TypeError, ValueError) as exc:
        raise EscalationWorkflowCorruptError(f"Invalid final escalation report payload: {exc}") from None


def _tuple_of_attempt_summaries(
    payload: object,
    *,
    history_limit: int = _DEFAULT_HISTORY_LIMIT,
) -> tuple[EscalationAttemptSummary, ...]:
    if not isinstance(payload, (list, tuple)):
        raise EscalationWorkflowCorruptError("Escalation workflow field 'history' must be a list/tuple")
    items = tuple(escalation_attempt_summary_from_dict(item) for item in payload)
    if len(items) <= history_limit:
        return items
    return items[-history_limit:]
