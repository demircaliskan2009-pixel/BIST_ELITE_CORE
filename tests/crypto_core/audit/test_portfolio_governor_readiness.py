"""Tests for Phase 16I — paper governor readiness / current-exposure gate.

Covers ``evaluate_paper_governor_readiness``: a deterministic, fail-closed verdict over the
paper-governor lifecycle current-state (READY / BLOCKED / OVER_BUDGET) under an optional exposure
policy.

  1. Empty lifecycle/store readiness is deterministic and safe (structurally READY, no caps)
  2. Active-only below caps is READY
  3. Active over weight cap is OVER_BUDGET
  4. Active over notional cap is OVER_BUDGET
  5. Blocked current plan blocks readiness when policy requires; allowed off otherwise
  6. Active -> blocked same plan blocks and zeroes active exposure
  7. Malformed/tampered/broken source fails closed through lifecycle/replay validation
  8. Invalid cap values reject (fail-closed)
  9. Block reasons deterministic; both governance + budget reasons surface together
 10. Output is immutable
 11. No order/live/venue/scheduler field leaks
 12. Repeated same input gives identical digest/output; accepts view/store/entries

PRD reference: §1.14-§1.28 Risk/Governance, §1.21 No-Trade, §4 DecisionLedger/EvidenceStore, Phase 16I.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from crypto_core.audit.portfolio_governor_ledger import build_portfolio_governor_ledger_entry
from crypto_core.audit.portfolio_governor_ledger_replay import PortfolioGovernorLedgerReplayError
from crypto_core.audit.portfolio_governor_ledger_store import (
    PortfolioGovernorLedgerStore,
    _expected_entry_digest,
)
from crypto_core.audit.portfolio_governor_lifecycle import summarize_paper_governor_lifecycle
from crypto_core.audit.portfolio_governor_readiness import (
    PaperGovernorReadinessError,
    PaperGovernorReadinessPolicy,
    PaperGovernorReadinessStatus,
    evaluate_paper_governor_readiness,
    paper_governor_readiness_to_dict,
)
from crypto_core.service.allocation_governor_view import govern_allocation_decision
from crypto_core.service.allocator_risk_bridge import (
    SleeveRiskDecision,
    build_allocation_decision,
)
from crypto_core.service.portfolio_allocation_projection import project_governed_allocation
from crypto_core.service.portfolio_governor_consumption import consume_portfolio_allocation
from crypto_core.service.sleeve_admission_controller import (
    PaperShadowActivationPlan,
    PaperShadowActivationStatus,
    PaperShadowSourceManifestStatus,
)

_CORR = "corr:portfolio-governor-001"
_CAPITAL = 10_000.0
_HEX64 = "a" * 64


def _ready_plan(plan_id="paper-shadow-activation:deadbeef"):
    return PaperShadowActivationPlan(
        plan_id=plan_id,
        activation_status=PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW,
        source_manifest_status=PaperShadowSourceManifestStatus.READY,
        active_sleeves=("micro-1", "micro-2"),
        pbo_allocation_caps=(("micro-1", 0.5), ("micro-2", 0.5)),
    )


def _allocated_directive(plan_id="paper-shadow-activation:deadbeef", budget=1.0, capital_base=_CAPITAL):
    risk = {
        "micro-1": SleeveRiskDecision("micro-1", approved=True),
        "micro-2": SleeveRiskDecision("micro-2", approved=True),
    }
    view = govern_allocation_decision(build_allocation_decision(_ready_plan(plan_id), risk, budget=budget))
    record = project_governed_allocation(view, capital_base=capital_base)
    return consume_portfolio_allocation(record)


def _blocked_directive(plan_id="paper-shadow-activation:blocked"):
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


def _entry(directive, *, previous=None, correlation_id=_CORR):
    return build_portfolio_governor_ledger_entry(
        directive, correlation_id=correlation_id, previous_entry_digest=previous
    )


def test_empty_readiness_is_safe_and_deterministic():
    first = evaluate_paper_governor_readiness(PortfolioGovernorLedgerStore())
    second = evaluate_paper_governor_readiness(())
    assert first.status == PaperGovernorReadinessStatus.READY
    assert first.ready is True
    assert first.entry_count == 0
    assert first.active_count == 0
    assert first.blocked_count == 0
    assert first.head_digest is None
    assert first.block_reasons == ()
    assert first.max_current_active_weight is None  # no invented permissive limit
    assert first == second
    assert first.readiness_digest == second.readiness_digest
    assert len(first.readiness_digest) == 64


def test_active_only_below_caps_is_ready():
    active = _entry(_allocated_directive(budget=1.0))
    policy = PaperGovernorReadinessPolicy(max_current_active_weight=1.0, max_current_active_notional=10_000.0)
    readiness = evaluate_paper_governor_readiness((active,), policy=policy)
    assert readiness.status == PaperGovernorReadinessStatus.READY
    assert readiness.ready is True
    assert readiness.active_count == 1
    assert readiness.block_reasons == ()
    assert readiness.max_current_active_weight == 1.0
    assert readiness.max_current_active_notional == 10_000.0


def test_active_over_weight_cap_is_over_budget():
    active = _entry(_allocated_directive(budget=1.0))
    policy = PaperGovernorReadinessPolicy(max_current_active_weight=0.5)
    readiness = evaluate_paper_governor_readiness((active,), policy=policy)
    assert readiness.status == PaperGovernorReadinessStatus.OVER_BUDGET
    assert readiness.ready is False
    assert "paper_governor_readiness:active_weight_exceeds_cap" in readiness.block_reasons


def test_active_over_notional_cap_is_over_budget():
    active = _entry(_allocated_directive(budget=1.0))
    policy = PaperGovernorReadinessPolicy(max_current_active_notional=5_000.0)
    readiness = evaluate_paper_governor_readiness((active,), policy=policy)
    assert readiness.status == PaperGovernorReadinessStatus.OVER_BUDGET
    assert "paper_governor_readiness:active_notional_exceeds_cap" in readiness.block_reasons


def test_blocked_plan_blocks_readiness_by_policy():
    active = _entry(_allocated_directive())
    blocked = _entry(_blocked_directive(), previous=active.entry_digest)
    blocking = evaluate_paper_governor_readiness((active, blocked))
    assert blocking.status == PaperGovernorReadinessStatus.BLOCKED
    assert "paper_governor_readiness:blocked_plans_present" in blocking.block_reasons
    # Policy can disable the structural block (still not permissive on caps).
    permissive = evaluate_paper_governor_readiness(
        (active, blocked), policy=PaperGovernorReadinessPolicy(blocked_plans_block_readiness=False)
    )
    assert permissive.status == PaperGovernorReadinessStatus.READY
    assert permissive.blocked_count == 1  # still reported, just not gating


def test_active_then_blocked_same_plan_blocks_and_zeroes_exposure():
    active = _entry(_allocated_directive())
    blocked_same = _entry(_blocked_directive("paper-shadow-activation:deadbeef"), previous=active.entry_digest)
    readiness = evaluate_paper_governor_readiness((active, blocked_same))
    assert readiness.status == PaperGovernorReadinessStatus.BLOCKED
    assert readiness.active_count == 0
    assert readiness.total_active_weight == 0.0
    assert readiness.total_active_notional == 0.0


def test_governance_and_budget_reasons_surface_together():
    active = _entry(_allocated_directive(budget=1.0))
    blocked = _entry(_blocked_directive(), previous=active.entry_digest)
    # active plan weight 1.0 over a 0.5 cap AND a blocked plan present.
    policy = PaperGovernorReadinessPolicy(max_current_active_weight=0.5)
    readiness = evaluate_paper_governor_readiness((active, blocked), policy=policy)
    # Governance block takes status precedence, but both reasons are recorded.
    assert readiness.status == PaperGovernorReadinessStatus.BLOCKED
    assert "paper_governor_readiness:blocked_plans_present" in readiness.block_reasons
    assert "paper_governor_readiness:active_weight_exceeds_cap" in readiness.block_reasons
    assert readiness.block_reasons == tuple(sorted(set(readiness.block_reasons)))


def test_broken_source_fails_closed():
    active = _entry(_allocated_directive())
    orphan = _entry(_blocked_directive(), previous=_HEX64)
    with pytest.raises(PortfolioGovernorLedgerReplayError):
        evaluate_paper_governor_readiness((active, orphan))


def test_tampered_source_fails_closed():
    active = _entry(_allocated_directive())
    forged = replace(active, total_weight=999.0)
    forged = replace(forged, entry_digest=_expected_entry_digest(forged))
    with pytest.raises(PortfolioGovernorLedgerReplayError):
        evaluate_paper_governor_readiness((forged,))


def test_malformed_source_fails_closed():
    with pytest.raises(PortfolioGovernorLedgerReplayError):
        evaluate_paper_governor_readiness({"not": "a source"})


def test_invalid_caps_reject():
    active = _entry(_allocated_directive())
    for policy in (
        PaperGovernorReadinessPolicy(max_current_active_weight=-1.0),
        PaperGovernorReadinessPolicy(max_current_active_weight=float("nan")),
        PaperGovernorReadinessPolicy(max_current_active_weight=float("inf")),
        PaperGovernorReadinessPolicy(max_current_active_weight=True),
        PaperGovernorReadinessPolicy(max_current_active_notional=-5.0),
    ):
        with pytest.raises(PaperGovernorReadinessError):
            evaluate_paper_governor_readiness((active,), policy=policy)


def test_non_paper_view_rejected():
    active = _entry(_allocated_directive())
    view = summarize_paper_governor_lifecycle((active,))
    for bad in (
        replace(view, paper_only=False),
        replace(view, real_orders_enabled=True),
        replace(view, real_money_enabled=True),
    ):
        with pytest.raises(PaperGovernorReadinessError):
            evaluate_paper_governor_readiness(bad)


def test_readiness_is_immutable():
    readiness = evaluate_paper_governor_readiness((_entry(_allocated_directive()),))
    assert isinstance(readiness.block_reasons, tuple)
    with pytest.raises((AttributeError, TypeError)):
        readiness.ready = True  # type: ignore[misc]


def test_repeated_and_view_store_entries_equivalent():
    active = _entry(_allocated_directive())
    blocked = _entry(_blocked_directive(), previous=active.entry_digest)
    store = PortfolioGovernorLedgerStore()
    store.append(active)
    store.append(blocked)
    view = summarize_paper_governor_lifecycle(store)
    from_view = evaluate_paper_governor_readiness(view)
    from_store = evaluate_paper_governor_readiness(store)
    from_entries = evaluate_paper_governor_readiness((active, blocked))
    assert from_view == from_store == from_entries
    assert from_view.readiness_digest == from_entries.readiness_digest


def test_no_order_or_live_fields_leak():
    readiness = evaluate_paper_governor_readiness((_entry(_allocated_directive()),))
    forbidden = {"order", "order_intent", "route", "venue", "exchange", "schedule", "scheduler", "live"}
    assert {field.name for field in fields(readiness)}.isdisjoint(forbidden)
    assert readiness.paper_only is True
    assert readiness.real_orders_enabled is False
    assert readiness.real_money_enabled is False
    payload = paper_governor_readiness_to_dict(readiness)
    assert payload["schema_version"] == "paper-governor-readiness.v1"
    assert set(payload).isdisjoint(forbidden)
