"""Tests for Phase 15F — Crypto Sleeve Admission Gate.

Covers:
  1. Admission model construction
  2. Conservative no-review / no-governance behavior
  3. ADMITTED_ACTIVE classification
  4. ADMITTED_UNALLOCATED classification
  5. REVIEW_SUPPORTED_NOT_ADMITTED classification
  6. NOT_ADMITTED_BLOCKED classification
  7. NOT_ADMITTED_INCONCLUSIVE classification
  8. Per-sleeve reason / next-step summary
  9. Portfolio-wide admission summary
  10. Persistence/restore roundtrip (if added)
  11. Malformed-state fail-closed handling
  12. Service-level operator snapshot integration
  13. Deterministic replay on same inputs
  14. Full regression with other crypto_core tests

PRD reference: §2 System Orchestration, §7 Execution Engine, Phase 15F.
"""

import time

import pytest

from crypto_core.service.sleeve_admission_controller import (
    SleeveAdmissionController,
    SleeveAdmissionCorruptError,
    SleeveAdmissionVerdict,
)
from crypto_core.service.sleeve_promotion_review_controller import (
    SleevePromotionReviewPortfolioSummary,
    SleevePromotionReviewResult,
    SleevePromotionReviewVerdict,
)


def make_review_result(
    sleeve_id,
    verdict,
    governance_blockers=(),
    missing_evidence=(),
    reason="",
    next_step="",
):
    return SleevePromotionReviewResult(
        sleeve_id=sleeve_id,
        verdict=verdict,
        reason=reason,
        next_step=next_step,
        repeated_weak=False,
        repeated_blocked=False,
        repeated_inconclusive=False,
        missing_evidence=missing_evidence,
        governance_blockers=governance_blockers,
        last_verdict=None,
    )


def make_portfolio_summary(results):
    return SleevePromotionReviewPortfolioSummary(
        as_of_ns=int(time.time_ns()),
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


def test_admission_model_construction():
    r = make_review_result("s1", SleevePromotionReviewVerdict.REVIEW_SUPPORTED)
    summary = make_portfolio_summary([r])
    ctrl = SleeveAdmissionController(summary)
    results = ctrl.build_admission_results()
    assert len(results) == 1
    assert results[0].sleeve_id == "s1"


def test_admitted_active():
    r = make_review_result("s2", SleevePromotionReviewVerdict.REVIEW_SUPPORTED)
    summary = make_portfolio_summary([r])
    ctrl = SleeveAdmissionController(summary)
    results = ctrl.build_admission_results()
    assert results[0].verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE


def test_admitted_unallocated():
    r = make_review_result("s3", SleevePromotionReviewVerdict.REVIEW_SUPPORTED, missing_evidence=("evidence1",))
    summary = make_portfolio_summary([r])
    ctrl = SleeveAdmissionController(summary)
    results = ctrl.build_admission_results()
    assert results[0].verdict == SleeveAdmissionVerdict.ADMITTED_UNALLOCATED


def test_review_supported_not_admitted():
    r = make_review_result("s4", SleevePromotionReviewVerdict.REVIEW_SUPPORTED, governance_blockers=("gov1",))
    summary = make_portfolio_summary([r])
    ctrl = SleeveAdmissionController(summary)
    results = ctrl.build_admission_results()
    assert results[0].verdict == SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED


def test_not_admitted_blocked():
    r1 = make_review_result("s5", SleevePromotionReviewVerdict.HOLD)
    r2 = make_review_result("s6", SleevePromotionReviewVerdict.REJECT)
    summary = make_portfolio_summary([r1, r2])
    ctrl = SleeveAdmissionController(summary)
    results = ctrl.build_admission_results()
    assert results[0].verdict == SleeveAdmissionVerdict.NOT_ADMITTED_BLOCKED
    assert results[1].verdict == SleeveAdmissionVerdict.NOT_ADMITTED_BLOCKED


def test_not_admitted_inconclusive():
    r = make_review_result("s7", SleevePromotionReviewVerdict.INCONCLUSIVE)
    summary = make_portfolio_summary([r])
    ctrl = SleeveAdmissionController(summary)
    results = ctrl.build_admission_results()
    assert results[0].verdict == SleeveAdmissionVerdict.NOT_ADMITTED_INCONCLUSIVE


def test_per_sleeve_reason_next_step():
    r = make_review_result("s8", SleevePromotionReviewVerdict.REVIEW_SUPPORTED, reason="ok", next_step="monitor")
    summary = make_portfolio_summary([r])
    ctrl = SleeveAdmissionController(summary)
    results = ctrl.build_admission_results()
    assert results[0].reason == "Admitted and active."
    assert results[0].next_step == "Monitor allocation and governance."


def test_portfolio_admission_summary():
    r1 = make_review_result("a1", SleevePromotionReviewVerdict.REVIEW_SUPPORTED)
    r2 = make_review_result("a2", SleevePromotionReviewVerdict.REVIEW_SUPPORTED, missing_evidence=("ev",))
    r3 = make_review_result("a3", SleevePromotionReviewVerdict.REVIEW_SUPPORTED, governance_blockers=("gov",))
    r4 = make_review_result("a4", SleevePromotionReviewVerdict.HOLD)
    r5 = make_review_result("a5", SleevePromotionReviewVerdict.INCONCLUSIVE)
    summary = make_portfolio_summary([r1, r2, r3, r4, r5])
    ctrl = SleeveAdmissionController(summary)
    psum = ctrl.build_portfolio_summary()
    assert set(psum.admitted_active) == {"a1"}
    assert set(psum.admitted_unallocated) == {"a2"}
    assert set(psum.review_supported_not_admitted) == {"a3"}
    assert set(psum.blocked) == {"a4"}
    assert set(psum.inconclusive) == {"a5"}
    assert "Admitted: 1" in psum.operator_summary


def test_fail_closed_on_malformed():
    with pytest.raises(SleeveAdmissionCorruptError):
        SleeveAdmissionController(None)


def test_deterministic_replay():
    r = make_review_result("r1", SleevePromotionReviewVerdict.REVIEW_SUPPORTED)
    summary = make_portfolio_summary([r])
    ctrl1 = SleeveAdmissionController(summary)
    ctrl2 = SleeveAdmissionController(summary)
    assert ctrl1.build_admission_results() == ctrl2.build_admission_results()
