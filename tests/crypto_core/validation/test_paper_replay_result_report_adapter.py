"""Tests for the deterministic-replay-output -> PaperReplayResultReport producer adapter."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from crypto_core.validation.deterministic_replay_executor import (
    DeterministicReplayInput,
    DeterministicReplayStatus,
    build_deterministic_replay_input,
    deterministic_replay_output_digest,
    execute_deterministic_replay,
)
from crypto_core.validation.paper_replay_result_report import (
    PaperReplayResultReport,
    PaperReplayResultReportStatus,
)
from crypto_core.validation.paper_replay_result_report_adapter import (
    PaperReplayResultReportAdapterError,
    build_paper_replay_result_report_from_deterministic_replay,
)
from crypto_core.validation.paper_replay_run_plan import (
    PaperReplayRunPlan,
    PaperReplayRunPlanStatus,
    paper_replay_run_plan_to_dict,
)

_CORR = "corr:replay-result-report-adapter-001"
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
        "bundle_digest": "f" * 64,
        "admission_digest": "1" * 64,
        "bridge_digest": "e" * 64,
        "manifest_digest": "2" * 64,
        "intake_digest": "9" * 64,
        "intake_status": "READY",
        "replay_source_id": "offline-replay-v1",
        "historical_data_source_id": "historical-perp-journal-v1",
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


def _events() -> list[dict[str, object]]:
    return [
        {"event_type": "mark_price", "symbol": "BTC-PERP", "mark_price": "100.5", "sequence": 1},
        {"event_type": "mark_price", "symbol": "BTC-PERP", "mark_price": "101.0", "sequence": 2},
    ]


def _input(events=None, run_plan=None, correlation_id=_CORR) -> DeterministicReplayInput:
    run_plan = _run_plan() if run_plan is None else run_plan
    events = _events() if events is None else events
    return build_deterministic_replay_input(run_plan, events=events, correlation_id=correlation_id)


def _pair(events=None, run_plan=None):
    inp = _input(events=events, run_plan=run_plan)
    return inp, execute_deterministic_replay(inp)


def _build(inp, out, **overrides):
    kwargs = {"report_id": _REPORT_ID, "correlation_id": _CORR}
    kwargs.update(overrides)
    return build_paper_replay_result_report_from_deterministic_replay(inp, out, **kwargs)


def _reseal(out):
    """Recompute output_digest so a forged output is internally self-consistent (re-proves)."""
    return replace(out, output_digest=deterministic_replay_output_digest(out))


# 1. accepted output builds a real PaperReplayResultReport carrying the output's computed digests


def test_accepted_output_builds_result_report_with_output_digests():
    inp, out = _pair()
    assert out.status is DeterministicReplayStatus.ACCEPTED
    report = _build(inp, out)
    assert isinstance(report, PaperReplayResultReport)
    assert report.status is PaperReplayResultReportStatus.READY
    assert report.outcome_status == "COMPLETED"
    assert report.result_report_id == _REPORT_ID
    assert report.replay_trace_digest == out.replay_trace_digest
    assert report.metrics_digest == out.metrics_digest
    assert report.decision_trace_digest == out.decision_trace_digest
    assert report.paper_only is True
    assert report.real_orders_enabled is False
    assert report.real_money_enabled is False


# 2. report digest deterministic across repeated builds


def test_report_digest_deterministic_across_builds():
    inp, out = _pair()
    first = _build(inp, out)
    second = _build(inp, out)
    assert first.result_report_digest == second.result_report_digest


# 3. replay_output.input_digest mismatch fails closed


def test_output_input_digest_mismatch_fails_closed():
    inp, out = _pair()
    with pytest.raises(PaperReplayResultReportAdapterError):
        _build(inp, replace(out, input_digest="0" * 64))


def test_input_self_digest_mismatch_fails_closed():
    inp, out = _pair()
    with pytest.raises(PaperReplayResultReportAdapterError) as exc:
        _build(replace(inp, input_digest="0" * 64), out)
    assert "replay_input_digest_mismatch" in str(exc.value)


# 4. tampered replay_output.output_digest fails closed


def test_output_digest_tamper_fails_closed():
    inp, out = _pair()
    with pytest.raises(PaperReplayResultReportAdapterError) as exc:
        _build(inp, replace(out, output_digest="0" * 64))
    assert "output_digest_mismatch" in str(exc.value)


# 5. wrong replay_output / replay_input schema_version fails closed


def test_wrong_output_schema_version_fails_closed():
    inp, out = _pair()
    with pytest.raises(PaperReplayResultReportAdapterError) as exc:
        _build(inp, replace(out, schema_version="evil"))
    assert "replay_output_schema_version_unexpected" in str(exc.value)


def test_wrong_input_schema_version_fails_closed():
    inp, out = _pair()
    with pytest.raises(PaperReplayResultReportAdapterError) as exc:
        _build(replace(inp, schema_version="evil"), out)
    assert "replay_input_schema_version_unexpected" in str(exc.value)


# 6. rejected deterministic replay output maps fail-closed to a REJECTED report


def test_rejected_output_maps_to_rejected_report():
    inp, out = _pair(events=[])  # empty sequence -> REJECTED per executor contract
    assert out.status is DeterministicReplayStatus.REJECTED
    report = _build(inp, out)
    assert report.status is PaperReplayResultReportStatus.REJECTED
    assert report.outcome_status == "REJECTED"
    # the executor's computed digests are still faithfully recorded
    assert report.replay_trace_digest == out.replay_trace_digest
    assert report.metrics_digest == out.metrics_digest
    assert report.decision_trace_digest == out.decision_trace_digest


# 7. caller cannot override trace/metrics/decision digests


def test_caller_cannot_override_digests():
    inp, out = _pair()
    report = _build(inp, out)
    assert report.replay_trace_digest == out.replay_trace_digest
    assert report.metrics_digest == out.metrics_digest
    assert report.decision_trace_digest == out.decision_trace_digest
    with pytest.raises(TypeError):
        build_paper_replay_result_report_from_deterministic_replay(
            inp,
            out,
            report_id=_REPORT_ID,
            correlation_id=_CORR,
            replay_trace_digest="a" * 64,  # type: ignore[call-arg]
        )


# 8. malformed input/output type raises adapter Error, no raw leak


def test_malformed_call_inputs_raise_adapter_error():
    inp, out = _pair()
    with pytest.raises(PaperReplayResultReportAdapterError):
        build_paper_replay_result_report_from_deterministic_replay(
            {"not": "input"},  # type: ignore[arg-type]
            out,
            report_id=_REPORT_ID,
            correlation_id=_CORR,
        )
    with pytest.raises(PaperReplayResultReportAdapterError):
        build_paper_replay_result_report_from_deterministic_replay(
            inp,
            "not-output",  # type: ignore[arg-type]
            report_id=_REPORT_ID,
            correlation_id=_CORR,
        )
    with pytest.raises(PaperReplayResultReportAdapterError):
        _build(inp, out, report_id="")
    with pytest.raises(PaperReplayResultReportAdapterError):
        _build(inp, out, correlation_id="")


def test_malformed_executor_artifact_raises_adapter_error_not_raw():
    out = _pair()[1]
    bad_input = DeterministicReplayInput(
        schema_version="deterministic-replay-executor.v1",
        run_plan=_run_plan(),
        events=("not-json",),
        correlation_id=_CORR,
        input_digest="0" * 64,
    )
    with pytest.raises(PaperReplayResultReportAdapterError) as exc:
        _build(bad_input, out)
    assert "replay_evidence_malformed" in str(exc.value)


def test_malformed_input_run_plan_raises_adapter_error_not_raw():
    out = _pair()[1]
    bad_input = DeterministicReplayInput(
        schema_version="deterministic-replay-executor.v1",
        run_plan=None,  # type: ignore[arg-type]
        events=(),
        correlation_id=_CORR,
        input_digest="0" * 64,
    )
    with pytest.raises(PaperReplayResultReportAdapterError) as exc:
        _build(bad_input, out)
    assert "replay_evidence_malformed" in str(exc.value)


def test_malformed_output_internals_raise_adapter_error_not_raw():
    inp, out = _pair()
    broken = replace(out, trace_entries=("not-a-trace-entry",))  # type: ignore[arg-type]
    with pytest.raises(PaperReplayResultReportAdapterError) as exc:
        _build(inp, broken)
    assert "replay_evidence_malformed" in str(exc.value)


# context binding: a self-consistent forged output must match the input's run-plan/replay context


def test_output_run_plan_digest_mismatch_fails_closed():
    # self-consistent forged output (output_digest re-proves) must still be rejected on context binding
    inp, out = _pair()
    forged = _reseal(replace(out, run_plan_digest="a" * 64))
    with pytest.raises(PaperReplayResultReportAdapterError) as exc:
        _build(inp, forged)
    assert "run_plan_digest_mismatch" in str(exc.value)


def test_output_replay_mode_mismatch_fails_closed():
    inp, out = _pair()
    forged = _reseal(replace(out, replay_mode="deterministic_replay_dry_run"))
    with pytest.raises(PaperReplayResultReportAdapterError) as exc:
        _build(inp, forged)
    assert "replay_mode_mismatch" in str(exc.value)


def test_output_requested_replay_id_mismatch_fails_closed():
    inp, out = _pair()
    forged = _reseal(replace(out, requested_replay_id="other-replay"))
    with pytest.raises(PaperReplayResultReportAdapterError) as exc:
        _build(inp, forged)
    assert "requested_replay_id_mismatch" in str(exc.value)


def test_output_correlation_id_mismatch_fails_closed():
    inp, out = _pair()
    forged = _reseal(replace(out, correlation_id="corr:other"))
    with pytest.raises(PaperReplayResultReportAdapterError) as exc:
        _build(inp, forged)
    assert "correlation_id_mismatch" in str(exc.value)


# 9. forbidden live/order/scheduler/connector/BIST tokens in correlation/metadata are rejected


@pytest.mark.parametrize(
    ("kwargs", "reason_token"),
    (
        ({"correlation_id": "live_execution_loop"}, "forbidden_scope_token"),
        ({"report_id": "order-routing-report"}, "forbidden_scope_token"),
        ({"metadata": {"note": "scheduler_loop"}}, "forbidden_scope_token"),
        ({"metadata": {"venue": "bist30"}}, "bist_scope_leakage"),
    ),
)
def test_forbidden_tokens_rejected_via_report(kwargs, reason_token):
    inp, out = _pair()
    report = _build(inp, out, **kwargs)
    assert report.status is PaperReplayResultReportStatus.REJECTED
    assert any(reason_token in reason for reason in report.rejection_reasons)


# 10. module purity: no os/pathlib/time/datetime/random/threading/network/service/connector/runtime imports


def test_module_purity_no_impure_imports():
    import crypto_core.validation.paper_replay_result_report_adapter as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level: set[str] = set()
    crypto_submodules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module.split(".")[0])
            parts = node.module.split(".")
            if parts[0] == "crypto_core" and len(parts) > 1:
                crypto_submodules.add(parts[1])
    impure = {
        "os",
        "sys",
        "io",
        "pathlib",
        "time",
        "datetime",
        "threading",
        "asyncio",
        "multiprocessing",
        "socket",
        "subprocess",
        "random",
        "secrets",
        "uuid",
        "requests",
        "http",
        "urllib",
        "sqlite3",
    }
    assert top_level.isdisjoint(impure)
    assert crypto_submodules.isdisjoint({"service", "connector", "runtime", "venue", "execution", "orchestrator"})
