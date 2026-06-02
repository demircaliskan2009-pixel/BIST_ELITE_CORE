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

import hashlib
import json
import time

import pytest

from crypto_core.service.evidence_store import EvidenceStore, EvidenceStoreConfig
from crypto_core.service.promotion_review import (
    PromotionReviewEvidencePrecheck,
    current_promotion_review_evidence_precheck,
)
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


def _accepted_promotion_evidence_precheck() -> PromotionReviewEvidencePrecheck:
    return PromotionReviewEvidencePrecheck(
        accepted=True,
        evidence_digest="a" * 64,
        review_id="review-accepted",
        verdict="promote",
        campaign_ids=("camp-1",),
    )


def _rejected_promotion_evidence_precheck(reason: str) -> PromotionReviewEvidencePrecheck:
    return PromotionReviewEvidencePrecheck(
        accepted=False,
        rejection_reasons=(reason,),
        review_id="review-rejected",
        verdict="hold",
        campaign_ids=("camp-1",),
    )


def _promotion_review_payload(
    *,
    verdict: str = "promote",
    review_id: str = "review-current",
    reviewed_at_ns: int = 123,
    campaign_ids: tuple[str, ...] = ("camp-1",),
) -> dict:
    return {
        "review_id": review_id,
        "reviewed_at_ns": reviewed_at_ns,
        "verdict": verdict,
        "readiness_level": "paper_live",
        "readiness_is_supportive": True,
        "campaign_ids": list(campaign_ids),
    }


def _promotion_review_digest(payload: dict) -> str:
    canonical = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _promotion_review_evidence_payload(payload: dict) -> dict:
    return {
        "schema_version": "1",
        "payload_type": "promotion_review",
        "evidence_digest": _promotion_review_digest(payload),
        "promotion_review": dict(payload),
        "review_id": payload["review_id"],
        "reviewed_at_ns": payload["reviewed_at_ns"],
        "verdict": payload["verdict"],
        "readiness_level": payload["readiness_level"],
        "campaign_ids": list(payload["campaign_ids"]),
    }


def _store_with_snapshot(tmp_path, payload: dict) -> EvidenceStore:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    assert store.save_snapshot("promotion_review", payload).success is True
    return store


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


def test_valid_canonical_accepted_promotion_evidence_allows_active_and_unallocated(tmp_path):
    payload = _promotion_review_payload()
    store = _store_with_snapshot(tmp_path, payload)
    assert store.append_evidence("promotion_review", _promotion_review_evidence_payload(payload)).success is True

    precheck = current_promotion_review_evidence_precheck(store)
    active = make_review_result("active", SleevePromotionReviewVerdict.REVIEW_SUPPORTED)
    unallocated = make_review_result(
        "unallocated",
        SleevePromotionReviewVerdict.REVIEW_SUPPORTED,
        missing_evidence=("stage4:comparison_missing",),
    )
    results = SleeveAdmissionController(
        make_portfolio_summary([active, unallocated]),
        promotion_evidence_precheck=precheck,
    ).build_admission_results()

    assert precheck.accepted is True
    assert results[0].verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE
    assert results[1].verdict == SleeveAdmissionVerdict.ADMITTED_UNALLOCATED
    assert results[1].evidence_blockers == ("stage4:comparison_missing",)


def test_missing_promotion_evidence_blocks_supported_sleeve_admission(tmp_path):
    payload = _promotion_review_payload()
    store = _store_with_snapshot(tmp_path, payload)
    precheck = current_promotion_review_evidence_precheck(store)
    result = SleeveAdmissionController(
        make_portfolio_summary([make_review_result("s1", SleevePromotionReviewVerdict.REVIEW_SUPPORTED)]),
        promotion_evidence_precheck=precheck,
    ).build_admission_results()[0]

    assert precheck.rejection_reasons == ("promotion_review_evidence:currentness_missing",)
    assert result.verdict == SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED
    assert result.evidence_blockers == ("promotion_review_evidence:currentness_missing",)


def test_legacy_digestless_promotion_evidence_is_not_currentness_proof(tmp_path):
    payload = _promotion_review_payload()
    store = _store_with_snapshot(tmp_path, payload)
    assert store.append_evidence("promotion_review", payload).success is True

    precheck = current_promotion_review_evidence_precheck(store)

    assert precheck.accepted is False
    assert precheck.rejection_reasons == ("promotion_review_evidence:legacy_digestless_not_currentness_provable",)


