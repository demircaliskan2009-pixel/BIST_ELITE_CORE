"""Tests for the paper sleeve admission review readiness gate (paper-only review-readiness record)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from crypto_core.validation.paper_replay_governance_review_decision import (
    PaperReplayGovernanceReviewDecision,
    PaperReplayGovernanceReviewDecisionStatus,
    paper_replay_governance_review_decision_to_dict,
)
from crypto_core.validation.paper_sleeve_admission_review_readiness import (
    PaperSleeveAdmissionReviewAction,
    PaperSleeveAdmissionReviewReadiness,
    PaperSleeveAdmissionReviewReadinessError,
    PaperSleeveAdmissionReviewReadinessStatus,
    build_paper_sleeve_admission_review_readiness,
    paper_sleeve_admission_review_readiness_to_dict,
)

_SOURCE = "offline-replay-v1"
_HIST = "historical-perp-journal-v1"
_REVIEW_EVIDENCE = "a" * 64
_RATIONALE = "b" * 64
_CORR = "corr:paper-sleeve-admission-review-readiness-001"
_READINESS_ID = "sleeve-review-readiness-001"
_CASE_ID = "admission-case-001"
_SLEEVE_ID = "sleeve-candidate-micro-1"
_REVIEWER = "reviewer-admission-1"
_REQUEST = PaperSleeveAdmissionReviewAction.REQUEST_PAPER_SLEEVE_ADMISSION_REVIEW

# Upstream carried digest field -> expected reason name on this gate.
_CARRIED_DIGESTS = (
    ("bundle_digest", "bundle_digest"),
    ("admission_digest", "admission_digest"),
    ("bridge_digest", "bridge_digest"),
    ("manifest_digest", "manifest_digest"),
    ("intake_digest", "intake_digest"),
    ("run_plan_digest", "run_plan_digest"),
    ("result_report_digest", "result_report_digest"),
    ("readiness_digest", "readiness_digest"),
    ("replay_trace_digest", "replay_trace_digest"),
    ("metrics_digest", "metrics_digest"),
    ("decision_trace_digest", "decision_trace_digest"),
    ("review_evidence_digest", "governance_review_evidence_digest"),
    ("rationale_digest", "governance_rationale_digest"),
    ("governance_decision_digest", "governance_decision_digest"),
)


def _governance(**overrides) -> PaperReplayGovernanceReviewDecision:
    base = {
        "schema_version": "paper-replay-governance-review-decision.v1",
        "status": PaperReplayGovernanceReviewDecisionStatus.READY,
        "ready": True,
        "governance_decision_id": "governance-decision-001",
        "decision": "APPROVED_FOR_PAPER_REVIEW",
        "reviewer_id": "reviewer-governance-1",
        "readiness_id": "readiness-001",
        "promotion_target": "PAPER_SLEEVE_ADMISSION_REVIEW",
        "readiness_status": "READY",
        "result_report_id": "result-report-001",
        "run_plan_id": "run-plan-001",
        "replay_mode": "offline_paper_replay",
        "requested_replay_id": "paper-replay-001",
        "operator_id": "operator-quant-1",
        "strategy_id": "bridge-s01",
        "strategy_digest": "d" * 64,
        "bundle_digest": "f" * 64,
        "admission_digest": "1" * 64,
        "bridge_digest": "e" * 64,
        "manifest_digest": "2" * 64,
        "intake_digest": "9" * 64,
        "run_plan_digest": "8" * 64,
        "result_report_digest": "7" * 64,
        "replay_trace_digest": "3" * 64,
        "metrics_digest": "4" * 64,
        "decision_trace_digest": "5" * 64,
        "readiness_digest": "6" * 64,
        "replay_source_id": _SOURCE,
        "historical_data_source_id": _HIST,
        "review_evidence_digest": "c" * 64,
        "rationale_digest": "a" * 64,
        "metadata": (),
        "rejection_reasons": (),
        "needs_research_reasons": (),
        "correlation_id": "corr:governance-001",
        "governance_decision_digest": "0" * 64,
    }
    base.update(overrides)
    record = PaperReplayGovernanceReviewDecision(**base)
    if "governance_decision_digest" in overrides:
        return record
    payload = paper_replay_governance_review_decision_to_dict(record)
    payload.pop("governance_decision_digest", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return replace(record, governance_decision_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _readiness(governance=None, **overrides):
    governance = _governance() if governance is None else governance
    kwargs = {
        "review_readiness_id": _READINESS_ID,
        "admission_case_id": _CASE_ID,
        "sleeve_candidate_id": _SLEEVE_ID,
        "reviewer_id": _REVIEWER,
        "action": _REQUEST,
        "review_evidence_digest": _REVIEW_EVIDENCE,
        "rationale_digest": _RATIONALE,
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return build_paper_sleeve_admission_review_readiness(governance, **kwargs)


def test_ready_approved_governance_request_builds_ready():
    record = _readiness()
    assert isinstance(record, PaperSleeveAdmissionReviewReadiness)
    assert record.status is PaperSleeveAdmissionReviewReadinessStatus.READY
    assert record.ready is True
    assert record.review_readiness_id == _READINESS_ID
    assert record.admission_case_id == _CASE_ID
    assert record.sleeve_candidate_id == _SLEEVE_ID
    assert record.action == "REQUEST_PAPER_SLEEVE_ADMISSION_REVIEW"
    assert record.governance_decision == "APPROVED_FOR_PAPER_REVIEW"
    assert record.governance_status == "READY"
    assert record.rejection_reasons == ()
    assert len(record.review_readiness_digest) == 64
    assert record.paper_only is True
    assert record.real_orders_enabled is False
    assert record.real_money_enabled is False


def test_string_action_accepted():
    assert _readiness(action="REQUEST_PAPER_SLEEVE_ADMISSION_REVIEW").status is (
        PaperSleeveAdmissionReviewReadinessStatus.READY
    )


def test_forged_governance_decision_digest_rejects_before_ready():
    forged = _governance(governance_decision_digest="0" * 64)
    record = _readiness(forged)
    assert record.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    assert record.ready is False
    assert "paper_sleeve_admission_review_readiness:governance_decision_digest_mismatch" in record.rejection_reasons


def test_tampered_governance_field_rejects():
    tampered = replace(_governance(), operator_id="forged-operator")  # keeps stale digest
    record = _readiness(tampered)
    assert record.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    assert "paper_sleeve_admission_review_readiness:governance_decision_digest_mismatch" in record.rejection_reasons


def test_non_ready_governance_statuses_propagate():
    rejected = _governance(
        status=PaperReplayGovernanceReviewDecisionStatus.REJECTED,
        ready=False,
        decision="REJECTED",
        rejection_reasons=("paper_replay_governance_review_decision:x",),
    )
    assert _readiness(rejected).status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED

    needs = _governance(
        status=PaperReplayGovernanceReviewDecisionStatus.NEEDS_RESEARCH,
        ready=False,
        decision="NEEDS_RESEARCH",
        needs_research_reasons=("paper_replay_governance_review_decision:y",),
    )
    assert _readiness(needs).status is PaperSleeveAdmissionReviewReadinessStatus.NEEDS_RESEARCH

    insufficient = _governance(
        status=PaperReplayGovernanceReviewDecisionStatus.INSUFFICIENT_EVIDENCE,
        ready=False,
        decision="INSUFFICIENT_EVIDENCE",
    )
    assert _readiness(insufficient).status is PaperSleeveAdmissionReviewReadinessStatus.INSUFFICIENT_EVIDENCE


def test_ready_status_but_ready_false_rejects():
    record = _readiness(_governance(ready=False))
    assert record.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    assert "paper_sleeve_admission_review_readiness:governance_ready_mismatch" in record.rejection_reasons


def test_ready_status_but_not_approved_rejects():
    record = _readiness(_governance(decision="NEEDS_RESEARCH"))
    assert record.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    assert "paper_sleeve_admission_review_readiness:governance_decision_not_approved" in record.rejection_reasons


@pytest.mark.parametrize(
    ("action", "expected"),
    (
        (PaperSleeveAdmissionReviewAction.REJECT, PaperSleeveAdmissionReviewReadinessStatus.REJECTED),
        (PaperSleeveAdmissionReviewAction.NEEDS_RESEARCH, PaperSleeveAdmissionReviewReadinessStatus.NEEDS_RESEARCH),
        (
            PaperSleeveAdmissionReviewAction.INSUFFICIENT_EVIDENCE,
            PaperSleeveAdmissionReviewReadinessStatus.INSUFFICIENT_EVIDENCE,
        ),
    ),
)
def test_action_maps(action, expected):
    assert _readiness(action=action).status is expected


def test_unknown_action_rejects():
    record = _readiness(action="APPROVE")
    assert record.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    assert "paper_sleeve_admission_review_readiness:action_unknown" in record.rejection_reasons
    assert _readiness(action=7).status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED


def test_malformed_ids_reject():
    for field in (
        "review_readiness_id",
        "admission_case_id",
        "sleeve_candidate_id",
        "reviewer_id",
        "correlation_id",
    ):
        record = _readiness(**{field: ""})
        assert record.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
        assert f"paper_sleeve_admission_review_readiness:{field}_invalid" in record.rejection_reasons


def test_malformed_review_digests_reject():
    for field in ("review_evidence_digest", "rationale_digest"):
        record = _readiness(**{field: "bad"})
        assert record.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
        assert f"paper_sleeve_admission_review_readiness:{field}_invalid" in record.rejection_reasons


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("review_evidence_digest", b"not-json"),
        ("review_evidence_digest", None),
        ("rationale_digest", object()),
        ("rationale_digest", 42),
    ),
)
def test_non_string_review_digests_reject_without_raising(field, value):
    record = _readiness(**{field: value})
    assert record.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    assert record.ready is False
    assert f"paper_sleeve_admission_review_readiness:{field}_invalid" in record.rejection_reasons
    assert len(record.review_readiness_digest) == 64


@pytest.mark.parametrize(("field", "reason"), _CARRIED_DIGESTS)
def test_malformed_carried_digests_reject(field, reason):
    overrides: dict = {field: "bad"}
    if field != "governance_decision_digest":
        overrides["governance_decision_digest"] = "2" * 64
    record = _readiness(_governance(**overrides))
    assert record.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    assert f"paper_sleeve_admission_review_readiness:{reason}_invalid" in record.rejection_reasons


@pytest.mark.parametrize("value", (object(), b"bad"))
@pytest.mark.parametrize(("field", "reason"), _CARRIED_DIGESTS)
def test_non_string_carried_digest_rejects_without_raising(field, reason, value):
    # Forge an upstream record carrying a non-string/non-serializable digest; explicit digest override
    # skips the fixture recompute over the forged field. Must fail closed, not raise during hashing.
    overrides: dict = {field: value}
    if field != "governance_decision_digest":
        overrides["governance_decision_digest"] = "2" * 64
    record = _readiness(_governance(**overrides))
    assert record.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    assert record.ready is False
    assert f"paper_sleeve_admission_review_readiness:{reason}_invalid" in record.rejection_reasons
    assert len(record.review_readiness_digest) == 64


@pytest.mark.parametrize("value", (object(), b"bad"))
def test_non_string_strategy_digest_rejects_without_raising(value):
    # strategy_digest is str | None and copied into the payload; a non-string value must not raise.
    record = _readiness(_governance(strategy_digest=value, governance_decision_digest="2" * 64))
    assert record.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    assert record.ready is False
    assert len(record.review_readiness_digest) == 64


@pytest.mark.parametrize(
    ("governance", "reason"),
    (
        (_governance(paper_only=False), "paper_sleeve_admission_review_readiness:governance_non_paper"),
        (
            _governance(real_orders_enabled=True),
            "paper_sleeve_admission_review_readiness:governance_real_orders_enabled",
        ),
        (
            _governance(real_money_enabled=True),
            "paper_sleeve_admission_review_readiness:governance_real_money_enabled",
        ),
    ),
)
def test_unsafe_governance_flags_reject_even_with_matching_digest(governance, reason):
    record = _readiness(governance)
    assert record.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    assert record.ready is False
    assert reason in record.rejection_reasons


def test_forbidden_tokens_reject():
    forbidden = _readiness(review_readiness_id="live_execution_review")
    assert forbidden.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    assert "paper_sleeve_admission_review_readiness:forbidden_scope_token" in forbidden.rejection_reasons

    bist = _readiness(reviewer_id="bist30-desk")
    assert bist.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    assert "paper_sleeve_admission_review_readiness:bist_scope_leakage" in bist.rejection_reasons

    shadow = _readiness(sleeve_candidate_id="shadow-sleeve-1")
    assert shadow.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    assert "paper_sleeve_admission_review_readiness:forbidden_scope_token" in shadow.rejection_reasons

    bad_source = _readiness(_governance(replay_source_id="scheduler_loop"))
    assert bad_source.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    assert "paper_sleeve_admission_review_readiness:forbidden_scope_token" in bad_source.rejection_reasons


@pytest.mark.parametrize(
    ("kwargs", "governance"),
    (
        ({"review_readiness_id": "order"}, None),
        ({"admission_case_id": "orders"}, None),
        ({"sleeve_candidate_id": "real_order"}, None),
        ({"review_readiness_id": "order-routing"}, None),
        ({"reviewer_id": "desk_order_router"}, None),
        ({"metadata": {"note": "real-orders"}}, None),
        ({}, _governance(operator_id="desk-order")),
    ),
)
def test_plain_order_scope_tokens_reject(kwargs, governance):
    record = _readiness(governance=governance, **kwargs)
    assert record.status is PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    assert record.ready is False
    assert "paper_sleeve_admission_review_readiness:forbidden_scope_token" in record.rejection_reasons


@pytest.mark.parametrize("value", ("border-study", "orderly-paper-review", "preorder-check"))
def test_unrelated_order_substrings_do_not_reject(value):
    assert _readiness(review_readiness_id=value).status is PaperSleeveAdmissionReviewReadinessStatus.READY


def test_deterministic_digest_identical_input():
    first = _readiness()
    second = _readiness()
    assert first.review_readiness_digest == second.review_readiness_digest
    assert paper_sleeve_admission_review_readiness_to_dict(first) == (
        paper_sleeve_admission_review_readiness_to_dict(second)
    )
    payload = paper_sleeve_admission_review_readiness_to_dict(first)
    assert payload["review_readiness_digest"] == first.review_readiness_digest


def test_material_change_changes_digest():
    base = _readiness()
    assert _readiness(admission_case_id="admission-case-002").review_readiness_digest != (base.review_readiness_digest)
    assert _readiness(rationale_digest="c" * 64).review_readiness_digest != base.review_readiness_digest


def test_metadata_normalized_and_deterministic():
    first = _readiness(metadata={"scope": "crypto_only", "desk": "micro"})
    second = _readiness(metadata={"desk": "micro", "scope": "crypto_only"})
    assert first.metadata == (("desk", "micro"), ("scope", "crypto_only"))
    assert first.review_readiness_digest == second.review_readiness_digest


def test_wrong_type_and_bad_metadata_raise():
    with pytest.raises(PaperSleeveAdmissionReviewReadinessError):
        build_paper_sleeve_admission_review_readiness(
            {"status": "READY"},  # type: ignore[arg-type]
            review_readiness_id=_READINESS_ID,
            admission_case_id=_CASE_ID,
            sleeve_candidate_id=_SLEEVE_ID,
            reviewer_id=_REVIEWER,
            action=_REQUEST,
            review_evidence_digest=_REVIEW_EVIDENCE,
            rationale_digest=_RATIONALE,
            correlation_id=_CORR,
        )
    with pytest.raises(PaperSleeveAdmissionReviewReadinessError):
        _readiness(metadata={"k": 5})
    with pytest.raises(PaperSleeveAdmissionReviewReadinessError):
        _readiness(metadata={5: "v"})


def test_immutable_and_no_forbidden_fields():
    record = _readiness()
    with pytest.raises(FrozenInstanceError):
        record.status = PaperSleeveAdmissionReviewReadinessStatus.REJECTED  # type: ignore[misc]
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
        "admitted",
        "allocation",
    }
    assert {field.name for field in fields(record)}.isdisjoint(forbidden)
    payload = paper_sleeve_admission_review_readiness_to_dict(record)
    assert payload["schema_version"] == "paper-sleeve-admission-review-readiness.v1"
    assert set(payload).isdisjoint(forbidden)
