"""Tests for the paper replay promotion-readiness gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from crypto_core.validation.paper_replay_promotion_readiness import (
    PaperReplayPromotionReadiness,
    PaperReplayPromotionReadinessError,
    PaperReplayPromotionReadinessStatus,
    PaperReplayPromotionTarget,
    build_paper_replay_promotion_readiness,
    paper_replay_promotion_readiness_to_dict,
)
from crypto_core.validation.paper_replay_result_report import (
    PaperReplayOutcomeStatus,
    PaperReplayResultReport,
    PaperReplayResultReportStatus,
    paper_replay_result_report_to_dict,
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
_DECISION = "5" * 64
_CORR = "corr:paper-replay-promotion-readiness-001"
_READINESS_ID = "promotion-readiness-001"
_REVIEWER = "governance-reviewer-1"


def _with_report_digest(report: PaperReplayResultReport) -> PaperReplayResultReport:
    payload = paper_replay_result_report_to_dict(report)
    payload.pop("result_report_digest", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return replace(report, result_report_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _report(**overrides) -> PaperReplayResultReport:
    base = {
        "schema_version": "paper-replay-result-report.v1",
        "status": PaperReplayResultReportStatus.READY,
        "ready": True,
        "result_report_id": "result-report-001",
        "outcome_status": PaperReplayOutcomeStatus.COMPLETED.value,
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
        "run_plan_status": "READY",
        "replay_source_id": _SOURCE,
        "historical_data_source_id": _HIST,
        "replay_trace_digest": _TRACE,
        "metrics_digest": _METRICS,
        "decision_trace_digest": _DECISION,
        "metadata": (),
        "rejection_reasons": (),
        "needs_research_reasons": (),
        "correlation_id": "corr:result-report-001",
        "result_report_digest": _REPORT,
    }
    base.update(overrides)
    report = PaperReplayResultReport(**base)
    if "result_report_digest" in overrides:
        return report
    return _with_report_digest(report)


def _readiness(report=None, **overrides):
    report = _report() if report is None else report
    kwargs = {
        "readiness_id": _READINESS_ID,
        "promotion_target": PaperReplayPromotionTarget.PAPER_CANDIDATE_REVIEW,
        "reviewer_id": _REVIEWER,
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return build_paper_replay_promotion_readiness(report, **kwargs)


def test_ready_report_candidate_review_builds_ready_readiness():
    readiness = _readiness()

    assert isinstance(readiness, PaperReplayPromotionReadiness)
    assert readiness.status is PaperReplayPromotionReadinessStatus.READY
    assert readiness.ready is True
    assert readiness.promotion_target == "PAPER_CANDIDATE_REVIEW"
    assert readiness.result_report_digest == _report().result_report_digest
    assert readiness.rejection_reasons == ()
    assert len(readiness.readiness_digest) == 64
    assert readiness.paper_only is True
    assert readiness.real_orders_enabled is False
    assert readiness.real_money_enabled is False


def test_ready_report_sleeve_admission_review_builds_ready_readiness():
    readiness = _readiness(promotion_target=PaperReplayPromotionTarget.PAPER_SLEEVE_ADMISSION_REVIEW)

    assert readiness.status is PaperReplayPromotionReadinessStatus.READY
    assert readiness.ready is True
    assert readiness.promotion_target == "PAPER_SLEEVE_ADMISSION_REVIEW"


def test_forged_result_report_digest_rejects_before_ready():
    forged = _report(result_report_digest="0" * 64)
    readiness = _readiness(forged)

    assert readiness.status is PaperReplayPromotionReadinessStatus.REJECTED
    assert readiness.ready is False
    assert "paper_replay_promotion_readiness:result_report_digest_mismatch" in readiness.rejection_reasons


def test_tampered_report_field_with_stale_digest_rejects():
    tampered = replace(_report(), operator_id="forged-operator")
    readiness = _readiness(tampered)

    assert readiness.status is PaperReplayPromotionReadinessStatus.REJECTED
    assert "paper_replay_promotion_readiness:result_report_digest_mismatch" in readiness.rejection_reasons


def test_report_statuses_propagate():
    rejected = _with_report_digest(
        replace(
            _report(),
            status=PaperReplayResultReportStatus.REJECTED,
            ready=False,
            rejection_reasons=("paper_replay_result_report:x",),
        )
    )
    assert _readiness(rejected).status is PaperReplayPromotionReadinessStatus.REJECTED

    needs = _with_report_digest(
        replace(
            _report(),
            status=PaperReplayResultReportStatus.NEEDS_RESEARCH,
            ready=False,
            needs_research_reasons=("paper_replay_result_report:y",),
        )
    )
    assert _readiness(needs).status is PaperReplayPromotionReadinessStatus.NEEDS_RESEARCH

    insufficient = _with_report_digest(
        replace(_report(), status=PaperReplayResultReportStatus.INSUFFICIENT_EVIDENCE, ready=False)
    )
    assert _readiness(insufficient).status is PaperReplayPromotionReadinessStatus.INSUFFICIENT_EVIDENCE


def test_ready_report_ready_false_rejects():
    report = _with_report_digest(replace(_report(), ready=False))
    readiness = _readiness(report)

    assert readiness.status is PaperReplayPromotionReadinessStatus.REJECTED
    assert readiness.ready is False
    assert "paper_replay_promotion_readiness:report_ready_mismatch" in readiness.rejection_reasons


@pytest.mark.parametrize("target", ("", "LIVE_EXECUTION", "PAPER_RUNTIME_PROMOTION"))
def test_invalid_or_unknown_promotion_target_rejects(target):
    readiness = _readiness(promotion_target=target)

    assert readiness.status is PaperReplayPromotionReadinessStatus.REJECTED
    assert readiness.ready is False
    assert any(
        reason
        in {
            "paper_replay_promotion_readiness:promotion_target_invalid",
            "paper_replay_promotion_readiness:promotion_target_unknown",
        }
        for reason in readiness.rejection_reasons
    )


@pytest.mark.parametrize(
    "field",
    (
        "bundle_digest",
        "admission_digest",
        "bridge_digest",
        "manifest_digest",
        "intake_digest",
        "run_plan_digest",
        "result_report_digest",
        "replay_trace_digest",
        "metrics_digest",
        "decision_trace_digest",
    ),
)
def test_malformed_chain_and_result_digests_reject(field):
    report = _report(**{field: "bad"})
    if field != "result_report_digest":
        report = _with_report_digest(report)
    readiness = _readiness(report)

    assert readiness.status is PaperReplayPromotionReadinessStatus.REJECTED
    assert f"paper_replay_promotion_readiness:{field}_invalid" in readiness.rejection_reasons


@pytest.mark.parametrize(
    ("kwargs", "report", "reason"),
    (
        ({"readiness_id": ""}, None, "paper_replay_promotion_readiness:readiness_id_invalid"),
        ({"reviewer_id": ""}, None, "paper_replay_promotion_readiness:reviewer_id_invalid"),
        ({"correlation_id": ""}, None, "paper_replay_promotion_readiness:correlation_id_invalid"),
        ({}, _with_report_digest(replace(_report(), result_report_id="")), "result_report_id_invalid"),
        ({}, _with_report_digest(replace(_report(), run_plan_id="")), "run_plan_id_invalid"),
        ({}, _with_report_digest(replace(_report(), requested_replay_id="")), "requested_replay_id_invalid"),
        ({}, _with_report_digest(replace(_report(), operator_id="")), "operator_id_invalid"),
        ({}, _with_report_digest(replace(_report(), replay_source_id="")), "replay_source_id_invalid"),
        (
            {},
            _with_report_digest(replace(_report(), historical_data_source_id="")),
            "historical_data_source_id_invalid",
        ),
    ),
)
def test_malformed_ids_and_source_ids_reject(kwargs, report, reason):
    readiness = _readiness(report=report, **kwargs)

    assert readiness.status is PaperReplayPromotionReadinessStatus.REJECTED
    assert readiness.ready is False
    assert any(reason in rejection for rejection in readiness.rejection_reasons)


@pytest.mark.parametrize(
    ("report", "reason"),
    (
        (
            _with_report_digest(replace(_report(), paper_only=False)),
            "paper_replay_promotion_readiness:report_non_paper",
        ),
        (
            _with_report_digest(replace(_report(), real_orders_enabled=True)),
            "paper_replay_promotion_readiness:report_real_orders_enabled",
        ),
        (
            _with_report_digest(replace(_report(), real_money_enabled=True)),
            "paper_replay_promotion_readiness:report_real_money_enabled",
        ),
    ),
)
def test_unsafe_report_flags_reject_even_with_matching_digest(report, reason):
    readiness = _readiness(report)

    assert readiness.status is PaperReplayPromotionReadinessStatus.REJECTED
    assert readiness.ready is False
    assert reason in readiness.rejection_reasons


@pytest.mark.parametrize(
    ("kwargs", "report"),
    (
        ({"readiness_id": "order"}, None),
        ({"readiness_id": "orders"}, None),
        ({"readiness_id": "real_order"}, None),
        ({"readiness_id": "order-routing"}, None),
        ({"reviewer_id": "desk_order_router"}, None),
        ({"metadata": {"note": "real-orders"}}, None),
        ({}, _with_report_digest(replace(_report(), operator_id="desk-order"))),
        ({"readiness_id": "bist30-review"}, None),
        ({"readiness_id": "live_execution_review"}, None),
        ({"readiness_id": "private_api_review"}, None),
        ({"readiness_id": "scheduler-review"}, None),
    ),
)
def test_forbidden_scope_tokens_reject(kwargs, report):
    readiness = _readiness(report=report, **kwargs)

    assert readiness.status is PaperReplayPromotionReadinessStatus.REJECTED
    assert readiness.ready is False
    assert (
        "paper_replay_promotion_readiness:forbidden_scope_token" in readiness.rejection_reasons
        or "paper_replay_promotion_readiness:bist_scope_leakage" in readiness.rejection_reasons
    )


@pytest.mark.parametrize("value", ("border-study", "orderly-paper-review", "preorder-check"))
def test_unrelated_order_substrings_do_not_reject(value):
    assert _readiness(readiness_id=value).status is PaperReplayPromotionReadinessStatus.READY


def test_metadata_normalized_and_deterministic():
    first = _readiness(metadata={"scope": "crypto_only", "desk": "micro"})
    second = _readiness(metadata={"desk": "micro", "scope": "crypto_only"})

    assert first.metadata == (("desk", "micro"), ("scope", "crypto_only"))
    assert first.readiness_digest == second.readiness_digest
    assert paper_replay_promotion_readiness_to_dict(first) == paper_replay_promotion_readiness_to_dict(second)
    assert paper_replay_promotion_readiness_to_dict(first)["readiness_digest"] == first.readiness_digest


def test_material_input_change_changes_digest():
    base = _readiness()

    assert _readiness(readiness_id="promotion-readiness-002").readiness_digest != base.readiness_digest
    assert _readiness(reviewer_id="governance-reviewer-2").readiness_digest != base.readiness_digest
    assert _readiness(report=_report(metrics_digest="6" * 64)).readiness_digest != base.readiness_digest


def test_wrong_type_and_bad_metadata_raise():
    with pytest.raises(PaperReplayPromotionReadinessError):
        build_paper_replay_promotion_readiness(
            {"status": "READY"},  # type: ignore[arg-type]
            readiness_id=_READINESS_ID,
            promotion_target=PaperReplayPromotionTarget.PAPER_CANDIDATE_REVIEW,
            reviewer_id=_REVIEWER,
            correlation_id=_CORR,
        )
    with pytest.raises(PaperReplayPromotionReadinessError):
        _readiness(metadata={"k": 5})
    with pytest.raises(PaperReplayPromotionReadinessError):
        _readiness(metadata={5: "v"})


def test_immutable_and_no_forbidden_fields():
    readiness = _readiness()
    with pytest.raises(FrozenInstanceError):
        readiness.status = PaperReplayPromotionReadinessStatus.REJECTED  # type: ignore[misc]
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
    assert {field.name for field in fields(readiness)}.isdisjoint(forbidden)
    payload = paper_replay_promotion_readiness_to_dict(readiness)
    assert payload["schema_version"] == "paper-replay-promotion-readiness.v1"
    assert set(payload).isdisjoint(forbidden)
