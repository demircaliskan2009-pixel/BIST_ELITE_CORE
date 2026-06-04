"""Tests for paper-governor readiness audit record projection."""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from crypto_core.audit.portfolio_governor_ledger import build_portfolio_governor_ledger_entry
from crypto_core.audit.portfolio_governor_ledger_store import PortfolioGovernorLedgerStore
from crypto_core.audit.portfolio_governor_readiness import (
    PaperGovernorReadinessPolicy,
    PaperGovernorReadinessStatus,
    evaluate_paper_governor_readiness,
)
from crypto_core.audit.portfolio_governor_readiness_record import (
    PaperGovernorReadinessRecordError,
    _expected_readiness_digest,
    build_paper_governor_readiness_record,
    paper_governor_readiness_record_to_dict,
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

_CORR = "corr:portfolio-governor-readiness-record-001"
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


def _with_fresh_readiness_digest(readiness):
    return replace(readiness, readiness_digest=_expected_readiness_digest(readiness))


def test_ready_readiness_record_preserves_provenance_and_is_deterministic():
    readiness = _readiness_ready()
    first = build_paper_governor_readiness_record(readiness, correlation_id=_CORR)
    second = build_paper_governor_readiness_record(readiness, correlation_id=_CORR)

    assert first == second
    assert first.record_digest == second.record_digest
    assert len(first.record_digest) == 64
    assert first.status == PaperGovernorReadinessStatus.READY
    assert first.ready is True
    assert first.readiness_digest == readiness.readiness_digest
    assert first.lifecycle_digest == readiness.lifecycle_digest
    assert first.replay_digest == readiness.replay_digest
    assert first.head_digest == readiness.head_digest
    assert first.evidence_refs == (
        first.evidence_refs[0],
        first.evidence_refs[1],
        first.evidence_refs[2],
        first.evidence_refs[3],
    )
    assert [ref.source_type for ref in first.evidence_refs] == [
        "paper_governor_readiness",
        "portfolio_governor_lifecycle",
        "portfolio_governor_ledger_replay",
        "portfolio_governor_ledger_head",
    ]
    assert [ref.digest for ref in first.evidence_refs] == [
        readiness.readiness_digest,
        readiness.lifecycle_digest,
        readiness.replay_digest,
        readiness.head_digest,
    ]


def test_empty_ready_record_has_no_head_evidence_ref():
    readiness = evaluate_paper_governor_readiness(PortfolioGovernorLedgerStore())
    record = build_paper_governor_readiness_record(readiness)
    assert record.head_digest is None
    assert [ref.source_type for ref in record.evidence_refs] == [
        "paper_governor_readiness",
        "portfolio_governor_lifecycle",
        "portfolio_governor_ledger_replay",
    ]


def test_rejects_malformed_or_non_readiness_input():
    with pytest.raises(PaperGovernorReadinessRecordError):
        build_paper_governor_readiness_record({"not": "readiness"})  # type: ignore[arg-type]


def test_non_paper_readiness_rejects():
    readiness = _with_fresh_readiness_digest(replace(_readiness_ready(), paper_only=False))
    with pytest.raises(PaperGovernorReadinessRecordError):
        build_paper_governor_readiness_record(readiness)


def test_missing_or_invalid_readiness_digest_rejects():
    readiness = replace(_readiness_ready(), readiness_digest="")
    with pytest.raises(PaperGovernorReadinessRecordError):
        build_paper_governor_readiness_record(readiness)


def test_tampered_readiness_with_stale_digest_rejects():
    readiness = replace(_readiness_over_budget(), total_active_weight=0.1)
    with pytest.raises(PaperGovernorReadinessRecordError):
        build_paper_governor_readiness_record(readiness)


def test_invalid_provenance_digests_reject():
    readiness = _readiness_ready()
    for bad in (
        replace(readiness, replay_digest="bad"),
        replace(readiness, lifecycle_digest="bad"),
        replace(readiness, head_digest="bad"),
    ):
        bad = _with_fresh_readiness_digest(bad)
        with pytest.raises(PaperGovernorReadinessRecordError):
            build_paper_governor_readiness_record(bad)


def test_invalid_previous_record_digest_rejects():
    with pytest.raises(PaperGovernorReadinessRecordError):
        build_paper_governor_readiness_record(_readiness_ready(), previous_record_digest="not-hex")


def test_ready_blocked_and_over_budget_record_statuses_are_deterministic():
    cases = (
        (_readiness_ready(), PaperGovernorReadinessStatus.READY),
        (_readiness_blocked(), PaperGovernorReadinessStatus.BLOCKED),
        (_readiness_over_budget(), PaperGovernorReadinessStatus.OVER_BUDGET),
    )
    for readiness, status in cases:
        first = build_paper_governor_readiness_record(readiness, previous_record_digest=_HEX64)
        second = build_paper_governor_readiness_record(readiness, previous_record_digest=_HEX64)
        assert first.status == status
        assert first.record_digest == second.record_digest
        assert first.previous_record_digest == _HEX64


def test_block_reasons_and_blocker_summary_must_be_stable():
    readiness = _with_fresh_readiness_digest(replace(_readiness_blocked(), block_reasons=("z", "a")))
    with pytest.raises(PaperGovernorReadinessRecordError):
        build_paper_governor_readiness_record(readiness)

    readiness = _with_fresh_readiness_digest(replace(_readiness_blocked(), blocker_summary=("z", "a")))
    with pytest.raises(PaperGovernorReadinessRecordError):
        build_paper_governor_readiness_record(readiness)


def test_status_must_match_block_reasons():
    readiness = _with_fresh_readiness_digest(
        replace(
            _readiness_over_budget(),
            status=PaperGovernorReadinessStatus.BLOCKED,
            ready=False,
        )
    )
    with pytest.raises(PaperGovernorReadinessRecordError):
        build_paper_governor_readiness_record(readiness)


def test_counts_and_exposure_must_be_consistent():
    readiness = _with_fresh_readiness_digest(replace(_readiness_ready(), entry_count=0))
    with pytest.raises(PaperGovernorReadinessRecordError):
        build_paper_governor_readiness_record(readiness)

    readiness = _with_fresh_readiness_digest(
        replace(_readiness_ready(), active_count=0, total_active_weight=1.0, total_active_notional=10_000.0)
    )
    with pytest.raises(PaperGovernorReadinessRecordError):
        build_paper_governor_readiness_record(readiness)


def test_no_order_live_venue_scheduler_fields_leak():
    record = build_paper_governor_readiness_record(_readiness_ready())
    forbidden = {"order", "order_intent", "route", "venue", "exchange", "schedule", "scheduler", "execution"}
    assert {field.name for field in fields(record)}.isdisjoint(forbidden)
    assert record.paper_only is True
    assert record.real_orders_enabled is False
    assert record.real_money_enabled is False

    payload = paper_governor_readiness_record_to_dict(record)
    assert payload["record_schema_version"] == "paper-governor-readiness-record.v1"
    assert set(payload).isdisjoint(forbidden)
    assert payload["record_digest"] == record.record_digest
