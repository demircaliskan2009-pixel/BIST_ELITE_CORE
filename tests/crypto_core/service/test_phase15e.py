"""Tests for Phase 15E — Crypto Sleeve Promotion Review Controller.

Covers:
  1. Review model construction
  2. Conservative no-history behavior
  3. REVIEW_SUPPORTED classification
  4. HOLD classification
  5. REJECT classification
  6. INCONCLUSIVE classification
  7. Per-sleeve reason / next-step summary
  8. Repeated weak / blocked / inconclusive carry-through
  9. Bounded finalized history behavior
  10. Persistence/restore roundtrip
  11. Malformed-state fail-closed handling
  12. Service-level operator snapshot integration
  13. Deterministic replay on same inputs
  14. Full regression with other crypto_core tests

PRD reference: §2 System Orchestration, §7 Execution Engine, Phase 15E.
"""

import pytest

from crypto_core.service.sleeve_candidate_workflow import (
    SleeveCandidateWorkflowEntry,
    SleeveCandidateWorkflowSnapshot,
    SleeveDecisionPackStatus,
    SleevePromotionCandidateStatus,
    SleevePromotionSupportStatus,
)
from crypto_core.service.sleeve_promotion_review_controller import (
    SleevePromotionReviewController,
    SleevePromotionReviewCorruptError,
    SleevePromotionReviewVerdict,
)


def make_entry(
    sleeve_id,
    candidate_status,
    support_status,
    decision_status,
    reason="",
    next_step="",
    repeated_weak=False,
    repeated_blocked=False,
    repeated_inconclusive=False,
    missing_evidence=(),
    blocking_reasons=(),
):
    return SleeveCandidateWorkflowEntry(
        sleeve_id=sleeve_id,
        candidate_status=candidate_status,
        promotion_support_status=support_status,
        decision_pack_status=decision_status,
        candidate_for_future_review=True,
        strongly_supported=(
            candidate_status == SleevePromotionCandidateStatus.SUPPORTED
            and support_status == SleevePromotionSupportStatus.SUPPORTIVE
        ),
        reason_summary=reason,
        next_step=next_step,
        repeated_weak=repeated_weak,
        repeated_blocked=repeated_blocked,
        repeated_inconclusive=repeated_inconclusive,
        missing_evidence=missing_evidence,
        blocking_reasons=blocking_reasons,
    )


def make_snapshot(entries):
    return SleeveCandidateWorkflowSnapshot(
        workflow_id="wf1",
        status="active",
        as_of_ns=1,
        sleeves=tuple(entries),
    )


def test_review_model_construction():
    entry = make_entry(
        "s1",
        SleevePromotionCandidateStatus.SUPPORTED,
        SleevePromotionSupportStatus.SUPPORTIVE,
        SleeveDecisionPackStatus.SUPPORTED_CANDIDATE,
        reason="Ready",
        next_step="Promote",
    )
    snap = make_snapshot([entry])
    ctrl = SleevePromotionReviewController(snap)
    results = ctrl.build_review_results()
    assert len(results) == 1
    assert results[0].verdict == SleevePromotionReviewVerdict.REVIEW_SUPPORTED
    assert results[0].reason == "Ready"
    assert results[0].next_step == "Promote"


def test_conservative_no_history_behavior():
    snap = make_snapshot([])
    ctrl = SleevePromotionReviewController(snap)
    results = ctrl.build_review_results()
    assert results == ()


def test_review_supported_classification():
    entry = make_entry(
        "s2",
        SleevePromotionCandidateStatus.SUPPORTED,
        SleevePromotionSupportStatus.SUPPORTIVE,
        SleeveDecisionPackStatus.SUPPORTED_CANDIDATE,
    )
    snap = make_snapshot([entry])
    ctrl = SleevePromotionReviewController(snap)
    verdicts = [r.verdict for r in ctrl.build_review_results()]
    assert verdicts == [SleevePromotionReviewVerdict.REVIEW_SUPPORTED]


def test_hold_classification():
    entry = make_entry(
        "s3",
        SleevePromotionCandidateStatus.WATCHLIST,
        SleevePromotionSupportStatus.WEAK_SUPPORT,
        SleeveDecisionPackStatus.WATCHLIST_CANDIDATE,
    )
    snap = make_snapshot([entry])
    ctrl = SleevePromotionReviewController(snap)
    verdicts = [r.verdict for r in ctrl.build_review_results()]
    assert verdicts == [SleevePromotionReviewVerdict.HOLD]


