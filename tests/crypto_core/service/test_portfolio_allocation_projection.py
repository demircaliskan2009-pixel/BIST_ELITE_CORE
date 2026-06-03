"""Tests for Phase 16C — portfolio allocation projection.

Covers ``project_governed_allocation``: projecting a paper-only ``GovernedAllocationView`` into a
deterministic paper portfolio allocation record (weights -> paper capital notionals) with an
independent operational halt gate.

  1. BLOCKED view -> no portfolio targets
  2. Malformed view -> error
  3. Non-paper view -> rejected (fail-closed)
  4. Invalid capital base -> rejected (fail-closed)
  5. Operational halt -> no targets, halt blocker surfaced
  6. Happy path -> deterministic targets, notional = weight * capital_base
  7. Provenance (plan_id, source_decision_digest, view_digest) preserved
  8. Blockers sorted-unique and auditable
  9. Deterministic repeated output (including record digest)
 10. Per-sleeve weights verbatim; total weight <= budget; total notional <= budget * capital_base
 11. Paper-only invariants on the record

PRD reference: §1.14-§1.28 Risk/Governance, §7 Execution Engine, Phase 16C.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from crypto_core.service.allocation_governor_view import (
    govern_allocation_decision,
)
from crypto_core.service.allocator_risk_bridge import (
    AllocationStatus,
    SleeveRiskDecision,
    build_allocation_decision,
)
from crypto_core.service.portfolio_allocation_projection import (
    PortfolioAllocationError,
    project_governed_allocation,
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


def _allocated_view(budget=1.0):
    risk = {
        "micro-1": SleeveRiskDecision("micro-1", approved=True),
        "micro-2": SleeveRiskDecision("micro-2", approved=True),
    }
    return govern_allocation_decision(build_allocation_decision(_ready_plan(), risk, budget=budget))


def _blocked_view():
    plan = PaperShadowActivationPlan(
        plan_id="paper-shadow-activation:blocked",
        activation_status=PaperShadowActivationStatus.BLOCKED,
        source_manifest_status=PaperShadowSourceManifestStatus.BLOCKED,
        active_sleeves=("micro-1",),
        evidence_blockers=("sleeve_admission_evidence:currentness_missing",),
    )
    decision = build_allocation_decision(plan, {"micro-1": SleeveRiskDecision("micro-1", approved=True)})
    return govern_allocation_decision(decision)


def test_blocked_view_yields_no_targets():
    record = project_governed_allocation(_blocked_view(), capital_base=10_000.0)
    assert record.status == AllocationStatus.BLOCKED
    assert record.targets == ()
    assert record.total_weight == 0.0
    assert record.total_notional == 0.0
    assert "portfolio_allocation:view_blocked" in record.blockers


def test_malformed_view_raises():
    with pytest.raises(PortfolioAllocationError):
        project_governed_allocation({"not": "a view"}, capital_base=1.0)


def test_non_paper_view_rejected():
    view = _allocated_view()
    for bad in (
        replace(view, real_orders_enabled=True),
        replace(view, real_money_enabled=True),
        replace(view, paper_only=False),
    ):
        with pytest.raises(PortfolioAllocationError):
            project_governed_allocation(bad, capital_base=1.0)


def test_invalid_capital_base_rejected():
    view = _allocated_view()
    for capital in (-1.0, 0.0, float("nan"), float("inf"), True):
        with pytest.raises(PortfolioAllocationError):
            project_governed_allocation(view, capital_base=capital)


def test_invalid_view_budget_or_total_rejected():
    for bad in (
        replace(_allocated_view(), budget=-1.0),
        replace(_allocated_view(), budget=float("nan")),
        replace(_allocated_view(), budget=True),
        replace(_allocated_view(), total_effective=float("inf")),
        replace(_allocated_view(), total_effective=True),
    ):
        with pytest.raises(PortfolioAllocationError):
            project_governed_allocation(bad, capital_base=10_000.0)


def test_operational_halt_zeroes_targets():
    record = project_governed_allocation(
        _allocated_view(),
        capital_base=10_000.0,
        halt_blockers=("operator_halt:manual", "kill_switch:ks_blocked", "no_trade:active"),
    )
    assert record.status == AllocationStatus.BLOCKED
    assert record.targets == ()
    assert record.total_notional == 0.0
    assert "portfolio_allocation:operational_halt" in record.blockers
    assert "kill_switch:ks_blocked" in record.blockers
    assert "no_trade:active" in record.blockers
    assert "operator_halt:manual" in record.blockers


def test_happy_path_projects_notionals():
    view = _allocated_view(budget=1.0)
    record = project_governed_allocation(view, capital_base=10_000.0)
    assert record.status == AllocationStatus.ALLOCATED
    targets = {target.sleeve_id: target for target in record.targets}
    assert set(targets) == {"micro-1", "micro-2"}
    assert targets["micro-1"].weight == 0.5
    assert abs(targets["micro-1"].notional - 5_000.0) < _EPS
    assert abs(targets["micro-2"].notional - 5_000.0) < _EPS
    assert abs(record.total_notional - 10_000.0) < _EPS


def test_provenance_preserved():
    view = _allocated_view()
    record = project_governed_allocation(view, capital_base=1.0)
    assert record.plan_id == view.plan_id
    assert record.source_decision_digest == view.source_decision_digest
    assert record.view_digest == view.view_digest
    assert len(record.record_digest) == 64


def test_blockers_sorted_and_unique():
    record = project_governed_allocation(_blocked_view(), capital_base=1.0, halt_blockers=("z", "a", "z"))
    assert record.blockers == tuple(sorted(set(record.blockers)))


def test_deterministic_repeated_output():
    view = _allocated_view()
    first = project_governed_allocation(view, capital_base=10_000.0)
    second = project_governed_allocation(view, capital_base=10_000.0)
    assert first == second
    assert first.record_digest == second.record_digest


def test_weights_verbatim_and_totals_bounded():
    view = _allocated_view(budget=1.0)
    record = project_governed_allocation(view, capital_base=10_000.0)
    decided = dict(view.effective_allocations)
    projected = {target.sleeve_id: target.weight for target in record.targets}
    assert projected == decided
    assert record.total_weight <= record.budget + _EPS
    assert record.total_notional <= record.budget * record.capital_base + _EPS
    assert record.total_weight == round(math.fsum(t.weight for t in record.targets), 12)


def test_paper_only_invariants():
    record = project_governed_allocation(_allocated_view(), capital_base=1.0)
    assert record.paper_only is True
    assert record.real_orders_enabled is False
    assert record.real_money_enabled is False


def test_total_weight_over_budget_fails_closed():
    view = replace(
        _allocated_view(budget=1.0),
        budget=0.75,
        total_effective=1.0,
        effective_allocations=(("micro-1", 0.5), ("micro-2", 0.5)),
    )
    with pytest.raises(PortfolioAllocationError):
        project_governed_allocation(view, capital_base=10_000.0)


def test_total_inconsistent_with_targets_fails_closed():
    view = replace(
        _allocated_view(),
        total_effective=0.25,
        effective_allocations=(("micro-1", 0.5), ("micro-2", 0.5)),
    )
    with pytest.raises(PortfolioAllocationError):
        project_governed_allocation(view, capital_base=10_000.0)


def test_malformed_effective_allocation_fails_closed():
    for bad_allocations in (
        [("micro-1", 0.5)],
        (("micro-1", float("nan")),),
        ((True, 0.5),),
        (("micro-1", 0.5, "extra"),),
    ):
        view = replace(_allocated_view(), effective_allocations=bad_allocations)
        with pytest.raises(PortfolioAllocationError):
            project_governed_allocation(view, capital_base=10_000.0)
