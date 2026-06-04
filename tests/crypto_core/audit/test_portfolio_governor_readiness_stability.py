"""Tests for the paper governor readiness stability gate.

Covers ``evaluate_paper_governor_readiness_stability``: a deterministic, fail-closed verdict
(STABLE_READY / NOT_READY / UNSTABLE) over the readiness status-transition history under an explicit
stability policy.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from crypto_core.audit.portfolio_governor_ledger import build_portfolio_governor_ledger_entry
from crypto_core.audit.portfolio_governor_readiness import (
    PaperGovernorReadinessPolicy,
    evaluate_paper_governor_readiness,
)
from crypto_core.audit.portfolio_governor_readiness_record import build_paper_governor_readiness_record
from crypto_core.audit.portfolio_governor_readiness_record_replay import PaperGovernorReadinessRecordReplayError
from crypto_core.audit.portfolio_governor_readiness_record_store import PaperGovernorReadinessRecordStore
from crypto_core.audit.portfolio_governor_readiness_stability import (
    PaperGovernorReadinessStability,
    PaperGovernorReadinessStabilityError,
    PaperGovernorReadinessStabilityPolicy,
    PaperGovernorReadinessStabilityStatus,
    evaluate_paper_governor_readiness_stability,
    paper_governor_readiness_stability_to_dict,
)
from crypto_core.audit.portfolio_governor_readiness_transition import trace_paper_governor_readiness_transitions
from crypto_core.service.allocation_governor_view import govern_allocation_decision
from crypto_core.service.allocator_risk_bridge import SleeveRiskDecision, build_allocation_decision
from crypto_core.service.portfolio_allocation_projection import project_governed_allocation
from crypto_core.service.portfolio_governor_consumption import consume_portfolio_allocation
from crypto_core.service.sleeve_admission_controller import (
    PaperShadowActivationPlan,
    PaperShadowActivationStatus,
    PaperShadowSourceManifestStatus,
)

_CORR = "corr:paper-governor-readiness-stability-001"
_CAPITAL = 10_000.0
_HEX64 = "a" * 64
_STABLE = PaperGovernorReadinessStabilityStatus.STABLE_READY
_NOT_READY = PaperGovernorReadinessStabilityStatus.NOT_READY
_UNSTABLE = PaperGovernorReadinessStabilityStatus.UNSTABLE


def _ready_plan(plan_id: str = "paper-shadow-activation:deadbeef") -> PaperShadowActivationPlan:
    return PaperShadowActivationPlan(
        plan_id=plan_id,
        activation_status=PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW,
        source_manifest_status=PaperShadowSourceManifestStatus.READY,
        active_sleeves=("micro-1", "micro-2"),
        pbo_allocation_caps=(("micro-1", 0.5), ("micro-2", 0.5)),
    )


def _allocated_directive(plan_id: str = "paper-shadow-activation:deadbeef", budget: float = 1.0):
    risk = {
        "micro-1": SleeveRiskDecision("micro-1", approved=True),
        "micro-2": SleeveRiskDecision("micro-2", approved=True),
    }
    view = govern_allocation_decision(build_allocation_decision(_ready_plan(plan_id), risk, budget=budget))
    record = project_governed_allocation(view, capital_base=_CAPITAL)
    return consume_portfolio_allocation(record)


def _blocked_directive(plan_id: str = "paper-shadow-activation:blocked"):
    plan = PaperShadowActivationPlan(
        plan_id=plan_id,
        activation_status=PaperShadowActivationStatus.BLOCKED,
        source_manifest_status=PaperShadowSourceManifestStatus.BLOCKED,
        active_sleeves=("micro-1",),
        evidence_blockers=("sleeve_admission_evidence:currentness_missing",),
    )
    decision = build_allocation_decision(plan, {"micro-1": SleeveRiskDecision("micro-1", approved=True)})
    record = project_governed_allocation(govern_allocation_decision(decision), capital_base=_CAPITAL)
    return consume_portfolio_allocation(record)


def _entry(directive, *, previous: str | None = None):
    return build_portfolio_governor_ledger_entry(directive, correlation_id=_CORR, previous_entry_digest=previous)


def _readiness_ready():
    active = _entry(_allocated_directive())
    return evaluate_paper_governor_readiness(
        (active,),
        policy=PaperGovernorReadinessPolicy(max_current_active_weight=1.0, max_current_active_notional=10_000.0),
    )


def _readiness_blocked():
    active = _entry(_allocated_directive())
    blocked = _entry(_blocked_directive(), previous=active.entry_digest)
    return evaluate_paper_governor_readiness((active, blocked))


def _readiness_over_budget():
    active = _entry(_allocated_directive())
    return evaluate_paper_governor_readiness(
        (active,), policy=PaperGovernorReadinessPolicy(max_current_active_weight=0.5)
    )


def _record(readiness, *, previous: str | None = None):
    return build_paper_governor_readiness_record(readiness, correlation_id=_CORR, previous_record_digest=previous)


def _chain(*readinesses):
    records: list = []
    previous = None
    for readiness in readinesses:
        record = _record(readiness, previous=previous)
        records.append(record)
        previous = record.record_digest
    return tuple(records)


def test_empty_source_is_not_ready():
    decision = evaluate_paper_governor_readiness_stability(PaperGovernorReadinessRecordStore())
    assert decision.stability_status is _NOT_READY
    assert decision.stable_ready is False
    assert decision.latest_status is None
    assert decision.latest_ready is False
    assert decision.entry_count == 0
    assert "stability:empty_chain" in decision.block_reasons
    assert len(decision.stability_digest) == 64
    assert evaluate_paper_governor_readiness_stability(()) == decision


def test_single_ready_tail_one_is_stable():
    decision = evaluate_paper_governor_readiness_stability(_chain(_readiness_ready()))
    assert decision.stability_status is _STABLE
    assert decision.stable_ready is True
    assert decision.block_reasons == ()


def test_single_ready_tail_two_is_unstable():
    decision = evaluate_paper_governor_readiness_stability(
        _chain(_readiness_ready()), policy=PaperGovernorReadinessStabilityPolicy(min_ready_tail_records=2)
    )
    assert decision.stability_status is _UNSTABLE
    assert decision.stable_ready is False
    assert "stability:insufficient_ready_tail" in decision.block_reasons


def test_ready_ready_tail_two_is_stable():
    decision = evaluate_paper_governor_readiness_stability(
        _chain(_readiness_ready(), _readiness_ready()),
        policy=PaperGovernorReadinessStabilityPolicy(min_ready_tail_records=2),
    )
    assert decision.stability_status is _STABLE
    assert decision.stable_ready is True


def test_latest_blocked_is_not_ready():
    decision = evaluate_paper_governor_readiness_stability(_chain(_readiness_ready(), _readiness_blocked()))
    assert decision.stability_status is _NOT_READY
    assert decision.stable_ready is False
    assert "stability:latest_not_ready" in decision.block_reasons


def test_latest_over_budget_is_not_ready():
    decision = evaluate_paper_governor_readiness_stability(_chain(_readiness_ready(), _readiness_over_budget()))
    assert decision.stability_status is _NOT_READY
    assert decision.stable_ready is False


def test_ready_blocked_ready_default_is_unstable():
    # Default policy blocks stability on any historical BLOCKED record.
    decision = evaluate_paper_governor_readiness_stability(
        _chain(_readiness_ready(), _readiness_blocked(), _readiness_ready())
    )
    assert decision.stability_status is _UNSTABLE
    assert decision.stable_ready is False
    assert "stability:historical_blocked_records" in decision.block_reasons


def test_ready_blocked_ready_unstable_on_total_transitions_cap():
    decision = evaluate_paper_governor_readiness_stability(
        _chain(_readiness_ready(), _readiness_blocked(), _readiness_ready()),
        policy=PaperGovernorReadinessStabilityPolicy(blocked_status_blocks_stability=False, max_total_transitions=1),
    )
    assert decision.stability_status is _UNSTABLE
    assert "stability:too_many_total_transitions" in decision.block_reasons


def test_ready_blocked_ready_unstable_on_recent_transitions_cap():
    decision = evaluate_paper_governor_readiness_stability(
        _chain(_readiness_ready(), _readiness_blocked(), _readiness_ready()),
        policy=PaperGovernorReadinessStabilityPolicy(blocked_status_blocks_stability=False, max_recent_transitions=0),
    )
    assert decision.stability_status is _UNSTABLE
    assert "stability:too_many_recent_transitions" in decision.block_reasons


def test_ready_blocked_ready_stable_only_when_policy_allows():
    # Explicitly allow historical blocks, short tail, and no transition caps.
    decision = evaluate_paper_governor_readiness_stability(
        _chain(_readiness_ready(), _readiness_blocked(), _readiness_ready()),
        policy=PaperGovernorReadinessStabilityPolicy(min_ready_tail_records=1, blocked_status_blocks_stability=False),
    )
    assert decision.stability_status is _STABLE
    assert decision.stable_ready is True
    assert decision.block_reasons == ()


def test_invalid_policy_rejects():
    records = _chain(_readiness_ready())
    for policy in (
        PaperGovernorReadinessStabilityPolicy(min_ready_tail_records=0),
        PaperGovernorReadinessStabilityPolicy(min_ready_tail_records=True),
        PaperGovernorReadinessStabilityPolicy(max_total_transitions=-1),
        PaperGovernorReadinessStabilityPolicy(max_recent_transitions=-1),
        PaperGovernorReadinessStabilityPolicy(max_total_transitions=True),
    ):
        with pytest.raises(PaperGovernorReadinessStabilityError):
            evaluate_paper_governor_readiness_stability(records, policy=policy)


def test_broken_chain_rejects():
    ready = _record(_readiness_ready())
    orphan = _record(_readiness_blocked(), previous=_HEX64)
    with pytest.raises(PaperGovernorReadinessRecordReplayError):
        evaluate_paper_governor_readiness_stability((ready, orphan))


def test_duplicate_record_digest_rejects():
    ready = _record(_readiness_ready())
    with pytest.raises(PaperGovernorReadinessRecordReplayError):
        evaluate_paper_governor_readiness_stability((ready, ready))


def test_tampered_record_rejects():
    ready = _record(_readiness_ready())
    tampered = replace(ready, total_active_weight=999.0)
    with pytest.raises(PaperGovernorReadinessRecordReplayError):
        evaluate_paper_governor_readiness_stability((tampered,))


def test_malformed_source_rejects():
    with pytest.raises(PaperGovernorReadinessStabilityError):
        evaluate_paper_governor_readiness_stability({"not": "a source"})


def test_trace_input_equivalent_for_tail_one_policy():
    records = _chain(_readiness_ready(), _readiness_ready())
    trace = trace_paper_governor_readiness_transitions(records)
    store = PaperGovernorReadinessRecordStore()
    for record in records:
        store.append(record)
    policy = PaperGovernorReadinessStabilityPolicy(min_ready_tail_records=1, blocked_status_blocks_stability=False)
    from_records = evaluate_paper_governor_readiness_stability(records, policy=policy)
    from_store = evaluate_paper_governor_readiness_stability(store, policy=policy)
    from_list = evaluate_paper_governor_readiness_stability(list(records), policy=policy)
    from_trace = evaluate_paper_governor_readiness_stability(trace, policy=policy)
    assert from_records == from_store == from_list == from_trace
    assert from_records.stability_status is _STABLE


def test_trace_source_tail_two_is_unverifiable():
    trace = trace_paper_governor_readiness_transitions(_chain(_readiness_ready(), _readiness_ready()))
    decision = evaluate_paper_governor_readiness_stability(
        trace, policy=PaperGovernorReadinessStabilityPolicy(min_ready_tail_records=2)
    )
    assert decision.stability_status is _UNSTABLE
    assert "stability:ready_tail_unverifiable" in decision.block_reasons


def test_trace_source_recent_cap_is_unverifiable():
    trace = trace_paper_governor_readiness_transitions(_chain(_readiness_ready(), _readiness_ready()))
    decision = evaluate_paper_governor_readiness_stability(
        trace,
        policy=PaperGovernorReadinessStabilityPolicy(blocked_status_blocks_stability=False, max_recent_transitions=0),
    )
    assert decision.stability_status is _UNSTABLE
    assert "stability:recent_transitions_unverifiable" in decision.block_reasons


def test_tampered_trace_rejects():
    trace = trace_paper_governor_readiness_transitions(_chain(_readiness_ready()))
    tampered = replace(trace, latest_ready=False)  # stale transition_digest
    with pytest.raises(PaperGovernorReadinessStabilityError):
        evaluate_paper_governor_readiness_stability(tampered)


def test_trace_with_mismatched_schema_version_rejects():
    # Regression (Codex P2): the digest hard-codes the schema version, so a changed schema_version
    # field would otherwise keep the original digest valid and bypass the provenance check.
    trace = trace_paper_governor_readiness_transitions(_chain(_readiness_ready()))
    spoofed = replace(trace, schema_version="future")
    with pytest.raises(PaperGovernorReadinessStabilityError):
        evaluate_paper_governor_readiness_stability(spoofed)


def test_decision_is_immutable():
    decision = evaluate_paper_governor_readiness_stability(_chain(_readiness_ready()))
    assert isinstance(decision.block_reasons, tuple)
    with pytest.raises((AttributeError, TypeError)):
        decision.stable_ready = True  # type: ignore[misc]


def test_repeated_evaluation_is_deterministic():
    records = _chain(_readiness_ready(), _readiness_blocked(), _readiness_ready())
    policy = PaperGovernorReadinessStabilityPolicy(min_ready_tail_records=1, max_total_transitions=5)
    first = evaluate_paper_governor_readiness_stability(records, policy=policy)
    second = evaluate_paper_governor_readiness_stability(records, policy=policy)
    assert first == second
    assert first.stability_digest == second.stability_digest


def test_no_order_or_live_fields_leak():
    decision = evaluate_paper_governor_readiness_stability(_chain(_readiness_ready()))
    forbidden = {"order", "order_intent", "route", "venue", "exchange", "schedule", "scheduler", "live"}
    assert {field.name for field in fields(decision)}.isdisjoint(forbidden)
    assert decision.paper_only is True
    assert decision.real_orders_enabled is False
    assert decision.real_money_enabled is False
    payload = paper_governor_readiness_stability_to_dict(decision)
    assert payload["schema_version"] == "paper-governor-readiness-stability.v1"
    assert set(payload).isdisjoint(forbidden)
    assert isinstance(decision, PaperGovernorReadinessStability)
