"""Tests for Phase 16E — portfolio governor ledger entry.

Covers ``build_portfolio_governor_ledger_entry``: projecting a paper-only
``PortfolioGovernorDirective`` into a deterministic, fail-closed, provenance-bound audit
ledger entry that can be written to a decision ledger / evidence store later.

  1. Malformed directive -> error (fail-closed)
  2. Non-paper directive -> rejected (fail-closed)
  3. Missing provenance / correlation id -> rejected (fail-closed)
  4. BLOCKED/HOLD directive -> RECORDED_BLOCKED, no targets, blockers preserved
  5. ALLOCATED/SET_PAPER_TARGET directive -> RECORDED_ACTIVE deterministic entry
  6. Provenance preserved exactly (plan_id + 4 digests) and bound as evidence refs
  7. Targets / weights / notionals / action preserved verbatim
  8. Tampered totals / targets / digest -> fail closed (digest mismatch)
  9. Blockers sorted-unique and auditable
 10. Deterministic repeated output (including entry digest); previous_entry_digest chaining
 11. Paper-only invariants; no order/route/scheduler/venue field produced

PRD reference: §1.14-§1.28 Risk/Governance, §4 DecisionLedger/EvidenceStore, Phase 16E.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, replace

import pytest

from crypto_core.audit.portfolio_governor_ledger import (
    PortfolioGovernorLedgerError,
    PortfolioGovernorLedgerStatus,
    build_portfolio_governor_ledger_entry,
    portfolio_governor_ledger_entry_to_dict,
)
from crypto_core.service.allocation_governor_view import govern_allocation_decision
from crypto_core.service.allocator_risk_bridge import (
    AllocationStatus,
    SleeveRiskDecision,
    build_allocation_decision,
)
from crypto_core.service.portfolio_allocation_projection import project_governed_allocation
from crypto_core.service.portfolio_governor_consumption import (
    GovernorActionType,
    SleeveTargetDirective,
    consume_portfolio_allocation,
)
from crypto_core.service.sleeve_admission_controller import (
    PaperShadowActivationPlan,
    PaperShadowActivationStatus,
    PaperShadowSourceManifestStatus,
)

_CORR = "corr:portfolio-governor-001"
_CAPITAL = 10_000.0
_DIRECTIVE_SCHEMA_VERSION = "portfolio-governor-directive.v1"


def _ready_plan(active=("micro-1", "micro-2"), caps=(("micro-1", 0.5), ("micro-2", 0.5))):
    return PaperShadowActivationPlan(
        plan_id="paper-shadow-activation:deadbeef",
        activation_status=PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW,
        source_manifest_status=PaperShadowSourceManifestStatus.READY,
        active_sleeves=active,
        pbo_allocation_caps=caps,
    )


def _allocated_directive(budget=1.0, capital_base=_CAPITAL):
    risk = {
        "micro-1": SleeveRiskDecision("micro-1", approved=True),
        "micro-2": SleeveRiskDecision("micro-2", approved=True),
    }
    view = govern_allocation_decision(build_allocation_decision(_ready_plan(), risk, budget=budget))
    record = project_governed_allocation(view, capital_base=capital_base)
    return consume_portfolio_allocation(record)


def _blocked_directive():
    plan = PaperShadowActivationPlan(
        plan_id="paper-shadow-activation:blocked",
        activation_status=PaperShadowActivationStatus.BLOCKED,
        source_manifest_status=PaperShadowSourceManifestStatus.BLOCKED,
        active_sleeves=("micro-1",),
        evidence_blockers=("sleeve_admission_evidence:currentness_missing",),
    )
    decision = build_allocation_decision(plan, {"micro-1": SleeveRiskDecision("micro-1", approved=True)})
    record = project_governed_allocation(govern_allocation_decision(decision), capital_base=_CAPITAL)
    return consume_portfolio_allocation(record)


def _directive_digest(directive) -> str:
    payload = {
        "schema_version": _DIRECTIVE_SCHEMA_VERSION,
        "plan_id": directive.plan_id,
        "status": directive.status.value,
        "action": directive.action.value,
        "budget": directive.budget,
        "capital_base": directive.capital_base,
        "total_weight": directive.total_weight,
        "total_notional": directive.total_notional,
        "targets": [[t.sleeve_id, t.action.value, t.weight, t.notional] for t in directive.targets],
        "blockers": list(directive.blockers),
        "source_decision_digest": directive.source_decision_digest,
        "view_digest": directive.view_digest,
        "record_digest": directive.record_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _with_recomputed_directive_digest(directive):
    return replace(directive, directive_digest=_directive_digest(directive))


def _is_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdefABCDEF" for char in value)


def test_malformed_directive_raises():
    with pytest.raises(PortfolioGovernorLedgerError):
        build_portfolio_governor_ledger_entry({"not": "a directive"}, correlation_id=_CORR)


def test_non_paper_directive_rejected():
    directive = _allocated_directive()
    for bad in (
        replace(directive, real_orders_enabled=True),
        replace(directive, real_money_enabled=True),
        replace(directive, paper_only=False),
    ):
        with pytest.raises(PortfolioGovernorLedgerError):
            build_portfolio_governor_ledger_entry(bad, correlation_id=_CORR)


def test_missing_provenance_rejected():
    directive = _allocated_directive()
    for bad in (
        replace(directive, plan_id=""),
        replace(directive, source_decision_digest=""),
        replace(directive, view_digest=""),
        replace(directive, record_digest=""),
        replace(directive, directive_digest=""),
    ):
        with pytest.raises(PortfolioGovernorLedgerError):
            build_portfolio_governor_ledger_entry(bad, correlation_id=_CORR)


def test_missing_correlation_id_rejected():
    with pytest.raises(PortfolioGovernorLedgerError):
        build_portfolio_governor_ledger_entry(_allocated_directive(), correlation_id="")


def test_invalid_previous_entry_digest_rejected():
    for previous_entry_digest in ("", "not-a-digest", "f" * 63, "g" * 64):
        with pytest.raises(PortfolioGovernorLedgerError):
            build_portfolio_governor_ledger_entry(
                _allocated_directive(),
                correlation_id=_CORR,
                previous_entry_digest=previous_entry_digest,
            )


def test_blocked_directive_records_blocked():
    entry = build_portfolio_governor_ledger_entry(_blocked_directive(), correlation_id=_CORR)
    assert entry.status == PortfolioGovernorLedgerStatus.RECORDED_BLOCKED
    assert entry.action == GovernorActionType.HOLD
    assert entry.targets == ()
    assert entry.total_weight == 0.0
    assert entry.total_notional == 0.0
    assert "portfolio_governor:record_blocked" in entry.blockers


def test_allocated_directive_records_active():
    directive = _allocated_directive(budget=1.0)
    entry = build_portfolio_governor_ledger_entry(directive, correlation_id=_CORR)
    assert entry.status == PortfolioGovernorLedgerStatus.RECORDED_ACTIVE
    assert entry.action == GovernorActionType.SET_PAPER_TARGET
    assert {target.sleeve_id for target in entry.targets} == {"micro-1", "micro-2"}
    assert len(entry.entry_digest) == 64


def test_targets_preserved_verbatim():
    directive = _allocated_directive(budget=1.0)
    entry = build_portfolio_governor_ledger_entry(directive, correlation_id=_CORR)
    assert entry.targets == directive.targets
    assert entry.total_weight == directive.total_weight
    assert entry.total_notional == directive.total_notional
    assert entry.blockers == directive.blockers
    assert entry.action == directive.action


def test_provenance_preserved_and_bound_as_evidence():
    directive = _allocated_directive()
    entry = build_portfolio_governor_ledger_entry(directive, correlation_id=_CORR)
    assert entry.plan_id == directive.plan_id
    assert entry.source_decision_digest == directive.source_decision_digest
    assert entry.view_digest == directive.view_digest
    assert entry.record_digest == directive.record_digest
    assert entry.directive_digest == directive.directive_digest
    evidence = {ref.source_type: ref.digest for ref in entry.evidence_refs}
    assert evidence == {
        "portfolio_allocation_decision": directive.source_decision_digest,
        "allocation_governor_view": directive.view_digest,
        "portfolio_allocation_record": directive.record_digest,
        "portfolio_governor_directive": directive.directive_digest,
    }
    assert all(_is_sha256_hex(ref.digest) for ref in entry.evidence_refs)


def test_invalid_provenance_digests_rejected():
    directive = _allocated_directive()
    for bad in (
        replace(directive, source_decision_digest="not-a-digest"),
        replace(directive, view_digest="g" * 64),
        replace(directive, record_digest="f" * 63),
        replace(directive, directive_digest="z" * 64),
    ):
        with pytest.raises(PortfolioGovernorLedgerError):
            build_portfolio_governor_ledger_entry(bad, correlation_id=_CORR)


def test_tampered_total_weight_fails_closed():
    directive = _allocated_directive(budget=1.0)
    with pytest.raises(PortfolioGovernorLedgerError):
        build_portfolio_governor_ledger_entry(
            replace(directive, total_weight=directive.total_weight + 0.25), correlation_id=_CORR
        )


def test_tampered_directive_digest_fails_closed():
    directive = _allocated_directive(budget=1.0)
    with pytest.raises(PortfolioGovernorLedgerError):
        build_portfolio_governor_ledger_entry(replace(directive, directive_digest="0" * 64), correlation_id=_CORR)


def test_tampered_target_fails_closed():
    directive = _allocated_directive(budget=1.0)
    first, *rest = directive.targets
    bumped = SleeveTargetDirective(
        sleeve_id=first.sleeve_id,
        action=first.action,
        weight=first.weight,
        notional=first.notional + 1_000.0,
    )
    with pytest.raises(PortfolioGovernorLedgerError):
        build_portfolio_governor_ledger_entry(replace(directive, targets=(bumped, *rest)), correlation_id=_CORR)


def test_self_consistent_total_weight_mismatch_fails_closed():
    directive = _allocated_directive(budget=1.0)
    tampered = _with_recomputed_directive_digest(replace(directive, total_weight=0.1))
    with pytest.raises(PortfolioGovernorLedgerError):
        build_portfolio_governor_ledger_entry(tampered, correlation_id=_CORR)


def test_self_consistent_total_notional_mismatch_fails_closed():
    directive = _allocated_directive(budget=1.0)
    tampered = _with_recomputed_directive_digest(replace(directive, total_notional=1.0))
    with pytest.raises(PortfolioGovernorLedgerError):
        build_portfolio_governor_ledger_entry(tampered, correlation_id=_CORR)


def test_self_consistent_redistributed_target_notional_fails_closed():
    directive = _allocated_directive(budget=1.0)
    first, second = directive.targets
    redistributed = (
        SleeveTargetDirective(
            sleeve_id=first.sleeve_id,
            action=first.action,
            weight=first.weight,
            notional=first.notional - 1_000.0,
        ),
        SleeveTargetDirective(
            sleeve_id=second.sleeve_id,
            action=second.action,
            weight=second.weight,
            notional=second.notional + 1_000.0,
        ),
    )
    tampered = _with_recomputed_directive_digest(replace(directive, targets=redistributed))
    with pytest.raises(PortfolioGovernorLedgerError):
        build_portfolio_governor_ledger_entry(tampered, correlation_id=_CORR)


def test_positive_weight_zero_notional_fails_closed():
    directive = _allocated_directive(budget=1.0)
    first, second = directive.targets
    zeroed = (
        SleeveTargetDirective(sleeve_id=first.sleeve_id, action=first.action, weight=first.weight, notional=0.0),
        second,
    )
    total_notional = round(sum(target.notional for target in zeroed), 12)
    tampered = _with_recomputed_directive_digest(replace(directive, targets=zeroed, total_notional=total_notional))
    with pytest.raises(PortfolioGovernorLedgerError):
        build_portfolio_governor_ledger_entry(tampered, correlation_id=_CORR)


def test_total_weight_over_budget_fails_closed():
    directive = _allocated_directive(budget=1.0)
    over_budget_targets = (
        SleeveTargetDirective("micro-1", GovernorActionType.SET_PAPER_TARGET, 0.75, 7_500.0),
        SleeveTargetDirective("micro-2", GovernorActionType.SET_PAPER_TARGET, 0.75, 7_500.0),
    )
    tampered = _with_recomputed_directive_digest(
        replace(directive, targets=over_budget_targets, total_weight=1.5, total_notional=15_000.0)
    )
    with pytest.raises(PortfolioGovernorLedgerError):
        build_portfolio_governor_ledger_entry(tampered, correlation_id=_CORR)


def test_total_notional_over_budget_capital_fails_closed():
    directive = _allocated_directive(budget=0.75)
    tampered = _with_recomputed_directive_digest(replace(directive, budget=0.5))
    with pytest.raises(PortfolioGovernorLedgerError):
        build_portfolio_governor_ledger_entry(tampered, correlation_id=_CORR)


def test_inconsistent_hold_with_targets_fails_closed():
    directive = _allocated_directive(budget=1.0)
    # Status forced to BLOCKED/HOLD while keeping targets -> structurally inconsistent.
    tampered = replace(directive, status=AllocationStatus.BLOCKED, action=GovernorActionType.HOLD)
    with pytest.raises(PortfolioGovernorLedgerError):
        build_portfolio_governor_ledger_entry(tampered, correlation_id=_CORR)


def test_blockers_sorted_and_unique():
    entry = build_portfolio_governor_ledger_entry(_blocked_directive(), correlation_id=_CORR)
    assert entry.blockers == tuple(sorted(set(entry.blockers)))


def test_deterministic_repeated_output():
    directive = _allocated_directive()
    first = build_portfolio_governor_ledger_entry(directive, correlation_id=_CORR)
    second = build_portfolio_governor_ledger_entry(directive, correlation_id=_CORR)
    assert first == second
    assert first.entry_digest == second.entry_digest


def test_previous_entry_digest_chaining_changes_digest():
    directive = _allocated_directive()
    base = build_portfolio_governor_ledger_entry(directive, correlation_id=_CORR)
    chained = build_portfolio_governor_ledger_entry(
        directive, correlation_id=_CORR, previous_entry_digest=base.entry_digest
    )
    assert chained.previous_entry_digest == base.entry_digest
    assert chained.entry_digest != base.entry_digest


def test_to_dict_is_canonical_and_paper_only():
    directive = _allocated_directive()
    entry = build_portfolio_governor_ledger_entry(directive, correlation_id=_CORR)
    payload = portfolio_governor_ledger_entry_to_dict(entry)
    assert payload["schema_version"] == "portfolio-governor-ledger-entry.v1"
    assert payload["status"] == "recorded_active"
    assert payload["paper_only"] is True
    assert payload["real_orders_enabled"] is False
    assert payload["real_money_enabled"] is False
    assert [ref["source_type"] for ref in payload["evidence_refs"]] == [
        "portfolio_allocation_decision",
        "allocation_governor_view",
        "portfolio_allocation_record",
        "portfolio_governor_directive",
    ]


def test_paper_only_invariants_and_no_order_fields():
    entry = build_portfolio_governor_ledger_entry(_allocated_directive(), correlation_id=_CORR)
    assert entry.paper_only is True
    assert entry.real_orders_enabled is False
    assert entry.real_money_enabled is False
    forbidden = {"order", "order_intent", "route", "venue", "exchange", "schedule", "scheduler", "live"}
    entry_field_names = {field.name for field in fields(entry)}
    assert entry_field_names.isdisjoint(forbidden)
    target_field_names = {field.name for field in fields(entry.targets[0])}
    assert target_field_names.isdisjoint(forbidden)
    for action in (entry.action, *(target.action for target in entry.targets)):
        assert action in {GovernorActionType.SET_PAPER_TARGET, GovernorActionType.HOLD}
