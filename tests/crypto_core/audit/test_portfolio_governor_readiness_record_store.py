"""Tests for the append-only paper governor readiness record store."""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from crypto_core.audit.decision_ledger import DecisionEvidenceRef
from crypto_core.audit.portfolio_governor_ledger import build_portfolio_governor_ledger_entry
from crypto_core.audit.portfolio_governor_readiness import (
    PaperGovernorReadinessPolicy,
    PaperGovernorReadinessStatus,
    evaluate_paper_governor_readiness,
)
from crypto_core.audit.portfolio_governor_readiness_record import build_paper_governor_readiness_record
from crypto_core.audit.portfolio_governor_readiness_record_store import (
    PaperGovernorReadinessRecordStore,
    PaperGovernorReadinessRecordStoreError,
    _expected_record_digest,
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

_CORR = "corr:paper-governor-readiness-record-store-001"
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


def _allocated_directive(
    plan_id: str = "paper-shadow-activation:deadbeef", budget: float = 1.0, capital_base: float = _CAPITAL
):
    risk = {
        "micro-1": SleeveRiskDecision("micro-1", approved=True),
        "micro-2": SleeveRiskDecision("micro-2", approved=True),
    }
    view = govern_allocation_decision(build_allocation_decision(_ready_plan(plan_id), risk, budget=budget))
    record = project_governed_allocation(view, capital_base=capital_base)
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


def _fresh_record(record):
    return replace(record, record_digest=_expected_record_digest(record))


def test_malformed_non_record_input_rejects():
    store = PaperGovernorReadinessRecordStore()
    with pytest.raises(PaperGovernorReadinessRecordStoreError):
        store.append({"not": "a readiness record"})


def test_non_paper_record_rejects():
    store = PaperGovernorReadinessRecordStore()
    record = _record(_readiness_ready())
    for bad in (
        replace(record, paper_only=False),
        replace(record, real_orders_enabled=True),
        replace(record, real_money_enabled=True),
    ):
        with pytest.raises(PaperGovernorReadinessRecordStoreError):
            store.append(bad)


def test_invalid_or_stale_record_digest_rejects():
    store = PaperGovernorReadinessRecordStore()
    record = _record(_readiness_ready())
    with pytest.raises(PaperGovernorReadinessRecordStoreError):
        store.append(replace(record, record_digest="not-hex"))
    with pytest.raises(PaperGovernorReadinessRecordStoreError):
        store.append(replace(record, total_active_weight=record.total_active_weight + 0.1))


def test_invalid_provenance_digests_reject():
    store = PaperGovernorReadinessRecordStore()
    record = _record(_readiness_ready())
    for bad in (
        replace(record, readiness_digest="bad"),
        replace(record, replay_digest="bad"),
        replace(record, lifecycle_digest="bad"),
        replace(record, head_digest="bad"),
    ):
        with pytest.raises(PaperGovernorReadinessRecordStoreError):
            store.append(bad)


def test_evidence_refs_must_be_canonical_and_stable():
    store = PaperGovernorReadinessRecordStore()
    record = _record(_readiness_ready())
    with pytest.raises(PaperGovernorReadinessRecordStoreError):
        store.append(replace(record, evidence_refs=()))

    wrong_source = replace(record.evidence_refs[0], source_type="wrong_source")
    bad = replace(record, evidence_refs=(wrong_source, *record.evidence_refs[1:]))
    bad = _fresh_record(bad)
    with pytest.raises(PaperGovernorReadinessRecordStoreError):
        store.append(bad)

    noncanonical = DecisionEvidenceRef(
        source_type=record.evidence_refs[0].source_type,
        digest=record.evidence_refs[0].digest,
        source_id="not-builder-canonical",
    )
    bad = replace(record, evidence_refs=(noncanonical, *record.evidence_refs[1:]))
    bad = _fresh_record(bad)
    with pytest.raises(PaperGovernorReadinessRecordStoreError):
        store.append(bad)


def test_status_ready_and_block_reasons_must_remain_coherent():
    store = PaperGovernorReadinessRecordStore()
    record = _record(_readiness_over_budget())
    forged = replace(record, status=PaperGovernorReadinessStatus.BLOCKED, ready=False)
    forged = _fresh_record(forged)
    assert forged.record_digest == _expected_record_digest(forged)
    with pytest.raises(PaperGovernorReadinessRecordStoreError):
        store.append(forged)


def test_first_record_with_previous_digest_rejects():
    store = PaperGovernorReadinessRecordStore()
    record = _record(_readiness_ready(), previous=_HEX64)
    with pytest.raises(PaperGovernorReadinessRecordStoreError):
        store.append(record)


def test_second_record_without_required_previous_digest_rejects():
    store = PaperGovernorReadinessRecordStore()
    store.append(_record(_readiness_ready()))
    orphan = _record(_readiness_over_budget())
    with pytest.raises(PaperGovernorReadinessRecordStoreError):
        store.append(orphan)


def test_previous_digest_mismatch_rejects():
    store = PaperGovernorReadinessRecordStore()
    first = _record(_readiness_ready())
    store.append(first)
    wrong = _record(_readiness_over_budget(), previous=_HEX64)
    with pytest.raises(PaperGovernorReadinessRecordStoreError):
        store.append(wrong)


def test_duplicate_record_digest_rejects():
    store = PaperGovernorReadinessRecordStore()
    record = _record(_readiness_ready())
    store.append(record)
    with pytest.raises(PaperGovernorReadinessRecordStoreError):
        store.append(record)


def test_valid_first_and_second_append_preserves_ordered_chain():
    store = PaperGovernorReadinessRecordStore()
    first = _record(_readiness_ready())
    store.append(first)
    second = _record(_readiness_blocked(), previous=first.record_digest)
    store.append(second)

    assert store.snapshot() == (first, second)
    assert store.head_digest() == second.record_digest
    assert store.snapshot()[1].previous_record_digest == store.snapshot()[0].record_digest
    assert len(store) == 2


def test_lookup_by_record_digest_readiness_digest_and_status_is_deterministic():
    store = PaperGovernorReadinessRecordStore()
    ready = _record(_readiness_ready())
    store.append(ready)
    blocked = _record(_readiness_blocked(), previous=ready.record_digest)
    store.append(blocked)
    over_budget = _record(_readiness_over_budget(), previous=blocked.record_digest)
    store.append(over_budget)

    assert store.get_by_record_digest(ready.record_digest) is ready
    assert store.get_by_record_digest("f" * 64) is None
    assert store.find_by_readiness_digest(ready.readiness_digest) == (ready,)
    assert store.find_by_status(PaperGovernorReadinessStatus.READY) == (ready,)
    assert store.find_by_status(PaperGovernorReadinessStatus.BLOCKED) == (blocked,)
    assert store.find_by_status(PaperGovernorReadinessStatus.OVER_BUDGET) == (over_budget,)


def test_lookup_rejects_malformed_queries():
    store = PaperGovernorReadinessRecordStore()
    for call in (
        lambda: store.get_by_record_digest(""),
        lambda: store.find_by_readiness_digest(""),
        lambda: store.find_by_status("ready"),  # type: ignore[arg-type]
    ):
        with pytest.raises(PaperGovernorReadinessRecordStoreError):
            call()


def test_snapshot_is_immutable_and_isolated_from_later_appends():
    store = PaperGovernorReadinessRecordStore()
    first = _record(_readiness_ready())
    store.append(first)
    snapshot = store.snapshot()
    assert isinstance(snapshot, tuple)

    second = _record(_readiness_blocked(), previous=first.record_digest)
    store.append(second)
    assert snapshot == (first,)
    assert store.snapshot() == (first, second)


def test_ready_blocked_and_over_budget_records_store_correctly():
    store = PaperGovernorReadinessRecordStore()
    ready = _record(_readiness_ready())
    store.append(ready)
    blocked = _record(_readiness_blocked(), previous=ready.record_digest)
    store.append(blocked)
    over_budget = _record(_readiness_over_budget(), previous=blocked.record_digest)
    store.append(over_budget)

    assert [record.status for record in store.snapshot()] == [
        PaperGovernorReadinessStatus.READY,
        PaperGovernorReadinessStatus.BLOCKED,
        PaperGovernorReadinessStatus.OVER_BUDGET,
    ]


def test_no_order_live_venue_scheduler_fields_leak_from_stored_records():
    store = PaperGovernorReadinessRecordStore()
    store.append(_record(_readiness_ready()))
    forbidden = {"order", "order_intent", "route", "venue", "exchange", "schedule", "scheduler", "execution"}
    for record in store.snapshot():
        assert {field.name for field in fields(record)}.isdisjoint(forbidden)
        assert record.paper_only is True
        assert record.real_orders_enabled is False
        assert record.real_money_enabled is False


def test_repeated_same_append_sequence_yields_same_ordered_digests_and_head():
    def _build_store():
        store = PaperGovernorReadinessRecordStore()
        first = _record(_readiness_ready())
        store.append(first)
        second = _record(_readiness_blocked(), previous=first.record_digest)
        store.append(second)
        third = _record(_readiness_over_budget(), previous=second.record_digest)
        store.append(third)
        return store

    first_store = _build_store()
    second_store = _build_store()
    assert [record.record_digest for record in first_store.snapshot()] == [
        record.record_digest for record in second_store.snapshot()
    ]
    assert first_store.head_digest() == second_store.head_digest()
