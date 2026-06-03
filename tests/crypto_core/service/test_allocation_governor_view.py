"""Tests for Phase 16B — allocation governor view.

Covers ``govern_allocation_decision``: governing an allocator<->risk ``AllocationDecision`` into a
paper-only, provenance-bound effective allocation view.

  1. BLOCKED decision -> empty effective allocation
  2. Non-paper decision (real orders/money or paper_only False) -> rejected (fail-closed)
  3. Malformed decision -> error
  4. Governance halt -> empty effective allocation, halt blocker surfaced
  5. Happy path ALLOCATED -> deterministic effective allocation view
  6. Source decision digest + plan id preserved
  7. Blockers sorted-unique and auditable
  8. Deterministic repeated output (including the view digest)
  9. Per-sleeve weights preserved verbatim and total bounded by budget
 10. BLOCKED sleeves excluded from the effective allocation
 11. Paper-only invariants on the view

PRD reference: §1.14-§1.28 Risk/Governance, §7 Execution Engine, Phase 16B.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from crypto_core.service.allocation_governor_view import (
    AllocationGovernorError,
    govern_allocation_decision,
)
from crypto_core.service.allocator_risk_bridge import (
    AllocationDecision,
    AllocationStatus,
    SleeveAllocation,
    SleeveRiskDecision,
    build_allocation_decision,
)
from crypto_core.service.sleeve_admission_controller import (
    PaperShadowActivationPlan,
    PaperShadowActivationStatus,
    PaperShadowSourceManifestStatus,
)

_EPS = 1e-9


def _ready_plan(active=("micro-1", "micro-2"), caps=(("micro-1", 0.5), ("micro-2", 0.5))):
    return PaperShadowActivationPlan(
        plan_id="paper-shadow-activation:deadbeef",
        activation_status=PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW,
        source_manifest_status=PaperShadowSourceManifestStatus.READY,
        active_sleeves=active,
        pbo_allocation_caps=caps,
    )


def _allocated_decision(budget=1.0):
    risk = {
        "micro-1": SleeveRiskDecision("micro-1", approved=True),
        "micro-2": SleeveRiskDecision("micro-2", approved=True),
    }
    return build_allocation_decision(_ready_plan(), risk, budget=budget)


def _blocked_decision():
    plan = PaperShadowActivationPlan(
        plan_id="paper-shadow-activation:blocked",
        activation_status=PaperShadowActivationStatus.BLOCKED,
        source_manifest_status=PaperShadowSourceManifestStatus.BLOCKED,
        active_sleeves=("micro-1",),
        evidence_blockers=("sleeve_admission_evidence:currentness_missing",),
    )
    return build_allocation_decision(plan, {"micro-1": SleeveRiskDecision("micro-1", approved=True)})


def test_blocked_decision_yields_no_effective_allocation():
    view = govern_allocation_decision(_blocked_decision())
    assert view.status == AllocationStatus.BLOCKED
    assert view.effective_allocations == ()
    assert view.total_effective == 0.0
    assert "allocation_governor:decision_blocked" in view.blockers


def test_non_paper_decision_rejected():
    base = AllocationDecision(
        plan_id="p",
        status=AllocationStatus.ALLOCATED,
        budget=1.0,
        total_allocated=0.5,
        allocations=(SleeveAllocation("micro-1", AllocationStatus.ALLOCATED, 0.5, 0.5, ()),),
        blockers=(),
        decision_digest="abc",
    )

    for bad in (
        replace(base, real_orders_enabled=True),
        replace(base, real_money_enabled=True),
        replace(base, paper_only=False),
    ):
        with pytest.raises(AllocationGovernorError):
            govern_allocation_decision(bad)


def test_malformed_decision_raises():
    with pytest.raises(AllocationGovernorError):
        govern_allocation_decision({"not": "a decision"})


def test_governance_halt_blocks_allocation():
    view = govern_allocation_decision(_allocated_decision(), governance_blockers=("governance:operator_halt",))
    assert view.status == AllocationStatus.BLOCKED
    assert view.effective_allocations == ()
    assert view.total_effective == 0.0
    assert "allocation_governor:governance_halt" in view.blockers
    assert "governance:operator_halt" in view.blockers


def test_happy_path_effective_allocation():
    decision = _allocated_decision(budget=1.0)
    view = govern_allocation_decision(decision)
    assert view.status == AllocationStatus.ALLOCATED
    assert dict(view.effective_allocations) == {"micro-1": 0.5, "micro-2": 0.5}
    assert abs(view.total_effective - decision.total_allocated) < _EPS
    assert view.total_effective <= decision.budget + _EPS


def test_digest_and_plan_id_preserved():
    decision = _allocated_decision()
    view = govern_allocation_decision(decision)
    assert view.plan_id == decision.plan_id
    assert view.source_decision_digest == decision.decision_digest
    assert len(view.view_digest) == 64


def test_blockers_sorted_and_unique():
    view = govern_allocation_decision(_blocked_decision(), governance_blockers=("z_gov", "a_gov", "z_gov"))
    assert view.blockers == tuple(sorted(set(view.blockers)))


def test_deterministic_repeated_output():
    decision = _allocated_decision()
    first = govern_allocation_decision(decision)
    second = govern_allocation_decision(decision)
    assert first == second
    assert first.view_digest == second.view_digest


def test_weights_preserved_and_bounded():
    decision = _allocated_decision(budget=1.0)
    view = govern_allocation_decision(decision)
    decided = {a.sleeve_id: a.weight for a in decision.allocations if a.status == AllocationStatus.ALLOCATED}
    assert dict(view.effective_allocations) == decided
    assert sum(weight for _, weight in view.effective_allocations) <= decision.budget + _EPS


def test_blocked_sleeve_excluded_from_effective():
    risk = {
        "micro-1": SleeveRiskDecision("micro-1", approved=True),
        "micro-2": SleeveRiskDecision("micro-2", approved=False, block_reasons=("ks_blocked",)),
    }
    decision = build_allocation_decision(_ready_plan(), risk, budget=1.0)
    view = govern_allocation_decision(decision)
    assert set(dict(view.effective_allocations)) == {"micro-1"}
    assert view.status == AllocationStatus.ALLOCATED


def test_paper_only_invariants():
    view = govern_allocation_decision(_allocated_decision())
    assert view.paper_only is True
    assert view.real_orders_enabled is False
    assert view.real_money_enabled is False


def _paper_decision(*, status, budget, total_allocated, allocations, blockers=()):
    return AllocationDecision(
        plan_id="p",
        status=status,
        budget=budget,
        total_allocated=total_allocated,
        allocations=allocations,
        blockers=blockers,
        decision_digest="digest",
    )


def test_oversized_decision_fails_closed():
    # Regression (P2): a hand-built decision whose effective weights exceed budget must NOT expose an
    # oversized total_effective — fail closed.
    bad = _paper_decision(
        status=AllocationStatus.ALLOCATED,
        budget=1.0,
        total_allocated=999.0,
        allocations=(SleeveAllocation("micro-1", AllocationStatus.ALLOCATED, 5.0, 5.0, ()),),
    )
    with pytest.raises(AllocationGovernorError):
        govern_allocation_decision(bad)


def test_nonzero_total_with_no_effective_sleeves_fails_closed():
    # Regression (P2): status ALLOCATED + nonzero total but every sleeve BLOCKED -> inconsistent ->
    # must fail closed (never expose a nonzero total with no effective sleeves).
    bad = _paper_decision(
        status=AllocationStatus.ALLOCATED,
        budget=1.0,
        total_allocated=5.0,
        allocations=(SleeveAllocation("micro-1", AllocationStatus.BLOCKED, 0.0, 0.0, ("x",)),),
        blockers=("x",),
    )
    with pytest.raises(AllocationGovernorError):
        govern_allocation_decision(bad)


def test_total_inconsistent_with_effective_weights_fails_closed():
    # Regression (P2): total_allocated disagrees with the sum of ALLOCATED positive weights.
    bad = _paper_decision(
        status=AllocationStatus.ALLOCATED,
        budget=1.0,
        total_allocated=0.9,
        allocations=(SleeveAllocation("micro-1", AllocationStatus.ALLOCATED, 0.5, 0.5, ()),),
    )
    with pytest.raises(AllocationGovernorError):
        govern_allocation_decision(bad)


def test_invalid_budget_fails_closed():
    for budget in (-1.0, float("nan"), float("inf")):
        bad = _paper_decision(
            status=AllocationStatus.ALLOCATED,
            budget=budget,
            total_allocated=0.5,
            allocations=(SleeveAllocation("micro-1", AllocationStatus.ALLOCATED, 0.5, 0.5, ()),),
        )
        with pytest.raises(AllocationGovernorError):
            govern_allocation_decision(bad)


def test_non_finite_weight_fails_closed():
    bad = _paper_decision(
        status=AllocationStatus.ALLOCATED,
        budget=1.0,
        total_allocated=0.5,
        allocations=(SleeveAllocation("micro-1", AllocationStatus.ALLOCATED, float("nan"), 0.5, ()),),
    )
    with pytest.raises(AllocationGovernorError):
        govern_allocation_decision(bad)


def test_total_effective_derived_not_copied():
    # A valid decision's derived total equals the sum of effective weights (verbatim weights, exact).
    decision = _allocated_decision(budget=1.0)
    view = govern_allocation_decision(decision)
    assert view.total_effective == round(math.fsum(w for _, w in view.effective_allocations), 12)
    assert view.total_effective <= decision.budget
