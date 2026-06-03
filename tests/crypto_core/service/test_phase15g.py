"""Tests for Phase 15G — evidence-gated paper/shadow activation plan builder.

Covers ``build_paper_shadow_activation_plan``:
  1. Missing evidence store → BLOCKED with evidence_store_missing blocker
  2. Rejected currentness precheck → evidence blockers surfaced, BLOCKED
  3. Admitted-unallocated-only summary (no active sleeve) → activation blocker, BLOCKED
  4. Accepted current evidence + active sleeve → READY_FOR_PAPER_SHADOW
  5. Summary-level evidence blocker surfaced even when evidence is current → BLOCKED
  6. Summary-level governance blocker surfaced and forces BLOCKED
  7. Deterministic blocker ordering and idempotent plan construction

PRD reference: §2 System Orchestration, §7 Execution Engine, Phase 15G.
"""

from __future__ import annotations

from dataclasses import replace

from crypto_core.service.evidence_store import EvidenceStore, EvidenceStoreConfig
from crypto_core.service.sleeve_admission_controller import (
    PaperShadowActivationStatus,
    PaperShadowSourceManifestStatus,
    SleeveAdmissionController,
    SleeveAdmissionStore,
    build_paper_shadow_activation_plan,
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


def test_build_plan_missing_evidence_store_blocked():
    summary = _admitted_summary("micro-1")
    plan = build_paper_shadow_activation_plan(summary, None)
    assert plan.activation_status == PaperShadowActivationStatus.BLOCKED
    assert plan.source_manifest_status == PaperShadowSourceManifestStatus.BLOCKED
    assert "sleeve_admission_evidence:evidence_store_missing" in plan.evidence_blockers


def test_build_plan_precheck_rejected_populates_evidence_blockers(tmp_path):
    summary = _admitted_summary("micro-1")
    store = _evidence_store(tmp_path)
    # Snapshot present but no canonical evidence record → currentness_missing rejection.
    assert store.save_snapshot("sleeve_admission", sleeve_admission_outcome_to_dict(summary)).success is True

    plan = build_paper_shadow_activation_plan(summary, store)
    assert plan.activation_status == PaperShadowActivationStatus.BLOCKED
    assert "sleeve_admission_evidence:currentness_missing" in plan.evidence_blockers


def test_build_plan_no_admitted_active_populates_activation_blockers(tmp_path):
    summary = _unallocated_only_summary("micro-1")
    # Persist so currentness precheck accepts (admitted_unallocated is non-empty).
    store = _persisted_store(tmp_path, summary)

    plan = build_paper_shadow_activation_plan(summary, store)
    assert plan.active_sleeves == ()
    assert plan.admitted_unallocated_sleeves == ("micro-1",)
    assert plan.activation_status == PaperShadowActivationStatus.BLOCKED
    assert "sleeve_admission:no_active_sleeves" in plan.activation_blockers


def test_build_plan_all_gates_pass_yields_ready_for_paper_shadow(tmp_path):
    summary = _admitted_summary("micro-1")
    store = _persisted_store(tmp_path, summary)

    plan = build_paper_shadow_activation_plan(summary, store)
    assert plan.activation_status == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW
    assert plan.source_manifest_status == PaperShadowSourceManifestStatus.READY
    assert plan.active_sleeves == ("micro-1",)
    assert plan.evidence_blockers == ()
    assert plan.activation_blockers == ()
    assert plan.governance_blockers == ()
    assert plan.plan_id == f"paper-shadow-activation:{sleeve_admission_digest(summary)}"


def test_build_plan_runtime_evidence_blockers_surfaced(tmp_path):
    base = _admitted_summary("micro-1")
    summary = replace(base, evidence_blockers=("sleeve_admission:evidence_hold",))
    # Persist the modified summary so the currentness precheck still accepts.
    store = _persisted_store(tmp_path, summary)

    plan = build_paper_shadow_activation_plan(summary, store)
    assert "sleeve_admission:evidence_hold" in plan.evidence_blockers
    assert plan.activation_status == PaperShadowActivationStatus.BLOCKED


def test_build_plan_runtime_governance_blockers_surfaced(tmp_path):
    base = _admitted_summary("micro-1")
    summary = replace(base, governance_blockers=("governance:pending_operator_review",))
    store = _persisted_store(tmp_path, summary)

    plan = build_paper_shadow_activation_plan(summary, store)
    assert "governance:pending_operator_review" in plan.governance_blockers
    assert plan.activation_status == PaperShadowActivationStatus.BLOCKED


def test_build_plan_evidence_for_other_summary_blocks(tmp_path):
    # Accepted currentness evidence exists for outcome A, but the caller passes a different
    # admitted summary B. The precheck still accepts (it proves A), so readiness must NOT be
    # derived from the unproven B: the digest mismatch forces BLOCKED with an evidence blocker.
    summary_a = _admitted_summary("micro-1")
    summary_b = _admitted_summary("micro-2")
    assert sleeve_admission_digest(summary_a) != sleeve_admission_digest(summary_b)
    store = _persisted_store(tmp_path, summary_a)

    plan = build_paper_shadow_activation_plan(summary_b, store)
    assert plan.activation_status == PaperShadowActivationStatus.BLOCKED
    assert "sleeve_admission_evidence:summary_evidence_mismatch" in plan.evidence_blockers
    # plan_id still reflects the passed (unproven) summary, but the plan is not READY.
    assert plan.plan_id == f"paper-shadow-activation:{sleeve_admission_digest(summary_b)}"


def test_build_plan_matching_evidence_is_ready(tmp_path):
    # Control for the mismatch test: when the persisted evidence binds to the same summary,
    # the digest matches and the plan is READY.
    summary = _admitted_summary("micro-1")
    store = _persisted_store(tmp_path, summary)

    plan = build_paper_shadow_activation_plan(summary, store)
    assert plan.activation_status == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW
    assert "sleeve_admission_evidence:summary_evidence_mismatch" not in plan.evidence_blockers


def test_build_plan_deterministic_blocker_ordering():
    base = _admitted_summary("micro-1")
    summary = replace(base, evidence_blockers=("z-blocker", "a-blocker"))
    # evidence_store None → precheck contributes evidence_store_missing first, then summary blockers.
    plan_first = build_paper_shadow_activation_plan(summary, None)
    plan_second = build_paper_shadow_activation_plan(summary, None)

    assert plan_first.evidence_blockers == (
        "sleeve_admission_evidence:evidence_store_missing",
        "z-blocker",
        "a-blocker",
    )
    assert plan_first == plan_second
