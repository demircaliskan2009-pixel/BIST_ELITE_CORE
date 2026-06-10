"""Tests for the paper replay result report (paper-only record of an offline replay outcome)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from crypto_core.validation.paper_replay_result_report import (
    PaperReplayOutcomeStatus,
    PaperReplayResultReport,
    PaperReplayResultReportError,
    PaperReplayResultReportStatus,
    build_paper_replay_result_report,
    paper_replay_result_report_to_dict,
)
from crypto_core.validation.paper_replay_run_plan import (
    PaperReplayRunPlan,
    PaperReplayRunPlanStatus,
    paper_replay_run_plan_to_dict,
)

_SOURCE = "offline-replay-v1"
_HIST = "historical-perp-journal-v1"
_BUNDLE = "f" * 64
_ADMISSION = "1" * 64
_BRIDGE = "e" * 64
_MANIFEST = "2" * 64
_INTAKE = "9" * 64
_TRACE = "3" * 64
_METRICS = "4" * 64
_DECISION = "5" * 64
_CORR = "corr:paper-replay-result-report-001"
_REPORT_ID = "result-report-001"


def _run_plan(**overrides) -> PaperReplayRunPlan:
    base = {
        "schema_version": "paper-replay-run-plan.v1",
        "status": PaperReplayRunPlanStatus.READY,
        "ready": True,
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
        "intake_status": "READY",
        "replay_source_id": _SOURCE,
        "historical_data_source_id": _HIST,
        "metadata": (),
        "rejection_reasons": (),
        "needs_research_reasons": (),
        "correlation_id": "corr:run-plan-001",
        "run_plan_digest": "0" * 64,
    }
    base.update(overrides)
    run_plan = PaperReplayRunPlan(**base)
    if "run_plan_digest" in overrides:
        return run_plan
    payload = paper_replay_run_plan_to_dict(run_plan)
    payload.pop("run_plan_digest", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return replace(run_plan, run_plan_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _report(run_plan=None, **overrides):
    run_plan = _run_plan() if run_plan is None else run_plan
    kwargs = {
        "result_report_id": _REPORT_ID,
        "outcome_status": PaperReplayOutcomeStatus.COMPLETED,
        "replay_trace_digest": _TRACE,
        "metrics_digest": _METRICS,
        "decision_trace_digest": _DECISION,
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return build_paper_replay_result_report(run_plan, **kwargs)


def test_ready_run_plan_completed_outcome_builds_ready_report():
    report = _report()
    assert isinstance(report, PaperReplayResultReport)
    assert report.status is PaperReplayResultReportStatus.READY
    assert report.ready is True
    assert report.result_report_id == _REPORT_ID
    assert report.outcome_status == "COMPLETED"
    assert report.run_plan_status == "READY"
    assert report.replay_trace_digest == _TRACE
    assert report.metrics_digest == _METRICS
    assert report.decision_trace_digest == _DECISION
    assert report.rejection_reasons == ()
    assert len(report.result_report_digest) == 64
    assert report.paper_only is True
    assert report.real_orders_enabled is False
    assert report.real_money_enabled is False


def test_string_outcome_status_accepted():
    assert _report(outcome_status="COMPLETED").status is PaperReplayResultReportStatus.READY


def test_forged_run_plan_digest_rejects_before_ready():
    forged = _run_plan(run_plan_digest="0" * 64)
    report = _report(forged)
    assert report.status is PaperReplayResultReportStatus.REJECTED
    assert report.ready is False
    assert "paper_replay_result_report:run_plan_digest_mismatch" in report.rejection_reasons


def test_tampered_run_plan_field_rejects():
    tampered = replace(_run_plan(), operator_id="forged-operator")  # keeps stale run_plan_digest
    report = _report(tampered)
    assert report.status is PaperReplayResultReportStatus.REJECTED
    assert "paper_replay_result_report:run_plan_digest_mismatch" in report.rejection_reasons


@pytest.mark.parametrize(
    ("run_plan", "reason"),
    (
        (_run_plan(run_plan_id=""), "paper_replay_result_report:run_plan_id_invalid"),
        (_run_plan(replay_mode=""), "paper_replay_result_report:run_plan_replay_mode_invalid"),
        (_run_plan(replay_mode="fast_replay"), "paper_replay_result_report:run_plan_replay_mode_unknown"),
        (_run_plan(requested_replay_id=""), "paper_replay_result_report:requested_replay_id_invalid"),
        (_run_plan(operator_id=""), "paper_replay_result_report:operator_id_invalid"),
        (_run_plan(replay_source_id=""), "paper_replay_result_report:replay_source_id_invalid"),
        (
            _run_plan(historical_data_source_id=""),
            "paper_replay_result_report:historical_data_source_id_invalid",
        ),
    ),
)
def test_malformed_matching_digest_run_plan_identities_reject(run_plan, reason):
    report = _report(run_plan)

    assert report.status is PaperReplayResultReportStatus.REJECTED
    assert report.ready is False
    assert reason in report.rejection_reasons


def test_non_ready_run_plan_statuses_propagate():
    rejected = _run_plan(
        status=PaperReplayRunPlanStatus.REJECTED, ready=False, rejection_reasons=("paper_replay_run_plan:x",)
    )
    assert _report(rejected).status is PaperReplayResultReportStatus.REJECTED

    needs = _run_plan(
        status=PaperReplayRunPlanStatus.NEEDS_RESEARCH, ready=False, needs_research_reasons=("paper_replay_run_plan:y",)
    )
    assert _report(needs).status is PaperReplayResultReportStatus.NEEDS_RESEARCH

    insufficient = _run_plan(status=PaperReplayRunPlanStatus.INSUFFICIENT_EVIDENCE, ready=False)
    assert _report(insufficient).status is PaperReplayResultReportStatus.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize(
    ("outcome", "expected"),
    (
        (PaperReplayOutcomeStatus.REJECTED, PaperReplayResultReportStatus.REJECTED),
        (PaperReplayOutcomeStatus.NEEDS_RESEARCH, PaperReplayResultReportStatus.NEEDS_RESEARCH),
        (PaperReplayOutcomeStatus.INSUFFICIENT_EVIDENCE, PaperReplayResultReportStatus.INSUFFICIENT_EVIDENCE),
    ),
)
def test_outcome_status_maps(outcome, expected):
    assert _report(outcome_status=outcome).status is expected


def test_unknown_outcome_status_rejects():
    report = _report(outcome_status="DONE")
    assert report.status is PaperReplayResultReportStatus.REJECTED
    assert "paper_replay_result_report:outcome_status_unknown" in report.rejection_reasons


def test_invalid_chain_and_result_digests_reject():
    assert _report(_run_plan(bundle_digest="bad")).status is PaperReplayResultReportStatus.REJECTED
    assert _report(_run_plan(admission_digest="bad")).status is PaperReplayResultReportStatus.REJECTED
    assert _report(_run_plan(bridge_digest="bad")).status is PaperReplayResultReportStatus.REJECTED
    assert _report(_run_plan(manifest_digest="bad")).status is PaperReplayResultReportStatus.REJECTED
    assert _report(_run_plan(intake_digest="bad")).status is PaperReplayResultReportStatus.REJECTED
    for field in ("replay_trace_digest", "metrics_digest", "decision_trace_digest"):
        report = _report(**{field: "bad"})
        assert report.status is PaperReplayResultReportStatus.REJECTED
        assert f"paper_replay_result_report:{field}_invalid" in report.rejection_reasons


@pytest.mark.parametrize(
    ("run_plan", "reason"),
    (
        (_run_plan(paper_only=False), "paper_replay_result_report:run_plan_non_paper"),
        (_run_plan(real_orders_enabled=True), "paper_replay_result_report:run_plan_real_orders_enabled"),
        (_run_plan(real_money_enabled=True), "paper_replay_result_report:run_plan_real_money_enabled"),
    ),
)
def test_unsafe_run_plan_flags_reject_even_with_matching_digest(run_plan, reason):
    report = _report(run_plan)
    assert report.status is PaperReplayResultReportStatus.REJECTED
    assert report.ready is False
    assert reason in report.rejection_reasons


def test_malformed_or_forbidden_identity_rejects():
    assert _report(result_report_id="").status is PaperReplayResultReportStatus.REJECTED

    forbidden = _report(result_report_id="live_execution_report")
    assert forbidden.status is PaperReplayResultReportStatus.REJECTED
    assert "paper_replay_result_report:forbidden_scope_token" in forbidden.rejection_reasons

    bist = _report(result_report_id="bist30-report")
    assert bist.status is PaperReplayResultReportStatus.REJECTED
    assert "paper_replay_result_report:bist_scope_leakage" in bist.rejection_reasons

    bad_source = _report(_run_plan(replay_source_id="scheduler_loop"))
    assert bad_source.status is PaperReplayResultReportStatus.REJECTED
    assert "paper_replay_result_report:forbidden_scope_token" in bad_source.rejection_reasons


@pytest.mark.parametrize(
    ("kwargs", "run_plan"),
    (
        ({"result_report_id": "order"}, None),
        ({"result_report_id": "orders"}, None),
        ({"result_report_id": "real_order"}, None),
        ({"result_report_id": "order-routing"}, None),
        ({"metadata": {"note": "desk_order_router"}}, None),
        ({"metadata": {"note": "real-orders"}}, None),
        ({}, _run_plan(operator_id="desk-order")),
    ),
)
def test_plain_order_scope_tokens_reject(kwargs, run_plan):
    report = _report(run_plan=run_plan, **kwargs)
    assert report.status is PaperReplayResultReportStatus.REJECTED
    assert report.ready is False
    assert "paper_replay_result_report:forbidden_scope_token" in report.rejection_reasons


@pytest.mark.parametrize("value", ("border-study", "orderly-paper-review", "preorder-check"))
def test_unrelated_order_substrings_do_not_reject(value):
    assert _report(result_report_id=value).status is PaperReplayResultReportStatus.READY


def test_wrong_type_and_bad_metadata_raise():
    with pytest.raises(PaperReplayResultReportError):
        build_paper_replay_result_report(
            {"status": "READY"},  # type: ignore[arg-type]
            result_report_id=_REPORT_ID,
            outcome_status=PaperReplayOutcomeStatus.COMPLETED,
            replay_trace_digest=_TRACE,
            metrics_digest=_METRICS,
            decision_trace_digest=_DECISION,
            correlation_id=_CORR,
        )
    with pytest.raises(PaperReplayResultReportError):
        _report(correlation_id="")
    with pytest.raises(PaperReplayResultReportError):
        _report(metadata={"k": 5})
    with pytest.raises(PaperReplayResultReportError):
        _report(metadata={5: "v"})


def test_metadata_normalized_and_deterministic():
    first = _report(metadata={"scope": "crypto_only", "desk": "micro"})
    second = _report(metadata={"desk": "micro", "scope": "crypto_only"})
    assert first.metadata == (("desk", "micro"), ("scope", "crypto_only"))
    assert first.result_report_digest == second.result_report_digest
    assert paper_replay_result_report_to_dict(first) == paper_replay_result_report_to_dict(second)
    assert paper_replay_result_report_to_dict(first)["result_report_digest"] == first.result_report_digest


def test_material_change_changes_digest():
    base = _report()
    assert _report(result_report_id="result-report-002").result_report_digest != base.result_report_digest
    assert _report(metrics_digest="6" * 64).result_report_digest != base.result_report_digest


def test_immutable_and_no_forbidden_fields():
    report = _report()
    with pytest.raises(FrozenInstanceError):
        report.status = PaperReplayResultReportStatus.REJECTED  # type: ignore[misc]
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
    assert {field.name for field in fields(report)}.isdisjoint(forbidden)
    payload = paper_replay_result_report_to_dict(report)
    assert payload["schema_version"] == "paper-replay-result-report.v1"
    assert set(payload).isdisjoint(forbidden)
