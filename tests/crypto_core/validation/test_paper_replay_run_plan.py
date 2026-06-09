"""Tests for the paper replay run plan gate (paper-only consumer of a READY intake)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from crypto_core.validation.paper_replay_intake import (
    PaperReplayIntake,
    PaperReplayIntakeStatus,
    paper_replay_intake_to_dict,
)
from crypto_core.validation.paper_replay_run_plan import (
    PaperReplayRunPlan,
    PaperReplayRunPlanError,
    PaperReplayRunPlanStatus,
    build_paper_replay_run_plan,
    paper_replay_run_plan_to_dict,
)

_SOURCE = "offline-replay-v1"
_HIST = "historical-perp-journal-v1"
_BUNDLE = "f" * 64
_ADMISSION = "1" * 64
_BRIDGE = "e" * 64
_MANIFEST = "2" * 64
_CORR = "corr:paper-replay-run-plan-001"
_RUN_PLAN_ID = "run-plan-001"


def _intake(**overrides) -> PaperReplayIntake:
    base = {
        "schema_version": "paper-replay-intake.v1",
        "status": PaperReplayIntakeStatus.READY,
        "ready": True,
        "requested_replay_id": "paper-replay-001",
        "operator_id": "operator-quant-1",
        "strategy_id": "bridge-s01",
        "strategy_digest": "d" * 64,
        "bundle_digest": _BUNDLE,
        "admission_digest": _ADMISSION,
        "bridge_digest": _BRIDGE,
        "manifest_digest": _MANIFEST,
        "manifest_status": "READY",
        "replay_source_id": _SOURCE,
        "historical_data_source_id": _HIST,
        "metadata": (),
        "rejection_reasons": (),
        "needs_research_reasons": (),
        "correlation_id": "corr:intake-001",
        "intake_digest": "0" * 64,
    }
    base.update(overrides)
    intake = PaperReplayIntake(**base)
    if "intake_digest" in overrides:
        return intake
    payload = paper_replay_intake_to_dict(intake)
    payload.pop("intake_digest", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return replace(intake, intake_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _run_plan(intake=None, **overrides):
    intake = _intake() if intake is None else intake
    kwargs = {
        "run_plan_id": _RUN_PLAN_ID,
        "replay_mode": "offline_paper_replay",
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return build_paper_replay_run_plan(intake, **kwargs)


def test_ready_intake_builds_ready_run_plan():
    run_plan = _run_plan()
    assert isinstance(run_plan, PaperReplayRunPlan)
    assert run_plan.status is PaperReplayRunPlanStatus.READY
    assert run_plan.ready is True
    assert run_plan.run_plan_id == _RUN_PLAN_ID
    assert run_plan.replay_mode == "offline_paper_replay"
    assert run_plan.intake_status == "READY"
    assert run_plan.bundle_digest == _BUNDLE
    assert run_plan.replay_source_id == _SOURCE
    assert run_plan.rejection_reasons == ()
    assert len(run_plan.run_plan_digest) == 64
    assert run_plan.paper_only is True
    assert run_plan.real_orders_enabled is False
    assert run_plan.real_money_enabled is False


def test_both_allowed_modes_ready():
    assert _run_plan(replay_mode="offline_paper_replay").status is PaperReplayRunPlanStatus.READY
    assert _run_plan(replay_mode="deterministic_replay_dry_run").status is PaperReplayRunPlanStatus.READY


def test_forged_intake_digest_rejects_before_ready():
    forged = _intake(intake_digest="0" * 64)
    run_plan = _run_plan(forged)
    assert run_plan.status is PaperReplayRunPlanStatus.REJECTED
    assert run_plan.ready is False
    assert "paper_replay_run_plan:intake_digest_mismatch" in run_plan.rejection_reasons


def test_tampered_intake_field_rejects():
    tampered = replace(_intake(), operator_id="forged-operator")  # keeps stale intake_digest
    run_plan = _run_plan(tampered)
    assert run_plan.status is PaperReplayRunPlanStatus.REJECTED
    assert "paper_replay_run_plan:intake_digest_mismatch" in run_plan.rejection_reasons


@pytest.mark.parametrize(
    ("intake", "reason"),
    (
        (_intake(paper_only=False), "paper_replay_run_plan:intake_non_paper"),
        (_intake(real_orders_enabled=True), "paper_replay_run_plan:intake_real_orders_enabled"),
        (_intake(real_money_enabled=True), "paper_replay_run_plan:intake_real_money_enabled"),
    ),
)
def test_non_paper_intake_flags_reject_even_with_matching_digest(intake, reason):
    run_plan = _run_plan(intake)

    assert run_plan.status is PaperReplayRunPlanStatus.REJECTED
    assert run_plan.ready is False
    assert reason in run_plan.rejection_reasons


def test_non_ready_intake_statuses_propagate():
    rejected = _intake(
        status=PaperReplayIntakeStatus.REJECTED, ready=False, rejection_reasons=("paper_replay_intake:x",)
    )
    assert _run_plan(rejected).status is PaperReplayRunPlanStatus.REJECTED

    needs = _intake(
        status=PaperReplayIntakeStatus.NEEDS_RESEARCH, ready=False, needs_research_reasons=("paper_replay_intake:y",)
    )
    assert _run_plan(needs).status is PaperReplayRunPlanStatus.NEEDS_RESEARCH

    insufficient = _intake(status=PaperReplayIntakeStatus.INSUFFICIENT_EVIDENCE, ready=False)
    assert _run_plan(insufficient).status is PaperReplayRunPlanStatus.INSUFFICIENT_EVIDENCE


def test_invalid_chain_digests_reject():
    assert _run_plan(_intake(bundle_digest="bad")).status is PaperReplayRunPlanStatus.REJECTED
    assert _run_plan(_intake(admission_digest="bad")).status is PaperReplayRunPlanStatus.REJECTED
    assert _run_plan(_intake(bridge_digest="bad")).status is PaperReplayRunPlanStatus.REJECTED
    assert _run_plan(_intake(manifest_digest="bad")).status is PaperReplayRunPlanStatus.REJECTED
    bad_intake_digest = _run_plan(_intake(intake_digest="bad"))
    assert bad_intake_digest.status is PaperReplayRunPlanStatus.REJECTED
    assert "paper_replay_run_plan:intake_digest_invalid" in bad_intake_digest.rejection_reasons


def test_invalid_replay_mode_rejects():
    empty = _run_plan(replay_mode="")
    assert empty.status is PaperReplayRunPlanStatus.REJECTED
    assert "paper_replay_run_plan:replay_mode_invalid" in empty.rejection_reasons
    unknown = _run_plan(replay_mode="fast_replay")
    assert unknown.status is PaperReplayRunPlanStatus.REJECTED
    assert "paper_replay_run_plan:replay_mode_unknown" in unknown.rejection_reasons


def test_malformed_or_forbidden_identity_rejects():
    assert _run_plan(run_plan_id="").status is PaperReplayRunPlanStatus.REJECTED

    forbidden = _run_plan(run_plan_id="live_execution_run")
    assert forbidden.status is PaperReplayRunPlanStatus.REJECTED
    assert "paper_replay_run_plan:forbidden_scope_token" in forbidden.rejection_reasons

    bist = _run_plan(run_plan_id="bist30-run")
    assert bist.status is PaperReplayRunPlanStatus.REJECTED
    assert "paper_replay_run_plan:bist_scope_leakage" in bist.rejection_reasons

    bad_source = _run_plan(_intake(replay_source_id="scheduler_loop"))
    assert bad_source.status is PaperReplayRunPlanStatus.REJECTED
    assert "paper_replay_run_plan:forbidden_scope_token" in bad_source.rejection_reasons


@pytest.mark.parametrize(
    ("kwargs", "intake"),
    (
        ({"run_plan_id": "order"}, None),
        ({"run_plan_id": "orders"}, None),
        ({"run_plan_id": "real_order"}, None),
        ({"run_plan_id": "order-routing"}, None),
        ({"metadata": {"note": "desk_order_router"}}, None),
        ({"metadata": {"note": "real-orders"}}, None),
        ({}, _intake(operator_id="desk-order")),
    ),
)
def test_plain_order_scope_tokens_reject(kwargs, intake):
    run_plan = _run_plan(intake=intake, **kwargs)
    assert run_plan.status is PaperReplayRunPlanStatus.REJECTED
    assert run_plan.ready is False
    assert "paper_replay_run_plan:forbidden_scope_token" in run_plan.rejection_reasons


@pytest.mark.parametrize("value", ("border-study", "orderly-paper-review", "preorder-check"))
def test_unrelated_order_substrings_do_not_reject(value):
    assert _run_plan(run_plan_id=value).status is PaperReplayRunPlanStatus.READY


def test_wrong_type_and_bad_metadata_raise():
    with pytest.raises(PaperReplayRunPlanError):
        build_paper_replay_run_plan(
            {"status": "READY"},  # type: ignore[arg-type]
            run_plan_id=_RUN_PLAN_ID,
            replay_mode="offline_paper_replay",
            correlation_id=_CORR,
        )
    with pytest.raises(PaperReplayRunPlanError):
        _run_plan(correlation_id="")
    with pytest.raises(PaperReplayRunPlanError):
        _run_plan(metadata={"k": 5})
    with pytest.raises(PaperReplayRunPlanError):
        _run_plan(metadata={5: "v"})


def test_metadata_normalized_and_deterministic():
    first = _run_plan(metadata={"scope": "crypto_only", "desk": "micro"})
    second = _run_plan(metadata={"desk": "micro", "scope": "crypto_only"})
    assert first.metadata == (("desk", "micro"), ("scope", "crypto_only"))
    assert first.run_plan_digest == second.run_plan_digest
    assert paper_replay_run_plan_to_dict(first) == paper_replay_run_plan_to_dict(second)
    assert paper_replay_run_plan_to_dict(first)["run_plan_digest"] == first.run_plan_digest


def test_material_change_changes_digest():
    base = _run_plan()
    assert _run_plan(run_plan_id="run-plan-002").run_plan_digest != base.run_plan_digest
    assert _run_plan(replay_mode="deterministic_replay_dry_run").run_plan_digest != base.run_plan_digest


def test_immutable_and_no_forbidden_fields():
    run_plan = _run_plan()
    with pytest.raises(FrozenInstanceError):
        run_plan.status = PaperReplayRunPlanStatus.REJECTED  # type: ignore[misc]
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
    assert {field.name for field in fields(run_plan)}.isdisjoint(forbidden)
    payload = paper_replay_run_plan_to_dict(run_plan)
    assert payload["schema_version"] == "paper-replay-run-plan.v1"
    assert set(payload).isdisjoint(forbidden)
