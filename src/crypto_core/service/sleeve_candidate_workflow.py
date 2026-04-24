"""Sleeve candidate workflow controller — Phase 15C.

Deterministic workflow manager for the operator-facing sleeve candidate surface.

Design rules:
  - Reuses existing SleevePortfolioSnapshot truth only.
  - No new promotion engine or synthetic maturity state.
  - Bounded finalized history only; malformed persisted state fails closed.
  - PAPER-ONLY.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum

from crypto_core.service.evidence_store import EvidenceStore, WriteResult
from crypto_core.service.sleeve_portfolio import (
    SleeveDecisionPackStatus,
    SleevePortfolioSnapshot,
    SleevePromotionCandidateStatus,
    SleevePromotionSupportStatus,
)

_DEFAULT_HISTORY_LIMIT = 5
_WORKFLOW_SNAPSHOT_NAME = "sleeve_candidate_workflow"
_WORKFLOW_REQUIRED_FIELDS = frozenset({"workflow_id", "status", "created_at_ns", "updated_at_ns", "history"})

_CANDIDATE_RANK = {
    SleevePromotionCandidateStatus.BLOCKED: -1,
    SleevePromotionCandidateStatus.NOT_A_CANDIDATE: 0,
    SleevePromotionCandidateStatus.WATCHLIST: 1,
    SleevePromotionCandidateStatus.SUPPORTED: 2,
}

_SUPPORT_RANK = {
    SleevePromotionSupportStatus.BLOCKED: -1,
    SleevePromotionSupportStatus.INCONCLUSIVE: 0,
    SleevePromotionSupportStatus.WEAK_SUPPORT: 1,
    SleevePromotionSupportStatus.SUPPORTIVE: 2,
}

_DECISION_PACK_RANK = {
    SleeveDecisionPackStatus.BLOCKED: -1,
    SleeveDecisionPackStatus.INSUFFICIENT_EVIDENCE: 0,
    SleeveDecisionPackStatus.WATCHLIST_CANDIDATE: 1,
    SleeveDecisionPackStatus.SUPPORTED_CANDIDATE: 2,
    SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED: 3,
    SleeveDecisionPackStatus.RECOMMENDED_ACTIVE: 4,
}


class SleeveCandidateWorkflowStatus(str, Enum):
    """Deterministic sleeve candidate workflow states."""

    CREATED = "created"
    ACTIVE = "active"
    FINALIZED = "finalized"


class SleeveCandidateProgression(str, Enum):
    """Current-vs-previous candidate progression classification."""

    NOT_ASSESSED = "not_assessed"
    FIRST_INSPECTION = "first_inspection"
    NEW_CANDIDATE = "new_candidate"
    IMPROVED = "improved"
    REGRESSED = "regressed"
    REMOVED = "removed"
    UNCHANGED = "unchanged"
    MIXED = "mixed"


class SleeveCandidateWorkflowCorruptError(RuntimeError):
    """Raised when persisted sleeve candidate workflow state is malformed."""


@dataclass(frozen=True)
class SleeveCandidateWorkflowEntry:
    """Compact per-sleeve candidate workflow truth and progression."""

    sleeve_id: str
    candidate_status: SleevePromotionCandidateStatus
    promotion_support_status: SleevePromotionSupportStatus
    decision_pack_status: SleeveDecisionPackStatus
    candidate_for_future_review: bool
    strongly_supported: bool
    progression_state: SleeveCandidateProgression = SleeveCandidateProgression.NOT_ASSESSED
    previous_candidate_status: str | None = None
    previous_promotion_support_status: str | None = None
    repeated_weak: bool = False
    repeated_blocked: bool = False
    repeated_inconclusive: bool = False
    missing_evidence: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()
    reason_summary: str = ""
    next_step: str = ""


@dataclass(frozen=True)
class SleeveCandidateWorkflowHistoryEntry:
    """Bounded finalized candidate workflow history entry."""

    workflow_id: str
    as_of_ns: int
    summary: str
    candidate_sleeve_ids: tuple[str, ...] = ()
    supported_candidate_sleeve_ids: tuple[str, ...] = ()
    weak_candidate_sleeve_ids: tuple[str, ...] = ()
    blocked_candidate_sleeve_ids: tuple[str, ...] = ()
    inconclusive_candidate_sleeve_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SleeveCandidateWorkflowSnapshot:
    """Current operator-facing candidate workflow snapshot."""

    workflow_id: str
    status: str
    as_of_ns: int
    sleeves: tuple[SleeveCandidateWorkflowEntry, ...] = ()
    candidate_sleeve_ids: tuple[str, ...] = ()
    supported_candidate_sleeve_ids: tuple[str, ...] = ()
    weak_candidate_sleeve_ids: tuple[str, ...] = ()
    blocked_candidate_sleeve_ids: tuple[str, ...] = ()
    inconclusive_candidate_sleeve_ids: tuple[str, ...] = ()
    summary: str = ""
    comparison_to_previous: dict = None  # type: ignore[assignment]
    history_summary: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "comparison_to_previous",
            {} if self.comparison_to_previous is None else dict(self.comparison_to_previous),
        )
        object.__setattr__(self, "history_summary", {} if self.history_summary is None else dict(self.history_summary))


class SleeveCandidateWorkflowController:
    """First-class workflow manager for sleeve candidate inspection."""

    def __init__(
        self,
        *,
        evidence_store: EvidenceStore | None = None,
        workflow_id: str | None = None,
        created_at_ns: int | None = None,
        updated_at_ns: int | None = None,
        history_limit: int = _DEFAULT_HISTORY_LIMIT,
        history: tuple[SleeveCandidateWorkflowHistoryEntry, ...] = (),
        current_snapshot: SleeveCandidateWorkflowSnapshot | None = None,
        status: SleeveCandidateWorkflowStatus = SleeveCandidateWorkflowStatus.CREATED,
        clock_ns: Callable[[], int] | None = None,
    ) -> None:
        self._clock_ns = time.time_ns if clock_ns is None else clock_ns
        now = self._now_ns() if created_at_ns is None else created_at_ns
        self._created_at_ns = now
        self._updated_at_ns = now if updated_at_ns is None else updated_at_ns
        self._workflow_id = workflow_id or f"sleeve-candidate-{now}"
        self._status = status
        self._history_limit = max(1, history_limit)
        self._evidence_store = evidence_store
        self._history = self._bounded_history(history)
        self._current_snapshot = current_snapshot

    @property
    def workflow_id(self) -> str:
        return self._workflow_id

    @property
    def status(self) -> SleeveCandidateWorkflowStatus:
        return self._status

    @property
    def history(self) -> tuple[SleeveCandidateWorkflowHistoryEntry, ...]:
        return self._history

    @property
    def current_snapshot(self) -> SleeveCandidateWorkflowSnapshot | None:
        return self._current_snapshot

    def start(
        self,
        *,
        workflow_id: str | None = None,
        started_at_ns: int | None = None,
    ) -> str:
        """Start a new candidate workflow inspection cycle."""
        if self._status == SleeveCandidateWorkflowStatus.ACTIVE:
            raise RuntimeError(f"Cannot start sleeve candidate workflow {self._workflow_id!r}: already active")
        now = self._now_ns() if started_at_ns is None else started_at_ns
        self._workflow_id = workflow_id or f"sleeve-candidate-{now}"
        self._created_at_ns = now
        self._updated_at_ns = now
        self._status = SleeveCandidateWorkflowStatus.ACTIVE
        self._current_snapshot = None
        self._persist_workflow()
        return self._workflow_id

    def inspect(self, portfolio_snapshot: SleevePortfolioSnapshot) -> SleeveCandidateWorkflowSnapshot:
        """Inspect current sleeve candidate truth without finalizing history."""
        self._require_active("inspect")
        snapshot = self._build_snapshot(portfolio_snapshot, status=SleeveCandidateWorkflowStatus.ACTIVE)
        self._current_snapshot = snapshot
        self._updated_at_ns = snapshot.as_of_ns
        self._persist_workflow()
        return snapshot

    def finalize(self, portfolio_snapshot: SleevePortfolioSnapshot) -> SleeveCandidateWorkflowSnapshot:
        """Finalize the current inspection and append bounded history."""
        self._require_active("finalize")
        snapshot = self._build_snapshot(portfolio_snapshot, status=SleeveCandidateWorkflowStatus.FINALIZED)
        history_entry = SleeveCandidateWorkflowHistoryEntry(
            workflow_id=self._workflow_id,
            as_of_ns=snapshot.as_of_ns,
            summary=snapshot.summary,
            candidate_sleeve_ids=snapshot.candidate_sleeve_ids,
            supported_candidate_sleeve_ids=snapshot.supported_candidate_sleeve_ids,
            weak_candidate_sleeve_ids=snapshot.weak_candidate_sleeve_ids,
            blocked_candidate_sleeve_ids=snapshot.blocked_candidate_sleeve_ids,
            inconclusive_candidate_sleeve_ids=snapshot.inconclusive_candidate_sleeve_ids,
        )
        self._history = self._bounded_history(self._history + (history_entry,))
        final_snapshot = self._build_snapshot(
            portfolio_snapshot,
            status=SleeveCandidateWorkflowStatus.FINALIZED,
            previous_snapshot=self._current_snapshot,
        )
        self._current_snapshot = final_snapshot
        self._status = SleeveCandidateWorkflowStatus.FINALIZED
        self._updated_at_ns = final_snapshot.as_of_ns
        self._persist_workflow()
        return final_snapshot

    def reset(self, *, reset_at_ns: int | None = None) -> None:
        """Reset the active/finalized workflow while preserving bounded history."""
        now = self._now_ns() if reset_at_ns is None else reset_at_ns
        self._status = SleeveCandidateWorkflowStatus.CREATED
        self._current_snapshot = None
        self._updated_at_ns = now
        self._persist_workflow()

    def compare_to_previous(self, snapshot: SleeveCandidateWorkflowSnapshot) -> dict:
        """Compare current snapshot with the previous inspected workflow snapshot."""
        previous = self._current_snapshot
        if previous is None:
            overall = (
                SleeveCandidateProgression.FIRST_INSPECTION.value
                if snapshot.sleeves
                else SleeveCandidateProgression.NOT_ASSESSED.value
            )
            return {
                "available": False,
                "changed": bool(snapshot.sleeves),
                "progression_state": overall,
                "previous_as_of_ns": None,
                "current_as_of_ns": snapshot.as_of_ns,
                "changed_sleeves": [
                    {
                        "sleeve_id": item.sleeve_id,
                        "previous_candidate_status": None,
                        "current_candidate_status": item.candidate_status.value,
                        "progression_state": item.progression_state.value,
                    }
                    for item in snapshot.sleeves
                ],
            }

        previous_by_id = {item.sleeve_id: item for item in previous.sleeves}
        changed_sleeves: list[dict] = []
        for item in snapshot.sleeves:
            previous_item = previous_by_id.get(item.sleeve_id)
            if previous_item is None or _entry_signature(previous_item) != _entry_signature(item):
                changed_sleeves.append(
                    {
                        "sleeve_id": item.sleeve_id,
                        "previous_candidate_status": (
                            None if previous_item is None else previous_item.candidate_status.value
                        ),
                        "current_candidate_status": item.candidate_status.value,
                        "progression_state": item.progression_state.value,
                    }
                )
        overall = _overall_progression_state(snapshot.sleeves)
        return {
            "available": True,
            "changed": bool(changed_sleeves),
            "progression_state": overall.value,
            "previous_as_of_ns": previous.as_of_ns,
            "current_as_of_ns": snapshot.as_of_ns,
            "changed_sleeves": changed_sleeves,
        }

    def history_summary(self, snapshot: SleeveCandidateWorkflowSnapshot | None = None) -> dict:
        """Compact bounded history summary, optionally including the current snapshot."""
        latest = self._history[-1] if self._history else None
        weak_counts: dict[str, int] = {}
        blocked_counts: dict[str, int] = {}
        inconclusive_counts: dict[str, int] = {}

        for entry in self._history:
            _bump_counts(weak_counts, entry.weak_candidate_sleeve_ids)
            _bump_counts(blocked_counts, entry.blocked_candidate_sleeve_ids)
            _bump_counts(inconclusive_counts, entry.inconclusive_candidate_sleeve_ids)

        if snapshot is not None:
            _bump_counts(weak_counts, snapshot.weak_candidate_sleeve_ids)
            _bump_counts(blocked_counts, snapshot.blocked_candidate_sleeve_ids)
            _bump_counts(inconclusive_counts, snapshot.inconclusive_candidate_sleeve_ids)

        return {
            "total_finalized_workflows": len(self._history),
            "latest_finalized_as_of_ns": None if latest is None else latest.as_of_ns,
            "latest_summary": None if latest is None else latest.summary,
            "repeated_weak_sleeve_ids": sorted(key for key, count in weak_counts.items() if count >= 2),
            "repeated_blocked_sleeve_ids": sorted(key for key, count in blocked_counts.items() if count >= 2),
            "repeated_inconclusive_sleeve_ids": sorted(key for key, count in inconclusive_counts.items() if count >= 2),
        }

    def save_state(self) -> WriteResult | None:
        """Persist workflow state via EvidenceStore."""
        if self._evidence_store is None:
            return None
        return self._evidence_store.save_snapshot(_WORKFLOW_SNAPSHOT_NAME, self._workflow_state_to_dict())

    @classmethod
    def restore(
        cls,
        evidence_store: EvidenceStore,
        *,
        history_limit: int = _DEFAULT_HISTORY_LIMIT,
        clock_ns: Callable[[], int] | None = None,
    ) -> SleeveCandidateWorkflowController:
        """Restore controller state from persisted workflow snapshot."""
        envelope = evidence_store.load_snapshot(_WORKFLOW_SNAPSHOT_NAME)
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise SleeveCandidateWorkflowCorruptError(
                f"Sleeve candidate workflow 'data' must be a dict, got {type(data).__name__!r}"
            )
        missing = _WORKFLOW_REQUIRED_FIELDS - set(data)
        if missing:
            raise SleeveCandidateWorkflowCorruptError(
                f"Sleeve candidate workflow missing required fields: {sorted(missing)!r}"
            )

        try:
            status = SleeveCandidateWorkflowStatus(_require_non_empty_string(data.get("status"), "status"))
        except ValueError:
            raise SleeveCandidateWorkflowCorruptError(
                f"Invalid sleeve candidate workflow status {data.get('status')!r}"
            ) from None

        controller = cls(
            evidence_store=evidence_store,
            workflow_id=_require_non_empty_string(data.get("workflow_id"), "workflow_id"),
            created_at_ns=_require_non_negative_int(data.get("created_at_ns"), "created_at_ns"),
            updated_at_ns=_require_non_negative_int(data.get("updated_at_ns"), "updated_at_ns"),
            history_limit=history_limit,
            history=_tuple_of_history(data.get("history", ()), history_limit=history_limit),
            current_snapshot=(
                None
                if data.get("current_snapshot") is None
                else sleeve_candidate_workflow_snapshot_from_dict(dict(data.get("current_snapshot")))
            ),
            status=status,
            clock_ns=clock_ns,
        )
        return controller

    def _build_snapshot(
        self,
        portfolio_snapshot: SleevePortfolioSnapshot,
        *,
        status: SleeveCandidateWorkflowStatus,
        previous_snapshot: SleeveCandidateWorkflowSnapshot | None = None,
    ) -> SleeveCandidateWorkflowSnapshot:
        if not isinstance(portfolio_snapshot, SleevePortfolioSnapshot):
            raise TypeError("portfolio_snapshot must be a SleevePortfolioSnapshot")

        previous = self._current_snapshot if previous_snapshot is None else previous_snapshot
        previous_by_id = {} if previous is None else {item.sleeve_id: item for item in previous.sleeves}

        raw_entries: list[SleeveCandidateWorkflowEntry] = []
        for sleeve in portfolio_snapshot.sleeves:
            previous_entry = previous_by_id.get(sleeve.sleeve_id)
            raw_entries.append(
                SleeveCandidateWorkflowEntry(
                    sleeve_id=sleeve.sleeve_id,
                    candidate_status=sleeve.promotion_candidate.status,
                    promotion_support_status=sleeve.promotion_support.status,
                    decision_pack_status=sleeve.decision_pack.status,
                    candidate_for_future_review=sleeve.promotion_candidate.candidate_for_future_review,
                    strongly_supported=sleeve.promotion_candidate.strongly_supported,
                    progression_state=_progression_state(previous_entry, sleeve),
                    previous_candidate_status=(
                        None if previous_entry is None else previous_entry.candidate_status.value
                    ),
                    previous_promotion_support_status=(
                        None if previous_entry is None else previous_entry.promotion_support_status.value
                    ),
                    missing_evidence=tuple(sleeve.promotion_candidate.missing_evidence),
                    blocking_reasons=tuple(sleeve.promotion_candidate.blocking_reasons),
                    reason_summary=sleeve.promotion_candidate.reason_summary,
                    next_step=sleeve.promotion_candidate.next_step,
                )
            )

        provisional = SleeveCandidateWorkflowSnapshot(
            workflow_id=self._workflow_id,
            status=status.value,
            as_of_ns=portfolio_snapshot.as_of_ns,
            sleeves=tuple(raw_entries),
            candidate_sleeve_ids=tuple(item.sleeve_id for item in raw_entries if item.candidate_for_future_review),
            supported_candidate_sleeve_ids=tuple(
                item.sleeve_id
                for item in raw_entries
                if item.candidate_status == SleevePromotionCandidateStatus.SUPPORTED
            ),
            weak_candidate_sleeve_ids=tuple(item.sleeve_id for item in raw_entries if _is_weak(item)),
            blocked_candidate_sleeve_ids=tuple(item.sleeve_id for item in raw_entries if _is_blocked(item)),
            inconclusive_candidate_sleeve_ids=tuple(item.sleeve_id for item in raw_entries if _is_inconclusive(item)),
            summary="",
        )
        comparison = self.compare_to_previous(provisional)
        history_summary = self.history_summary(provisional)
        repeated_weak = set(history_summary["repeated_weak_sleeve_ids"])
        repeated_blocked = set(history_summary["repeated_blocked_sleeve_ids"])
        repeated_inconclusive = set(history_summary["repeated_inconclusive_sleeve_ids"])

        entries = tuple(
            replace(
                item,
                repeated_weak=item.sleeve_id in repeated_weak,
                repeated_blocked=item.sleeve_id in repeated_blocked,
                repeated_inconclusive=item.sleeve_id in repeated_inconclusive,
            )
            for item in provisional.sleeves
        )
        summary = (
            f"candidates={len(provisional.candidate_sleeve_ids)}; "
            f"supported={len(provisional.supported_candidate_sleeve_ids)}; "
            f"weak={len(provisional.weak_candidate_sleeve_ids)}; "
            f"blocked={len(provisional.blocked_candidate_sleeve_ids)}; "
            f"inconclusive={len(provisional.inconclusive_candidate_sleeve_ids)}; "
            f"progression={comparison['progression_state']}"
        )
        return SleeveCandidateWorkflowSnapshot(
            workflow_id=self._workflow_id,
            status=status.value,
            as_of_ns=portfolio_snapshot.as_of_ns,
            sleeves=entries,
            candidate_sleeve_ids=provisional.candidate_sleeve_ids,
            supported_candidate_sleeve_ids=provisional.supported_candidate_sleeve_ids,
            weak_candidate_sleeve_ids=provisional.weak_candidate_sleeve_ids,
            blocked_candidate_sleeve_ids=provisional.blocked_candidate_sleeve_ids,
            inconclusive_candidate_sleeve_ids=provisional.inconclusive_candidate_sleeve_ids,
            summary=summary,
            comparison_to_previous=comparison,
            history_summary=history_summary,
        )

    def _require_active(self, operation: str) -> None:
        if self._status != SleeveCandidateWorkflowStatus.ACTIVE:
            raise RuntimeError(
                f"Cannot {operation} sleeve candidate workflow {self._workflow_id!r}: status={self._status.value!r}"
            )

    def _now_ns(self) -> int:
        return _require_non_negative_int(self._clock_ns(), "clock_ns")

    def _persist_workflow(self) -> None:
        if self._evidence_store is not None:
            self._evidence_store.save_snapshot(_WORKFLOW_SNAPSHOT_NAME, self._workflow_state_to_dict())

    def _workflow_state_to_dict(self) -> dict:
        return {
            "workflow_id": self._workflow_id,
            "status": self._status.value,
            "created_at_ns": self._created_at_ns,
            "updated_at_ns": self._updated_at_ns,
            "history_limit": self._history_limit,
            "history": [sleeve_candidate_workflow_history_entry_to_dict(item) for item in self._history],
            "current_snapshot": (
                None
                if self._current_snapshot is None
                else sleeve_candidate_workflow_snapshot_to_dict(self._current_snapshot)
            ),
        }

    def _bounded_history(
        self,
        history: tuple[SleeveCandidateWorkflowHistoryEntry, ...],
    ) -> tuple[SleeveCandidateWorkflowHistoryEntry, ...]:
        if len(history) <= self._history_limit:
            return history
        return history[-self._history_limit :]


def sleeve_candidate_workflow_entry_to_dict(entry: SleeveCandidateWorkflowEntry) -> dict:
    return {
        "sleeve_id": entry.sleeve_id,
        "candidate_status": entry.candidate_status.value,
        "promotion_support_status": entry.promotion_support_status.value,
        "decision_pack_status": entry.decision_pack_status.value,
        "candidate_for_future_review": entry.candidate_for_future_review,
        "strongly_supported": entry.strongly_supported,
        "progression_state": entry.progression_state.value,
        "previous_candidate_status": entry.previous_candidate_status,
        "previous_promotion_support_status": entry.previous_promotion_support_status,
        "repeated_weak": entry.repeated_weak,
        "repeated_blocked": entry.repeated_blocked,
        "repeated_inconclusive": entry.repeated_inconclusive,
        "missing_evidence": list(entry.missing_evidence),
        "blocking_reasons": list(entry.blocking_reasons),
        "reason_summary": entry.reason_summary,
        "next_step": entry.next_step,
    }


def sleeve_candidate_workflow_entry_from_dict(data: dict) -> SleeveCandidateWorkflowEntry:
    if not isinstance(data, dict):
        raise SleeveCandidateWorkflowCorruptError(
            f"Sleeve candidate workflow entry must be a dict, got {type(data).__name__!r}"
        )
    return SleeveCandidateWorkflowEntry(
        sleeve_id=_require_non_empty_string(data.get("sleeve_id"), "sleeve_id"),
        candidate_status=SleevePromotionCandidateStatus(
            _require_non_empty_string(data.get("candidate_status"), "candidate_status")
        ),
        promotion_support_status=SleevePromotionSupportStatus(
            _require_non_empty_string(data.get("promotion_support_status"), "promotion_support_status")
        ),
        decision_pack_status=SleeveDecisionPackStatus(
            _require_non_empty_string(data.get("decision_pack_status"), "decision_pack_status")
        ),
        candidate_for_future_review=_require_bool(
            data.get("candidate_for_future_review", False), "candidate_for_future_review"
        ),
        strongly_supported=_require_bool(data.get("strongly_supported", False), "strongly_supported"),
        progression_state=SleeveCandidateProgression(
            _require_non_empty_string(data.get("progression_state"), "progression_state")
        ),
        previous_candidate_status=_optional_string(data.get("previous_candidate_status"), "previous_candidate_status"),
        previous_promotion_support_status=_optional_string(
            data.get("previous_promotion_support_status"), "previous_promotion_support_status"
        ),
        repeated_weak=_require_bool(data.get("repeated_weak", False), "repeated_weak"),
        repeated_blocked=_require_bool(data.get("repeated_blocked", False), "repeated_blocked"),
        repeated_inconclusive=_require_bool(data.get("repeated_inconclusive", False), "repeated_inconclusive"),
        missing_evidence=_tuple_of_strings(data.get("missing_evidence", ()), "missing_evidence"),
        blocking_reasons=_tuple_of_strings(data.get("blocking_reasons", ()), "blocking_reasons"),
        reason_summary="" if data.get("reason_summary", "") is None else str(data.get("reason_summary", "")),
        next_step=_require_non_empty_string(data.get("next_step"), "next_step"),
    )


def sleeve_candidate_workflow_history_entry_to_dict(entry: SleeveCandidateWorkflowHistoryEntry) -> dict:
    return {
        "workflow_id": entry.workflow_id,
        "as_of_ns": entry.as_of_ns,
        "summary": entry.summary,
        "candidate_sleeve_ids": list(entry.candidate_sleeve_ids),
        "supported_candidate_sleeve_ids": list(entry.supported_candidate_sleeve_ids),
        "weak_candidate_sleeve_ids": list(entry.weak_candidate_sleeve_ids),
        "blocked_candidate_sleeve_ids": list(entry.blocked_candidate_sleeve_ids),
        "inconclusive_candidate_sleeve_ids": list(entry.inconclusive_candidate_sleeve_ids),
    }


def sleeve_candidate_workflow_history_entry_from_dict(data: dict) -> SleeveCandidateWorkflowHistoryEntry:
    if not isinstance(data, dict):
        raise SleeveCandidateWorkflowCorruptError(
            f"Sleeve candidate workflow history entry must be a dict, got {type(data).__name__!r}"
        )
    return SleeveCandidateWorkflowHistoryEntry(
        workflow_id=_require_non_empty_string(data.get("workflow_id"), "workflow_id"),
        as_of_ns=_require_non_negative_int(data.get("as_of_ns"), "as_of_ns"),
        summary="" if data.get("summary", "") is None else str(data.get("summary", "")),
        candidate_sleeve_ids=_tuple_of_strings(data.get("candidate_sleeve_ids", ()), "candidate_sleeve_ids"),
        supported_candidate_sleeve_ids=_tuple_of_strings(
            data.get("supported_candidate_sleeve_ids", ()), "supported_candidate_sleeve_ids"
        ),
        weak_candidate_sleeve_ids=_tuple_of_strings(
            data.get("weak_candidate_sleeve_ids", ()), "weak_candidate_sleeve_ids"
        ),
        blocked_candidate_sleeve_ids=_tuple_of_strings(
            data.get("blocked_candidate_sleeve_ids", ()), "blocked_candidate_sleeve_ids"
        ),
        inconclusive_candidate_sleeve_ids=_tuple_of_strings(
            data.get("inconclusive_candidate_sleeve_ids", ()), "inconclusive_candidate_sleeve_ids"
        ),
    )


def sleeve_candidate_workflow_snapshot_to_dict(snapshot: SleeveCandidateWorkflowSnapshot) -> dict:
    return {
        "workflow_id": snapshot.workflow_id,
        "status": snapshot.status,
        "as_of_ns": snapshot.as_of_ns,
        "sleeves": [sleeve_candidate_workflow_entry_to_dict(item) for item in snapshot.sleeves],
        "candidate_sleeve_ids": list(snapshot.candidate_sleeve_ids),
        "supported_candidate_sleeve_ids": list(snapshot.supported_candidate_sleeve_ids),
        "weak_candidate_sleeve_ids": list(snapshot.weak_candidate_sleeve_ids),
        "blocked_candidate_sleeve_ids": list(snapshot.blocked_candidate_sleeve_ids),
        "inconclusive_candidate_sleeve_ids": list(snapshot.inconclusive_candidate_sleeve_ids),
        "summary": snapshot.summary,
        "comparison_to_previous": dict(snapshot.comparison_to_previous),
        "history_summary": dict(snapshot.history_summary),
    }


def sleeve_candidate_workflow_snapshot_from_dict(data: dict) -> SleeveCandidateWorkflowSnapshot:
    if not isinstance(data, dict):
        raise SleeveCandidateWorkflowCorruptError(
            f"Sleeve candidate workflow snapshot must be a dict, got {type(data).__name__!r}"
        )

    sleeves_value = data.get("sleeves", ())
    if not isinstance(sleeves_value, (list, tuple)):
        raise SleeveCandidateWorkflowCorruptError("Sleeve candidate workflow field 'sleeves' must be a list/tuple")

    return SleeveCandidateWorkflowSnapshot(
        workflow_id=_require_non_empty_string(data.get("workflow_id"), "workflow_id"),
        status=_require_non_empty_string(data.get("status"), "status"),
        as_of_ns=_require_non_negative_int(data.get("as_of_ns"), "as_of_ns"),
        sleeves=tuple(sleeve_candidate_workflow_entry_from_dict(dict(item)) for item in sleeves_value),
        candidate_sleeve_ids=_tuple_of_strings(data.get("candidate_sleeve_ids", ()), "candidate_sleeve_ids"),
        supported_candidate_sleeve_ids=_tuple_of_strings(
            data.get("supported_candidate_sleeve_ids", ()), "supported_candidate_sleeve_ids"
        ),
        weak_candidate_sleeve_ids=_tuple_of_strings(
            data.get("weak_candidate_sleeve_ids", ()), "weak_candidate_sleeve_ids"
        ),
        blocked_candidate_sleeve_ids=_tuple_of_strings(
            data.get("blocked_candidate_sleeve_ids", ()), "blocked_candidate_sleeve_ids"
        ),
        inconclusive_candidate_sleeve_ids=_tuple_of_strings(
            data.get("inconclusive_candidate_sleeve_ids", ()), "inconclusive_candidate_sleeve_ids"
        ),
        summary="" if data.get("summary", "") is None else str(data.get("summary", "")),
        comparison_to_previous=(
            {} if data.get("comparison_to_previous") is None else dict(data.get("comparison_to_previous"))
        ),
        history_summary={} if data.get("history_summary") is None else dict(data.get("history_summary")),
    )


def _entry_signature(entry: SleeveCandidateWorkflowEntry) -> tuple:
    return (
        entry.sleeve_id,
        entry.candidate_status.value,
        entry.promotion_support_status.value,
        entry.decision_pack_status.value,
        entry.candidate_for_future_review,
        entry.strongly_supported,
        tuple(entry.missing_evidence),
        tuple(entry.blocking_reasons),
    )


def _progression_state(
    previous: SleeveCandidateWorkflowEntry | None,
    sleeve,
) -> SleeveCandidateProgression:
    if previous is None:
        if sleeve.promotion_candidate.candidate_for_future_review:
            return SleeveCandidateProgression.NEW_CANDIDATE
        return SleeveCandidateProgression.FIRST_INSPECTION

    current_signature = (
        sleeve.promotion_candidate.status.value,
        sleeve.promotion_support.status.value,
        sleeve.decision_pack.status.value,
        sleeve.promotion_candidate.candidate_for_future_review,
        sleeve.promotion_candidate.strongly_supported,
        tuple(sleeve.promotion_candidate.missing_evidence),
        tuple(sleeve.promotion_candidate.blocking_reasons),
    )
    if _entry_signature(previous)[1:] == current_signature:
        return SleeveCandidateProgression.UNCHANGED

    if previous.candidate_for_future_review and not sleeve.promotion_candidate.candidate_for_future_review:
        return SleeveCandidateProgression.REMOVED
    if not previous.candidate_for_future_review and sleeve.promotion_candidate.candidate_for_future_review:
        return SleeveCandidateProgression.NEW_CANDIDATE

    previous_rank = (
        _CANDIDATE_RANK[previous.candidate_status],
        _SUPPORT_RANK[previous.promotion_support_status],
        _DECISION_PACK_RANK[previous.decision_pack_status],
        1 if previous.strongly_supported else 0,
    )
    current_rank = (
        _CANDIDATE_RANK[sleeve.promotion_candidate.status],
        _SUPPORT_RANK[sleeve.promotion_support.status],
        _DECISION_PACK_RANK[sleeve.decision_pack.status],
        1 if sleeve.promotion_candidate.strongly_supported else 0,
    )
    if current_rank > previous_rank:
        return SleeveCandidateProgression.IMPROVED
    if current_rank < previous_rank:
        return SleeveCandidateProgression.REGRESSED
    return SleeveCandidateProgression.UNCHANGED


def _overall_progression_state(
    entries: tuple[SleeveCandidateWorkflowEntry, ...],
) -> SleeveCandidateProgression:
    states = {item.progression_state for item in entries}
    states.discard(SleeveCandidateProgression.UNCHANGED)
    states.discard(SleeveCandidateProgression.NOT_ASSESSED)
    if not states:
        return SleeveCandidateProgression.UNCHANGED if entries else SleeveCandidateProgression.NOT_ASSESSED
    if len(states) == 1:
        return next(iter(states))
    return SleeveCandidateProgression.MIXED


def _is_weak(entry: SleeveCandidateWorkflowEntry) -> bool:
    return (
        entry.candidate_status == SleevePromotionCandidateStatus.WATCHLIST
        or entry.promotion_support_status == SleevePromotionSupportStatus.WEAK_SUPPORT
    )


def _is_blocked(entry: SleeveCandidateWorkflowEntry) -> bool:
    return (
        entry.candidate_status == SleevePromotionCandidateStatus.BLOCKED
        or entry.promotion_support_status == SleevePromotionSupportStatus.BLOCKED
        or entry.decision_pack_status == SleeveDecisionPackStatus.BLOCKED
    )


def _is_inconclusive(entry: SleeveCandidateWorkflowEntry) -> bool:
    return (
        not entry.candidate_for_future_review
        and not _is_blocked(entry)
        and entry.promotion_support_status == SleevePromotionSupportStatus.INCONCLUSIVE
    )


def _bump_counts(target: dict[str, int], sleeve_ids: tuple[str, ...]) -> None:
    for sleeve_id in sleeve_ids:
        target[sleeve_id] = target.get(sleeve_id, 0) + 1


def _tuple_of_history(
    value: object,
    *,
    history_limit: int,
) -> tuple[SleeveCandidateWorkflowHistoryEntry, ...]:
    if not isinstance(value, (list, tuple)):
        raise SleeveCandidateWorkflowCorruptError("history must be a list/tuple")
    history = tuple(
        item
        if isinstance(item, SleeveCandidateWorkflowHistoryEntry)
        else sleeve_candidate_workflow_history_entry_from_dict(dict(item))
        for item in value
    )
    if len(history) <= history_limit:
        return history
    return history[-history_limit:]


def _tuple_of_strings(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise SleeveCandidateWorkflowCorruptError(f"{field_name} must be a list/tuple")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise SleeveCandidateWorkflowCorruptError(f"{field_name} entries must be str")
        result.append(item)
    return tuple(result)


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SleeveCandidateWorkflowCorruptError(f"{field_name} must be a non-empty str")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SleeveCandidateWorkflowCorruptError(f"{field_name} must be a str or None")
    return value


def _require_non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise SleeveCandidateWorkflowCorruptError(f"{field_name} must be a non-negative int")
    return value


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise SleeveCandidateWorkflowCorruptError(f"{field_name} must be a bool")
    return value
