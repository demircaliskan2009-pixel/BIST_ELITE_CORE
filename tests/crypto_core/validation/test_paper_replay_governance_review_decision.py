"""Tests for the paper replay governance review decision gate (paper-only record of a review verdict)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from crypto_core.validation.paper_replay_governance_review_decision import (
    PaperReplayGovernanceDecision,
    PaperReplayGovernanceReviewDecision,
    PaperReplayGovernanceReviewDecisionError,
    PaperReplayGovernanceReviewDecisionStatus,
    build_paper_replay_governance_review_decision,
    paper_replay_governance_review_decision_to_dict,
)
from crypto_core.validation.paper_replay_promotion_readiness import (
    PaperReplayPromotionReadiness,
    PaperReplayPromotionReadinessStatus,
    paper_replay_promotion_readiness_to_dict,
)

_SOURCE = "offline-replay-v1"
_HIST = "historical-perp-journal-v1"
_BUNDLE = "f" * 64
_ADMISSION = "1" * 64
_BRIDGE = "e" * 64
_MANIFEST = "2" * 64
_INTAKE = "9" * 64
_RUN_PLAN = "8" * 64
_REPORT = "7" * 64
_TRACE = "3" * 64
_METRICS = "4" * 64
_DECISION_TRACE = "5" * 64
_REVIEW_EVIDENCE = "a" * 64
_RATIONALE = "b" * 64
_CORR = "corr:paper-replay-governance-review-decision-001"
_DECISION_ID = "governance-decision-001"
_REVIEWER = "reviewer-governance-1"

_DIGEST_FIELDS = (
    "bundle_digest",
    "admission_digest",
    "bridge_digest",
    "manifest_digest",
    "intake_digest",
    "run_plan_digest",
    "result_report_digest",
    "readiness_digest",
    "replay_trace_digest",
    "metrics_digest",
    "decision_trace_digest",
)


def _readiness(**overrides) -> PaperReplayPromotionReadiness:
    base = {
        "schema_version": "paper-replay-promotion-readiness.v1",
        "status": PaperReplayPromotionReadinessStatus.READY,
        "ready": True,
        "readiness_id": "readiness-001",
        "promotion_target": "PAPER_CANDIDATE_REVIEW",
        "reviewer_id": "reviewer-readiness-1",
        "result_report_id": "result-report-001",
        "outcome_status": "COMPLETED",
        "report_status": "READY",
        "run_plan_id": "run-plan-001",
        "replay_mode": "offline_paper_replay",
        "requested_replay_id": "paper-replay-001",
        "operator_id": "operator-quant-1",
        "strategy_id": "bridge-s01",
        "strategy_digest": "d" * 64,
        "bundle_digest": _BUNDLE,
        "admission_digest": _ADMISSION,
        "bridge_digest": _BRIDGE,
        "manifest_digest": _MANIFEST,
        "intake_digest": _INTAKE,
        "run_plan_digest": _RUN_PLAN,
        "result_report_digest": _REPORT,
        "replay_source_id": _SOURCE,
        "historical_data_source_id": _HIST,
        "replay_trace_digest": _TRACE,
        "metrics_digest": _METRICS,
        "decision_trace_digest": _DECISION_TRACE,
        "metadata": (),
        "rejection_reasons": (),
        "needs_research_reasons": (),
        "correlation_id": "corr:readiness-001",
        "readiness_digest": "0" * 64,
    }
    base.update(overrides)
    readiness = PaperReplayPromotionReadiness(**base)
    if "readiness_digest" in overrides:
        return readiness
    payload = paper_replay_promotion_readiness_to_dict(readiness)
    payload.pop("readiness_digest", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return replace(readiness, readiness_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _decision(readiness=None, **overrides):
    readiness = _readiness() if readiness is None else readiness
    kwargs = {
        "governance_decision_id": _DECISION_ID,
        "decision": PaperReplayGovernanceDecision.APPROVED_FOR_PAPER_REVIEW,
        "reviewer_id": _REVIEWER,
        "review_evidence_digest": _REVIEW_EVIDENCE,
        "rationale_digest": _RATIONALE,
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return build_paper_replay_governance_review_decision(readiness, **kwargs)


def test_ready_readiness_approved_builds_ready_decision():
    record = _decision()
    assert isinstance(record, PaperReplayGovernanceReviewDecision)
    assert record.status is PaperReplayGovernanceReviewDecisionStatus.READY
    assert record.ready is True
    assert record.governance_decision_id == _DECISION_ID
    assert record.decision == "APPROVED_FOR_PAPER_REVIEW"
    assert record.reviewer_id == _REVIEWER
    assert record.readiness_status == "READY"
    assert record.review_evidence_digest == _REVIEW_EVIDENCE
    assert record.rationale_digest == _RATIONALE
    assert record.rejection_reasons == ()
    assert len(record.governance_decision_digest) == 64
    assert record.paper_only is True
    assert record.real_orders_enabled is False
    assert record.real_money_enabled is False


def test_string_decision_accepted():
    assert _decision(decision="APPROVED_FOR_PAPER_REVIEW").status is (PaperReplayGovernanceReviewDecisionStatus.READY)


def test_forged_readiness_digest_rejects_before_ready():
    forged = _readiness(readiness_digest="0" * 64)
    record = _decision(forged)
    assert record.status is PaperReplayGovernanceReviewDecisionStatus.REJECTED
    assert record.ready is False
    assert "paper_replay_governance_review_decision:readiness_digest_mismatch" in record.rejection_reasons


def test_tampered_readiness_field_rejects():
    tampered = replace(_readiness(), operator_id="forged-operator")  # keeps stale readiness_digest
    record = _decision(tampered)
    assert record.status is PaperReplayGovernanceReviewDecisionStatus.REJECTED
    assert "paper_replay_governance_review_decision:readiness_digest_mismatch" in record.rejection_reasons


def test_non_ready_readiness_statuses_propagate():
    rejected = _readiness(
        status=PaperReplayPromotionReadinessStatus.REJECTED,
        ready=False,
        rejection_reasons=("paper_replay_promotion_readiness:x",),
    )
    assert _decision(rejected).status is PaperReplayGovernanceReviewDecisionStatus.REJECTED

    needs = _readiness(
        status=PaperReplayPromotionReadinessStatus.NEEDS_RESEARCH,
        ready=False,
        needs_research_reasons=("paper_replay_promotion_readiness:y",),
    )
    assert _decision(needs).status is PaperReplayGovernanceReviewDecisionStatus.NEEDS_RESEARCH

    insufficient = _readiness(status=PaperReplayPromotionReadinessStatus.INSUFFICIENT_EVIDENCE, ready=False)
    assert _decision(insufficient).status is PaperReplayGovernanceReviewDecisionStatus.INSUFFICIENT_EVIDENCE


def test_ready_status_but_ready_false_rejects():
    record = _decision(_readiness(ready=False))
    assert record.status is PaperReplayGovernanceReviewDecisionStatus.REJECTED
    assert "paper_replay_governance_review_decision:readiness_ready_mismatch" in record.rejection_reasons


@pytest.mark.parametrize(
    ("decision", "expected"),
    (
        (PaperReplayGovernanceDecision.REJECTED, PaperReplayGovernanceReviewDecisionStatus.REJECTED),
        (PaperReplayGovernanceDecision.NEEDS_RESEARCH, PaperReplayGovernanceReviewDecisionStatus.NEEDS_RESEARCH),
        (
            PaperReplayGovernanceDecision.INSUFFICIENT_EVIDENCE,
            PaperReplayGovernanceReviewDecisionStatus.INSUFFICIENT_EVIDENCE,
        ),
    ),
)
def test_decision_maps(decision, expected):
    assert _decision(decision=decision).status is expected


def test_unknown_decision_rejects():
    record = _decision(decision="APPROVED")
    assert record.status is PaperReplayGovernanceReviewDecisionStatus.REJECTED
    assert "paper_replay_governance_review_decision:decision_unknown" in record.rejection_reasons
    assert _decision(decision=5).status is PaperReplayGovernanceReviewDecisionStatus.REJECTED


def test_malformed_ids_reject():
    assert _decision(governance_decision_id="").status is PaperReplayGovernanceReviewDecisionStatus.REJECTED
    assert _decision(reviewer_id="").status is PaperReplayGovernanceReviewDecisionStatus.REJECTED
    assert _decision(correlation_id="").status is PaperReplayGovernanceReviewDecisionStatus.REJECTED
    for field in (
        "readiness_id",
        "promotion_target",
        "result_report_id",
        "run_plan_id",
        "requested_replay_id",
        "operator_id",
        "replay_source_id",
        "historical_data_source_id",
    ):
        record = _decision(_readiness(**{field: ""}))
        assert record.status is PaperReplayGovernanceReviewDecisionStatus.REJECTED
        assert f"paper_replay_governance_review_decision:{field}_invalid" in record.rejection_reasons


def test_malformed_review_digests_reject():
    for field in ("review_evidence_digest", "rationale_digest"):
        record = _decision(**{field: "bad"})
        assert record.status is PaperReplayGovernanceReviewDecisionStatus.REJECTED
        assert f"paper_replay_governance_review_decision:{field}_invalid" in record.rejection_reasons


@pytest.mark.parametrize("field", _DIGEST_FIELDS)
def test_malformed_carried_digests_reject(field):
    record = _decision(_readiness(**{field: "bad"}))
    assert record.status is PaperReplayGovernanceReviewDecisionStatus.REJECTED
    assert f"paper_replay_governance_review_decision:{field}_invalid" in record.rejection_reasons


@pytest.mark.parametrize(
    ("readiness", "reason"),
    (
        (_readiness(paper_only=False), "paper_replay_governance_review_decision:readiness_non_paper"),
        (
            _readiness(real_orders_enabled=True),
            "paper_replay_governance_review_decision:readiness_real_orders_enabled",
        ),
        (
            _readiness(real_money_enabled=True),
            "paper_replay_governance_review_decision:readiness_real_money_enabled",
        ),
    ),
)
def test_unsafe_readiness_flags_reject_even_with_matching_digest(readiness, reason):
    record = _decision(readiness)
    assert record.status is PaperReplayGovernanceReviewDecisionStatus.REJECTED
    assert record.ready is False
    assert reason in record.rejection_reasons


def test_forbidden_tokens_reject():
    forbidden = _decision(governance_decision_id="live_execution_decision")
    assert forbidden.status is PaperReplayGovernanceReviewDecisionStatus.REJECTED
    assert "paper_replay_governance_review_decision:forbidden_scope_token" in forbidden.rejection_reasons

    bist = _decision(reviewer_id="bist30-desk")
    assert bist.status is PaperReplayGovernanceReviewDecisionStatus.REJECTED
    assert "paper_replay_governance_review_decision:bist_scope_leakage" in bist.rejection_reasons

    bad_source = _decision(_readiness(replay_source_id="scheduler_loop"))
    assert bad_source.status is PaperReplayGovernanceReviewDecisionStatus.REJECTED
    assert "paper_replay_governance_review_decision:forbidden_scope_token" in bad_source.rejection_reasons


@pytest.mark.parametrize(
    ("kwargs", "readiness"),
    (
        ({"governance_decision_id": "order"}, None),
        ({"governance_decision_id": "orders"}, None),
        ({"governance_decision_id": "real_order"}, None),
        ({"governance_decision_id": "order-routing"}, None),
        ({"reviewer_id": "desk_order_router"}, None),
        ({"metadata": {"note": "real-orders"}}, None),
        ({}, _readiness(operator_id="desk-order")),
    ),
)
def test_plain_order_scope_tokens_reject(kwargs, readiness):
    record = _decision(readiness=readiness, **kwargs)
    assert record.status is PaperReplayGovernanceReviewDecisionStatus.REJECTED
    assert record.ready is False
    assert "paper_replay_governance_review_decision:forbidden_scope_token" in record.rejection_reasons


@pytest.mark.parametrize("value", ("border-study", "orderly-paper-review", "preorder-check"))
def test_unrelated_order_substrings_do_not_reject(value):
    assert _decision(governance_decision_id=value).status is PaperReplayGovernanceReviewDecisionStatus.READY


def test_deterministic_digest_identical_input():
    first = _decision()
    second = _decision()
    assert first.governance_decision_digest == second.governance_decision_digest
    assert paper_replay_governance_review_decision_to_dict(first) == (
        paper_replay_governance_review_decision_to_dict(second)
    )
    payload = paper_replay_governance_review_decision_to_dict(first)
    assert payload["governance_decision_digest"] == first.governance_decision_digest


def test_material_change_changes_digest():
    base = _decision()
    assert (
        _decision(governance_decision_id="governance-decision-002").governance_decision_digest
        != base.governance_decision_digest
    )
    assert _decision(rationale_digest="c" * 64).governance_decision_digest != base.governance_decision_digest


def test_metadata_normalized_and_deterministic():
    first = _decision(metadata={"scope": "crypto_only", "desk": "micro"})
    second = _decision(metadata={"desk": "micro", "scope": "crypto_only"})
    assert first.metadata == (("desk", "micro"), ("scope", "crypto_only"))
    assert first.governance_decision_digest == second.governance_decision_digest


def test_wrong_type_and_bad_metadata_raise():
    with pytest.raises(PaperReplayGovernanceReviewDecisionError):
        build_paper_replay_governance_review_decision(
            {"status": "READY"},  # type: ignore[arg-type]
            governance_decision_id=_DECISION_ID,
            decision=PaperReplayGovernanceDecision.APPROVED_FOR_PAPER_REVIEW,
            reviewer_id=_REVIEWER,
            review_evidence_digest=_REVIEW_EVIDENCE,
            rationale_digest=_RATIONALE,
            correlation_id=_CORR,
        )
    with pytest.raises(PaperReplayGovernanceReviewDecisionError):
        _decision(metadata={"k": 5})
    with pytest.raises(PaperReplayGovernanceReviewDecisionError):
        _decision(metadata={5: "v"})


def test_immutable_and_no_forbidden_fields():
    record = _decision()
    with pytest.raises(FrozenInstanceError):
        record.status = PaperReplayGovernanceReviewDecisionStatus.REJECTED  # type: ignore[misc]
    forbidden = {
        "order",
        "route",
        "venue",
        "exchange",
        "scheduler",
        "live",
        "runtime",
        "persistence",
        "store",
        "engine",
    }
    assert {field.name for field in fields(record)}.isdisjoint(forbidden)
    payload = paper_replay_governance_review_decision_to_dict(record)
    assert payload["schema_version"] == "paper-replay-governance-review-decision.v1"
    assert set(payload).isdisjoint(forbidden)