def test_malformed_promotion_evidence_blocks_fail_closed(tmp_path):
    payload = _promotion_review_payload()
    store = _store_with_snapshot(tmp_path, payload)
    assert store.append_evidence("promotion_review", {"payload_type": "promotion_review"}).success is True

    precheck = current_promotion_review_evidence_precheck(store)

    assert precheck.accepted is False
    assert precheck.rejection_reasons == ("promotion_review_evidence:store_or_payload_malformed",)


def test_wrong_promotion_evidence_payload_type_blocks_fail_closed(tmp_path):
    payload = _promotion_review_payload()
    bad_payload = _promotion_review_evidence_payload(payload)
    bad_payload["payload_type"] = "not_promotion_review"
    store = _store_with_snapshot(tmp_path, payload)
    assert store.append_evidence("promotion_review", bad_payload).success is True

    precheck = current_promotion_review_evidence_precheck(store)

    assert precheck.accepted is False
    assert precheck.rejection_reasons == ("promotion_review_evidence:store_or_payload_malformed",)


def test_non_accepted_promotion_outcome_blocks_supported_sleeve_admission(tmp_path):
    payload = _promotion_review_payload(verdict="hold")
    store = _store_with_snapshot(tmp_path, payload)
    assert store.append_evidence("promotion_review", _promotion_review_evidence_payload(payload)).success is True
    precheck = current_promotion_review_evidence_precheck(store)
    result = SleeveAdmissionController(
        make_portfolio_summary([make_review_result("s1", SleevePromotionReviewVerdict.REVIEW_SUPPORTED)]),
        promotion_evidence_precheck=precheck,
    ).build_admission_results()[0]

    assert precheck.rejection_reasons == ("promotion_review_evidence:promotion_not_accepted",)
    assert result.verdict == SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED


def test_tampered_promotion_evidence_digest_blocks_fail_closed(tmp_path):
    payload = _promotion_review_payload()
    tampered_payload = _promotion_review_evidence_payload(payload)
    tampered_payload["promotion_review"]["reviewed_at_ns"] = payload["reviewed_at_ns"] + 1
    store = _store_with_snapshot(tmp_path, payload)
    assert store.append_evidence("promotion_review", tampered_payload).success is True

    precheck = current_promotion_review_evidence_precheck(store)

    assert precheck.accepted is False
    assert precheck.rejection_reasons == ("promotion_review_evidence:store_or_payload_malformed",)


def test_duplicate_canonical_promotion_evidence_blocks_as_ambiguous(tmp_path):
    payload = _promotion_review_payload()
    evidence_payload = _promotion_review_evidence_payload(payload)
    store = _store_with_snapshot(tmp_path, payload)
    assert store.append_evidence("promotion_review", evidence_payload).success is True
    assert store.append_evidence("promotion_review", evidence_payload).success is True

    precheck = current_promotion_review_evidence_precheck(store)

    assert precheck.accepted is False
    assert precheck.rejection_reasons == ("promotion_review_evidence:currentness_ambiguous",)


def test_promotion_evidence_blockers_are_ordered_after_existing_evidence_blockers():
    precheck = _rejected_promotion_evidence_precheck("promotion_review_evidence:currentness_missing")
    result = SleeveAdmissionController(
        make_portfolio_summary(
            [
                make_review_result(
                    "s1",
                    SleevePromotionReviewVerdict.REVIEW_SUPPORTED,
                    missing_evidence=("stage4:comparison_missing",),
                )
            ]
        ),
        promotion_evidence_precheck=precheck,
    ).build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED
    assert result.evidence_blockers == (
        "stage4:comparison_missing",
        "promotion_review_evidence:currentness_missing",
    )


def test_test_unit_classification_can_still_supply_explicit_accepted_promotion_proof():
    result = SleeveAdmissionController(
        make_portfolio_summary([make_review_result("s1", SleevePromotionReviewVerdict.REVIEW_SUPPORTED)]),
        promotion_evidence_precheck=_accepted_promotion_evidence_precheck(),
    ).build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE
