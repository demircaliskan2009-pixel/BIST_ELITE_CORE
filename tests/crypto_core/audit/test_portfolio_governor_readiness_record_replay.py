"""Tests for the paper governor readiness record replay / current-decision view.

Covers ``replay_paper_governor_readiness_records``: replaying the append-only
``PaperGovernorReadinessRecordStore`` (or ordered records) into a deterministic, immutable
current-decision view (latest verdict, per-status counts, current block reasons/blocker summary,
latest caps/totals, provenance).

  1. Empty store replay is deterministic and safe
  2. Single READY record yields READY current view
  3. READY -> BLOCKED chain yields BLOCKED latest/current view
  4. READY -> OVER_BUDGET chain yields OVER_BUDGET latest/current view
  5. status_counts are deterministic
  6. Current block reasons / blocker summary reflect the latest record
  7. Broken previous_record_digest chain rejects (fail-closed)
  8. Duplicate record_digest rejects (fail-closed)
  9. Tampered / stale record_digest rejects through store validation
 10. Tuple / list input and store input are equivalent
 11. Output is immutable
 12. No order/live/venue/scheduler field leaks
 13. Repeated same input gives identical replay_digest/output
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
from crypto_core.audit.portfolio_governor_readiness_record_replay import (
    PaperGovernorReadinessRecordReplayError,
    paper_governor_readiness_record_replay_to_dict,
    replay_paper_governor_readiness_records,
)
from crypto_core.audit.portfolio_governor_readiness_record_store import PaperGovernorReadinessRecordStore
from crypto_core.service.allocation_governor_view import govern_allocation_decision
from crypto_core.service.allocator_risk_bridge import SleeveRiskDecision, build_allocation_decision
from crypto_core.service.portfolio_allocation_projection import project_governed_allocation
from crypto_core.service.portfolio_governor_consumption import consume_portfolio_allocation
from crypto_core.service.sleeve_admission_controller import (
    PaperShadowActivationPlan,
    PaperShadowActivationStatus,
    PaperShadowSourceManifestStatus,
)

_CORR = "corr:paper-governor-readiness-record-replay-001"
_CAPITAL = 10_000.0
_HEX64 = "a" * 64


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


def _record(readiness, *, previous: str | None = None, correlation_id: str = _CORR):
    return build_paper_governor_readiness_record(
        readiness, correlation_id=correlation_id, previous_record_digest=previous
    )


def _chain(*readinesses):
    records = []
    previous = None
    for readiness in readinesses:
        record = _record(readiness, previous=previous)
        records.append(record)
        previous = record.record_digest
    return tuple(records)


def test_empty_store_replay_is_safe_and_deterministic():
    first = replay_paper_governor_readiness_records(PaperGovernorReadinessRecordStore())
    second = replay_paper_governor_readiness_records(())
    assert first.entry_count == 0
    assert first.head_record_digest is None
    assert first.latest_record_digest is None
    assert first.latest_status is None
    assert first.latest_ready is False
    assert first.latest_readiness_digest is None
    assert first.current_block_reasons == ()
    assert first.current_blocker_summary == ()
    assert first.latest_evidence_refs == ()
    assert dict(first.status_counts) == {"ready": 0, "blocked": 0, "over_budget": 0}
    assert first == second
    assert first.replay_digest == second.replay_digest
    assert len(first.replay_digest) == 64


def test_single_ready_record_yields_ready_view():
    (record,) = _chain(_readiness_ready())
    replay = replay_paper_governor_readiness_records((record,))
    assert replay.entry_count == 1
    assert replay.head_record_digest == record.record_digest
    assert replay.latest_record_digest == record.record_digest
    assert replay.latest_status is PaperGovernorReadinessStatus.READY
    assert replay.latest_ready is True
    assert replay.latest_readiness_digest == record.readiness_digest
    assert replay.current_block_reasons == ()
    assert dict(replay.status_counts) == {"ready": 1, "blocked": 0, "over_budget": 0}


def test_ready_then_blocked_chain_is_blocked_current():
    records = _chain(_readiness_ready(), _readiness_blocked())
    replay = replay_paper_governor_readiness_records(records)
    assert replay.entry_count == 2
    assert replay.latest_status is PaperGovernorReadinessStatus.BLOCKED
    assert replay.latest_ready is False
    assert replay.head_record_digest == records[-1].record_digest
    assert "paper_governor_readiness:blocked_plans_present" in replay.current_block_reasons
    assert replay.current_blocker_summary != ()
    assert dict(replay.status_counts) == {"ready": 1, "blocked": 1, "over_budget": 0}


def test_ready_then_over_budget_chain_is_over_budget_current():
    records = _chain(_readiness_ready(), _readiness_over_budget())
    replay = replay_paper_governor_readiness_records(records)
    assert replay.latest_status is PaperGovernorReadinessStatus.OVER_BUDGET
    assert replay.latest_ready is False
    assert "paper_governor_readiness:active_weight_exceeds_cap" in replay.current_block_reasons
    assert replay.latest_max_current_active_weight == 0.5
    assert dict(replay.status_counts) == {"ready": 1, "blocked": 0, "over_budget": 1}


def test_current_fields_reflect_latest_record():
    records = _chain(_readiness_ready(), _readiness_blocked())
    replay = replay_paper_governor_readiness_records(records)
    latest = records[-1]
    assert replay.current_block_reasons == latest.block_reasons
    assert replay.current_blocker_summary == latest.blocker_summary
    assert replay.latest_total_active_weight == latest.total_active_weight
    assert replay.latest_total_active_notional == latest.total_active_notional
    assert replay.latest_evidence_refs == latest.evidence_refs


def test_broken_chain_rejects():
    ready = _record(_readiness_ready())
    orphan = _record(_readiness_blocked(), previous=_HEX64)  # wrong previous digest
    with pytest.raises(PaperGovernorReadinessRecordReplayError):
        replay_paper_governor_readiness_records((ready, orphan))


def test_duplicate_record_digest_rejects():
    ready = _record(_readiness_ready())
    with pytest.raises(PaperGovernorReadinessRecordReplayError):
        replay_paper_governor_readiness_records((ready, ready))


def test_tampered_record_rejects():
    ready = _record(_readiness_ready())
    tampered = replace(ready, total_active_weight=999.0)  # content changed, stale record_digest
    with pytest.raises(PaperGovernorReadinessRecordReplayError):
        replay_paper_governor_readiness_records((tampered,))


def test_malformed_source_rejects():
    with pytest.raises(PaperGovernorReadinessRecordReplayError):
        replay_paper_governor_readiness_records({"not": "a source"})


def test_non_record_element_rejects():
    with pytest.raises(PaperGovernorReadinessRecordReplayError):
        replay_paper_governor_readiness_records(("not-a-record",))


def test_store_tuple_list_inputs_equivalent():
    records = _chain(_readiness_ready(), _readiness_blocked())
    store = PaperGovernorReadinessRecordStore()
    for record in records:
        store.append(record)
    from_store = replay_paper_governor_readiness_records(store)
    from_tuple = replay_paper_governor_readiness_records(records)
    from_list = replay_paper_governor_readiness_records(list(records))
    assert from_store == from_tuple == from_list
    assert from_store.replay_digest == from_tuple.replay_digest == from_list.replay_digest


def test_replay_output_is_immutable():
    records = _chain(_readiness_ready(), _readiness_blocked())
    replay = replay_paper_governor_readiness_records(records)
    assert isinstance(replay.status_counts, tuple)
    assert isinstance(replay.current_block_reasons, tuple)
    with pytest.raises((AttributeError, TypeError)):
        replay.entry_count = 9  # type: ignore[misc]


def test_repeated_replay_is_deterministic():
    records = _chain(_readiness_ready(), _readiness_over_budget())
    first = replay_paper_governor_readiness_records(records)
    second = replay_paper_governor_readiness_records(records)
    assert first == second
    assert first.replay_digest == second.replay_digest


def test_no_order_or_live_fields_leak():
    replay = replay_paper_governor_readiness_records(_chain(_readiness_ready()))
    forbidden = {"order", "order_intent", "route", "venue", "exchange", "schedule", "scheduler", "live"}
    assert {field.name for field in fields(replay)}.isdisjoint(forbidden)
    assert replay.paper_only is True
    assert replay.real_orders_enabled is False
    assert replay.real_money_enabled is False
    payload = paper_governor_readiness_record_replay_to_dict(replay)
    assert payload["schema_version"] == "paper-governor-readiness-record-replay.v1"
    assert set(payload).isdisjoint(forbidden)
