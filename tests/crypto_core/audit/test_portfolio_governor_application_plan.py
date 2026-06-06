"""Tests for the paper governor application plan.

Covers ``build_paper_governor_application_plan``: collapsing the paper-governor readiness foundation
into one product-facing decision (APPLY / HOLD / BLOCK), deterministically and fail-closed.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from crypto_core.audit.portfolio_governor_application_plan import (
    PaperGovernorApplicationMode,
    PaperGovernorApplicationPlan,
    PaperGovernorApplicationPlanError,
    build_paper_governor_application_plan,
    paper_governor_application_plan_to_dict,
)
from crypto_core.audit.portfolio_governor_ledger import build_portfolio_governor_ledger_entry
from crypto_core.audit.portfolio_governor_readiness import (
    PaperGovernorReadinessPolicy,
    PaperGovernorReadinessStatus,
    evaluate_paper_governor_readiness,
)
from crypto_core.audit.portfolio_governor_readiness_record import build_paper_governor_readiness_record
from crypto_core.audit.portfolio_governor_readiness_record_store import PaperGovernorReadinessRecordStore
from crypto_core.audit.portfolio_governor_readiness_stability import (
    PaperGovernorReadinessStabilityPolicy,
    evaluate_paper_governor_readiness_stability,
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

_CORR = "corr:paper-governor-application-plan-001"
_CAPITAL = 10_000.0
_HEX64 = "a" * 64
_APPLY = PaperGovernorApplicationMode.APPLY
_HOLD = PaperGovernorApplicationMode.HOLD
_BLOCK = PaperGovernorApplicationMode.BLOCK


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


class _CountingStore(PaperGovernorReadinessRecordStore):
    """A record store that counts ``snapshot`` calls, to prove the builder reads it at most once."""

    def __init__(self):
        super().__init__()
        self._snapshot_calls = 0

    def snapshot(self):
        self._snapshot_calls += 1
        return super().snapshot()

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return id(self)


def test_empty_source_blocks_and_never_applies():
    plan = build_paper_governor_application_plan(PaperGovernorReadinessRecordStore())
    assert plan.application_mode is _BLOCK
    assert plan.can_apply is False
    assert plan.latest_status is None
    assert plan.latest_ready is False
    assert plan.entry_count == 0
    assert "paper_governor_application_plan:not_ready" in plan.reason_codes
    assert build_paper_governor_application_plan(()).plan_digest == plan.plan_digest


def test_stable_ready_chain_applies():
    plan = build_paper_governor_application_plan(_chain(_readiness_ready()))
    assert plan.application_mode is _APPLY
    assert plan.can_apply is True
    assert plan.latest_status is PaperGovernorReadinessStatus.READY
    assert plan.latest_ready is True
    assert plan.stable_ready is True
    assert plan.blockers == ()
    assert plan.reason_codes == ("paper_governor_application_plan:stable_ready",)


def test_latest_blocked_blocks():
    plan = build_paper_governor_application_plan(_chain(_readiness_ready(), _readiness_blocked()))
    assert plan.application_mode is _BLOCK
    assert plan.can_apply is False
    assert plan.latest_status is PaperGovernorReadinessStatus.BLOCKED


def test_latest_over_budget_blocks():
    plan = build_paper_governor_application_plan(_chain(_readiness_ready(), _readiness_over_budget()))
    assert plan.application_mode is _BLOCK
    assert plan.can_apply is False
    assert plan.latest_status is PaperGovernorReadinessStatus.OVER_BUDGET


def test_ready_but_unstable_holds():
    plan = build_paper_governor_application_plan(_chain(_readiness_ready()), min_ready_tail_records=2)
    assert plan.application_mode is _HOLD
    assert plan.can_apply is False
    assert plan.latest_status is PaperGovernorReadinessStatus.READY
    assert plan.latest_ready is True
    assert plan.stable_ready is False
    assert plan.reason_codes == ("paper_governor_application_plan:ready_but_unstable",)


def test_malformed_source_type_rejects():
    for bad in ({"not": "a source"}, 5, "records"):
        with pytest.raises(PaperGovernorApplicationPlanError):
            build_paper_governor_application_plan(bad)


def test_broken_chain_rejects():
    ready = _record(_readiness_ready())
    orphan = _record(_readiness_blocked(), previous=_HEX64)
    with pytest.raises(PaperGovernorApplicationPlanError):
        build_paper_governor_application_plan((ready, orphan))


def test_duplicate_record_rejects():
    ready = _record(_readiness_ready())
    with pytest.raises(PaperGovernorApplicationPlanError):
        build_paper_governor_application_plan((ready, ready))


def test_tampered_record_rejects():
    ready = _record(_readiness_ready())
    tampered = replace(ready, total_active_weight=999.0)
    with pytest.raises(PaperGovernorApplicationPlanError):
        build_paper_governor_application_plan((tampered,))


def test_non_record_element_rejects():
    with pytest.raises(PaperGovernorApplicationPlanError):
        build_paper_governor_application_plan(("not-a-record",))


def test_precomputed_objects_rejected():
    # Direct precomputed objects are not accepted sources; the plan must derive from records.
    records = _chain(_readiness_ready())
    trace = trace_paper_governor_readiness_transitions(records)
    stability = evaluate_paper_governor_readiness_stability(records)
    for precomputed in (trace, stability):
        with pytest.raises(PaperGovernorApplicationPlanError):
            build_paper_governor_application_plan(precomputed)


def test_provenance_digests_preserved_and_canonical():
    records = _chain(_readiness_ready())
    stability = evaluate_paper_governor_readiness_stability(
        records, policy=PaperGovernorReadinessStabilityPolicy(min_ready_tail_records=1)
    )
    plan = build_paper_governor_application_plan(records)
    assert plan.head_record_digest == stability.head_record_digest
    assert plan.replay_digest == stability.replay_digest
    assert plan.transition_digest == stability.transition_digest
    assert plan.stability_digest == stability.stability_digest
    assert len(plan.plan_digest) == 64
    payload = paper_governor_application_plan_to_dict(plan)
    assert payload["plan_digest"] == plan.plan_digest
    assert payload["stability_digest"] == stability.stability_digest


def test_deterministic_output_and_digest():
    records = _chain(_readiness_ready(), _readiness_blocked(), _readiness_ready())
    first = build_paper_governor_application_plan(records, min_ready_tail_records=1)
    second = build_paper_governor_application_plan(records, min_ready_tail_records=1)
    assert first == second
    assert first.plan_digest == second.plan_digest
    assert paper_governor_application_plan_to_dict(first) == paper_governor_application_plan_to_dict(second)


def test_mutable_store_read_exactly_once():
    records = _chain(_readiness_ready())
    store = _CountingStore()
    for record in records:
        store.append(record)
    plan = build_paper_governor_application_plan(store)
    assert plan.application_mode is _APPLY
    assert store._snapshot_calls == 1


def test_invalid_min_ready_tail_records_rejects():
    records = _chain(_readiness_ready())
    for bad in (0, -1, True, "2", 1.0):
        with pytest.raises(PaperGovernorApplicationPlanError):
            build_paper_governor_application_plan(records, min_ready_tail_records=bad)


def test_no_order_or_live_fields_leak():
    plan = build_paper_governor_application_plan(_chain(_readiness_ready()))
    forbidden = {"order", "order_intent", "route", "venue", "exchange", "schedule", "scheduler", "live"}
    assert {field.name for field in fields(plan)}.isdisjoint(forbidden)
    assert plan.paper_only is True
    assert plan.real_orders_enabled is False
    assert plan.real_money_enabled is False
    payload = paper_governor_application_plan_to_dict(plan)
    assert payload["schema_version"] == "paper-governor-application-plan.v1"
    assert set(payload).isdisjoint(forbidden)
    assert isinstance(plan, PaperGovernorApplicationPlan)
