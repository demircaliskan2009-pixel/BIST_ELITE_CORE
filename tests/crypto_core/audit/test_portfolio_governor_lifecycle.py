"""Tests for Phase 16H — paper governor lifecycle current-state view.

Covers ``summarize_paper_governor_lifecycle``: summarizing the append-only governor ledger chain
(store or ordered entries) into a deterministic, immutable current-state view (current active vs
blocked plan states with blockers, current active totals, blocker summary).

  1. Empty source view is deterministic and safe
  2. Active-only chain produces current active state
  3. Active -> blocked (same plan) produces blocked current state, zero current active totals
  4. Multiple plans aggregate current active totals correctly
  5. Blocker summary is deterministic (sorted-unique across current plans)
  6. Store source and equivalent tuple source produce identical views
  7. Broken / tampered / malformed chain fails closed through replay validation
  8. Output is immutable
  9. Repeated same input yields identical digest/output
 10. No order/live/venue/scheduler field leaks

PRD reference: §1.14-§1.28 Risk/Governance, §4 DecisionLedger/EvidenceStore, Phase 16H.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from crypto_core.audit.portfolio_governor_ledger import (
    PortfolioGovernorLedgerStatus,
    build_portfolio_governor_ledger_entry,
)
from crypto_core.audit.portfolio_governor_ledger_replay import PortfolioGovernorLedgerReplayError
from crypto_core.audit.portfolio_governor_ledger_store import (
    PortfolioGovernorLedgerStore,
    _expected_entry_digest,
)
from crypto_core.audit.portfolio_governor_lifecycle import (
    paper_governor_lifecycle_view_to_dict,
    summarize_paper_governor_lifecycle,
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


def _ready_plan(plan_id="paper-shadow-activation:deadbeef", caps=(("micro-1", 0.5), ("micro-2", 0.5))):
    return PaperShadowActivationPlan(
        plan_id=plan_id,
        activation_status=PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW,
        source_manifest_status=PaperShadowSourceManifestStatus.READY,
        active_sleeves=("micro-1", "micro-2"),
        pbo_allocation_caps=caps,
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


def test_empty_source_view_is_safe_and_deterministic():
    first = summarize_paper_governor_lifecycle(PortfolioGovernorLedgerStore())
    second = summarize_paper_governor_lifecycle(())
    assert first.entry_count == 0
    assert first.active_count == 0
    assert first.blocked_count == 0
    assert first.head_digest is None
    assert first.current_active_plans == ()
    assert first.current_blocked_plans == ()
    assert first.total_active_weight == 0.0
    assert first.total_active_notional == 0.0
    assert first.blocker_summary == ()
    assert first == second
    assert first.lifecycle_digest == second.lifecycle_digest
    assert len(first.lifecycle_digest) == 64


def test_active_only_chain_current_active_state():
    active = _entry(_allocated_directive())
    view = summarize_paper_governor_lifecycle((active,))
    assert view.active_count == 1
    assert view.blocked_count == 0
    assert len(view.current_active_plans) == 1
    assert view.current_blocked_plans == ()
    assert view.current_active_plans[0].plan_id == "paper-shadow-activation:deadbeef"
    assert view.current_active_plans[0].status == PortfolioGovernorLedgerStatus.RECORDED_ACTIVE
    assert view.total_active_weight == active.total_weight
    assert abs(view.total_active_notional - active.total_notional) < 1e-9


def test_active_then_blocked_same_plan_is_blocked_current_state():
    active = _entry(_allocated_directive())  # plan deadbeef, active
    blocked_same = _entry(_blocked_directive("paper-shadow-activation:deadbeef"), previous=active.entry_digest)
    view = summarize_paper_governor_lifecycle((active, blocked_same))
    assert view.entry_count == 2
    assert view.active_count == 0
    assert view.blocked_count == 1
    assert view.current_active_plans == ()
    assert len(view.current_blocked_plans) == 1
    assert view.current_blocked_plans[0].plan_id == "paper-shadow-activation:deadbeef"
    assert view.total_active_weight == 0.0
    assert view.total_active_notional == 0.0
    # The blocked plan's blockers surface in its state and the summary.
    assert view.current_blocked_plans[0].blockers != ()
    assert "portfolio_governor:record_blocked" in view.blocker_summary


def test_multiple_plans_aggregate_active_totals():
    a = _entry(_allocated_directive("paper-shadow-activation:plan-a"))
    b = _entry(_allocated_directive("paper-shadow-activation:plan-b"), previous=a.entry_digest)
    view = summarize_paper_governor_lifecycle((a, b))
    assert view.active_count == 2
    assert {state.plan_id for state in view.current_active_plans} == {
        "paper-shadow-activation:plan-a",
        "paper-shadow-activation:plan-b",
    }
    assert abs(view.total_active_weight - (a.total_weight + b.total_weight)) < 1e-9
    assert abs(view.total_active_notional - (a.total_notional + b.total_notional)) < 1e-9


def test_blocker_summary_sorted_unique():
    active = _entry(_allocated_directive())
    blocked = _entry(_blocked_directive(), previous=active.entry_digest)
    view = summarize_paper_governor_lifecycle((active, blocked))
    assert view.blocker_summary == tuple(sorted(set(view.blocker_summary)))


def test_store_and_tuple_sources_match():
    active = _entry(_allocated_directive())
    blocked = _entry(_blocked_directive(), previous=active.entry_digest)
    store = PortfolioGovernorLedgerStore()
    store.append(active)
    store.append(blocked)
    from_store = summarize_paper_governor_lifecycle(store)
    from_tuple = summarize_paper_governor_lifecycle((active, blocked))
    assert from_store == from_tuple
    assert from_store.lifecycle_digest == from_tuple.lifecycle_digest


def test_broken_chain_fails_closed():
    active = _entry(_allocated_directive())
    orphan = _entry(_blocked_directive(), previous=_HEX64)
    with pytest.raises(PortfolioGovernorLedgerReplayError):
        summarize_paper_governor_lifecycle((active, orphan))


def test_tampered_entry_fails_closed():
    active = _entry(_allocated_directive())
    forged = replace(active, total_weight=999.0)
    forged = replace(forged, entry_digest=_expected_entry_digest(forged))
    with pytest.raises(PortfolioGovernorLedgerReplayError):
        summarize_paper_governor_lifecycle((forged,))


def test_malformed_source_fails_closed():
    with pytest.raises(PortfolioGovernorLedgerReplayError):
        summarize_paper_governor_lifecycle({"not": "a source"})


def test_view_is_immutable():
    active = _entry(_allocated_directive())
    view = summarize_paper_governor_lifecycle((active,))
    assert isinstance(view.current_active_plans, tuple)
    assert isinstance(view.blocker_summary, tuple)
    with pytest.raises((AttributeError, TypeError)):
        view.active_count = 5  # type: ignore[misc]


def test_repeated_view_is_deterministic():
    active = _entry(_allocated_directive())
    blocked = _entry(_blocked_directive(), previous=active.entry_digest)
    first = summarize_paper_governor_lifecycle((active, blocked))
    second = summarize_paper_governor_lifecycle((active, blocked))
    assert first == second
    assert first.lifecycle_digest == second.lifecycle_digest


def test_no_order_or_live_fields_leak():
    active = _entry(_allocated_directive())
    view = summarize_paper_governor_lifecycle((active,))
    forbidden = {"order", "order_intent", "route", "venue", "exchange", "schedule", "scheduler", "live"}
    assert {field.name for field in fields(view)}.isdisjoint(forbidden)
    assert {field.name for field in fields(view.current_active_plans[0])}.isdisjoint(forbidden)
    assert view.paper_only is True
    assert view.real_orders_enabled is False
    assert view.real_money_enabled is False
    payload = paper_governor_lifecycle_view_to_dict(view)
    assert payload["schema_version"] == "portfolio-governor-lifecycle-view.v1"
    assert set(payload).isdisjoint(forbidden)
