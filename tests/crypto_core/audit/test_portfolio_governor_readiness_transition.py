"""Tests for the paper governor readiness status-transition view.

Covers ``trace_paper_governor_readiness_transitions``: tracing readiness status changes
(READY/BLOCKED/OVER_BUDGET) across the append-only readiness-record chain into a deterministic,
immutable forensic view.

  1. Empty source is deterministic and latest_ready False
  2. Single READY record has zero transitions
  3. READY -> BLOCKED has one transition
  4. READY -> BLOCKED -> READY has two transitions and latest READY
  5. READY -> OVER_BUDGET -> BLOCKED transitions are ordered and deterministic
  6. READY -> READY has no status-change transition but status_counts historical
  7. Transition payload preserves record/readiness digests and block reasons
  8. Store / list / tuple inputs are equivalent
  9. Broken previous_record_digest chain rejects (fail-closed)
 10. Duplicate record_digest rejects (fail-closed)
 11. Tampered / stale record_digest rejects (fail-closed)
 12. Output is immutable
 13. No order/live/venue/scheduler field leaks
 14. Repeated same input gives identical digest/output
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from crypto_core.audit.portfolio_governor_ledger import build_portfolio_governor_ledger_entry
from crypto_core.audit.portfolio_governor_readiness import (
    PaperGovernorReadinessPolicy,
    PaperGovernorReadinessStatus,
    evaluate_paper_governor_readiness,
)
from crypto_core.audit.portfolio_governor_readiness_record import build_paper_governor_readiness_record
from crypto_core.audit.portfolio_governor_readiness_record_replay import PaperGovernorReadinessRecordReplayError
from crypto_core.audit.portfolio_governor_readiness_record_store import PaperGovernorReadinessRecordStore
from crypto_core.audit.portfolio_governor_readiness_transition import (
    PaperGovernorReadinessTransitionTrace,
    paper_governor_readiness_transition_trace_to_dict,
    trace_paper_governor_readiness_transitions,
)
from crypto_core.service.allocation_governor_view import govern_allocation_decision
from crypto_core.service.allocator_risk_bridge import SleeveRiskDecision, build_allocation_decision
from crypto_core.service.portfolio_allocation_projection import project_governed_allocation
from crypto_core.service.portfolio_governor_consumption import consume_portfolio_allocation
from crypto_core.service.sleeve_admission_controller import (
    PaperShadowActivationPlan,
    PaperShadowActivationStatus,
    PaperShadowSourceManifestStatus,
)

_CORR = "corr:paper-governor-readiness-transition-001"
_CAPITAL = 10_000.0
_HEX64 = "a" * 64
_READY = PaperGovernorReadinessStatus.READY
_BLOCKED = PaperGovernorReadinessStatus.BLOCKED
_OVER_BUDGET = PaperGovernorReadinessStatus.OVER_BUDGET


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


def _entry(directive, *, previous: str | None = None, correlation_id: str = _CORR):
    return build_portfolio_governor_ledger_entry(
        directive, correlation_id=correlation_id, previous_entry_digest=previous
    )


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


def test_empty_source_is_safe_and_deterministic():
    first = trace_paper_governor_readiness_transitions(PaperGovernorReadinessRecordStore())
    second = trace_paper_governor_readiness_transitions(())
    assert first.entry_count == 0
    assert first.head_record_digest is None
    assert first.first_status is None
    assert first.latest_status is None
    assert first.latest_ready is False
    assert first.transition_count == 0
    assert first.transitions == ()
    assert dict(first.status_counts) == {"ready": 0, "blocked": 0, "over_budget": 0}
    assert first == second
    assert first.transition_digest == second.transition_digest
    assert len(first.transition_digest) == 64


def test_single_ready_record_has_zero_transitions():
    records = _chain(_readiness_ready())
    trace = trace_paper_governor_readiness_transitions(records)
    assert trace.entry_count == 1
    assert trace.first_status is _READY
    assert trace.latest_status is _READY
    assert trace.latest_ready is True
    assert trace.transition_count == 0
    assert trace.transitions == ()


def test_ready_to_blocked_has_one_transition():
    records = _chain(_readiness_ready(), _readiness_blocked())
    trace = trace_paper_governor_readiness_transitions(records)
    assert trace.transition_count == 1
    transition = trace.transitions[0]
    assert transition.transition_index == 0
    assert transition.from_status is _READY
    assert transition.to_status is _BLOCKED
    assert trace.first_status is _READY
    assert trace.latest_status is _BLOCKED
    assert trace.latest_ready is False


def test_ready_blocked_ready_has_two_transitions_latest_ready():
    records = _chain(_readiness_ready(), _readiness_blocked(), _readiness_ready())
    trace = trace_paper_governor_readiness_transitions(records)
    assert trace.transition_count == 2
    assert [(t.from_status, t.to_status) for t in trace.transitions] == [
        (_READY, _BLOCKED),
        (_BLOCKED, _READY),
    ]
    assert [t.transition_index for t in trace.transitions] == [0, 1]
    assert trace.first_status is _READY
    assert trace.latest_status is _READY
    assert trace.latest_ready is True


def test_ready_over_budget_blocked_transitions_are_ordered():
    records = _chain(_readiness_ready(), _readiness_over_budget(), _readiness_blocked())
    trace = trace_paper_governor_readiness_transitions(records)
    assert [(t.from_status, t.to_status) for t in trace.transitions] == [
        (_READY, _OVER_BUDGET),
        (_OVER_BUDGET, _BLOCKED),
    ]
    assert trace.transition_count == 2
    assert dict(trace.status_counts) == {"ready": 1, "blocked": 1, "over_budget": 1}


def test_ready_to_ready_has_no_status_change_transition():
    records = _chain(_readiness_ready(), _readiness_ready())
    trace = trace_paper_governor_readiness_transitions(records)
    assert trace.entry_count == 2
    assert trace.transition_count == 0
    assert trace.transitions == ()
    assert dict(trace.status_counts) == {"ready": 2, "blocked": 0, "over_budget": 0}


def test_transition_payload_preserves_digests_and_reasons():
    records = _chain(_readiness_ready(), _readiness_blocked())
    trace = trace_paper_governor_readiness_transitions(records)
    transition = trace.transitions[0]
    assert transition.from_record_digest == records[0].record_digest
    assert transition.to_record_digest == records[1].record_digest
    assert transition.from_readiness_digest == records[0].readiness_digest
    assert transition.to_readiness_digest == records[1].readiness_digest
    assert transition.from_block_reasons == records[0].block_reasons
    assert transition.to_block_reasons == records[1].block_reasons
    assert transition.from_blocker_summary == records[0].blocker_summary
    assert transition.to_blocker_summary == records[1].blocker_summary
    assert "paper_governor_readiness:blocked_plans_present" in transition.to_block_reasons


def test_store_tuple_list_inputs_equivalent():
    records = _chain(_readiness_ready(), _readiness_blocked(), _readiness_ready())
    store = PaperGovernorReadinessRecordStore()
    for record in records:
        store.append(record)
    from_store = trace_paper_governor_readiness_transitions(store)
    from_tuple = trace_paper_governor_readiness_transitions(records)
    from_list = trace_paper_governor_readiness_transitions(list(records))
    assert from_store == from_tuple == from_list
    assert from_store.transition_digest == from_tuple.transition_digest == from_list.transition_digest


def test_broken_chain_rejects():
    ready = _record(_readiness_ready())
    orphan = _record(_readiness_blocked(), previous=_HEX64)
    with pytest.raises(PaperGovernorReadinessRecordReplayError):
        trace_paper_governor_readiness_transitions((ready, orphan))


def test_duplicate_record_digest_rejects():
    ready = _record(_readiness_ready())
    with pytest.raises(PaperGovernorReadinessRecordReplayError):
        trace_paper_governor_readiness_transitions((ready, ready))


def test_tampered_record_rejects():
    ready = _record(_readiness_ready())
    tampered = replace(ready, total_active_weight=999.0)
    with pytest.raises(PaperGovernorReadinessRecordReplayError):
        trace_paper_governor_readiness_transitions((tampered,))


def test_malformed_source_rejects():
    with pytest.raises(PaperGovernorReadinessRecordReplayError):
        trace_paper_governor_readiness_transitions({"not": "a source"})


def test_trace_is_immutable():
    records = _chain(_readiness_ready(), _readiness_blocked())
    trace = trace_paper_governor_readiness_transitions(records)
    assert isinstance(trace.transitions, tuple)
    with pytest.raises((AttributeError, TypeError)):
        trace.transition_count = 9  # type: ignore[misc]


def test_repeated_trace_is_deterministic():
    records = _chain(_readiness_ready(), _readiness_blocked(), _readiness_over_budget())
    first = trace_paper_governor_readiness_transitions(records)
    second = trace_paper_governor_readiness_transitions(records)
    assert first == second
    assert first.transition_digest == second.transition_digest


def test_no_order_or_live_fields_leak():
    trace = trace_paper_governor_readiness_transitions(_chain(_readiness_ready(), _readiness_blocked()))
    forbidden = {"order", "order_intent", "route", "venue", "exchange", "schedule", "scheduler", "live"}
    assert {field.name for field in fields(trace)}.isdisjoint(forbidden)
    assert {field.name for field in fields(trace.transitions[0])}.isdisjoint(forbidden)
    assert trace.paper_only is True
    assert trace.real_orders_enabled is False
    assert trace.real_money_enabled is False
    payload = paper_governor_readiness_transition_trace_to_dict(trace)
    assert payload["schema_version"] == "paper-governor-readiness-transition-trace.v1"
    assert set(payload).isdisjoint(forbidden)


def test_trace_consumes_type_is_trace():
    trace = trace_paper_governor_readiness_transitions(_chain(_readiness_ready()))
    assert isinstance(trace, PaperGovernorReadinessTransitionTrace)


class _SneakyList(list):
    """A list whose second-and-later iteration yields a different (extra) snapshot."""

    def __init__(self, items, extra):
        super().__init__(items)
        self._base = list(items)
        self._extra = extra
        self._reads = 0

    def __iter__(self):
        self._reads += 1
        if self._reads >= 2:
            return iter([*self._base, self._extra])
        return iter(self._base)

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return id(self)


def test_single_snapshot_used_for_validation_and_transitions():
    # Regression (Codex P2): the source is snapshotted once, so a list/store that returns a different
    # second snapshot cannot make transitions disagree with the validated summary.
    records = _chain(_readiness_ready(), _readiness_blocked())
    extra = _record(_readiness_ready(), previous=records[-1].record_digest)
    sneaky = _SneakyList(list(records), extra)
    trace_sneaky = trace_paper_governor_readiness_transitions(sneaky)
    trace_plain = trace_paper_governor_readiness_transitions(records)
    assert trace_sneaky == trace_plain
    assert trace_sneaky.entry_count == 2
    assert trace_sneaky.transition_count == 1
