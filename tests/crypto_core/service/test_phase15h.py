"""Tests for Phase 15H — evidence→paper-shadow-session bridge.

Covers ``prepare_paper_shadow_session_from_evidence``, which carries the PR #217 evidence/digest
gate into the PaperShadow session lifecycle. A session may reach READY only through the evidence-
gated activation plan; every fail-closed case keeps it BLOCKED and unstartable:
  1. Missing evidence store → BLOCKED session, never READY
  2. Accepted evidence for a different summary (digest mismatch) → BLOCKED
  3. Rejected/stale currentness (snapshot but no canonical record) → BLOCKED
  4. No admitted active sleeve → BLOCKED
  5. Summary governance blocker propagates to the session → BLOCKED
  6. All gates pass → READY session that can start()
  7. BLOCKED session cannot start() (lifecycle fail-closed end to end)
  8. Deterministic session/plan identifiers and blocker ordering
  9. Malformed summary propagates SleeveAdmissionCorruptError

PRD reference: §2 System Orchestration, §7 Execution Engine, Phase 15H.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from crypto_core.service.evidence_store import EvidenceStore, EvidenceStoreConfig
from crypto_core.service.paper_shadow_session_controller import (
    PaperShadowSessionController,
    PaperShadowSessionCorruptError,
    PaperShadowSessionStatus,
    prepare_paper_shadow_session_from_evidence,
)
from crypto_core.service.sleeve_admission_controller import (
    SleeveAdmissionController,
    SleeveAdmissionCorruptError,
    SleeveAdmissionStore,
    sleeve_admission_digest,
    sleeve_admission_outcome_to_dict,
)
from crypto_core.service.sleeve_promotion_review_controller import (
    SleevePromotionReviewPortfolioSummary,
    SleevePromotionReviewResult,
    SleevePromotionReviewVerdict,
)


def _review_result(sleeve_id, verdict, *, missing_evidence=(), governance_blockers=()):
    return SleevePromotionReviewResult(
        sleeve_id=sleeve_id,
        verdict=verdict,
        reason="",
        next_step="",
        repeated_weak=False,
        repeated_blocked=False,
        repeated_inconclusive=False,
        missing_evidence=missing_evidence,
        governance_blockers=governance_blockers,
        last_verdict=None,
    )


def _review_summary(results):
    return SleevePromotionReviewPortfolioSummary(
        as_of_ns=123,
        review_results=tuple(results),
        supported=tuple(r.sleeve_id for r in results if r.verdict == SleevePromotionReviewVerdict.REVIEW_SUPPORTED),
        hold=tuple(r.sleeve_id for r in results if r.verdict == SleevePromotionReviewVerdict.HOLD),
        reject=tuple(r.sleeve_id for r in results if r.verdict == SleevePromotionReviewVerdict.REJECT),
        inconclusive=tuple(r.sleeve_id for r in results if r.verdict == SleevePromotionReviewVerdict.INCONCLUSIVE),
        repeated_weak=(),
        repeated_blocked=(),
        repeated_inconclusive=(),
        missing_evidence=(),
        governance_blockers=(),
        operator_summary="",
    )


def _admitted_summary(sleeve_id="micro-1"):
    controller = SleeveAdmissionController(
        _review_summary([_review_result(sleeve_id, SleevePromotionReviewVerdict.REVIEW_SUPPORTED)])
    )
    return controller.build_portfolio_summary()


def _unallocated_only_summary(sleeve_id="micro-1"):
    # missing_evidence on a REVIEW_SUPPORTED sleeve → ADMITTED_UNALLOCATED (no active sleeve).
    controller = SleeveAdmissionController(
        _review_summary(
            [_review_result(sleeve_id, SleevePromotionReviewVerdict.REVIEW_SUPPORTED, missing_evidence=("ev",))]
        )
    )
    return controller.build_portfolio_summary()


def _evidence_store(tmp_path):
    return EvidenceStore(evidence_dir=tmp_path / "sleeve_admission_evidence", config=EvidenceStoreConfig())


def _persisted_store(tmp_path, summary):
    store = _evidence_store(tmp_path)
    assert SleeveAdmissionStore(store).save_outcome(summary).success is True
    return store


def test_session_missing_evidence_store_blocked():
    summary = _admitted_summary("micro-1")
    snapshot = prepare_paper_shadow_session_from_evidence(summary, None)
    assert snapshot.status == PaperShadowSessionStatus.BLOCKED
    assert snapshot.status != PaperShadowSessionStatus.READY
    assert snapshot.plan_status == "blocked"
    assert "sleeve_admission_evidence:evidence_store_missing" in snapshot.evidence_blockers
    assert "sleeve_admission_evidence:evidence_store_missing" in snapshot.blockers_seen


def test_session_evidence_for_other_summary_blocked(tmp_path):
    # Accepted currentness evidence exists for outcome A; preparing a session for a different
    # summary B must NOT activate B — the digest mismatch keeps the session BLOCKED.
    summary_a = _admitted_summary("micro-1")
    summary_b = _admitted_summary("micro-2")
    store = _persisted_store(tmp_path, summary_a)

    snapshot = prepare_paper_shadow_session_from_evidence(summary_b, store)
    assert snapshot.status == PaperShadowSessionStatus.BLOCKED
    assert "sleeve_admission_evidence:summary_evidence_mismatch" in snapshot.evidence_blockers


def test_session_rejected_currentness_blocked(tmp_path):
    summary = _admitted_summary("micro-1")
    store = _evidence_store(tmp_path)
    # Snapshot present but no canonical evidence record → currentness_missing rejection.
    assert store.save_snapshot("sleeve_admission", sleeve_admission_outcome_to_dict(summary)).success is True

    snapshot = prepare_paper_shadow_session_from_evidence(summary, store)
    assert snapshot.status == PaperShadowSessionStatus.BLOCKED
    assert "sleeve_admission_evidence:currentness_missing" in snapshot.evidence_blockers


def test_session_no_admitted_active_blocked(tmp_path):
    summary = _unallocated_only_summary("micro-1")
    store = _persisted_store(tmp_path, summary)

    snapshot = prepare_paper_shadow_session_from_evidence(summary, store)
    assert snapshot.status == PaperShadowSessionStatus.BLOCKED
    assert snapshot.active_sleeves == ()
    assert "sleeve_admission:no_active_sleeves" in snapshot.activation_blockers


def test_session_governance_blocker_propagates(tmp_path):
    base = _admitted_summary("micro-1")
    summary = replace(base, governance_blockers=("governance:pending_operator_review",))
    store = _persisted_store(tmp_path, summary)

    snapshot = prepare_paper_shadow_session_from_evidence(summary, store)
    assert snapshot.status == PaperShadowSessionStatus.BLOCKED
    assert "governance:pending_operator_review" in snapshot.governance_blockers
    assert "governance:pending_operator_review" in snapshot.blockers_seen


def test_session_all_gates_pass_ready_and_startable(tmp_path):
    summary = _admitted_summary("micro-1")
    store = _persisted_store(tmp_path, summary)
    controller = PaperShadowSessionController()

    snapshot = prepare_paper_shadow_session_from_evidence(summary, store, controller=controller)
    assert snapshot.status == PaperShadowSessionStatus.READY
    assert snapshot.active_sleeves == ("micro-1",)
    assert snapshot.evidence_blockers == ()
    assert snapshot.activation_blockers == ()
    assert snapshot.governance_blockers == ()
    assert snapshot.plan_id == f"paper-shadow-activation:{sleeve_admission_digest(summary)}"
    # Paper-only invariants must hold; no live/order/money wiring.
    assert snapshot.paper_only is True
    assert snapshot.real_orders_enabled is False
    assert snapshot.real_money_enabled is False
    # A READY session can start.
    running = controller.start()
    assert running.status == PaperShadowSessionStatus.RUNNING


def test_session_blocked_cannot_start(tmp_path):
    summary = _admitted_summary("micro-1")
    controller = PaperShadowSessionController()
    snapshot = prepare_paper_shadow_session_from_evidence(summary, None, controller=controller)
    assert snapshot.status == PaperShadowSessionStatus.BLOCKED
    with pytest.raises(PaperShadowSessionCorruptError):
        controller.start()


def test_session_preparation_is_deterministic(tmp_path):
    summary = _admitted_summary("micro-1")
    store = _persisted_store(tmp_path, summary)
    first = prepare_paper_shadow_session_from_evidence(
        summary, store, controller=PaperShadowSessionController(clock_ns=lambda: 4242)
    )
    second = prepare_paper_shadow_session_from_evidence(
        summary, store, controller=PaperShadowSessionController(clock_ns=lambda: 4242)
    )
    assert first == second


def test_session_blocked_ordering_is_deterministic():
    base = _admitted_summary("micro-1")
    summary = replace(base, evidence_blockers=("z-blocker", "a-blocker"))
    first = prepare_paper_shadow_session_from_evidence(
        summary, None, controller=PaperShadowSessionController(clock_ns=lambda: 7)
    )
    second = prepare_paper_shadow_session_from_evidence(
        summary, None, controller=PaperShadowSessionController(clock_ns=lambda: 7)
    )
    assert first == second
    # evidence_store missing blocker is surfaced alongside the summary blockers, deterministically.
    assert "sleeve_admission_evidence:evidence_store_missing" in first.evidence_blockers
    assert "z-blocker" in first.evidence_blockers
    assert "a-blocker" in first.evidence_blockers


def test_session_malformed_summary_raises():
    with pytest.raises(SleeveAdmissionCorruptError):
        prepare_paper_shadow_session_from_evidence({"not": "a summary"}, None)
