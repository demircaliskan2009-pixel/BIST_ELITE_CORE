"""Tests for the deterministic replay executor (pure paper-only replay over a READY run plan)."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from crypto_core.validation.deterministic_replay_executor import (
    DeterministicReplayEventDecision,
    DeterministicReplayExecutor,
    DeterministicReplayExecutorError,
    DeterministicReplayInput,
    DeterministicReplayStatus,
    build_deterministic_replay_input,
    deterministic_replay_input_digest,
    deterministic_replay_input_to_dict,
    deterministic_replay_output_digest,
    deterministic_replay_output_to_dict,
    execute_deterministic_replay,
)
from crypto_core.validation.paper_replay_run_plan import (
    PaperReplayRunPlan,
    PaperReplayRunPlanStatus,
    paper_replay_run_plan_to_dict,
)

_BUNDLE = "f" * 64
_ADMISSION = "1" * 64
_BRIDGE = "e" * 64
_MANIFEST = "2" * 64
_INTAKE = "9" * 64
_CORR = "corr:deterministic-replay-001"


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


def _input(events=None, correlation_id=_CORR, run_plan=None) -> DeterministicReplayInput:
    run_plan = _run_plan() if run_plan is None else run_plan
    events = _events() if events is None else events
    return build_deterministic_replay_input(run_plan, events=events, correlation_id=correlation_id)


# 1. identical input -> identical output digest


def test_identical_input_identical_output_digest():
    out1 = execute_deterministic_replay(_input())
    out2 = execute_deterministic_replay(_input())
    assert out1.status is DeterministicReplayStatus.ACCEPTED
    assert out1.accepted is True
    assert out1.input_digest == out2.input_digest
    assert out1.output_digest == out2.output_digest
    assert out1.replay_trace_digest == out2.replay_trace_digest
    assert out1.metrics_digest == out2.metrics_digest
    assert out1.decision_trace_digest == out2.decision_trace_digest


def test_executor_class_matches_function():
    inp = _input()
    assert DeterministicReplayExecutor().execute(inp).output_digest == execute_deterministic_replay(inp).output_digest


# 2. changed input changes input/output digest


def test_changed_event_changes_input_and_output_digest():
    base = execute_deterministic_replay(_input())
    changed = execute_deterministic_replay(
        _input(events=[{"event_type": "mark_price", "symbol": "BTC-PERP", "mark_price": "200.0", "sequence": 1}])
    )
    assert changed.input_digest != base.input_digest
    assert changed.output_digest != base.output_digest
    assert changed.replay_trace_digest != base.replay_trace_digest


# 3. malformed input fails closed (raises)


def test_malformed_inputs_raise():
    with pytest.raises(DeterministicReplayExecutorError):
        build_deterministic_replay_input(_run_plan(), events=[123], correlation_id=_CORR)
    with pytest.raises(DeterministicReplayExecutorError):
        build_deterministic_replay_input(_run_plan(), events="not-a-list", correlation_id=_CORR)
    with pytest.raises(DeterministicReplayExecutorError):
        build_deterministic_replay_input({"status": "READY"}, events=_events(), correlation_id=_CORR)
    with pytest.raises(DeterministicReplayExecutorError):
        build_deterministic_replay_input(_run_plan(), events=_events(), correlation_id="")
    with pytest.raises(DeterministicReplayExecutorError):
        execute_deterministic_replay({"not": "an-input"})


# 4. noncanonical / NaN / non-JSON-serializable values rejected


def test_non_canonical_event_values_raise():
    with pytest.raises(DeterministicReplayExecutorError):
        build_deterministic_replay_input(_run_plan(), events=[{"x": float("nan")}], correlation_id=_CORR)
    with pytest.raises(DeterministicReplayExecutorError):
        build_deterministic_replay_input(_run_plan(), events=[{"x": float("inf")}], correlation_id=_CORR)
    with pytest.raises(DeterministicReplayExecutorError):
        build_deterministic_replay_input(_run_plan(), events=[{"x": object()}], correlation_id=_CORR)
    with pytest.raises(DeterministicReplayExecutorError):
        build_deterministic_replay_input(_run_plan(), events=[{1: "v"}], correlation_id=_CORR)


# 5. no wall-clock fields accepted


@pytest.mark.parametrize("key", ("timestamp", "created_at", "event_timestamp", "wall_clock", "now", "time_ns"))
def test_wall_clock_event_fields_rejected(key):
    out = execute_deterministic_replay(_input(events=[{key: "x", "symbol": "BTC-PERP"}]))
    assert out.status is DeterministicReplayStatus.REJECTED
    assert out.accepted is False
    assert "deterministic_replay_executor:wall_clock_field" in out.rejection_reasons
    assert out.rejected_event_count == 1


# 6. no live/private/order/scheduler/connector/shadow/BIST tokens accepted


@pytest.mark.parametrize(
    "event",
    (
        {"feed": "live_exchange"},
        {"side": "order"},
        {"side": "orders"},
        {"note": "order_router"},
        {"mode": "shadow_replay"},
        {"channel": "connector_ready"},
        {"stream": "private_feed"},
        {"component": "scheduler_loop"},
        {"market": "bist30"},
    ),
)
def test_forbidden_or_bist_event_tokens_rejected(event):
    out = execute_deterministic_replay(_input(events=[event]))
    assert out.status is DeterministicReplayStatus.REJECTED
    assert out.accepted is False
    assert out.rejected_event_count == 1


def test_specific_scope_reasons_surface():
    bist = execute_deterministic_replay(_input(events=[{"market": "bist30"}]))
    assert "deterministic_replay_executor:bist_scope_leakage" in bist.rejection_reasons
    order = execute_deterministic_replay(_input(events=[{"side": "order"}]))
    assert "deterministic_replay_executor:forbidden_scope_token" in order.rejection_reasons


@pytest.mark.parametrize("value", ("border-study", "orderly-tick", "preorder-check", "delivery-window"))
def test_unrelated_substrings_do_not_reject(value):
    out = execute_deterministic_replay(_input(events=[{"label": value, "symbol": "BTC-PERP"}]))
    assert out.status is DeterministicReplayStatus.ACCEPTED


# 7. trace_digest and metrics_digest are stable


def test_trace_and_metrics_digests_stable_and_counted():
    out1 = execute_deterministic_replay(_input())
    out2 = execute_deterministic_replay(_input())
    assert out1.replay_trace_digest == out2.replay_trace_digest
    assert out1.metrics_digest == out2.metrics_digest
    assert out1.decision_trace_digest == out2.decision_trace_digest
    assert out1.event_count == 2
    assert out1.accepted_event_count == 2
    assert out1.rejected_event_count == 0
    assert len(out1.replay_trace_digest) == 64
    assert len(out1.metrics_digest) == 64
    assert len(out1.decision_trace_digest) == 64


# 8. zero-event replay is deterministic and rejected per the explicit contract


def test_zero_event_replay_rejected_deterministically():
    out1 = execute_deterministic_replay(_input(events=[]))
    out2 = execute_deterministic_replay(_input(events=[]))
    assert out1.status is DeterministicReplayStatus.REJECTED
    assert out1.accepted is False
    assert out1.event_count == 0
    assert "deterministic_replay_executor:empty_event_sequence" in out1.rejection_reasons
    assert out1.output_digest == out2.output_digest


# 9. output is frozen/immutable


def test_output_and_input_are_frozen():
    out = execute_deterministic_replay(_input())
    with pytest.raises(FrozenInstanceError):
        out.status = DeterministicReplayStatus.REJECTED  # type: ignore[misc]
    inp = _input()
    with pytest.raises(FrozenInstanceError):
        inp.input_digest = "x"  # type: ignore[misc]


def test_no_forbidden_fields_and_paper_flags():
    out = execute_deterministic_replay(_input())
    forbidden = {"order", "route", "venue", "exchange", "scheduler", "live", "runtime", "broker", "connector"}
    assert {field.name for field in fields(out)}.isdisjoint(forbidden)
    assert out.paper_only is True
    assert out.real_orders_enabled is False
    assert out.real_money_enabled is False
    payload = deterministic_replay_output_to_dict(out)
    assert payload["schema_version"] == "deterministic-replay-executor.v1"
    assert set(payload).isdisjoint(forbidden)
    assert payload["output_digest"] == out.output_digest
    assert deterministic_replay_output_digest(out) == out.output_digest


# 10. module purity: no os/pathlib/time/threading/network/env/service/connector imports


def test_module_purity_no_impure_imports():
    import crypto_core.validation.deterministic_replay_executor as mod

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
        "requests",
        "http",
        "urllib",
        "sqlite3",
    }
    assert top_level.isdisjoint(impure)
    assert crypto_submodules.isdisjoint({"service", "connector", "runtime", "venue", "execution"})


# boundary digest re-proof + readiness/paper-safety


def test_forged_run_plan_digest_rejects():
    forged = _run_plan(run_plan_digest="0" * 64)
    out = execute_deterministic_replay(_input(run_plan=forged))
    assert out.status is DeterministicReplayStatus.REJECTED
    assert "deterministic_replay_executor:run_plan_digest_mismatch" in out.rejection_reasons


def test_tampered_run_plan_field_rejects():
    tampered = replace(_run_plan(), operator_id="forged-operator")  # keeps stale run_plan_digest
    out = execute_deterministic_replay(_input(run_plan=tampered))
    assert out.status is DeterministicReplayStatus.REJECTED
    assert "deterministic_replay_executor:run_plan_digest_mismatch" in out.rejection_reasons


def test_tampered_input_digest_rejects():
    tampered = replace(_input(), input_digest="0" * 64)
    out = execute_deterministic_replay(tampered)
    assert out.status is DeterministicReplayStatus.REJECTED
    assert "deterministic_replay_executor:input_digest_mismatch" in out.rejection_reasons


def test_non_ready_run_plan_rejects():
    rejected = _run_plan(status=PaperReplayRunPlanStatus.REJECTED, ready=False)
    out = execute_deterministic_replay(_input(run_plan=rejected))
    assert out.status is DeterministicReplayStatus.REJECTED
    assert "deterministic_replay_executor:run_plan_not_ready" in out.rejection_reasons


@pytest.mark.parametrize(
    ("override", "reason"),
    (
        ({"real_orders_enabled": True}, "deterministic_replay_executor:run_plan_real_orders_enabled"),
        ({"real_money_enabled": True}, "deterministic_replay_executor:run_plan_real_money_enabled"),
        ({"paper_only": False}, "deterministic_replay_executor:run_plan_non_paper"),
    ),
)
def test_unsafe_run_plan_flags_reject(override, reason):
    out = execute_deterministic_replay(_input(run_plan=_run_plan(**override)))
    assert out.status is DeterministicReplayStatus.REJECTED
    assert reason in out.rejection_reasons


def test_unknown_replay_mode_rejects():
    out = execute_deterministic_replay(_input(run_plan=_run_plan(replay_mode="fast_replay")))
    assert out.status is DeterministicReplayStatus.REJECTED
    assert "deterministic_replay_executor:replay_mode_unknown" in out.rejection_reasons


def test_forbidden_correlation_id_rejects():
    out = execute_deterministic_replay(_input(correlation_id="live_execution_loop"))
    assert out.status is DeterministicReplayStatus.REJECTED
    assert "deterministic_replay_executor:forbidden_scope_token" in out.rejection_reasons


# mixed events: deterministic counts + ordered trace


def test_mixed_events_counts_and_trace_order():
    out = execute_deterministic_replay(
        _input(
            events=[
                {"event_type": "mark_price", "symbol": "BTC-PERP", "mark_price": "100.0"},
                {"side": "order"},
            ]
        )
    )
    assert out.status is DeterministicReplayStatus.REJECTED
    assert out.event_count == 2
    assert out.accepted_event_count == 1
    assert out.rejected_event_count == 1
    assert out.trace_entries[0].sequence_id == 0
    assert out.trace_entries[0].decision is DeterministicReplayEventDecision.ACCEPT
    assert out.trace_entries[1].sequence_id == 1
    assert out.trace_entries[1].decision is DeterministicReplayEventDecision.REJECT
    assert "deterministic_replay_executor:forbidden_scope_token" in out.trace_entries[1].rejection_reasons


# input serializer round-trip digest


def test_input_to_dict_digest_matches():
    inp = _input()
    assert deterministic_replay_input_digest(inp) == inp.input_digest
    payload = deterministic_replay_input_to_dict(inp)
    assert payload["input_digest"] == inp.input_digest
    assert payload["schema_version"] == "deterministic-replay-executor.v1"
    assert isinstance(payload["events"], list)
    assert payload["events"][0]["symbol"] == "BTC-PERP"


def test_output_digests_compose_with_result_report_shape():
    # The three digests the executor computes are exactly what PaperReplayResultReport records.
    out = execute_deterministic_replay(_input())
    for digest in (out.replay_trace_digest, out.metrics_digest, out.decision_trace_digest):
        assert len(digest) == 64
        assert all(char in "0123456789abcdef" for char in digest)