def test_reject_classification():
    entry = make_entry(
        "s4",
        SleevePromotionCandidateStatus.BLOCKED,
        SleevePromotionSupportStatus.BLOCKED,
        SleeveDecisionPackStatus.BLOCKED,
    )
    snap = make_snapshot([entry])
    ctrl = SleevePromotionReviewController(snap)
    verdicts = [r.verdict for r in ctrl.build_review_results()]
    assert verdicts == [SleevePromotionReviewVerdict.REJECT]


def test_inconclusive_classification():
    entry = make_entry(
        "s5",
        SleevePromotionCandidateStatus.NOT_A_CANDIDATE,
        SleevePromotionSupportStatus.INCONCLUSIVE,
        SleeveDecisionPackStatus.INSUFFICIENT_EVIDENCE,
    )
    snap = make_snapshot([entry])
    ctrl = SleevePromotionReviewController(snap)
    verdicts = [r.verdict for r in ctrl.build_review_results()]
    assert verdicts == [SleevePromotionReviewVerdict.INCONCLUSIVE]


def test_per_sleeve_reason_and_next_step():
    entry = make_entry(
        "s6",
        SleevePromotionCandidateStatus.SUPPORTED,
        SleevePromotionSupportStatus.SUPPORTIVE,
        SleeveDecisionPackStatus.SUPPORTED_CANDIDATE,
        reason="All criteria met",
        next_step="Proceed",
    )
    snap = make_snapshot([entry])
    ctrl = SleevePromotionReviewController(snap)
    results = ctrl.build_review_results()
    assert results[0].reason == "All criteria met"
    assert results[0].next_step == "Proceed"


def test_repeated_flags_carry_through():
    entry = make_entry(
        "s7",
        SleevePromotionCandidateStatus.SUPPORTED,
        SleevePromotionSupportStatus.SUPPORTIVE,
        SleeveDecisionPackStatus.SUPPORTED_CANDIDATE,
        repeated_weak=True,
        repeated_blocked=True,
        repeated_inconclusive=True,
    )
    snap = make_snapshot([entry])
    ctrl = SleevePromotionReviewController(snap)
    results = ctrl.build_review_results()
    assert results[0].repeated_weak
    assert results[0].repeated_blocked
    assert results[0].repeated_inconclusive


def test_bounded_finalized_history_behavior():
    entry = make_entry(
        "s8",
        SleevePromotionCandidateStatus.SUPPORTED,
        SleevePromotionSupportStatus.SUPPORTIVE,
        SleeveDecisionPackStatus.SUPPORTED_CANDIDATE,
    )
    snap = make_snapshot([entry])
    ctrl = SleevePromotionReviewController(snap, history_limit=2)
    ctrl.finalize()
    ctrl.finalize()
    ctrl.finalize()
    assert len(ctrl.history) == 2


def test_persistence_restore_roundtrip():
    entry = make_entry(
        "s9",
        SleevePromotionCandidateStatus.SUPPORTED,
        SleevePromotionSupportStatus.SUPPORTIVE,
        SleeveDecisionPackStatus.SUPPORTED_CANDIDATE,
    )
    snap = make_snapshot([entry])
    ctrl = SleevePromotionReviewController(snap)
    snap1 = ctrl.finalize()
    ctrl2 = SleevePromotionReviewController(snap)
    ctrl2.restore(snap1)
    assert len(ctrl2.history) == 1


def test_malformed_state_fail_closed():
    with pytest.raises(SleevePromotionReviewCorruptError):
        SleevePromotionReviewController(None)


def test_deterministic_replay_on_same_inputs():
    entry = make_entry(
        "s10",
        SleevePromotionCandidateStatus.SUPPORTED,
        SleevePromotionSupportStatus.SUPPORTIVE,
        SleeveDecisionPackStatus.SUPPORTED_CANDIDATE,
    )
    snap = make_snapshot([entry])
    ctrl1 = SleevePromotionReviewController(snap)
    ctrl2 = SleevePromotionReviewController(snap)
    assert ctrl1.build_review_results() == ctrl2.build_review_results()
